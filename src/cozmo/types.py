"""The representation every tier converges on.

The three input tiers differ only in how much they know. They produce the same
fields; what differs is where those fields came from. Provenance is carried
alongside the data rather than inferred later, because the confidence interval
on every downstream measurement is a function of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class DepthSource(str, Enum):
    MEASURED = "measured"    # LiDAR time-of-flight
    INFERRED = "inferred"    # monocular depth model
    NONE = "none"


class PoseSource(str, Enum):
    DEVICE_OPTIMISED = "device_optimised"  # loop-closed by the capture app
    DEVICE_RAW = "device_raw"              # raw ARKit, drift uncorrected
    SFM = "sfm"                            # recovered by us
    NONE = "none"


@dataclass(frozen=True)
class Measurement:
    """A number that knows how it was produced and how much to trust it."""
    value: float
    lo: float
    hi: float
    unit: str
    provenance: tuple[str, ...]
    n: int = 0

    @property
    def half_width(self) -> float:
        return (self.hi - self.lo) / 2

    def __str__(self) -> str:
        return (f"{self.value:.4f} {self.unit} "
                f"[{self.lo:.4f}, {self.hi:.4f}] "
                f"(±{self.half_width * 100:.2f} cm, n={self.n})")


@dataclass
class PosedFrame:
    """One keyframe: pixels, depth, and where the camera was."""
    key: str
    depth: np.ndarray | None          # (h, w) metres, 0 = no return
    confidence: np.ndarray | None     # (h, w) 0=low 1=med 2=high
    K: np.ndarray                     # 3x3, scaled to the depth raster
    T_wc: np.ndarray | None           # 4x4 world <- camera
    depth_source: DepthSource
    pose_source: PoseSource
    meta: dict = field(default_factory=dict)


@dataclass
class Capture:
    """A whole session, plus what we know about how it was taken."""
    frames: list[PosedFrame]
    tier: str
    source: str
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def pose_sources(self) -> set[PoseSource]:
        return {f.pose_source for f in self.frames}

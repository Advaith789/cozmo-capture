"""Tier C ingest: a Polycam raw export becomes a Capture.

Two things about the export shape drive this module, both established from a
real export rather than the published format notes (docs/capture-bakeoff.md):

  * The archive has no wrapping folder — keyframes/ sits at the root.
  * corrected_cameras/ holds the loop-closed poses but drops the per-frame
    sensor metadata that cameras/ carries, so the two must be joined by
    filename stem: pose from corrected, metadata from raw.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np

from ..io.png import decode_gray
from ..types import Capture, DepthSource, PosedFrame, PoseSource

# Confidence bytes observed in real exports. The published notes say 0/127/255;
# the export says otherwise, so map by rank and treat anything else as unknown.
CONFIDENCE_LEVELS = {0: 0, 54: 1, 127: 1, 255: 2}


class _Archive:
    """Read either a .zip export or an unpacked directory."""

    def __init__(self, path: Path):
        self.path = path
        self._zip = zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
        if self._zip:
            self._names = [n for n in self._zip.namelist() if not n.endswith("/")]
        else:
            self._names = [str(p.relative_to(path))
                           for p in path.rglob("*") if p.is_file()]

    def stems(self, folder: str) -> list[str]:
        pre = folder.rstrip("/") + "/"
        return sorted(Path(n).stem for n in self._names if n.startswith(pre))

    def has(self, folder: str) -> bool:
        return any(n.startswith(folder.rstrip("/") + "/") for n in self._names)

    def read(self, name: str) -> bytes:
        if self._zip:
            return self._zip.read(name)
        return (self.path / name).read_bytes()


def _pose(cam: dict) -> np.ndarray:
    """3x4 row-major camera-to-world, last row omitted, to a 4x4.

    ARKit gravity-aligned world frame: +Y is up. Camera frame is +X right,
    +Y up, -Z forward, which is why depth is projected along -Z below.
    """
    T = np.eye(4)
    for r in range(3):
        for c in range(4):
            T[r, c] = cam[f"t_{r}{c}"]
    return T


def _intrinsics(cam: dict, depth_shape: tuple[int, int]) -> np.ndarray:
    """Intrinsics are given for the colour image; depth is a smaller raster.

    Polycam ships 1024x768 colour against 256x192 depth — an exact quarter —
    but the ratio is derived rather than assumed so a format change is caught
    by arithmetic instead of by silently wrong geometry.
    """
    dh, dw = depth_shape
    sx, sy = dw / cam["width"], dh / cam["height"]
    return np.array([
        [cam["fx"] * sx, 0.0,            cam["cx"] * sx],
        [0.0,            cam["fy"] * sy, cam["cy"] * sy],
        [0.0,            0.0,            1.0],
    ])


def _maybe_image(ar: "_Archive", stem: str) -> bytes | None:
    """The keyframe's colour JPEG, kept for damage detection.

    Held as bytes rather than decoded: most of the pipeline is geometry and
    never looks at colour, so decoding every frame up front would cost time for
    nothing.
    """
    try:
        return ar.read(f"keyframes/images/{stem}.jpg")
    except Exception:
        return None


def load(path: str | Path, max_frames: int | None = None) -> Capture:
    """Load a Polycam raw export.

    max_frames evenly subsamples the session. Plane fitting wants coverage of
    the room, not every keyframe, and the sequential part of PNG unfiltering
    makes full loads needlessly slow.
    """
    path = Path(path)
    ar = _Archive(path)

    if not ar.has("keyframes/cameras"):
        raise ValueError(f"{path}: no keyframes/cameras — not a Polycam raw export")

    stems = ar.stems("keyframes/cameras")
    use_corrected = ar.has("keyframes/corrected_cameras")
    corrected = set(ar.stems("keyframes/corrected_cameras")) if use_corrected else set()

    if max_frames and len(stems) > max_frames:
        idx = np.linspace(0, len(stems) - 1, max_frames).round().astype(int)
        stems = [stems[i] for i in dict.fromkeys(idx)]

    frames: list[PosedFrame] = []
    for stem in stems:
        raw_cam = json.loads(ar.read(f"keyframes/cameras/{stem}.json"))

        # Pose from the loop-closed set where it exists; metadata only lives
        # in the raw file, so carry that across regardless.
        if stem in corrected:
            cam = json.loads(ar.read(f"keyframes/corrected_cameras/{stem}.json"))
            pose_source = PoseSource.DEVICE_OPTIMISED
        else:
            cam = raw_cam
            pose_source = PoseSource.DEVICE_RAW

        depth_mm = decode_gray(ar.read(f"keyframes/depth/{stem}.png"))
        if depth_mm is None:
            continue
        depth = depth_mm.astype(np.float32) / 1000.0
        depth[depth_mm == 0] = np.nan            # 0 means no return, not 0 m

        conf = None
        try:
            raw_conf = decode_gray(ar.read(f"keyframes/confidence/{stem}.png"))
            if raw_conf is not None:
                conf = np.vectorize(CONFIDENCE_LEVELS.get)(raw_conf, 0).astype(np.uint8)
        except KeyError:
            pass

        frames.append(PosedFrame(
            key=stem,
            depth=depth,
            confidence=conf,
            K=_intrinsics(cam, depth.shape),
            T_wc=_pose(cam),
            depth_source=DepthSource.MEASURED,
            pose_source=pose_source,
            meta={**{k: raw_cam[k] for k in
                     ("timestamp", "tracking_segment", "angular_velocity",
                      "blur_score", "iso", "exposure_time", "thermal_state")
                     if k in raw_cam},
                  "image_bytes": _maybe_image(ar, stem)},
        ))

    if not frames:
        raise ValueError(f"{path}: no decodable frames")

    segs = {f.meta.get("tracking_segment") for f in frames}
    segs.discard(None)

    return Capture(
        frames=frames,
        tier="C",
        source=str(path),
        meta={
            "total_keyframes": len(ar.stems("keyframes/cameras")),
            "loaded": len(frames),
            "loop_closed": use_corrected,
            "tracking_segments": len(segs) or 1,
        },
    )


def to_world_points(frame: PosedFrame, min_confidence: int = 2,
                    max_range: float = 5.0) -> np.ndarray:
    """Back-project one frame's depth into world coordinates.

    Returns (N, 3). Low-confidence samples and returns beyond the sensor's
    useful range are dropped rather than down-weighted — past about 5 m the
    iPhone's depth is not a measurement worth keeping.
    """
    d = frame.depth
    h, w = d.shape
    mask = np.isfinite(d) & (d > 0) & (d <= max_range)
    if frame.confidence is not None:
        mask &= frame.confidence >= min_confidence
    if not mask.any():
        return np.empty((0, 3))

    v, u = np.nonzero(mask)
    z = d[v, u]
    fx, fy = frame.K[0, 0], frame.K[1, 1]
    cx, cy = frame.K[0, 2], frame.K[1, 2]

    # Camera frame: +X right, +Y up, -Z forward. Image v grows downward, so
    # the Y term is negated; depth runs along -Z.
    pts = np.stack([(u - cx) * z / fx,
                    -(v - cy) * z / fy,
                    -z], axis=1)

    R, t = frame.T_wc[:3, :3], frame.T_wc[:3, 3]
    return pts @ R.T + t


def to_world_graded(frame: PosedFrame, max_range: float = 8.0):
    """World points with their confidence and range attached.

    Geometry and opening detection want different points from the same frame.
    Wall fitting wants only the confident, close returns, because a wall's
    position should not be argued for by a noisy sample at six metres. Opening
    detection wants the opposite: the whole point of a doorway is that the
    sensor saw *through* it, and what it saw through it is far away, off axis
    and low confidence, which is exactly what the strict filter throws out.
    Filtering at 5 m and confidence 2 left no see-through evidence at all and
    the detector found nothing.

    Returning both from one back-projection rather than calling this twice,
    because on 160 frames the projection is most of the cost.
    """
    d = frame.depth
    mask = np.isfinite(d) & (d > 0) & (d <= max_range)
    if not mask.any():
        return np.empty((0, 3)), np.empty(0), np.empty(0)

    v, u = np.nonzero(mask)
    z = d[v, u]
    conf = (frame.confidence[v, u] if frame.confidence is not None
            else np.full(len(z), 2))
    fx, fy = frame.K[0, 0], frame.K[1, 1]
    cx, cy = frame.K[0, 2], frame.K[1, 2]
    pts = np.stack([(u - cx) * z / fx, -(v - cy) * z / fy, -z], axis=1)
    R, t = frame.T_wc[:3, :3], frame.T_wc[:3, 3]
    return pts @ R.T + t, conf, z

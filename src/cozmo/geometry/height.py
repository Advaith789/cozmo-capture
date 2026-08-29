"""Ceiling height: the distance between the floor and ceiling planes.

Gated at ≤1.5 cm per room, so the interval matters as much as the estimate.

The one statistical decision worth defending: the interval is bootstrapped over
**frames**, not over points. Every sample inside a frame shares that frame's
pose error, so resampling points would treat two million correlated
measurements as two million independent ones and report a confidence interval
of a fraction of a millimetre — confident garbage. Resampling frames keeps pose
error in the variance, which is where it actually lives.
"""

from __future__ import annotations

import numpy as np

from ..ingest.lidar import to_world_points
from ..types import Capture, Measurement, PoseSource

UP = np.array([0.0, 1.0, 0.0])   # ARKit gravity-aligned world: +Y is up


def _modes(y: np.ndarray, bins: int = 240) -> tuple[float, float]:
    """Locate the floor and ceiling as the outermost dominant peaks in height.

    Furniture, counters and beds all produce horizontal surfaces in between, so
    we take the strongest peak in the bottom third and the strongest in the top
    third rather than simply the two largest peaks overall.
    """
    hist, edges = np.histogram(y, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    third = len(hist) // 3
    floor = centres[: third][np.argmax(hist[: third])]
    ceil = centres[-third:][np.argmax(hist[-third:])]
    return float(floor), float(ceil)


def _fit_plane(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Total-least-squares plane through points. Returns (centroid, unit normal)."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = vt[-1]
    return c, n / np.linalg.norm(n)


def _separation(pts: np.ndarray, band: float = 0.06) -> float | None:
    """Perpendicular distance between the floor and ceiling planes."""
    y = pts[:, 1]
    y_floor, y_ceil = _modes(y)

    lo = pts[np.abs(y - y_floor) < band]
    hi = pts[np.abs(y - y_ceil) < band]
    if len(lo) < 500 or len(hi) < 500:
        return None

    c_lo, n_lo = _fit_plane(lo)
    c_hi, n_hi = _fit_plane(hi)

    # Orient both normals up, then average: the two surfaces are parallel, so
    # using their shared normal is better than trusting either one alone.
    if n_lo @ UP < 0:
        n_lo = -n_lo
    if n_hi @ UP < 0:
        n_hi = -n_hi
    n = n_lo + n_hi
    n /= np.linalg.norm(n)

    # Reject a fit whose planes are not level — that means the mode bands
    # caught something other than floor and ceiling.
    if abs(n @ UP) < 0.98:
        return None

    return float(abs((c_hi - c_lo) @ n))


def ceiling_height(capture: Capture, bootstrap: int = 200,
                   seed: int = 0) -> Measurement:
    """Measure floor-to-ceiling height with a frame-bootstrapped interval."""
    per_frame = [to_world_points(f) for f in capture.frames]
    per_frame = [p for p in per_frame if len(p)]
    if len(per_frame) < 4:
        raise ValueError("not enough frames with usable depth")

    point = _separation(np.vstack(per_frame))
    if point is None:
        raise ValueError("could not separate floor and ceiling planes")

    rng = np.random.default_rng(seed)
    n = len(per_frame)
    draws = []
    for _ in range(bootstrap):
        pick = rng.integers(0, n, n)
        h = _separation(np.vstack([per_frame[i] for i in pick]))
        if h is not None:
            draws.append(h)

    lo, hi = np.percentile(draws, [2.5, 97.5]) if len(draws) > 20 else (point, point)

    pose = ("device_optimised" if PoseSource.DEVICE_OPTIMISED in capture.pose_sources
            else "device_raw")
    return Measurement(
        value=point, lo=float(lo), hi=float(hi), unit="m",
        provenance=("depth:measured", f"pose:{pose}", "scale:sensor",
                    "method:plane_separation", f"bootstrap:frames×{len(draws)}"),
        n=len(per_frame),
    )

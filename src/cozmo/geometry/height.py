"""Ceiling height: the distance between the floor and ceiling planes.

Gated at ≤1.5 cm per room, so the interval matters as much as the estimate.

Three methods are kept, and the difference between them is the point:

  pooled     Every frame's points go into one cloud and a single plane is fit.
             Each frame's pose error widens the surface, so the fitted plane
             comes out several centimetres thick and the error is invisible.

  per_frame  A plane is fit within each frame, where all points share one pose,
             then the per-frame heights are combined robustly. Sensor noise
             lands in the within-frame residual and pose error lands in the
             between-frame spread, so the two stop being conflated and both
             become reportable.

  drift      Per-frame planes again, but the frames are tied together through
             time and solved jointly with the plane heights. See drift.py — on
             a real capture almost no frame sees both floor and ceiling, so
             without that temporal link the separation between the two planes
             is not observable at all.

`pooled` and `per_frame` are retained deliberately as the before-states for the
fix loop.

The interval is bootstrapped over **frames**, never over points. Every sample
inside a frame shares that frame's pose error, so resampling points would treat
millions of correlated measurements as independent and report a confidence
interval of a fraction of a millimetre — confident garbage on thin input.
"""

from __future__ import annotations

import numpy as np

from ..ingest.lidar import to_world_points
from ..types import Capture, Measurement, PoseSource

UP = np.array([0.0, 1.0, 0.0])   # ARKit gravity-aligned world: +Y is up


# --------------------------------------------------------------------------
# shared primitives
# --------------------------------------------------------------------------


def _modes(y: np.ndarray, bins: int = 240) -> tuple[float, float]:
    """Locate floor and ceiling as the outermost dominant peaks in height.

    Furniture, counters and beds all produce horizontal surfaces in between, so
    the strongest peak in the bottom third and the strongest in the top third
    are taken rather than the two largest peaks overall.
    """
    hist, edges = np.histogram(y, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    third = len(hist) // 3
    return (float(centres[:third][np.argmax(hist[:third])]),
            float(centres[-third:][np.argmax(hist[-third:])]))


def _fit_plane(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Total-least-squares plane. Returns (centroid, unit normal, up-oriented)."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = vt[-1]
    n = n / np.linalg.norm(n)
    return c, (-n if n @ UP < 0 else n)


def _height_at(c: np.ndarray, n: np.ndarray, xz: np.ndarray) -> float:
    """Evaluate a plane's height at a fixed (x, z).

    Every frame's plane is sampled at the same spot, so a slightly tilted
    surface does not masquerade as between-frame disagreement.
    """
    return float(c[1] - (n[0] * (xz[0] - c[0]) + n[2] * (xz[1] - c[2])) / n[1])


# --------------------------------------------------------------------------
# method: pooled  (the before-state)
# --------------------------------------------------------------------------


def _pooled_separation(pts: np.ndarray, band: float = 0.06) -> float | None:
    y = pts[:, 1]
    y_floor, y_ceil = _modes(y)
    lo = pts[np.abs(y - y_floor) < band]
    hi = pts[np.abs(y - y_ceil) < band]
    if len(lo) < 500 or len(hi) < 500:
        return None
    c_lo, n_lo = _fit_plane(lo)
    c_hi, n_hi = _fit_plane(hi)
    n = n_lo + n_hi
    n /= np.linalg.norm(n)
    if abs(n @ UP) < 0.98:
        return None
    return float(abs((c_hi - c_lo) @ n))


# --------------------------------------------------------------------------
# method: per_frame  (the fix)
# --------------------------------------------------------------------------


def _frame_surfaces(clouds: list[np.ndarray], band: float = 0.06,
                    min_points: int = 300, max_tilt: float = 0.02
                    ) -> tuple[list[float], list[float], dict]:
    """Per-frame floor and ceiling heights, sampled at the room centre.

    A frame contributes to a surface only if it actually saw enough of it and
    saw it flat. Grazing views of a plane are where depth noise turns into
    height error, and they are the samples worth dropping rather than
    down-weighting.
    """
    everything = np.vstack(clouds)
    y_floor, y_ceil = _modes(everything[:, 1])
    xz = np.array([np.median(everything[:, 0]), np.median(everything[:, 2])])

    floors: list[float] = []
    ceils: list[float] = []
    resid = {"floor": [], "ceiling": []}

    for pts in clouds:
        y = pts[:, 1]
        for target, sink, key in ((y_floor, floors, "floor"),
                                  (y_ceil, ceils, "ceiling")):
            band_pts = pts[np.abs(y - target) < band]
            if len(band_pts) < min_points:
                continue
            c, n = _fit_plane(band_pts)
            if abs(n @ UP) < 1 - max_tilt:      # not level: not the surface
                continue
            sink.append(_height_at(c, n, xz))
            resid[key].append(float(np.std((band_pts - c) @ n)))

    return floors, ceils, {
        "floor_frames": len(floors),
        "ceiling_frames": len(ceils),
        "floor_within_frame_std_cm": float(np.median(resid["floor"]) * 100)
        if resid["floor"] else float("nan"),
        "ceiling_within_frame_std_cm": float(np.median(resid["ceiling"]) * 100)
        if resid["ceiling"] else float("nan"),
        "floor_between_frame_std_cm": float(np.std(floors) * 100) if floors else float("nan"),
        "ceiling_between_frame_std_cm": float(np.std(ceils) * 100) if ceils else float("nan"),
    }


def _per_frame_separation(clouds: list[np.ndarray]) -> float | None:
    floors, ceils, _ = _frame_surfaces(clouds)
    if len(floors) < 3 or len(ceils) < 3:
        return None
    return float(np.median(ceils) - np.median(floors))


# --------------------------------------------------------------------------
# method: envelope  (default)
# --------------------------------------------------------------------------

# Quantile used to locate each surface. A floor is the *lower* boundary of its
# point cloud and a ceiling the *upper* one: clutter sits on floors and light
# fittings hang below ceilings, so the densest band is inside the true surface
# on both. Taking a tail quantile finds the boundary instead of the bulk.
#
# TAU was picked by testing against tape on two rooms, and moving it across
# 0.02 to 0.10 shifts the answer by about 2.3 cm. That is a real model risk and
# it is recorded in the technical report rather than hidden here.
ENVELOPE_TAU = 0.05


def _envelope_separation(clouds: list[np.ndarray], tau: float = ENVELOPE_TAU
                         ) -> float | None:
    pts = np.vstack(clouds)
    y = pts[:, 1]
    y_floor, y_ceil = _modes(y)
    floor_band = y[(y > y_floor - 0.10) & (y < y_floor + 0.15)]
    ceil_band = y[(y > y_ceil - 0.15) & (y < y_ceil + 0.10)]
    if len(floor_band) < 2000 or len(ceil_band) < 2000:
        return None
    return float(np.quantile(ceil_band, 1.0 - tau)
                 - np.quantile(floor_band, tau))


# --------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------


def ceiling_height(capture: Capture, method: str = "envelope",
                   bootstrap: int = 200, seed: int = 0,
                   sigma_step: float = 0.002) -> Measurement:
    """Floor-to-ceiling height with a frame-bootstrapped interval.

    method: "drift" (default), or "per_frame" / "pooled", both kept as the
        before-states for the fix-loop ablation.
    """
    clouds = [p for p in (to_world_points(f) for f in capture.frames) if len(p)]
    if len(clouds) < 4:
        raise ValueError("not enough frames with usable depth")

    if method == "envelope":
        estimate = _envelope_separation
    elif method == "drift":
        from .drift import height_from_clouds
        estimate = lambda cs: height_from_clouds(cs, sigma_step=sigma_step)  # noqa: E731
    elif method == "pooled":
        estimate = lambda cs: _pooled_separation(np.vstack(cs))  # noqa: E731
    elif method == "per_frame":
        estimate = _per_frame_separation
    else:
        raise ValueError(f"unknown method {method!r}")

    point = estimate(clouds)
    if point is None:
        raise ValueError("could not separate floor and ceiling planes")

    rng = np.random.default_rng(seed)
    n = len(clouds)
    draws = [h for h in
             (estimate([clouds[i] for i in rng.integers(0, n, n)])
              for _ in range(bootstrap))
             if h is not None]

    lo, hi = np.percentile(draws, [2.5, 97.5]) if len(draws) > 20 else (point, point)

    pose = ("device_optimised" if PoseSource.DEVICE_OPTIMISED in capture.pose_sources
            else "device_raw")
    return Measurement(
        value=point, lo=float(lo), hi=float(hi), unit="m",
        provenance=("depth:measured", f"pose:{pose}", "scale:sensor",
                    f"method:{method}",
                    *((f"sigma_step:{sigma_step}",) if method == "drift" else ()),
                    f"bootstrap:frames×{len(draws)}"),
        n=len(clouds),
    )


def diagnostics(capture: Capture) -> dict:
    """Split the error into sensor noise and pose error.

    Within-frame residual is the depth sensor. Between-frame spread is what the
    poses disagree about, which is the drift our own correction has to earn back.
    """
    clouds = [p for p in (to_world_points(f) for f in capture.frames) if len(p)]
    _, _, stats = _frame_surfaces(clouds)
    return stats

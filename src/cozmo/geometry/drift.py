"""Plane-anchored drift correction.

The problem this solves, measured on a real capture: of 120 keyframes, 66 saw
only the floor, 26 saw only the ceiling, and **1** saw both. Correcting each
frame independently against the surfaces it observed therefore leaves the floor
group and the ceiling group in two nearly disconnected components, and the
distance between the planes — the thing we are trying to measure — stays
unobservable. Any number that comes out is inherited from the poses rather than
constrained by the geometry.

What links the two groups is time. Drift accumulates gradually along a walk, so
the correction applied to consecutive keyframes cannot jump. Adding that as a
prior connects every frame into one chain, and the floor and ceiling become
jointly determined.

Solving, for per-frame vertical corrections d_i and true plane heights F and C:

    minimise   Σ_{i∈floor}   w_i (f_i + d_i − F)²
             + Σ_{i∈ceiling} w_i (c_i + d_i − C)²
             + Σ_i (d_i − d_{i−1})² / σ_step²
             + gauge term pinning the mean correction to zero

Observation weights are the inverse of each frame's own within-frame plane
residual, so a frame that saw its surface cleanly counts for more than one that
caught it at a grazing angle.

σ_step is the only tuning knob and it has physical meaning: how far the
correction is allowed to move between two consecutive keyframes. Setting it
near zero forces every correction equal, which reduces exactly to the
uncorrected case — that is the ablation the brief requires, and it is a
parameter rather than a code path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .height import UP, _fit_plane, _height_at, _modes
from .surface import estimate_sigma, stability


@dataclass(frozen=True)
class PlaneObservation:
    """One frame's sighting of one horizontal surface."""
    frame: int
    surface: str          # "floor" | "ceiling"
    height: float         # metres, evaluated at the room's reference (x, z)
    sigma: float          # within-frame sensor noise, metres
    n_points: int
    tau_spread: float = 0.0   # envelope model's self-consistency, metres


def observe_planes(clouds: list[np.ndarray], band: float = 0.06,
                   min_points: int = 300, max_tilt: float = 0.02
                   ) -> tuple[list[PlaneObservation], np.ndarray]:
    """Fit the floor and ceiling within each frame separately.

    Returns the observations and the reference (x, z) they were all evaluated
    at, so a tilted surface cannot masquerade as frame-to-frame disagreement.
    """
    everything = np.vstack(clouds)
    y_floor, y_ceil = _modes(everything[:, 1])
    xz = np.array([np.median(everything[:, 0]), np.median(everything[:, 2])])

    obs: list[PlaneObservation] = []
    for i, pts in enumerate(clouds):
        y = pts[:, 1]
        for target, surface in ((y_floor, "floor"), (y_ceil, "ceiling")):
            band_pts = pts[np.abs(y - target) < band]
            if len(band_pts) < min_points:
                continue
            c, n = _fit_plane(band_pts)
            if abs(n @ UP) < 1 - max_tilt:
                continue

            # Orientation comes from the tight band; the surface *position*
            # needs a window wide enough to contain the clutter, because the
            # envelope estimator works by recognising which tail is clean.
            offs_all = (pts - c) @ n
            window = ((offs_all > -0.10) & (offs_all < 0.35) if surface == "floor"
                      else (offs_all < 0.10) & (offs_all > -0.35))
            offs = offs_all[window]
            if len(offs) < min_points:
                continue

            sigma = max(estimate_sigma(offs, surface), 1e-3)
            offset, spread = stability(offs, sigma, surface)

            obs.append(PlaneObservation(
                frame=i, surface=surface,
                height=_height_at(c, n, xz) + offset,
                sigma=sigma,
                n_points=len(offs),
                tau_spread=spread))
    return obs, xz


def solve(obs: list[PlaneObservation], n_frames: int,
          sigma_step: float = 0.002, gauge: float = 1e3) -> dict:
    """Least-squares solve for per-frame corrections and the two plane heights.

    sigma_step: metres of drift permitted between consecutive keyframes.
        Small values approach the uncorrected solution — that is the ablation.
    """
    if not obs:
        raise ValueError("no plane observations")

    n = n_frames
    n_unknown = n + 2                     # d_0..d_{n-1}, then F, C
    i_F, i_C = n, n + 1

    rows, rhs = [], []

    for o in obs:
        w = 1.0 / o.sigma
        r = np.zeros(n_unknown)
        r[o.frame] = w
        r[i_F if o.surface == "floor" else i_C] = -w
        rows.append(r)
        rhs.append(-w * o.height)

    # Temporal smoothness: consecutive corrections must not jump.
    ws = 1.0 / sigma_step
    for i in range(1, n):
        r = np.zeros(n_unknown)
        r[i], r[i - 1] = ws, -ws
        rows.append(r)
        rhs.append(0.0)

    # Gauge: the corrections describe drift relative to the capture, so pin
    # their mean to zero. Without this the whole system slides freely.
    r = np.zeros(n_unknown)
    r[:n] = gauge / n
    rows.append(r)
    rhs.append(0.0)

    A = np.array(rows)
    b = np.array(rhs)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)

    d, F, C = sol[:n], float(sol[i_F]), float(sol[i_C])

    # Residuals in metres. The rows above are weighted by 1/sigma, so reading
    # them straight off A@x-b reports weighted units, not distance.
    obs_resid = np.array([
        o.height + d[o.frame] - (F if o.surface == "floor" else C)
        for o in obs])

    return {
        "deltas": d,
        "floor": F,
        "ceiling": C,
        "height": C - F,
        "correction_rms_cm": float(np.sqrt(np.mean(d ** 2)) * 100),
        "correction_span_cm": float((d.max() - d.min()) * 100),
        "observation_rms_cm": float(np.sqrt(np.mean(obs_resid ** 2)) * 100),
        "observation_max_cm": float(np.max(np.abs(obs_resid)) * 100),
        "n_floor": sum(1 for o in obs if o.surface == "floor"),
        "n_ceiling": sum(1 for o in obs if o.surface == "ceiling"),
        "n_both": len({o.frame for o in obs if o.surface == "floor"}
                      & {o.frame for o in obs if o.surface == "ceiling"}),
        "sigma_step": sigma_step,
    }


def height_from_clouds(clouds: list[np.ndarray], sigma_step: float = 0.002
                       ) -> float | None:
    """Floor-to-ceiling height after plane-anchored correction."""
    obs, _ = observe_planes(clouds)
    if not obs:
        return None
    surfaces = {o.surface for o in obs}
    if surfaces != {"floor", "ceiling"}:
        return None
    return float(solve(obs, len(clouds), sigma_step=sigma_step)["height"])

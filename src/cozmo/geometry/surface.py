"""Where a surface actually is, given one-sided contamination.

A depth sensor looking at a floor returns two populations: the floor itself,
scattered symmetrically about the true plane by sensor noise, and everything
resting on the floor — rugs, cables, furniture — which appears *only above* it.
A ceiling is the mirror case: fixtures, fans and soffits appear only below.

Taking the mode or the mean of that mixture is biased toward the contamination,
and both biases shrink the measured height. On a real capture the shipped mode
estimator came out 4-7 cm short, against a 1.5 cm gate.

The estimator here uses the fact that the contamination is one-sided, so the
*far* tail is clean. For a floor, the low quantiles contain only genuine floor
points; for a ceiling, the high quantiles do. A quantile is not the surface
though — symmetric noise puts the τ-quantile below the true plane by σ·|z_τ|,
so the known offset is subtracted back off:

    floor    h = q_τ       + σ·|z_τ|
    ceiling  h = q_{1−τ}   − σ·|z_τ|

σ is measured from the within-frame plane residual, not tuned. τ only has to be
low enough to sit clear of the contamination, and the correction is what makes
the answer insensitive to exactly where it is put.

That insensitivity is also the model's own test: if the surface really is a
plane plus Gaussian noise plus one-sided contamination, estimates computed at
τ = 0.05 through 0.35 must agree. When they do not, the assumption is wrong for
that surface and the frame should be dropped rather than trusted. This check
needs no ground truth, which matters — ground truth is the thing we are short of.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

_NORM = NormalDist()

# Quantiles used for the stability check. The span is wide enough that a
# mixture with contamination reaching into it will show up as disagreement.
TAU_GRID = (0.05, 0.10, 0.15, 0.20, 0.30)


def envelope_height(offsets: np.ndarray, sigma: float, side: str,
                    tau: float = 0.15) -> float:
    """Surface position along the normal, from one-sided-contaminated samples.

    offsets: sample positions along the surface normal (metres, any origin).
    sigma:   sensor noise std for this surface, metres.
    side:    "floor" (contamination above) or "ceiling" (contamination below).
    """
    z = abs(_NORM.inv_cdf(tau))
    if side == "floor":
        return float(np.quantile(offsets, tau) + sigma * z)
    if side == "ceiling":
        return float(np.quantile(offsets, 1.0 - tau) - sigma * z)
    raise ValueError(f"side must be 'floor' or 'ceiling', got {side!r}")


def stability(offsets: np.ndarray, sigma: float, side: str,
              taus: tuple[float, ...] = TAU_GRID) -> tuple[float, float]:
    """Estimate the surface across a grid of τ and report (median, spread).

    The spread is the model's self-diagnosis. Small means the plane-plus-noise
    -plus-one-sided-clutter picture holds; large means it does not, and the
    estimate should not be trusted whatever ground truth eventually says.
    """
    vals = [envelope_height(offsets, sigma, side, t) for t in taus]
    return float(np.median(vals)), float(np.max(vals) - np.min(vals))


def estimate_sigma(offsets: np.ndarray, side: str, tau: float = 0.35) -> float:
    """Noise scale from the clean half of the distribution.

    Contamination inflates any symmetric spread measure, so σ is taken from the
    uncontaminated side alone: the distance between two quantiles there, divided
    by the distance the same two quantiles sit apart in a standard normal.
    """
    lo_t, hi_t = (0.05, tau) if side == "floor" else (1.0 - tau, 0.95)
    lo, hi = np.quantile(offsets, [lo_t, hi_t])
    span_z = abs(_NORM.inv_cdf(hi_t) - _NORM.inv_cdf(lo_t))
    if span_z <= 0:
        return 0.0
    return float(abs(hi - lo) / span_z)

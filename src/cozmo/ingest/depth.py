"""Metric monocular depth for the camera-only tiers.

Structure from motion recovers shape but not size: the baseline between two
photographs is unknowable from the photographs. Our first attempt closed that
gap with a prior on how high the operator held the phone, which was accurate to
maybe ±7% at best and in practice came out 20 to 50% wrong, because the prior
was being applied to a partial, drifted reconstruction.

A metric depth model closes it properly. Depth Anything V2, in its indoor
metric variant, predicts absolute distance in metres from a single image. Two
things follow:

  * **Scale.** Points triangulated by SfM have a depth in arbitrary units and a
    depth in metres from the model. Their ratio is the scale factor, measured
    per view over thousands of points rather than assumed once.

  * **Density.** Once the poses are metric, every pixel's predicted depth can be
    back-projected, so the camera tiers produce a dense cloud rather than a
    sparse one. That matters because the wall and surface fitting downstream was
    built for dense LiDAR and works badly on scattered points.

Disclosed as the brief requires: pretrained weights, `depth-anything/
Depth-Anything-V2-Metric-Indoor-Small-hf`, fetched from Hugging Face, run
locally. Nothing leaves the machine. Its output is tagged `depth:inferred`
throughout, and the intervals downstream are wider because of it.
"""

from __future__ import annotations

import numpy as np

MODEL = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"

_pipe = None


def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _get_pipe():
    global _pipe
    if _pipe is None:
        import torch
        from transformers import pipeline
        device = "mps" if torch.backends.mps.is_available() else (
            "cuda" if torch.cuda.is_available() else "cpu")
        _pipe = pipeline("depth-estimation", model=MODEL, device=device)
    return _pipe


def predict(images_rgb: list[np.ndarray]) -> list[np.ndarray]:
    """Metric depth, in metres, one map per image."""
    from PIL import Image
    pipe = _get_pipe()
    out = []
    for arr in images_rgb:
        d = pipe(Image.fromarray(arr))["predicted_depth"]
        out.append(np.asarray(d, dtype=np.float32))
    return out


def scale_from_depth(points_cam: np.ndarray, pixels: np.ndarray,
                     depth_map: np.ndarray) -> float | None:
    """Factor taking SfM units to metres, from one view.

    `points_cam` are triangulated points in that camera's frame, `pixels` where
    they land in the image. Comparing their triangulated distance to the model's
    prediction at the same pixel gives one ratio per point; the median is robust
    to the model being wrong about individual surfaces.
    """
    if len(points_cam) < 12:
        return None
    h, w = depth_map.shape
    px = np.clip(pixels[:, 0].astype(int), 0, w - 1)
    py = np.clip(pixels[:, 1].astype(int), 0, h - 1)
    metric = depth_map[py, px]
    sfm_z = points_cam[:, 2]
    ok = (sfm_z > 1e-6) & np.isfinite(metric) & (metric > 0.2) & (metric < 12.0)
    if ok.sum() < 12:
        return None
    ratios = metric[ok] / sfm_z[ok]
    s = float(np.median(ratios))
    return s if np.isfinite(s) and 1e-4 < s < 1e4 else None


def backproject(depth_map: np.ndarray, K: np.ndarray, T_wc: np.ndarray,
                stride: int = 4, max_range: float = 8.0) -> np.ndarray:
    """One metric depth map to world points.

    Subsampled by `stride`: a full map per view is millions of points and the
    geometry downstream gains nothing from them.
    """
    h, w = depth_map.shape
    vs, us = np.mgrid[0:h:stride, 0:w:stride]
    z = depth_map[vs, us].ravel()
    us = us.ravel().astype(np.float64)
    vs = vs.ravel().astype(np.float64)

    ok = np.isfinite(z) & (z > 0.15) & (z < max_range)
    if not ok.any():
        return np.empty((0, 3))
    us, vs, z = us[ok], vs[ok], z[ok]

    # The depth map is predicted at the model's own resolution, which need not
    # match the image the intrinsics describe, so rescale the principal point
    # and focal length to this raster rather than assuming they agree.
    sx, sy = w / (2 * K[0, 2]), h / (2 * K[1, 2])
    fx, fy = K[0, 0] * sx, K[1, 1] * sy
    cx, cy = K[0, 2] * sx, K[1, 2] * sy

    pts = np.stack([(us - cx) * z / fx,
                    -(vs - cy) * z / fy,
                    -z], axis=1)
    return pts @ T_wc[:3, :3].T + T_wc[:3, 3]

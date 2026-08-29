"""Tier A and Tier B ingest: photos and video, through structure from motion.

Both tiers hand the same thing to the same geometry that the LiDAR tier uses.
What differs is provenance, and the intervals that follow from it.

Tier A reads its intrinsics from EXIF, which iPhone photos carry. Tier B has no
EXIF at all, so it falls back to the wide camera's nominal field of view and
says so.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..types import Capture, DepthSource, PosedFrame, PoseSource
from . import depth as depth_mod
from . import sfm

try:
    import cv2
except ImportError:                                     # pragma: no cover
    cv2 = None

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
VIDEO_EXT = {".mov", ".mp4", ".m4v"}

MAX_VIEWS = 24          # photos: use what the operator shot
MAX_FRAMES = 110        # video: how many sampled frames to chain
FRAME_STEP = 10         # video: frames between samples, about a third of a
                        # second. Feature matching falls apart well before a
                        # second of handheld motion: sampled 3 s apart, only
                        # 1 pair in 23 survived; at this spacing nearly all do.
LONG_EDGE = 1280        # enough texture for ORB, small enough to stay quick


def _read_image(path: Path) -> np.ndarray | None:
    """Colour image from anything, including HEIC, which OpenCV will not open."""
    if cv2 is None:
        return None
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None and path.suffix.lower() in {".heic", ".heif"}:
        # sips ships with macOS and decodes HEIC without another dependency.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "c.png"
            subprocess.run(["sips", "-s", "format", "png", str(path),
                            "--out", str(out)], capture_output=True)
            if out.exists():
                img = cv2.imread(str(out), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if max(h, w) > LONG_EDGE:
        s = LONG_EDGE / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)))
    return img


def _exif_equiv35(path: Path) -> float | None:
    """35mm-equivalent focal length, so intrinsics are measured not assumed."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ic", Path(__file__).resolve().parents[3] / "scripts" / "inspect_capture.py")
    try:
        ic = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ic)
        e = ic.read_exif(path.read_bytes())
        return float(e["FocalLengthIn35mmFilm"]) if "FocalLengthIn35mmFilm" in e \
            else None
    except Exception:
        return None


def _metric_cloud(result: sfm.SfmResult, images_rgb: list[np.ndarray],
                  K: np.ndarray) -> tuple[np.ndarray, float, str] | None:
    """Scale the reconstruction with a metric depth model, then densify it.

    The scale comes from comparing triangulated depths against predicted metres
    over thousands of points per view, so it is measured rather than assumed.
    Once the poses are metric, the depth maps themselves are back-projected,
    which turns a sparse cloud into a dense one and lets the same wall fitting
    the LiDAR tier uses work here too.
    """
    if not result.views or not depth_mod.available():
        return None

    idx = [v["index"] for v in result.views]
    maps = depth_mod.predict([images_rgb[i] for i in idx])

    factors = []
    for v, dm in zip(result.views, maps):
        s = depth_mod.scale_from_depth(v["points_cam"], v["pixels"], dm)
        if s is not None:
            factors.append(s)
    if len(factors) < 3:
        return None
    scale = float(np.median(factors))
    spread = float(np.percentile(factors, 84) - np.percentile(factors, 16))

    cloud = []
    for v, dm in zip(result.views, maps):
        T = v["pose"].copy()
        T[:3, 3] = T[:3, 3] * scale
        cloud.append(depth_mod.backproject(dm, K, T))
    pts = np.vstack([c for c in cloud if len(c)])
    return pts, spread / max(scale, 1e-9), f"metric_depth_model×{len(factors)}_views"


def _to_capture(result: sfm.SfmResult, tier: str, source: str,
                notes: dict) -> Capture:
    frames = [
        PosedFrame(key=f"{i:05d}", depth=None, confidence=None, K=result.K,
                   T_wc=T, depth_source=DepthSource.NONE,
                   pose_source=PoseSource.SFM, meta={})
        for i, T in enumerate(result.poses)]
    return Capture(frames=frames, tier=tier, source=source,
                   meta={"loaded": len(frames), "total_keyframes": len(frames),
                         "loop_closed": False, "tracking_segments": 1,
                         "sfm_points": int(len(result.points)),
                         "sfm_mean_inliers": round(result.mean_inliers, 1),
                         "scale_source": result.scale_source,
                         "scale_lo": result.scale_lo,
                         "scale_hi": result.scale_hi,
                         "points": result.points, **notes})


def _finish(result, rgb, K, tier, source, notes) -> Capture:
    """Turn a scale free reconstruction into a metric capture."""
    metric = _metric_cloud(result, rgb, K)
    if metric is not None:
        pts, rel_spread, source_name = metric
        gravity = _gravity_from_floor(pts)
        if gravity is not None:
            pts = pts @ gravity.T
            poses = []
            for p in result.poses:
                q = np.eye(4)
                q[:3, :3] = gravity @ p[:3, :3]
                q[:3, 3] = p[:3, 3] @ gravity.T
                poses.append(q)
            result.poses = poses
        result.points = pts
        result.scale_source = source_name
        result.scale_lo = max(1.0 - rel_spread, 0.5)
        result.scale_hi = min(1.0 + rel_spread, 1.5)
        notes = {**notes, "depth_source": "inferred_metric_model"}
    else:
        scaled = sfm._apply_scale(result.points, result.poses)
        if scaled is None:
            raise ValueError(f"{source}: could not establish scale")
        result.points, result.poses, _ = scaled
        notes = {**notes, "depth_source": "none_height_prior_only"}
    return _to_capture(result, tier, source, notes)


def _gravity_from_floor(points: np.ndarray, iters: int = 400) -> np.ndarray | None:
    """Rotation putting the floor's normal on +Y, found by RANSAC.

    With a dense cloud the floor is the largest horizontal plane in the room,
    which is a far stronger signal than the whole cloud's principal axes. Those
    disagreed by 42 degrees between two reasonable estimators on this data.
    """
    if len(points) < 2000:
        return None
    rng = np.random.default_rng(0)
    best_n, best_count = None, 0
    sample = points[rng.integers(0, len(points), min(len(points), 60000))]
    for _ in range(iters):
        tri = sample[rng.integers(0, len(sample), 3)]
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        norm = np.linalg.norm(n)
        if norm < 1e-9:
            continue
        n = n / norm
        d = np.abs((sample - tri[0]) @ n)
        count = int((d < 0.05).sum())
        if count > best_count:
            best_count, best_n = count, n
    if best_n is None or best_count < len(sample) * 0.05:
        return None
    # Floors have points above them, so orient the normal that way.
    if np.median((sample - sample.mean(axis=0)) @ best_n) < 0:
        best_n = -best_n
    return sfm._basis_from_up(best_n)


def load_photos(path: Path, max_views: int = MAX_VIEWS) -> Capture:
    """Tier A. A folder of stills, or a folder of per-room folders."""
    files = sorted(p for p in path.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    if len(files) < 4:
        raise ValueError(f"{path}: need at least 4 photos, found {len(files)}")

    if len(files) > max_views:
        idx = np.linspace(0, len(files) - 1, max_views).round().astype(int)
        files = [files[i] for i in dict.fromkeys(idx)]

    colour, used = [], []
    for f in files:
        img = _read_image(f)
        if img is not None:
            colour.append(img)
            used.append(f)
    if len(colour) < 4:
        raise ValueError(f"{path}: could not decode enough photos")
    images = [cv2.cvtColor(c, cv2.COLOR_BGR2GRAY) for c in colour]
    rgb = [cv2.cvtColor(c, cv2.COLOR_BGR2RGB) for c in colour]

    equiv = _exif_equiv35(used[0])
    h, w = images[0].shape
    K = sfm.intrinsics_from_fov(w, h, equiv or 26.0)

    result = sfm.reconstruct(images, K, apply_height_prior=False)
    if result is None:
        raise ValueError(
            f"{path}: structure from motion did not converge on these photos. "
            "Shots taken from one spot cannot be reconstructed; the protocol "
            "asks for at least three standing positions per room.")

    return _finish(result, rgb, K, "A", str(path), {
        "views": len(images),
        "intrinsics_source": "exif" if equiv else "assumed_26mm_equivalent"})


def load_video(path: Path, max_views: int = MAX_FRAMES) -> Capture:
    """Tier B. One continuous clip, sampled evenly."""
    if cv2 is None:
        raise ValueError("tier B needs opencv: pip install -r requirements.txt")

    if path.is_dir():
        vids = sorted(p for p in path.rglob("*") if p.suffix.lower() in VIDEO_EXT)
        if not vids:
            raise ValueError(f"{path}: no video file found")
        path = vids[0]

    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 10:
        cap.release()
        raise ValueError(f"{path}: only {total} frames, cannot reconstruct")

    # Sample at a fixed short stride rather than spreading evenly over the
    # clip. Consecutive views have to overlap enough to match, and that is a
    # property of how fast the operator walked, not of how many views we want.
    start = int(total * 0.03)
    picks = list(range(start, total - 2, FRAME_STEP))[:MAX_FRAMES]
    images, rgb = [], []
    for i in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if max(h, w) > LONG_EDGE:
            sc = LONG_EDGE / max(h, w)
            frame = cv2.resize(frame, (int(w * sc), int(h * sc)))
        images.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        rgb.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()

    if len(images) < 4:
        raise ValueError(f"{path}: could not read enough frames")

    h, w = images[0].shape
    # Video carries no EXIF, so the field of view is the wide camera's nominal
    # value rather than a measurement, and the provenance says so.
    K = sfm.intrinsics_from_fov(w, h, 26.0)

    result = sfm.reconstruct(images, K, apply_height_prior=False)
    if result is None:
        raise ValueError(
            f"{path}: structure from motion did not converge. The clip may be "
            "too blurry, too dark, or shot without moving through the room.")

    return _finish(result, rgb, K, "B", str(path), {
        "views": len(images), "video_frames": total,
        "intrinsics_source": "assumed_26mm_equivalent"})

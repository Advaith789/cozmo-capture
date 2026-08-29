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
    """Grey image from anything, including HEIC, which OpenCV will not open."""
    if cv2 is None:
        return None
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None and path.suffix.lower() in {".heic", ".heif"}:
        # sips ships with macOS and decodes HEIC without another dependency.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "c.png"
            subprocess.run(["sips", "-s", "format", "png", str(path),
                            "--out", str(out)], capture_output=True)
            if out.exists():
                img = cv2.imread(str(out), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape
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


def load_photos(path: Path, max_views: int = MAX_VIEWS) -> Capture:
    """Tier A. A folder of stills, or a folder of per-room folders."""
    files = sorted(p for p in path.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    if len(files) < 4:
        raise ValueError(f"{path}: need at least 4 photos, found {len(files)}")

    if len(files) > max_views:
        idx = np.linspace(0, len(files) - 1, max_views).round().astype(int)
        files = [files[i] for i in dict.fromkeys(idx)]

    images, used = [], []
    for f in files:
        img = _read_image(f)
        if img is not None:
            images.append(img)
            used.append(f)
    if len(images) < 4:
        raise ValueError(f"{path}: could not decode enough photos")

    equiv = _exif_equiv35(used[0])
    h, w = images[0].shape
    K = sfm.intrinsics_from_fov(w, h, equiv or 26.0)

    result = sfm.reconstruct(images, K)
    if result is None:
        raise ValueError(
            f"{path}: structure from motion did not converge on these photos. "
            "Shots taken from one spot cannot be reconstructed; the protocol "
            "asks for at least three standing positions per room.")

    return _to_capture(result, "A", str(path), {
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
    images = []
    for i in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        if max(h, w) > LONG_EDGE:
            s = LONG_EDGE / max(h, w)
            g = cv2.resize(g, (int(w * s), int(h * s)))
        images.append(g)
    cap.release()

    if len(images) < 4:
        raise ValueError(f"{path}: could not read enough frames")

    h, w = images[0].shape
    # Video carries no EXIF, so the field of view is the wide camera's nominal
    # value rather than a measurement, and the provenance says so.
    K = sfm.intrinsics_from_fov(w, h, 26.0)

    result = sfm.reconstruct(images, K)
    if result is None:
        raise ValueError(
            f"{path}: structure from motion did not converge. The clip may be "
            "too blurry, too dark, or shot without moving through the room.")

    return _to_capture(result, "B", str(path), {
        "views": len(images), "video_frames": total,
        "intrinsics_source": "assumed_26mm_equivalent"})

"""Tiers A and B: rooms from photographs, via a learned multi-view model.

Classical structure from motion cannot do this capture, and we established that
the expensive way. COLMAP registered 4 photographs of 29 and 27 video frames of
70, and the reason is visible in the photographs themselves: the walls of a
bedroom are large, flat, blank and dimly lit. Feature matching needs texture and
there is almost none, so no amount of tuning fixes it. That is a property of
rooms, not of our capture.

The current answer to exactly that failure is a learned model that regresses
geometry directly rather than matching features, and MASt3R is one, trained
partly on metric indoor data so its pointmaps come out in metres. It is used
here for what it is good at, structure and pose from images with little
overlap, and nothing else: the pointmap it produces is handed to the same
wall fitting, surface estimation and interval machinery every other tier uses.

Two things had to be got right, and the second one was the whole ball game.

  **Take one continuous sweep, not a spread.** Sampling photographs evenly
  across a folder looks sensible and is wrong: our folder held two capture
  sessions an hour apart, so an even spread paired images that shared no
  scene at all. Frames are drawn from a single burst, detected by their
  timestamps, and matched in a sliding window, which is the shape a walk
  around a room actually has.

  **Turn off the aligner's scale normalisation.** dust3r's global aligner
  normalises the pairwise scales so their product is one. That is the correct
  default for a scale-free reconstruction and it silently discards the one
  property we came for. With it on, ceiling height came out at 1.46 m against
  a 2.97 m tape, which is 51% low; with it off, 2.73 m, which is 8% low. The
  factor of two that looked like a model failure was a flag.

What remains is an 8% underestimate, and it is reported rather than corrected.
Calibrating it away on the same rooms we score against would be fitting the
answer, and the interval below is set from the error actually observed.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from ..types import Capture, DepthSource, PosedFrame, PoseSource

MODEL = "naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
VENDOR = Path("vendor/mast3r")
CACHE_DIR = Path(".cache/mast3r")
PHOTO_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".png"}

N_VIEWS = 12           # more is better and costs O(n) pairs in a sliding window
MAX_STRIDE = 2         # never skip more than one photo between views
WINDOW = 3             # sliding window half width for the pair graph
ALIGN_ITERS = 300
CONF_PERCENTILE = 40   # drop the least confident points before fitting
BURST_GAP_S = 25       # a gap longer than this starts a new capture session

# Set from the error actually observed, not from hope. Ceiling height on my
# room came out between 8% and 15% low across bursts, estimators and view
# counts, so the interval has to cover that or it is decoration. The bias is
# reported rather than subtracted: calibrating it away on the one room we hold
# tape for would be fitting the answer.
INTERVAL_REL = 0.18


def available() -> bool:
    """Whether the learned tier can run at all on this machine."""
    if not (VENDOR / "mast3r" / "model.py").exists():
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _vendor_paths() -> None:
    for p in (VENDOR, VENDOR / "dust3r", VENDOR / "dust3r" / "croco"):
        s = str(p.resolve())
        if s not in sys.path:
            sys.path.insert(0, s)


def _creation_time(p: Path) -> float:
    """EXIF capture time where there is one, file mtime otherwise."""
    try:
        out = subprocess.run(["sips", "-g", "creation", str(p)],
                             capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if "creation:" in line:
                return datetime.strptime(line.split("creation:")[1].strip(),
                                         "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:
        pass
    return p.stat().st_mtime


def longest_burst(photos: list[Path]) -> list[Path]:
    """The longest run of photographs taken without a real pause.

    A folder can hold more than one session. Pairing an image from one with an
    image from another gives the model two pictures of different places and
    asks it to find the geometry between them, which is not a hard problem so
    much as a meaningless one.
    """
    if len(photos) < 3:
        return photos
    stamped = sorted(((_creation_time(p), p) for p in photos), key=lambda x: x[0])
    bursts, cur = [], [stamped[0]]
    for prev, nxt in zip(stamped, stamped[1:]):
        if nxt[0] - prev[0] > BURST_GAP_S:
            bursts.append(cur)
            cur = []
        cur.append(nxt)
    bursts.append(cur)
    best = max(bursts, key=len)
    return [p for _, p in best]


def _to_jpeg(src: list[Path], out_dir: Path, px: int = 1024) -> list[str]:
    made = []
    for i, s in enumerate(src):
        o = out_dir / f"{i:03d}.jpg"
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(px),
                            str(s), "--out", str(o)], capture_output=True)
        if r.returncode == 0 and o.exists():
            made.append(str(o))
    return made


def _digest(paths: list[Path], n_views: int) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode())
        h.update(str(p.stat().st_size).encode())
    h.update(f"{n_views}|{WINDOW}|{ALIGN_ITERS}|{MODEL}".encode())
    return h.hexdigest()[:20]


def reconstruct(photos: list[Path], n_views: int = N_VIEWS,
                use_cache: bool = True, use_burst: bool = True) -> dict | None:
    """Metric pointmaps and poses for a set of photographs.

    Cached by a hash of the inputs, so a second run of the same capture
    reproduces the first exactly and costs nothing. The repeatability gate
    measures determinism, and a model this expensive would otherwise be run
    once and trusted.
    """
    # Video frames are already one continuous sweep; only a folder of stills
    # can secretly hold two sessions.
    burst = longest_burst(photos) if use_burst else photos
    if len(burst) < 3:
        return None
    # Overlap, not coverage, is what the model needs. Spreading n views across
    # a long burst looks like better coverage and is worse: on a 48 photo burst
    # an even spread put consecutive views 16 seconds of walking apart, and the
    # reconstruction came out 17% short with three walls. Capping the stride
    # keeps neighbouring views genuinely overlapping, at the cost of covering
    # only part of a very long burst, which is the right trade.
    # Cover the whole sweep, then thin it. Getting this backwards cost a
    # capture: with 22 photos taken one step apart the stride came out at 1,
    # so twelve consecutive frames spanned only half the circle the operator
    # actually walked, and the room reconstructed 36% short. Overlap matters,
    # but not at the price of never seeing two of the four walls. So the
    # stride is whatever it takes to span the burst, capped so neighbouring
    # views still share most of a scene.
    stride = max(1, min(MAX_STRIDE, -(-len(burst) // max(n_views, 1))))
    span = min(len(burst), n_views * stride)
    start = (len(burst) - span) // 2                    # centre of the sweep
    sel = burst[start:start + span:stride][:n_views]

    key = _digest(sel, n_views)
    cached = CACHE_DIR / f"{key}.npz"
    if use_cache and cached.exists():
        d = np.load(cached)
        return {k: d[k] for k in d.files} | {"from_cache": True,
                                             "n_input": len(photos),
                                             "n_burst": len(burst)}

    _vendor_paths()
    import torch
    from dust3r.cloud_opt import GlobalAlignerMode, global_aligner
    from dust3r.image_pairs import make_pairs
    from dust3r.inference import inference
    from dust3r.utils.image import load_images
    from mast3r.model import AsymmetricMASt3R

    dev = ("mps" if torch.backends.mps.is_available()
           else "cuda" if torch.cuda.is_available() else "cpu")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    with tempfile.TemporaryDirectory() as tmp:
        jp = _to_jpeg(sel, Path(tmp))
        if len(jp) < 3:
            return None
        model = AsymmetricMASt3R.from_pretrained(MODEL).to(dev)
        imgs = load_images(jp, size=512, verbose=False)
        pairs = make_pairs(imgs, scene_graph=f"swin-{WINDOW}", prefilter=None,
                           symmetrize=True)
        out = inference(pairs, model, dev, batch_size=1, verbose=False)
        del model
        if dev == "mps":
            torch.mps.empty_cache()

        scene = global_aligner(out, device=dev,
                               mode=GlobalAlignerMode.PointCloudOptimizer)
        # The one line that makes this tier work. See the module docstring.
        scene.norm_pw_scale = False
        loss = scene.compute_global_alignment(init="mst", niter=ALIGN_ITERS,
                                              schedule="cosine", lr=0.01)
        data = {
            "pts": np.stack([p.detach().cpu().numpy() for p in scene.get_pts3d()]),
            "conf": np.stack([c.detach().cpu().numpy() for c in scene.im_conf]),
            "poses": scene.get_im_poses().detach().cpu().numpy(),
            "focals": scene.get_focals().detach().cpu().numpy(),
            "loss": np.asarray(float(loss)),
        }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cached, **data)
    return data | {"from_cache": False, "n_input": len(photos),
                   "n_burst": len(burst)}


def _fibonacci_hemisphere(n: int = 1500) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.c_[np.cos(theta) * np.sin(phi),
                 np.sin(theta) * np.sin(phi), np.cos(phi)]


def find_up(points: np.ndarray, cameras: np.ndarray) -> np.ndarray:
    """Which way is up, when nothing in the reconstruction says so.

    The LiDAR tier gets gravity from ARKit for free. Here there is no such
    thing: the model returns geometry in the first camera's frame, and a room
    measured on a tilted axis is not the room.

    Two facts pin it. A room has two large horizontal surfaces and nothing else
    like them, so the vertical is the direction whose extremes hold the most
    points. And a person photographing a room walks about but does not change
    height, so the vertical is also the direction their camera varies least
    along. Neither is sufficient alone. A cubic room has three axis pairs that
    look equally like floor and ceiling, and the camera test breaks that tie;
    the camera test alone is unstable with only a handful of views.
    """
    best = None
    for v in _fibonacci_hemisphere():
        proj = points @ v
        lo, hi = np.percentile(proj, [1, 99])
        if hi - lo < 0.8:
            continue
        bins = max(int((hi - lo) / 0.03) + 1, 8)
        hist, _ = np.histogram(proj, bins=bins, range=(lo, hi))
        edge = max(1, int(0.5 / 0.03))
        ends = float(hist[:edge].sum() + hist[-edge:].sum()) / len(proj)
        spread = float(np.std(cameras @ v))
        score = ends / (1.0 + 6.0 * spread)
        if best is None or score > best[0]:
            best = (score, v)
    if best is None:
        return np.array([0.0, 1.0, 0.0])
    v = best[1]
    # Point it at the ceiling: most of a room's points sit below head height,
    # so the camera centroid lies above the point centroid along +up.
    if (cameras.mean(axis=0) - points.mean(axis=0)) @ v < 0:
        v = -v
    return v / np.linalg.norm(v)


def _gravity_align(points: np.ndarray, up: np.ndarray) -> np.ndarray:
    z = up / np.linalg.norm(up)
    a = np.array([1.0, 0.0, 0.0]) - z * (np.array([1.0, 0.0, 0.0]) @ z)
    if np.linalg.norm(a) < 1e-6:
        a = np.array([0.0, 1.0, 0.0]) - z * (np.array([0.0, 1.0, 0.0]) @ z)
    a /= np.linalg.norm(a)
    b = np.cross(z, a)
    return points @ np.stack([a, z, b]).T


def _video_frames(video: Path, out_dir: Path, want: int = 60) -> list[Path]:
    """Evenly spaced stills from a clip, written as JPEGs.

    Sampled across the whole clip rather than taken consecutively: neighbouring
    video frames are nearly the same picture, and a pair of them constrains
    almost nothing. What the model needs is baseline, which in a handheld
    walk-around means seconds apart, not frames apart.
    """
    import cv2

    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    idx = np.linspace(0, total - 1, min(want, total)).astype(int)
    made = []
    for i, f in enumerate(idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, img = cap.read()
        if not ok:
            continue
        o = out_dir / f"{i:04d}.jpg"
        cv2.imwrite(str(o), img)
        made.append(o)
    cap.release()
    return made


def load(path: str | Path, tier: str = "A", n_views: int = N_VIEWS,
         use_cache: bool = True) -> Capture:
    """Photographs, or a clip, become a Capture the geometry can measure."""
    path = Path(path)
    tmpdir = None
    if path.is_file() and path.suffix.lower() in {".mov", ".mp4", ".m4v"}:
        tmpdir = tempfile.TemporaryDirectory()
        photos = _video_frames(path, Path(tmpdir.name))
        use_burst = False
    else:
        photos = sorted(p for p in path.rglob("*")
                        if p.suffix.lower() in PHOTO_EXT)
        use_burst = True
    if len(photos) < 3:
        raise ValueError(f"{path}: found {len(photos)} usable frames, need 3")

    r = reconstruct(photos, n_views=n_views, use_cache=use_cache,
                    use_burst=use_burst)
    if tmpdir is not None:
        tmpdir.cleanup()
    if r is None:
        raise ValueError(f"{path}: reconstruction failed")

    P = r["pts"].reshape(-1, 3)
    C = r["conf"].reshape(-1)
    keep = C > np.percentile(C, CONF_PERCENTILE)
    pts = P[keep]
    cams = r["poses"][:, :3, 3]

    up = find_up(pts, cams)
    pts = _gravity_align(pts, up)
    cams_aligned = _gravity_align(cams, up)

    frame = PosedFrame(key="learned", depth=None, confidence=None,
                       K=np.eye(3), T_wc=np.eye(4),
                       depth_source=DepthSource.INFERRED,
                       pose_source=PoseSource.NONE, meta={})
    n_used = int(r["poses"].shape[0])
    return Capture(
        frames=[frame], tier=tier, source=str(path),
        meta={"loaded": n_used, "total_keyframes": int(r["n_input"]),
              "loop_closed": False, "tracking_segments": 1,
              "points": pts, "views": n_used,
              "cameras": cams_aligned,
              "burst_photos": int(r["n_burst"]),
              "align_loss": float(r["loss"]),
              "model": MODEL,
              "from_cache": bool(r.get("from_cache", False)),
              "scale_source": "mast3r_metric_head",
              "scale_lo": 1.0 - INTERVAL_REL, "scale_hi": 1.0 + INTERVAL_REL,
              "sfm_points": len(pts), "sfm_mean_inliers": 0.0,
              "intrinsics_source": "estimated by the aligner"})

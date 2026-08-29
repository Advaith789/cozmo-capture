"""One command per capture.

    python -m cozmo measure myroom/8_28_2026.zip

Tier is detected from the input rather than passed in, so the same command
serves all three.
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path


def detect_tier(path: Path) -> str:
    """Identify the tier from the shape of the input, not from a flag."""
    if path.is_file() and path.suffix.lower() in {".mov", ".mp4", ".m4v"}:
        return "B"
    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            if any(n.startswith("keyframes/") for n in z.namelist()):
                return "C"
        return "A"
    if path.is_dir():
        if (path / "keyframes").is_dir():
            return "C"
        imgs = [p for p in path.rglob("*")
                if p.suffix.lower() in {".jpg", ".jpeg", ".heic", ".heif", ".png"}]
        if imgs:
            return "A"
    raise ValueError(f"{path}: cannot tell which tier this is")


def cmd_measure(args: argparse.Namespace) -> int:
    import numpy as np

    from cozmo.geometry import walls
    from cozmo.geometry.height import _modes, ceiling_height
    from cozmo.ingest import lidar

    path = Path(args.capture)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1

    tier = detect_tier(path)
    print(f"capture   {path.name}")
    print(f"tier      {tier}")

    if tier != "C":
        print(f"\nTier {tier} ingest is not implemented yet — only Tier C runs today.")
        return 2

    t0 = time.time()
    cap = lidar.load(path, max_frames=args.frames)
    print(f"frames    {cap.meta['loaded']} of {cap.meta['total_keyframes']}"
          f"   loop-closed: {cap.meta['loop_closed']}"
          f"   tracking segments: {cap.meta['tracking_segments']}")
    if not cap.meta["loop_closed"]:
        print("          [!] no corrected poses — drift is uncorrected")
    if cap.meta["tracking_segments"] > 1:
        print("          [!] tracking broke mid-capture; poses across the break "
              "share no frame")

    gate = 0.015
    methods = ["pooled", "per_frame", "drift"] if args.ablate else [args.method]
    for m in methods:
        h = ceiling_height(cap, method=m, bootstrap=args.bootstrap,
                           sigma_step=args.sigma_step)
        verdict = "PASS" if h.half_width <= gate else "FAIL"
        print(f"\n{m:<10}       {h}")
        print(f"{'':<10}       gate ≤{gate * 100:.1f} cm → ±{h.half_width * 100:.2f} cm  {verdict}")
        if not args.ablate:
            print(f"provenance       {' | '.join(h.provenance)}")
    # Room dimensions from fitted wall planes.
    pts = np.vstack([lidar.to_world_points(f) for f in cap.frames])
    fy, cy = _modes(pts[:, 1])
    room = walls.detect(pts, fy, cy)
    print(f"\nroom axes        {room.theta_deg:.2f}°   "
          f"orthogonality {abs(room.axis_a @ room.axis_b):.1e}")
    for name, ws in (("A", room.walls_a), ("B", room.walls_b)):
        sp = walls.span(ws)
        detail = (f"{sp:.4f} m ({sp * 39.3701:.1f} in)" if sp
                  else "not enough parallel walls")
        extra = f"   [{len(ws)} planes found]" if len(ws) > 2 else ""
        print(f"  axis {name}         {detail}{extra}")
        for w in ws:
            print(f"{'':<18}plane at {w.offset:+7.3f} m   "
                  f"n={w.n_points:,}   planarity {w.residual_cm:.2f} cm")

    print(f"\nelapsed          {time.time() - t0:.1f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cozmo")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="measure a capture")
    m.add_argument("capture")
    m.add_argument("--frames", type=int, default=60,
                   help="max keyframes to load (default 60)")
    m.add_argument("--bootstrap", type=int, default=200)
    m.add_argument("--method", default="drift",
                   choices=["pooled", "per_frame", "drift"])
    m.add_argument("--sigma-step", dest="sigma_step", type=float, default=0.002,
                   help="metres of drift allowed between keyframes; "
                        "near-zero reproduces the uncorrected case")
    m.add_argument("--ablate", action="store_true",
                   help="run all three methods for the drift ablation")
    m.set_defaults(func=cmd_measure)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

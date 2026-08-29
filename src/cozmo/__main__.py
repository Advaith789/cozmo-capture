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


MESH_EXT = {".obj", ".ply"}


def detect_tier(path: Path) -> str:
    """Identify the tier from the shape of the input, not from a flag.

    "M" is the mesh fallback: a Polycam export taken without Developer Mode,
    which has no raw data but still carries the surfaces we measure.
    """
    if path.is_file() and path.suffix.lower() in MESH_EXT:
        return "M"
    if path.is_file() and path.suffix.lower() in {".mov", ".mp4", ".m4v"}:
        return "B"
    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if any(n.startswith("keyframes/") for n in names):
                return "C"
            if any(n.lower().endswith((".obj", ".ply")) for n in names):
                return "M"
        return "A"
    if path.is_dir():
        if (path / "keyframes").is_dir():
            return "C"
        if any(p.suffix.lower() in MESH_EXT for p in path.rglob("*")):
            return "M"
        if any(p.suffix.lower() in {".mov", ".mp4", ".m4v"} for p in path.rglob("*")):
            return "B"
        if any(p.suffix.lower() in {".jpg", ".jpeg", ".heic", ".heif", ".png"}
               for p in path.rglob("*")):
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
        print(f"\nTier {tier} ingest is not implemented yet — only Tier C runs in the measure subcommand; use run.")
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
    if tier == "C":
        pts = np.vstack([lidar.to_world_points(f) for f in cap.frames])
    else:
        pts = cap.meta["points"]
    if tier in ("C", "M"):
        fy, cy = _modes(pts[:, 1])
    else:
        # A sparse reconstruction puts points where there is texture, which is
        # furniture and posters, not blank ceilings. There is no dense band for
        # a mode to find, so the extremes of the cloud stand in for the two
        # surfaces, trimmed to shed stray triangulations.
        fy, cy = (float(np.percentile(pts[:, 1], 1.0)),
                  float(np.percentile(pts[:, 1], 99.0)))
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


def cmd_run(args: argparse.Namespace) -> int:
    """One command per capture: raw export in, JSON contract and plan out."""
    path = Path(args.capture)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1

    try:
        tier = detect_tier(path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("       expected a Polycam raw export (.zip or folder with "
              "keyframes/), a photo folder, or a video file.", file=sys.stderr)
        return 1

    print(f"capture   {path.name}\ntier      {tier}")
    try:
        import numpy as np

        from cozmo.contract import render, schema
        from cozmo.geometry import room as room_mod
        from cozmo.geometry import openings as openings_mod
        from cozmo.geometry import walls
        from cozmo.geometry.height import _modes, ceiling_height
        from cozmo.ingest import camera, lidar, mesh
    except ImportError as exc:
        print(f"error: the pipeline needs its dependencies: {exc}", file=sys.stderr)
        print("       python3 -m venv .venv && .venv/bin/pip install -r "
              "requirements.txt", file=sys.stderr)
        return 1

    t0 = time.time()
    try:
        if tier == "C":
            cap = lidar.load(path, max_frames=args.frames)
        elif tier == "M":
            cap = mesh.load(path)
        elif tier == "B":
            cap = camera.load_video(path)
        else:
            cap = camera.load_photos(path)
    except Exception as exc:
        print(f"error: could not read {path.name}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        print("       the archive may be truncated or still copying. "
              "Re-export and try again.", file=sys.stderr)
        return 1
    print(f"frames    {cap.meta['loaded']} of {cap.meta['total_keyframes']}")

    try:
        method = args.height_method if tier in ("C", "M") else "sparse"
        height = ceiling_height(cap, method=method,
                                bootstrap=args.bootstrap,
                                sigma_step=args.sigma_step)
    except Exception as exc:
        print(f"error: could not measure ceiling height: {exc}", file=sys.stderr)
        print("       the capture may not show enough floor and ceiling. "
              "Re-scan tilting up and down at each corner.", file=sys.stderr)
        return 3
    if tier == "C":
        pts = np.vstack([lidar.to_world_points(f) for f in cap.frames])
    else:
        pts = cap.meta["points"]
    if tier in ("C", "M"):
        fy, cy = _modes(pts[:, 1])
    else:
        # A sparse reconstruction puts points where there is texture, which is
        # furniture and posters, not blank ceilings. There is no dense band for
        # a mode to find, so the extremes of the cloud stand in for the two
        # surfaces, trimmed to shed stray triangulations.
        fy, cy = (float(np.percentile(pts[:, 1], 1.0)),
                  float(np.percentile(pts[:, 1], 99.0)))
    axes = walls.detect(pts, fy, cy)

    # Resample frames and re-detect, so the room's intervals carry the same
    # pose disagreement the ceiling interval does rather than an assumed value.
    if tier == "C":
        clouds = [c for c in (lidar.to_world_points(f) for f in cap.frames)
                  if len(c)]
        rng = np.random.default_rng(0)
        draws = []
        print(f"bootstrap {args.wall_draws} wall refits", end="", flush=True)
        for _ in range(args.wall_draws):
            pick = rng.integers(0, len(clouds), len(clouds))
            sub = np.vstack([clouds[i] for i in pick])
            d = walls.refit(axes, sub, fy, cy)
            if d is not None:
                draws.append(d)
            print(".", end="", flush=True)
        print()
    else:
        # On the camera tiers the scale comes from a prior on how high the
        # operator held the phone, and its spread swamps every other source of
        # error. Resampling points would report a tighter interval than the
        # scale itself justifies, so the interval is the prior, propagated.
        clouds = [pts]
        draws = []
        rng = np.random.default_rng(0)
        for s_factor in np.linspace(cap.meta["scale_lo"], cap.meta["scale_hi"], 24):
            d = walls.refit(axes, pts * s_factor, fy * s_factor, cy * s_factor)
            if d is not None:
                draws.append(d)

    rm = room_mod.build(axes, height, name=args.name, draws=draws)
    if rm is not None:
        stable = openings_mod.find_stable(clouds, rm.walls, fy, cy,
                                          draws=max(6, args.wall_draws // 6))
        rm.openings.extend((i, o) for i, o, _, _ in stable)
        rm.opening_ci.extend((lo, hi) for _, _, lo, hi in stable)
    if rm is None:
        print("error: could not close a room polygon from the detected walls",
              file=sys.stderr)
        return 3

    truth_walls = None
    if args.truth_walls:
        truth_walls = [float(x) for x in args.truth_walls.split(",")]
        if len(truth_walls) != 2:
            print("error: --truth-walls needs two values, one per wall pair",
                  file=sys.stderr)
            return 4

    gates = [
        schema.gate("ceiling_height", rm.ceiling_height, 0.015,
                    truth=args.truth_height),
        # Opposite edges of the polygon are the same physical wall pair, so a
        # single tape reading scores both.
        *[schema.gate(f"wall_length_{i}", m, 0.015,
                      truth=(truth_walls[i % 2] if truth_walls else None))
          for i, m in enumerate(rm.wall_lengths)],
    ]
    notes = [
        "Opening detection is EXPERIMENTAL and is not claimed against the "
        "opening-width gate: widths vary by up to a factor of two across "
        "frame counts, against a 2 cm gate.",
        "Damage regions not implemented.",
        "Single-room capture: no stitched multi-room plan or adjacency.",
        "Tiers A and B ingest not implemented.",
    ]

    out = Path(args.out)
    doc = schema.build(cap, [rm], gates=gates, notes=notes)
    jpath = schema.write(doc, out / f"{args.name}.json")
    spath = render.write(rm, out / f"{args.name}.svg", title=args.name)

    print(f"\nfloor area       {rm.floor_area}")
    print(f"perimeter        {rm.perimeter}")
    print(f"ceiling height   {rm.ceiling_height}")
    for i, m in enumerate(rm.wall_lengths):
        print(f"  wall {i}         {m}")
    if rm.openings:
        print(f"\nopenings         {len(rm.openings)} found  (EXPERIMENTAL, gate not claimed)")
        for k, (idx, o) in enumerate(rm.openings):
            lo, hi = rm.opening_ci[k] if k < len(rm.opening_ci) else (o.width, o.width)
            print(f"  wall {idx}          {o.kind:<6} width {o.width:.3f} m "
                  f"[{lo:.3f}, {hi:.3f}]  ({o.width * 39.3701:.1f} in)")

    print("\ngates")
    for g in gates:
        acc = (f"  accuracy {g['error_m'] * 100:+.1f} cm "
               f"{'PASS' if g['accuracy_pass'] else 'FAIL'}"
               if "error_m" in g else "  accuracy unscored (no ground truth)")
        print(f"  {g['gate']:<18} precision ±{g['interval_half_width_m'] * 100:5.2f} cm "
              f"{'PASS' if g['precision_pass'] else 'FAIL'}{acc}")

    print(f"\nwrote  {jpath}\n       {spath}")
    print(f"elapsed          {time.time() - t0:.1f}s")
    return 0


def _drift_median_cm(path: Path) -> float | None:
    """Median distance the pose optimiser moved each camera, in centimetres.

    Reads only the two camera folders, so it stays fast enough for a check that
    has to answer while someone is still standing in the room.
    """
    import json
    import math
    import zipfile

    try:
        if zipfile.is_zipfile(path):
            z = zipfile.ZipFile(path)
            names = z.namelist()
            read = z.read
        else:
            names = [str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()]
            read = lambda n: (path / n).read_bytes()  # noqa: E731

        raw = sorted(n for n in names if n.startswith("keyframes/cameras/"))
        cor = {Path(n).stem for n in names
               if n.startswith("keyframes/corrected_cameras/")}
        if not raw or not cor:
            return None
        step = max(1, len(raw) // 40)
        deltas = []
        for n in raw[::step]:
            stem = Path(n).stem
            if stem not in cor:
                continue
            a = json.loads(read(n))
            b = json.loads(read(f"keyframes/corrected_cameras/{stem}.json"))
            deltas.append(math.dist([a[f"t_{i}3"] for i in range(3)],
                                    [b[f"t_{i}3"] for i in range(3)]))
        if len(deltas) < 5:
            return None
        deltas.sort()
        return deltas[len(deltas) // 2] * 100
    except Exception:
        return None


def cmd_check(args: argparse.Namespace) -> int:
    """Go or no-go on a capture, in seconds, before committing to a full run.

    Exists for the walk-in test. If a capture is unusable you want to know while
    the operator is still standing in the room, not after a full run in front of
    an audience. Reads only metadata and a handful of frames.
    """
    path = Path(args.capture)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    try:
        tier = detect_tier(path)
    except ValueError as exc:
        print(f"NO GO   {exc}", file=sys.stderr)
        return 1

    print(f"capture   {path.name}\ntier      {tier}")
    if tier == "M":
        print("\nGO (fallback)  no raw export, so Developer Mode was off. The "
              "mesh still measures\n               to within about a "
              "centimetre, but intervals are assumed rather\n               "
              "than resampled. Prefer a raw export if you can re-capture.")
        return 0
    if tier != "C":
        print("\nNO GO     only the LiDAR tier measures reliably. Ask for a "
              "Polycam Space capture with Developer Mode on.")
        return 2

    try:
        from cozmo.ingest import lidar
        cap = lidar.load(path, max_frames=12)
    except Exception as exc:
        print(f"\nNO GO     cannot read this capture: {exc}", file=sys.stderr)
        return 1

    total = cap.meta["total_keyframes"]
    problems, warnings = [], []

    if not cap.meta["loop_closed"]:
        problems.append("no corrected poses: the scan was too long or was not "
                        "processed. Re-scan in under 7 minutes and let it finish.")
    if cap.meta["tracking_segments"] > 1:
        problems.append(f"tracking broke {cap.meta['tracking_segments'] - 1} time(s): "
                        "poses either side share no frame. Re-scan without "
                        "covering the lens or moving too fast.")
    if total < 60:
        problems.append(f"only {total} keyframes: too few to measure. Walk the "
                        "perimeter more slowly.")
    elif total < 120:
        warnings.append(f"{total} keyframes is on the thin side; 150+ is better.")

    # The strongest signal of a bad capture, and it costs only JSON reads:
    # how far the optimiser had to move each camera. On the benchmark's
    # non-compliant scan this was 5.3 cm median against 0.9 cm for a scan that
    # followed the protocol, and it is what separated the two.
    drift = _drift_median_cm(path)
    if drift is not None:
        print(f"drift     {drift:.1f} cm median correction")
        if drift > 4.0:
            problems.append(f"{drift:.1f} cm of drift: the walk did not give the "
                            "optimiser enough to work with. Walk the perimeter "
                            "with the wall on your right and pause at corners.")
        elif drift > 2.0:
            warnings.append(f"{drift:.1f} cm of drift is high; under 1 cm is "
                            "what a compliant capture gives.")

    isos = [f.meta["iso"] for f in cap.frames if "iso" in f.meta]
    if isos and sorted(isos)[len(isos) // 2] >= 1600:
        warnings.append("room is underlit: LiDAR copes, but tracking is weaker. "
                        "Turn on every light if you can.")

    spins = [f.meta["angular_velocity"] for f in cap.frames
             if "angular_velocity" in f.meta]
    if spins and sum(x > 1.0 for x in spins) / len(spins) > 0.3:
        warnings.append("a lot of fast panning; sweep more slowly next time.")

    print(f"frames    {total} keyframes, loop-closed: {cap.meta['loop_closed']}")
    for w in warnings:
        print(f"  warn    {w}")
    for p_ in problems:
        print(f"  STOP    {p_}")

    if problems:
        print("\nNO GO     re-capture before running the pipeline.")
        return 3
    print(f"\nGO        run:  python -m cozmo run \"{path}\" --name <room>")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cozmo")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="full pipeline: capture in, contract out",
                       description="Read a capture, measure the room, write a "
                                   "JSON contract and a dimensioned SVG plan.")
    r.add_argument("capture", help="Polycam raw export (.zip or folder), "
                                   "photo folder, or video file")
    r.add_argument("--out", default="out", help="output directory (default: out)")
    # Defaults are the settings every number in the benchmark report was
    # produced at. Typing the bare command on the day must reproduce the
    # quality the report claims, not something looser.
    r.add_argument("--frames", type=int, default=160,
                   help="keyframes to load; the benchmark used 160")
    r.add_argument("--bootstrap", type=int, default=40,
                   help="resamples for the ceiling interval")
    r.add_argument("--sigma-step", dest="sigma_step", type=float, default=0.002,
                   help="drift correction strength, metres per keyframe; "
                        "near zero reproduces the uncorrected case")
    r.add_argument("--name", default="room",
                   help="name for the room and the output files")
    r.add_argument("--height-method", dest="height_method", default="envelope",
                   choices=["envelope", "drift", "per_frame", "pooled"],
                   help="ceiling estimator; the last three are kept for the "
                        "fix-loop ablation")
    r.add_argument("--wall-draws", dest="wall_draws", type=int, default=50,
                   help="bootstrap resamples for the room's intervals")
    r.add_argument("--truth-walls", dest="truth_walls", default=None,
                   help="two tape wall lengths in metres, comma separated, "
                        "one per opposing pair")
    r.add_argument("--truth-height", dest="truth_height", type=float, default=None,
                   help="tape/laser ceiling height in metres, for gate scoring")
    r.set_defaults(func=cmd_run)

    ck = sub.add_parser("check", help="fast go/no-go on a capture before running")
    ck.add_argument("capture", help="the capture to sanity check")
    ck.set_defaults(func=cmd_check)

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

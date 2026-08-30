"""One command per capture.

    cozmo measure myroom/8_28_2026.zip

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


def _photo_height_only(path: Path, args: argparse.Namespace) -> int:
    """Tier A: ceiling height only, measured photo by photo.

    Wall geometry needs photographs joined into one reconstruction and eight
    wide-baseline stills cannot be joined, so this reports the one dimension a
    single photograph can carry and says plainly that it has nothing else.
    """
    from cozmo.ingest import camera

    print("\nTier A measures ceiling height only. Wall lengths need the photos")
    print("joined into one reconstruction, which eight wide-baseline stills")
    print("cannot support: COLMAP registered 4 of our 29.")

    # Rung one: metric depth per photo. Best when it works, and it needs a
    # floor it can find.
    heights = camera.photo_ceiling_heights(path)
    if len(heights) >= 3:
        import statistics
        med = statistics.median(heights)
        rel = camera.PHOTO_HEIGHT_REL
        source = "metric depth model, per photo median"
        prov = ("depth:inferred | pose:none | scale:metric_depth_model | "
                "method:per_photo_median | interval:cross_room_spread_±30pct")
        extra = f"photo spread     {max(heights) - min(heights):.2f} m"
        used = len(heights)
    else:
        # Rung two: ask a vision model. Weaker, and labelled as such.
        from cozmo.ingest import llm
        print(f"\nmetric depth found a floor in only {len(heights)} photo(s); "
              f"falling back to a vision model estimate.")
        if not llm.available():
            print("\nerror: no fallback available. Set OPENAI_API_KEY in .env, "
                  "or re-shoot with the floor visible in each photo.",
                  file=sys.stderr)
            return 3
        photos = sorted(p for p in path.rglob("*")
                        if p.suffix.lower() in {".heic", ".heif", ".jpg", ".jpeg"})
        agg, ests = llm.estimate_room(photos)
        if not agg:
            print("\nerror: the fallback returned nothing.", file=sys.stderr)
            return 3
        med = agg["ceiling_height_m"]
        rel = agg["interval_rel"]
        source = f"vision model estimate ({agg['model']})"
        prov = (f"depth:llm_estimate | pose:none | scale:model_prior | "
                f"method:{agg['prompt_version']} | "
                f"cached:{agg['all_cached']} | interval:observed_error_±35pct")
        extra = (f"also estimated    {agg['width_m']:.2f} x {agg['length_m']:.2f} m "
                 f"floor, NOT measured")
        used = agg["photos_used"]
        print(f"\n[!] This is an estimate from a language model, not a "
              f"measurement.\n    It reasons from door heights and typical "
              f"room sizes. On rooms where\n    we hold tape it came out "
              f"between 34% low and 15% high.")

    print(f"\nphotos used      {used}")
    print(f"source           {source}")
    print(f"ceiling height   {med:.3f} m  [{med * (1 - rel):.3f}, "
          f"{med * (1 + rel):.3f}]  (±{rel * 100:.0f}%)")
    print(f"{extra}")
    print(f"provenance       {prov}")
    if args.truth_height:
        err = (med - args.truth_height) * 100
        print(f"\naccuracy         {err:+.1f} cm vs tape "
              f"({(med / args.truth_height - 1) * 100:+.1f}%)   "
              f"{'PASS' if abs(err) / 100 / args.truth_height <= 0.08 else 'fail'} "
              f"against the photo tier's ±8% gate")
    print("\nNo wall lengths, no floor area, no plan: one dimension only.")
    return 0


def _cameras_fit(room, cameras, margin: float = 0.35) -> bool:
    """Whether every camera stands inside the room it reconstructed.

    A sanity check the LiDAR tier never needs and the photo tiers very much do.
    It is not a tolerance to tune: a photographer outside their own room is not
    a small error, it is a broken reconstruction.
    """
    import numpy as np

    poly = room.corners
    if poly is None or len(poly) < 3:
        return False
    xz = np.asarray(cameras)[:, [0, 2]]
    cx, cz = poly[:, 0], poly[:, 1]
    inside = np.zeros(len(xz), dtype=bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        cond = ((cz[i] > xz[:, 1]) != (cz[j] > xz[:, 1])) & (
            xz[:, 0] < (cx[j] - cx[i]) * (xz[:, 1] - cz[i])
            / (cz[j] - cz[i] + 1e-12) + cx[i])
        inside ^= cond
        j = i
    # The room must also be at least as big as the ground the operator covered.
    walked = float(np.ptp(xz, axis=0).max())
    biggest = max(m.value for m in room.wall_lengths) if room.wall_lengths else 0.0
    return bool(inside.mean() >= 0.8 and biggest >= walked + margin)


def _height_only(cap, height, args, tier: str, path: Path, t0: float) -> int:
    """Tiers A and B when the walls do not close a room.

    Reported as a partial result with the one dimension that is sound, rather
    than as a failure, because ceiling height from a photo reconstruction is a
    real measurement and a surveyor can use it.
    """
    import json
    from datetime import datetime, timezone

    print("\n[!] The reconstruction did not recover two opposing wall pairs, "
          "so no\n    room polygon closes. Ceiling height is reported; wall "
          "lengths, floor\n    area and the plan are not available from this "
          "capture.")
    print(f"\nceiling height   {height}")
    print(f"provenance       {' | '.join(height.provenance)}")
    if args.truth_height:
        err = (height.value - args.truth_height) * 100
        rel = height.value / args.truth_height - 1
        # The brief sets the tiers apart: photos within 8%, video within 3%.
        # Video is the tighter gate because a clip carries far more frames of
        # the same room than eight stills ever can.
        limit = 0.03 if tier == "B" else 0.08
        print(f"accuracy         {err:+.1f} cm vs tape ({rel:+.1%})   "
              f"{'PASS' if abs(rel) <= limit else 'fail'} against the "
              f"{'video' if tier == 'B' else 'photo'} tier's "
              f"±{limit * 100:.0f}% gate")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": "cozmo-plan/0.2",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capture": {"source": path.name, "tier": tier,
                    "frames_used": cap.meta.get("loaded"),
                    "frames_total": cap.meta.get("total_keyframes")},
        "rooms": [],
        "partial": {
            "ceiling_height_m": round(height.value, 4),
            "ci_low": round(height.lo, 4), "ci_high": round(height.hi, 4),
            "provenance": height.provenance,
        },
        "known_limitations": [
            "No room polygon: the reconstruction recovered fewer than two "
            "opposing wall pairs, so wall lengths, floor area and the plan "
            "cannot be produced from this capture.",
            "Ceiling height only, from a learned multi-view reconstruction.",
        ],
    }
    jpath = out / f"{args.name}.json"
    jpath.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote  {jpath}")
    print(f"elapsed          {time.time() - t0:.1f}s")
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

        from cozmo.contract import render, schema, scope
        from cozmo.geometry import concealed
        from cozmo.geometry import damage as damage_mod
        from cozmo.geometry import room as room_mod
        from cozmo.geometry import openings as openings_mod
        from cozmo.geometry import spaces as spaces_mod
        from cozmo.geometry import walls
        from cozmo.geometry.height import _modes, ceiling_height
        from cozmo.ingest import camera, lidar, mesh
    except ImportError as exc:
        print(f"error: the pipeline needs its dependencies: {exc}", file=sys.stderr)
        print("       python3 -m venv .venv && .venv/bin/pip install -r "
              "requirements.txt", file=sys.stderr)
        return 1

    t0 = time.time()
    # Tiers A and B go through the learned multi-view model where it is
    # installed. It is the only thing that reconstructs these rooms at all:
    # classical matching registered 4 photographs of 29 on blank bedroom walls.
    learned_mod = None
    if tier in ("A", "B") and not args.no_learned:
        from cozmo.ingest import learned as learned_mod
        if not learned_mod.available():
            print("\n[!] the learned tier is not installed "
                  "(see scripts/setup_learned.sh);")
            print("    falling back to per-photo metric depth.")
            learned_mod = None

    try:
        if tier == "C":
            cap = lidar.load(path, max_frames=args.frames)
        elif tier == "M":
            cap = mesh.load(path)
        elif learned_mod is not None:
            print(f"model     {learned_mod.MODEL.split('/')[-1]}")
            cap = learned_mod.load(path, tier=tier, n_views=args.views)
            print(f"views     {cap.meta['loaded']} from a burst of "
                  f"{cap.meta['burst_photos']}"
                  f"{'  (cached)' if cap.meta['from_cache'] else ''}")
        elif tier == "B":
            cap = camera.load_video(path)
        else:
            return _photo_height_only(path, args)
    except Exception as exc:
        print(f"error: could not read {path.name}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        print("       the archive may be truncated or still copying. "
              "Re-export and try again.", file=sys.stderr)
        return 1
    print(f"frames    {cap.meta['loaded']} of {cap.meta['total_keyframes']}")

    try:
        # The learned tier returns a dense pointmap, not a sparse feature
        # cloud, so it has real floor and ceiling bands for the envelope
        # estimator to find. Measured on my room: sparse read 17.7% low
        # because a tail quantile cuts the ceiling off when a tenth of the
        # points are up there; envelope read 9.6% low on the same cloud.
        if tier in ("C", "M"):
            method = args.height_method
        elif cap.meta.get("model"):
            method = "learned"      # a photo reconstruction, see _learned_separation
        else:
            method = "sparse"
        height = ceiling_height(cap, method=method,
                                bootstrap=args.bootstrap,
                                sigma_step=args.sigma_step)
    except Exception as exc:
        print(f"error: could not measure ceiling height: {exc}", file=sys.stderr)
        print("       the capture may not show enough floor and ceiling. "
              "Re-scan tilting up and down at each corner.", file=sys.stderr)
        return 3
    if tier == "C":
        # Back-project every frame exactly once. The world points, the camera
        # each was seen from, and the stacked cloud are all wanted downstream,
        # and re-deriving them separately was doing this twice over 160 frames.
        graded = [(lidar.to_world_graded(f), f.T_wc[:3, 3]) for f in cap.frames]
        # Strict for geometry, permissive for openings. See to_world_graded.
        views_all = [(p[(c >= 2) & (z <= 5.0)], ctr)
                     for (p, c, z), ctr in graded]
        views_all = [(p, ctr) for p, ctr in views_all if len(p)]
        views_open = [(p[c >= 1], ctr) for (p, c, z), ctr in graded]
        views_open = [(p, ctr) for p, ctr in views_open if len(p) > 200]
        clouds = [c for c, _ in views_all]
        pts = np.vstack(clouds) if clouds else np.empty((0, 3))
    else:
        views_all = []
        views_open = []
        clouds = [cap.meta["points"]]
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
    # Carve the capture into rooms before measuring anything. A capture that
    # covers two rooms fits one rectangle across both and reports dimensions
    # that belong to no real room, so the split has to happen first.
    seg = spaces_mod.segment(pts, fy)
    multi = seg.count > 1
    if multi:
        print(f"spaces    {seg.count} rooms, {len(seg.doorways)} doorway(s)")
        for d in seg.doorways:
            print(f"  doorway   rooms {d.room_a}-{d.room_b}   clear width "
                  f"{d.width_m:.3f} m  [{d.lo:.3f}, {d.hi:.3f}]")

    rooms = []
    for sp in seg.spaces:
        spts = sp.points if multi else pts
        ax = walls.detect(spts, fy, cy)
        if ax is None:
            continue
        # Work out once which of each frame's points belong to this room. The
        # bootstrap and the opening detector both need it, and asking twice
        # meant gridding every frame twice per room.
        if multi:
            masks = [seg.assign(c) == sp.index for c in clouds]
            rc = [c[m] for c, m in zip(clouds, masks) if m.sum() > 200]
            om = [seg.assign(c) == sp.index for c, _ in views_open]
            rv = [(c[m], ctr) for (c, ctr), m in zip(views_open, om)
                  if m.sum() > 200]
        else:
            rc = [c for c in clouds if len(c) > 200]
            rv = list(views_open)

        # Resample frames and re-detect, so the room's intervals carry the same
        # pose disagreement the ceiling interval does rather than an assumed
        # value.
        draws = []
        if tier == "C" and rc:
            rng = np.random.default_rng(0)
            tag = f" room {sp.index}" if multi else ""
            print(f"bootstrap {args.wall_draws} wall refits{tag}",
                  end="", flush=True)
            for _ in range(args.wall_draws):
                pick = rng.integers(0, len(rc), len(rc))
                d = walls.refit(ax, np.vstack([rc[i] for i in pick]), fy, cy)
                if d is not None:
                    draws.append(d)
                print(".", end="", flush=True)
            print()
        elif tier != "C":
            # On the camera tiers the scale comes from a prior on how high the
            # operator held the phone, and its spread swamps every other source
            # of error. Resampling points would report a tighter interval than
            # the scale itself justifies, so the interval is the prior,
            # propagated.
            draws = [walls.scaled(ax, f) for f in
                     np.linspace(cap.meta["scale_lo"], cap.meta["scale_hi"], 24)]

        nm = f"{args.name}-room{sp.index}" if multi else args.name
        r = room_mod.build(ax, height, name=nm, draws=draws)
        if r is None:
            continue
        if rv:
            for wi, w in enumerate(r.walls):
                for o in openings_mod.find_raytraced(rv, w, fy, cy):
                    r.openings.append((wi, o))
                    # A cell counts as seen through if any ray crossed it, so
                    # both edges round outward: the same one-cell quantisation
                    # the doorway widths carry.
                    r.opening_ci.append((round(o.width - openings_mod.RT_CELL, 3),
                                         round(o.width + openings_mod.RT_CELL, 3)))
        elif rc:
            stable = openings_mod.find_stable(rc, r.walls, fy, cy,
                                              draws=max(6, args.wall_draws // 6))
            r.openings.extend((i, o) for i, o, _, _ in stable)
            r.opening_ci.extend((lo, hi) for _, _, lo, hi in stable)
        rooms.append(r)

    # A photo reconstruction can close a polygon that is simply wrong, and a
    # confidently wrong room is worse than none. The photographer stood inside
    # the room, so every camera must fall within the walls it reports: on the
    # burst where the geometry collapsed, the walls came back at 1.16 and
    # 1.88 m while the camera path alone spanned 1.2 m, which is impossible.
    if rooms and tier in ("A", "B") and cap.meta.get("cameras") is not None:
        kept = [r for r in rooms if _cameras_fit(r, cap.meta["cameras"])]
        if not kept:
            print("\n[!] The reconstructed walls do not enclose the camera "
                  "positions, so\n    the room geometry is wrong however "
                  "neatly it closed. Discarded.")
        rooms = kept

    if multi and len(rooms) < seg.count:
        print(f"          {seg.count - len(rooms)} of {seg.count} spaces did "
              f"not close a polygon and are not reported;")
        print(f"          they are usually too small or seen from too few "
              f"angles to fit two opposing walls.")

    if not rooms:
        if tier in ("A", "B"):
            # A photo reconstruction often recovers some walls but not two
            # opposing pairs, and a room needs both to close. Ceiling height
            # survives that, because it needs only the floor and the ceiling,
            # so it is reported rather than thrown away.
            return _height_only(cap, height, args, tier, path, t0)
        print("error: could not close a room polygon from the detected walls",
              file=sys.stderr)
        return 3
    rm = rooms[0]

    truth_walls = None
    if args.truth_walls:
        truth_walls = [float(x) for x in args.truth_walls.split(",")]
        if len(truth_walls) != 2:
            print("error: --truth-walls needs two values, one per wall pair",
                  file=sys.stderr)
            return 4

    if multi:
        from dataclasses import replace as _replace
        line_items = [_replace(li, surface=f"{r.name}:{li.surface}")
                      for r in rooms for li in scope.build(r)]
    else:
        line_items = scope.build(rm)
    surface_m2 = sum(2 * r.floor_area.value
                     + r.perimeter.value * r.ceiling_height.value
                     for r in rooms)
    flags = (concealed.detect(cap.frames, fy, cy, room_surface_m2=surface_m2)
             if tier == "C" else [])

    # Damage detection is opt in and stays that way. It is a real detector
    # with a real measured failure rate: on a clean control room with nothing
    # wrong with it, it reported 79 regions. Shipping that on by default would
    # bury a true finding in noise, and the brief scores a phantom as harshly
    # as a miss. Kept reachable and documented rather than deleted, because a
    # measured negative result is worth more than a missing one.
    marks = []
    if args.damage and tier == "C":
        marks = damage_mod.detect(cap.frames)
        print(f"\ndamage regions   {len(marks)}  (EXPERIMENTAL, opt-in, "
              f"not claimed against any gate)")
        for m in marks[:12]:
            print(f"  [{m.kind}] {m.width_cm:.1f} x {m.height_cm:.1f} cm  "
                  f"seen in {m.seen_in} frames  conf {m.confidence:.2f}")
        if len(marks) > 12:
            print(f"  ... and {len(marks) - 12} more")

    print(f"\nscope line items")
    for li in line_items:
        print(f"  {li.surface:<10} {li.item:<28} {li.quantity:8.2f} {li.unit}"
              f"  [{li.lo:.2f}, {li.hi:.2f}]")
    if flags:
        print(f"\nconcealed-condition flags   {len(flags)}")
        for fl in flags:
            print(f"  [{fl.severity}] {fl.rule}")
            print(f"      {fl.finding}")

    gates = [
        schema.gate("ceiling_height", rm.ceiling_height, 0.015,
                    truth=args.truth_height),
        # Opposite edges of the polygon are the same physical wall pair, so a
        # single tape reading scores both.
        *[schema.gate(f"wall_length_{i}", m, 0.015,
                      truth=(truth_walls[i % 2] if truth_walls else None))
          for i, m in enumerate(rm.wall_lengths)],
    ]
    notes = ([
        f"This capture covers {seg.count} spaces. They were segmented and "
        f"measured separately; dimensions below are per room, and the gates "
        f"are scored against room 1.",
        "Doorway widths come from an occupancy grid and carry a one-cell "
        "interval; they are not claimed against the opening-width gate."]
        if multi else []) + [
        "Opening detection is EXPERIMENTAL and is not claimed against the "
        "opening-width gate. It measures the clear opening the sensor could "
        "see through at capture time, which equals the frame width only if "
        "the door stood fully open. On the one doorway we hold a tape for it "
        "read 0.587 m against a 0.958 m frame, and a partly open door and a "
        "measurement error are not separable without a controlled re-capture. "
        "The interval quoted is the precision of the see-through measurement, "
        "not the uncertainty in the frame width.",
        ("Damage detection is opt-in via --damage and is not claimed against "
         "any gate: it reported 79 regions on a clean control room."
         if not args.damage else
         "Damage regions below are EXPERIMENTAL: the detector reported 79 "
         "regions on a clean control room, so treat every one as a candidate "
         "for a human to confirm."),
    ] + ([] if multi else
         ["Single-room capture: one room, so no adjacency to report."])

    out = Path(args.out)
    doc = schema.build(cap, rooms, gates=gates, notes=notes,
                       scope_items=scope.to_json(line_items),
                       concealed=concealed.to_json(flags),
                       stitched=spaces_mod.to_json(seg) if multi else None,
                       damage=damage_mod.to_json(marks) if args.damage else None)
    jpath = schema.write(doc, out / f"{args.name}.json")
    svgs = [render.write(r, out / f"{r.name}.svg", title=r.name) for r in rooms]
    spath = svgs[0]

    for r in rooms:
        if multi:
            print(f"\n{r.name}")
        print(f"\nfloor area       {r.floor_area}")
        print(f"perimeter        {r.perimeter}")
        print(f"ceiling height   {r.ceiling_height}")
        for i, m in enumerate(r.wall_lengths):
            print(f"  wall {i}         {m}")
    if rm.openings:
        print(f"\nopenings         {len(rm.openings)} found  (EXPERIMENTAL, "
              f"clear opening not frame width, gate not claimed)")
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

    print(f"\nwrote  {jpath}")
    for sv in svgs:
        print(f"       {sv}")
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
    print(f"\nGO        run:  cozmo run \"{path}\" --name <room>")
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
    r.add_argument("--damage", action="store_true",
                   help="run the opt-in damage detector (Tier C only). It "
                        "over-fires: 79 regions on a clean control room, so "
                        "it is off by default and claimed against no gate.")
    r.add_argument("--views", type=int, default=12,
                   help="frames the learned tier reconstructs from "
                        "(tiers A and B; default: 12)")
    r.add_argument("--no-learned", dest="no_learned", action="store_true",
                   help="skip the learned multi-view model on tiers A and B "
                        "and fall back to per-photo metric depth")
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

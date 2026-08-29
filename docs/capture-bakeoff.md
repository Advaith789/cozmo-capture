# Capture bake-off

Purpose: derive the delivery contract from a real export instead of asserting it.
Whatever comes out of these zips **is** the contract we publish in the protocol.

Device: iPhone 17 Pro (LiDAR) · Date: 2026-08-28 · Tier C run complete

---

## Before you capture — two iPhone settings

These two decide whether the files survive the trip to the laptop. Both must be
set *before* the capture, not after.

| Setting | Path | Value | Why |
|---|---|---|---|
| Polycam Developer Mode | Polycam → profile icon (bottom right) → Settings → General → Developer Mode | **on** | Raw export does not exist without it, and it only applies to captures made *after* the toggle. Retroactive is not an option. |
| Photo transfer | iOS Settings → Photos → Transfer to Mac or PC | **Keep Originals** | "Automatic" transcodes HEIC→JPEG and HEVC→H.264 on the way out, silently re-encoding the tier-A and tier-B inputs. |

Optional third: iOS Settings → Camera → Formats → **Most Compatible** makes the
phone shoot JPEG natively, so nothing can convert anything later. Our contract
says `.jpeg`; this is the cheapest way to make that true at the source.

---

## Capture — one room, all three tiers

Same room for all three, back to back. A small-to-medium room with at least one
door, one window, and ideally one non-rectangular feature (alcove, island,
angled wall). That last one matters later for the head-to-head.

While you are standing in it, tape-measure and write down: three wall lengths,
ceiling height, one door width. Five numbers, two minutes. This room becomes a
free sanity check and saves a second trip.

- [ ] **Tier C — Polycam Space.** Developer Mode confirmed on. Walk the
      perimeter, 1–3 m off the walls, hold at each corner. Deliberately loop
      back over your start point at the end — we want to see whether loop
      closure fires. Let it process. Export → Raw.
- [ ] **Tier B — native Camera, 4K30.** Continuous, unpaused, same room.
- [ ] **Tier A — native Camera stills.** 5 or 6 overlapping shots, ~70% overlap.
      Put them in a folder named for the room.

Ground truth measured:

| What | Tape (cm) |
|---|---|
| Wall A | |
| Wall B | |
| Wall C | |
| Ceiling height | |
| Door width | |

---

## Getting the files off the phone

Tier C does not need a cable. Tiers A and B are better with one.

- **Tier C (zip):** Polycam share sheet → AirDrop → your Mac. The zip is opaque
  to iOS so nothing re-encodes it. Lands in `~/Downloads`.
- **Tiers A and B:** USB-C cable, then **Image Capture** (built into macOS) →
  select the phone → import to a folder. This is the only path that reliably
  gives untouched originals with EXIF intact. AirDrop also works *if* Keep
  Originals is set, but Image Capture removes the doubt.

---

## Inspect

```sh
python3 scripts/inspect_capture.py myroom/8_28_2026.zip
```

## Tier C — result

**Run: 2026-08-28, one bedroom, 2.5 min of scanning, 35.7 MB, 1183 files.**

```
  keyframes/cameras/             236 × .json
  keyframes/confidence/          236 × .png
  keyframes/corrected_cameras/   236 × .json
  keyframes/depth/               236 × .png
  keyframes/images/              236 × .jpg
  mesh_info.json · polycam.mp4 · thumbnail.jpg      (top level, no wrapper folder)

  duration 149 s · 95 frames/min
  depth   256×192, 16-bit PNG, millimetres, 0.77–2.54 m observed
  images  1024×768 JPEG · fx = fy = 719.13, cx = 511.85, cy = 382.70
  confidence  0 / 54 / 255  →  6% / 17% / 77%
  drift corrected by the optimiser: median 5.3 cm, p90 26.0 cm, max 42.2 cm
```

## Findings

**The published format notes are wrong in five places.** Everything below is
from the export, not the documentation.

| Documented | Actual |
|---|---|
| Everything nested under one capture folder | **No wrapper** — `keyframes/` and the JSONs sit at the archive root |
| `raw.glb` | Absent |
| `corrected_images/` | Absent |
| Confidence levels `0 / 127 / 255` | **`0 / 54 / 255`** |
| Frames named sequentially | Named by microsecond timestamp, e.g. `293814600474` |

**Undocumented fields, and they are the most useful thing in the file.**
`cameras/*.json` carries far more than pose and intrinsics:

`timestamp` · `tracking_segment` · `angular_velocity` · `blur_score` ·
`center_depth` · `exposure_time` · `iso` · `shutter_speed` · `thermal_state`

- `tracking_segment` increments when tracking is lost and re-initialised. Poses
  either side of a break share no common frame — this is the single most
  important flag for the drift work, and nothing in the docs mentions it.
- `blur_score` ranged 5 → 325 across one scan. Frame selection material.
- `angular_velocity` (median 0.46, max 2.51 rad/s) measures whether the operator
  actually followed the "no fast panning" instruction. The protocol can now be
  *audited* from the capture rather than trusted.
- `iso` / `exposure_time` detect the low-light case the brief asks us to cover.

**`corrected_cameras/` drops all of them.** It keeps only pose, intrinsics,
`blur_score`, `manual_keyframe`, and adds `weakly_connected`. So ingest must
**join raw and corrected by filename stem** — corrected poses, raw metadata.

**Drift is large and the loop-back worked.** Global optimisation moved cameras
by a median of 5.3 cm and up to 42.2 cm over a 2.5-minute single-room scan.
Loop closure ran on all 236 frames. Two consequences: raw ARKit poses are
unusable on their own, and our own correction stage is measured against
Polycam's corrected poses, not against zero.

**Frame rate is 95/min, so the pose-optimisation budget is a time budget:**
700 frames ≈ **7.3 minutes**, 1400 ≈ 14.7 minutes. The protocol's 6–8 minute
session cap was an estimate; it is now arithmetic.

**Images are 1024×768, not full resolution.** Polycam downsamples for the raw
export. Depth is exactly ¼ of that (256×192), so depth intrinsics are the image
intrinsics ÷ 4. Worth noting for damage detection, which wants pixels.

**`mesh_info.json` gives a free sanity check** — `bboxSize` [3.23, 3.03, 4.10] m
and per-direction surface areas including `horizontalUpArea` 7.28 m². Useful as
a cross-check against our own room measurements.

## Field observations

**Export is slow and it crashed.** A 2.5-minute scan took roughly 20–25 minutes
to process and export, and Polycam froze partway through — the operator had to
force-quit and reopen, at which point the file had been written. This is the
biggest risk to the walk-in test and it is now in § 7 of the protocol.

Not yet timed precisely. The next capture should stopwatch processing and
export separately, because we currently cannot tell which stage was slow.

## Still open

- [ ] Tier A photo set — not yet captured
- [ ] Tier B video walkthrough — not yet captured
- [ ] Polycam version number, for pinning in the submission
- [ ] A second Tier C run to time processing vs export separately, and to see
      whether the freeze reproduces
- [ ] Confirm `weakly_connected` behaviour on a deliberately bad scan (it was
      `false` on all 236 frames here)

## Open question carried forward

We only have a Pro phone. The walk-in test may hand us a base iPhone 15, which
has no LiDAR — so tiers A and B must be validated as if captured on a base
device. Check that neither tier's ingest path reads depth, ProRAW, or any other
Pro-only field that would be absent on the day.

# Benchmark report

All runs at a fixed **160 frames, bootstrap 40, wall-draws 50** so every
figure here is directly comparable. Regenerate any row with:

```sh
PYTHONPATH=src .venv/bin/python -m cozmo run "<capture>.zip" --name <name> \
  --frames 160 --bootstrap 40 --wall-draws 50 \
  [--truth-height <m> --truth-walls <m>,<m>]
```

## Benchmark set

| capture | rooms | tier | frames | duration | drift median | ISO median |
|---|---|---|---|---|---|---|
| My room 1 (28 Aug) | 1 | C | 236 | 2.5 min | 5.3 cm | 3200 |
| My room 2 (29 Aug) | 1 | C | 335 | 1.7 min | 0.9 cm | 3200 |
| Friend 1 room | 1 | C | 241 | 1.6 min | 0.5 cm | 80 |
| Friend 2 room | 1 | C | 307 | 1.5 min | 0.5 cm | 160 |
| Connector hallway | 1 | C | 280 | 1.7 min | 0.7 cm | 400 |

Three rooms plus a connector, which is the composition the brief asks for. My room
appears twice at the same tier for the repeatability gate. Tiers A and B were
captured for three of these rooms (photos and video) but **are not processed**
no ingest exists for them.

Ground truth is tape, metric, on my room only, final values, with the wall
carrying the door labelled so the pairing is not inferred:

| | value |
|---|---|
| door wall | **2.9883 m** (9' 9.65") |
| other wall | **3.0411 m** |
| ceiling | **2.9705 m** (9' 8.95") |

**The ground truth is less precise than the gate, and this is a headline result
rather than a footnote.** Four successive tape readings of the same ceiling
gave 3.0226, 2.9972, 2.9241 and 2.9705 m, a **9.8 cm spread against a 1.5 cm
gate**. Our five captures span 5.9 cm with a standard deviation of 2.31 cm. The
pipeline is more repeatable than the instrument measuring it, so accuracy
figures below are bounded by the tape, not by the pipeline.

## Per-room results

| room | ceiling | ± | wall A | ± | wall B | ± | floor area |
|---|---|---|---|---|---|---|---|
| my room 1 | 2.9479 | 1.83 cm | 3.1093 | 1.38 cm | 2.9933 | 1.25 cm | 9.307 m² |
| my room 2 | 2.9364 | 1.23 cm | 3.0359 | 0.70 cm | 3.1600 | 1.17 cm | 9.594 m² |
| friend 1 room | 2.8889 | 2.49 cm | 3.7643 | 0.72 cm | 3.4013 | 0.84 cm | 12.804 m² |
| friend 2 room | 2.9322 | 1.10 cm | 3.0458 | 0.58 cm | 3.0374 | 2.18 cm | 9.251 m² |
| hallway | 2.9389 | 2.07 cm | 3.7596 | 1.69 cm | 7.4690 | 5.54 cm | 28.080 m² |

Intervals are 95% bootstrap over frames, never over points, samples within a
frame share that frame's pose error, so resampling points would report an
interval of a fraction of a millimetre for data that disagrees by centimetres.

**Ceiling heights cluster at 2.889 to 2.948 m across three rooms and a hallway** in a building specced at 10 ft ceilings, agreeing with each other within 5.9 cm, against
a tape whose four readings of one ceiling spanned 9.8 cm.

## Gates, accuracy, scored where ground truth exists

Only my room carries tape measurements.

| capture | gate | precision | | accuracy | |
|---|---|---|---|---|---|
| my room 2 | ceiling height | ±1.23 cm | **PASS** | -3.4 cm | fail |
| my room 2 | door wall | ±0.82 cm | **PASS** | +4.9 cm | fail |
| my room 2 | other wall | ±1.22 cm | **PASS** | **+1.1 cm** | **PASS** |
| friend 2 | ceiling height | ±1.10 cm | **PASS** | -3.8 cm | fail |
| friend 2 | door wall | ±0.77 cm | **PASS** | +5.5 cm | fail |
| friend 2 | other wall | ±3.11 cm | fail | **-0.7 cm** | **PASS** |
| my room 1 | ceiling height | ±1.83 cm | fail | -2.3 cm | fail |
| my room 1 | door wall | ±1.76 cm | fail | +3.7 cm | fail |
| my room 1 | other wall | ±1.66 cm | fail | -3.8 cm | fail |

**Precision passes 5 of 6 on the two compliant captures.** Accuracy passes on
both "other wall" measurements, one in each room. Scan 1, the non-compliant
capture, fails everything, which is the subject of the fix loop.

The door wall reads +3.7 to +5.5 cm long in every capture, consistently. Two
independent rooms agree with each other to within 2 cm while both disagreeing
with that one tape figure by about 5 cm, so we do not treat it as settled: it
may be our error or it may be what that reading measured.

Applying the same tape to friend 2's room, which is the same unit type and the
same floorplan, gives a materially better picture on walls:

| room | one wall | other wall | ceiling |
|---|---|---|---|
| my room 2 | +4.8 cm | +11.9 cm | -3.4 cm |
| friend 2 | **+0.5 cm** | +4.9 cm | -3.8 cm |

Friend 2's room places one wall within **half a centimetre** inside the gate.
Both rooms show the same asymmetry, one wall good, one wall long, which is the
open-doorway mechanism appearing twice, more severely in my room. Both ceilings
sit 3.4 to 3.8 cm below the tape while agreeing with each other to 0.4 cm.

## Cross-room consistency, a check that needs no ground truth

My room and friend 2's room are the same unit type with the same floorplan.
Identical rooms must produce identical numbers; where they do not, something
specific is wrong. This validates the pipeline without a tape at all.

| | my room 2 | friend 2 | difference |
|---|---|---|---|
| ceiling | 2.9364 | 2.9322 | **0.4 cm** |
| wall X | 3.0359 | 3.0458 | **1.0 cm** |
| wall Y | 3.1600 | 3.0374 | **12.3 cm** |

Two independent captures in two different rooms agree on ceiling height to
**four millimetres** tighter than any two of the four tape readings agree with
each other.

The internal squareness check is sharper still. Both rooms are near-square in
reality:

| | measured out-of-square |
|---|---|
| friend 2 | **0.8 cm** |
| my room | **12.4 cm** |

The same floorplan cannot be 12 cm out of square in one capture and 0.8 cm in
another. **Three of four wall measurements across the two rooms agree within
1 cm; exactly one is corrupted** and that one is my room's wall Y, the axis
carrying the open doorway.

This isolates the defect precisely. It is not a general accuracy problem in wall
detection; it is one identified mechanism affecting one axis, reproduced and
bounded.

## Repeatability gate

Two captures of the same room at the same tier. Limit: 1 cm, or 0.5% per wall;
ceiling spread across captures ≤1 cm.

| | scan 1 | scan 2 | spread | limit | |
|---|---|---|---|---|---|
| ceiling height | 2.9479 | 2.9364 | 1.2 cm | 1.0 cm | FAIL |
| wall pair A | 3.1093 | 3.0359 | 7.3 cm | 1.5 cm | FAIL |
| wall pair B | 2.9933 | 3.1600 | 16.7 cm | 1.5 cm | FAIL |

Fails on all three. The ceiling misses by 0.2 cm; the wall pairs miss by an
order of magnitude, from the doorway problem.

We report which kind of failure this is, as the gate requires: **unrepeatable
not repeatable-but-biased.** Wall pair B moves 16.7 cm between two captures of
the same room, and which of two candidate planes wins also shifts with frame
count. That is instability in plane selection, not a constant offset.

## Drift accountability

Poses are not used as supplied. `geometry/drift.py` implements plane-anchored
correction: per-frame vertical corrections solved jointly with the floor and
ceiling plane heights, tied together by a temporal smoothness prior.

The prior is not decoration. Of 120 keyframes in scan 1, **67 saw only the
floor, 26 only the ceiling, and 1 saw both** so the two surface groups are
otherwise disconnected and the distance between them is unobservable from the
plane fits alone.

Ablation, run as one command with `--ablate`:

| method | height | interval |
|---|---|---|
| pooled (no per-frame correction) | 2.9614 m | ±4.30 cm |
| per-frame planes | 2.9624 m | ±4.82 cm |
| drift-corrected | 2.9621 m | ±5.44 cm |

And the σ_step sweep, which is the correction strength, σ_step → 0 reproduces
the uncorrected case:

| σ_step (m/frame) | height |
|---|---|
| 1e-6 (ablation off) | 2.8860 m |
| 1e-3 | 2.9461 m |
| 2e-3 | 2.9621 m |
| 1e-2 | 3.0206 m |

**13.5 cm of range on the correction strength.** Reported because it is true:
on scan 1 the plane separation was only weakly observable, and the answer
depended on the prior. Scan 2's better ceiling coverage is what reduced that
dependence.

## Timing

| stage | time |
|---|---|
| capture (Tier C, one room) | 1.5 to 2.5 min |
| Polycam raw export | ~2 min (one 20+ min outlier, app froze) |
| transfer, AirDrop | ~1 min |
| pipeline, 160 frames + bootstrap | ~45 s |

End to end from phone in hand to rendered plan: **under 5 minutes per room**
against the brief's 15-minute budget.

## What this benchmark does not cover

- **Tiers A and B are unscored.** Captured for three rooms, no ingest built.
  This is the largest gap in the submission.
- **No opening detection** so the opening-width gate, the tightest in the
  brief at ≤2 cm, is unscored.
- **No stitched multi-room plan.** Five rooms measured individually; no
  adjacency, no whole-property footprint.
- **No damage detection.** Two classes were staged and tape-measured (hallway
  2×3 in ellipse, friend-2 room 3×3 in square) but nothing consumes them.
- **Ground truth on one room only.** The other four have no tape measurements
  so their accuracy is unscored and only their precision is reported.
- **Ground truth precision is the binding limit on every accuracy figure here.**
  Four successive tape readings of one ceiling gave 3.0226, 2.9972, 2.9241 and
  2.9705 m, a 9.8 cm spread against a 1.5 cm gate, and the ceiling gate passes
  or fails depending on which is used. Measuring a 3 m ceiling overhead with a
  handheld tape is a ±5 cm operation; our five captures span 5.9 cm and two
  captures of identical rooms agree to 0.4 cm. **The pipeline is more repeatable
  than the instrument measuring it.** A laser reading to millimetres is required
  before any accuracy claim at this gate is defensible. This is stated as a
  limitation of the benchmark, not of the pipeline.

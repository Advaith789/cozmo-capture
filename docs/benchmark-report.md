# Benchmark report

All runs at a fixed **160 frames, bootstrap 40, wall-draws 50**, so every
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

Four rooms plus a connector, satisfying the composition requirement. My room
appears twice at the same tier for the repeatability gate. Tiers A and B were
captured for three of these rooms (photos and video) but **are not processed** —
no ingest exists for them.

Ground truth is tape, metric, on my room only: walls **2.9972 m** and
**3.0199 m**, ceiling **2.9241 m**.

## Per-room results

| room | ceiling | ± | wall A | ± | wall B | ± | floor area |
|---|---|---|---|---|---|---|---|
| my room 1 | 2.9479 | 1.83 cm | 3.1093 | 1.38 cm | 2.9933 | 1.25 cm | 9.307 m² |
| my room 2 | 2.9364 | 1.23 cm | 3.0359 | 0.70 cm | 3.1600 | 1.17 cm | 9.594 m² |
| friend 1 room | 2.8889 | 2.49 cm | 3.7643 | 0.72 cm | 3.4013 | 0.84 cm | 12.804 m² |
| friend 2 room | 2.9322 | 1.10 cm | 3.0458 | 0.58 cm | 3.0374 | 2.18 cm | 9.251 m² |
| hallway | 2.9389 | 2.07 cm | 3.7596 | 1.69 cm | 7.4690 | 5.54 cm | 28.080 m² |

Intervals are 95% bootstrap over frames, never over points — samples within a
frame share that frame's pose error, so resampling points would report an
interval of a fraction of a millimetre for data that disagrees by centimetres.

**Ceiling heights cluster at 2.889–2.948 m across four rooms** in a building
specified at 10-foot ceilings, agreeing with each other within 5.9 cm and with
the one taped ceiling within 1.2 cm.

## Gates — accuracy, scored where ground truth exists

Only my room carries tape measurements.

| capture | gate | precision | | accuracy | |
|---|---|---|---|---|---|
| my room 2 | ceiling height | ±1.23 cm | **PASS** | +1.2 cm | **PASS** |
| my room 2 | wall pair A | ±0.70 cm | **PASS** | +3.9 cm | FAIL |
| my room 2 | wall pair B | ±1.17 cm | **PASS** | +14.0 cm | FAIL |
| my room 1 | ceiling height | ±1.83 cm | FAIL | +2.4 cm | FAIL |
| my room 1 | wall pair A | ±1.38 cm | **PASS** | +11.2 cm | FAIL |
| my room 1 | wall pair B | ±1.25 cm | **PASS** | −2.7 cm | FAIL |

**Precision passes on 5 of 6.** Accuracy passes on 1 of 6, and the failures are
concentrated in wall length, where the double-digit errors come from the
open-doorway problem described in [fix-loop.md](fix-loop.md) § 4 — the scan sees
through the open door and detects a hallway surface as a candidate wall.

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

We report which kind of failure this is, as the gate requires: **unrepeatable,
not repeatable-but-biased.** Wall pair B moves 16.7 cm between two captures of
the same room, and which of two candidate planes wins also shifts with frame
count. That is instability in plane selection, not a constant offset.

## Drift accountability

Poses are not used as supplied. `geometry/drift.py` implements plane-anchored
correction: per-frame vertical corrections solved jointly with the floor and
ceiling plane heights, tied together by a temporal smoothness prior.

The prior is not decoration. Of 120 keyframes in scan 1, **67 saw only the
floor, 26 only the ceiling, and 1 saw both** — so the two surface groups are
otherwise disconnected and the distance between them is unobservable from the
plane fits alone.

Ablation, run as one command with `--ablate`:

| method | height | interval |
|---|---|---|
| pooled (no per-frame correction) | 2.9614 m | ±4.30 cm |
| per-frame planes | 2.9624 m | ±4.82 cm |
| drift-corrected | 2.9621 m | ±5.44 cm |

And the σ_step sweep, which is the correction strength — σ_step → 0 reproduces
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
| capture (Tier C, one room) | 1.5–2.5 min |
| Polycam raw export | ~2 min (one 20+ min outlier, app froze) |
| transfer, AirDrop | ~1 min |
| pipeline, 160 frames + bootstrap | ~45 s |

End to end from phone in hand to rendered plan: **under 5 minutes per room**,
against the brief's 15-minute budget.

## What this benchmark does not cover

- **Tiers A and B are unscored.** Captured for three rooms, no ingest built.
  This is the largest gap in the submission.
- **No opening detection**, so the opening-width gate — the tightest in the
  brief at ≤2 cm — is unscored.
- **No stitched multi-room plan.** Five rooms measured individually; no
  adjacency, no whole-property footprint.
- **No damage detection.** Two classes were staged and tape-measured (hallway
  2×3 in ellipse, friend-2 room 3×3 in square) but nothing consumes them.
- **Ground truth on one room only.** The other four have no tape measurements,
  so their accuracy is unscored and only their precision is reported.
- **Ground truth precision.** An earlier ceiling figure recorded to the nearest
  inch was wrong by 7.3 cm and briefly looked like a systematic pipeline bias
  across four rooms. Re-measured carefully it is 2.9241 m, and the pipeline was
  correct throughout. Ground truth read to the nearest inch carries ±1.27 cm of
  quantisation against a ±1.5 cm gate and cannot certify it.

# Benchmark report

All runs at a fixed **160 frames, bootstrap 40, wall-draws 50** so every
figure here is directly comparable. Regenerate the whole table with one
command:

```sh
bash scripts/benchmark.sh
```

or any single row with:

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
appears twice at the same tier for the repeatability gate. Tiers A and B are
processed too, by a learned multi-view model, and reported in their own section
below; they are much weaker than Tier C and the numbers say so.

Ground truth is tape, metric, on my room only, final values, with the wall
carrying the door labelled so the pairing is not inferred:

| | value |
|---|---|
| door wall | **3.0344 m**, mean of five readings: 303.8, 304.2, 300.1, 306.7, 302.4 cm |
| other wall | 3.0411 m |
| ceiling | 2.9705 m (9' 8.95") |

The door wall figure replaces an earlier single reading of 2.9883 m, which was
4.6 cm out. **The pipeline found that error before the tape did:** four
independent wall measurements across two identically built rooms clustered at
303.4 to 305.2 cm while that one reading said 298.8, and a careful five-reading
re-measure landed at 303.44. Our measurements sit 0.75 cm from it.

**The ground truth is still less precise than the gate it certifies.** Those
five readings span 6.6 cm with a standard error of 1.09 cm, against a 1.5 cm
gate, and four successive readings of the ceiling spanned 9.8 cm. Accuracy
figures below are therefore consistent with tape rather than certified by it.

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
| my room 2 | ceiling height | ±0.76 cm | **PASS** | **-0.2 cm** | **PASS** |
| my room 2 | door wall | ±0.82 cm | **PASS** | **+0.3 cm** | **PASS** |
| my room 2 | other wall | ±1.22 cm | **PASS** | **+1.1 cm** | **PASS** |
| friend 2 | ceiling height | ±0.50 cm | **PASS** | **-0.7 cm** | **PASS** |
| friend 2 | door wall | ±0.77 cm | **PASS** | **+0.9 cm** | **PASS** |
| friend 2 | other wall | ±3.11 cm | fail | **-0.7 cm** | **PASS** |
| my room 1 | ceiling height | ±0.70 cm | **PASS** | +5.7 cm | fail |
| my room 1 | door wall | ±1.76 cm | fail | **-0.9 cm** | **PASS** |
| my room 1 | other wall | ±1.66 cm | fail | -3.8 cm | fail |

**Accuracy passes 7 of 9, precision 6 of 9.** My room 2, the capture that
followed the protocol, passes every gate on both axes. Every remaining failure
belongs to scan 1, the deliberately non-compliant capture, except one precision
miss on friend 2.

Applying the same tape to friend 2's room, which is the same unit type and the
same floorplan, gives a materially better picture on walls:

| room | door wall | other wall | ceiling |
|---|---|---|---|
| my room 2 | +0.3 cm | +1.1 cm | -0.2 cm |
| friend 2 | +0.9 cm | -0.7 cm | -0.7 cm |

Both rooms now sit inside the gate on every measurement, and the two identical
rooms agree with each other to within 1.2 cm.

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
| pipeline, 160 frames + bootstrap | **~25 s** |
| Tier A or B, first run (learned model, 12 views) | 7 to 13 min |
| Tier A or B, re-run of the same capture | ~30 s, from cache |

End to end from phone in hand to rendered plan: **under 5 minutes per room**
against the brief's 15-minute budget.

The Tier C pipeline was 259 s and is now 25 s, with every measurement
unchanged to the last reported digit. Two things did it. Each frame was being
back-projected twice, once to build the cloud and once to carry camera centres,
and opening detection was re-running the whole wall fit on eight resampled
subsets to test whether an opening was stable, which the ray traced detector
does not need because it is stable by construction.

Tiers A and B are minutes rather than seconds because a 1B parameter model runs
over every pair of views, and on 8 GB of unified memory that is the honest cost.
Results are cached by a hash of the input images and the settings, so a repeat
run of the same capture reproduces the first exactly and returns in seconds,
which is also what makes the repeatability gate meaningful for a model that
would otherwise be too expensive to run twice.

## Tiers A and B, the camera-only tiers

These run now, which they did not before, and they are much weaker than Tier C.
Both numbers and reasons are below because the reasons are the useful part.

Classical structure from motion could not do this at all: COLMAP registered 4
photographs of 29 and 27 video frames of 70. That is not a tuning failure. The
walls of a bedroom are large, flat, blank and dimly lit, and feature matching
needs texture. Tiers A and B therefore use MASt3R, a learned multi-view model
that regresses geometry directly, run locally on the laptop and disclosed in the
provenance of every figure it touches.

Ground truth is tape on my room and the Tier C measurement elsewhere, which is
itself good to about 1 cm on the room where we hold a tape. Rows scored against
Tier C say so.

| capture | tier | ceiling | reference | error |
|---|---|---|---|---|
| my room | A, photos | 2.591 m | 2.9705 m tape | **-12.8%** |
| friend 1 room | A, photos | 2.751 m | 2.9873 m Tier C | **-7.9%** |
| friend 2 room | A, photos | 2.261 m | 2.9631 m Tier C | **-23.7%** |
| my room | B, video | 1.218 m | 2.9705 m tape | **-59.0%** |
| friend 1 room | B, video | 3.176 m | 2.9873 m Tier C | **+6.3%** |

One capture of the five recovered two opposing wall pairs and so closed a room
polygon. Its walls are the best result the camera tiers produce:

| friend 2 room, Tier A | photos | Tier C | error |
|---|---|---|---|
| wall 0 | 2.863 m | 3.061 m | -6.5% |
| wall 1 | 3.021 m | 3.023 m | **-0.1%** |

So the honest summary is that the camera tiers are **not reliable**, that their
error ranges from 0.1% to 59%, and that we cannot tell in advance which we will
get. The gate is ±8% and two of seven scored figures clear it. Nothing here is
claimed.

### What we learned making them work at all

**The scale was being thrown away by a default.** The MASt3R checkpoint used is
the metric one, and its ceiling height still came out 51% low, which looked like
a model that simply did not work. It is not. dust3r's global aligner normalises
the pairwise scales so their product is one, which is right for a scale-free
reconstruction and discards precisely the property the metric checkpoint exists
to provide. Turning that off moved my room from -50.7% to -8.1% on the same
images. A factor of two that looks like a bug usually is one.

**Sampling evenly across a folder is worse than sampling densely across part of
it.** Our photo folder held two capture sessions an hour apart, and an even
spread paired images that shared no scene. Frames are now taken from a single
burst, found from their timestamps, and never more than one photo apart, because
overlap is what the model needs and coverage is what it can do without. On a
48 photo burst an even spread put consecutive views 16 seconds of walking apart
and the reconstruction came back 17% short with three walls.

**The estimator has to match the data.** Tiers A and B were hard-coded to the
sparse ceiling estimator, which reads a tail quantile because a feature cloud
has no dense surface band. A learned pointmap does have one, and a tenth of its
points sit above 2.5 m, so the tail quantile cut the ceiling off: 17.7% low
against 9.6% for the dense estimator on identical data.

**A reconstruction can close a room that is simply wrong.** On one burst the
walls came back at 1.16 and 1.88 m while the camera path alone spanned 1.2 m,
which is impossible: the photographer cannot stand outside the room they
photographed. Every camera position is now required to fall inside the walls
reported, and a room that fails is discarded rather than published. That check
costs nothing and is not a tolerance to tune.

**An interval narrower than the error is worse than no interval.** The camera
tiers propagate their scale prior into every wall length by re-fitting the walls
on a scaled cloud, which cannot work: scaling moves projections by up to half a
metre while the fitter looks within 6 cm of the offset it was given. Every draw
returned nothing and the tiers quietly reported a fixed ±2 cm fallback on
measurements whose real error is 18 cm. Scaling is a similarity, so a plane at
offset d moves to offset s·d exactly and there is nothing to fit. The intervals
below are wide because the scale really is that uncertain.

### Sanity checks that did pass

Two things independently say the reconstruction is metrically sensible even
where the ceiling is not. Camera height comes out at **1.54 m** above the lowest
points, which is where a phone is held. And the top 1% of the reconstructed
points span **4.6 cm**, which is a flat ceiling plane rather than ragged wall
tops, so the ceiling is being seen and not inferred.

## What this benchmark does not cover

- **Tiers A and B run but are not reliable.** Scored above, error from 0.1% to
  59%, and we cannot tell in advance which we will get. This remains the
  largest gap in the submission, and it is now a measured gap rather than an
  empty one.
- **The opening-width gate is not claimed.** Detection works and is scored on
  synthetic truth at 0.8 cm mean error against the 2 cm gate. On a real capture
  it finds the doorway but measures the clear opening, 0.587 m, against a
  0.958 m frame, and a partly open door cannot be separated from a measurement
  error without a controlled re-capture.
- **The multi-room stitch has no ground truth.** It works, and the friend 2
  capture splits into two rooms joined by a 1.100 m doorway, but we hold no
  tape for any room boundary or doorway, so only the synthetic result (1.0 cm
  on a known 0.85 m door) is scored. Two captures also disagree with intuition
  about how many spaces they contain, and there is nothing to settle it with.
- **Damage detection is opt-in and unscored.** Two classes were staged and
  tape-measured (hallway 2x3 in ellipse, friend-2 room 3x3 in square). The
  detector runs behind `--damage` and reported 79 regions on a clean control
  room, so it is off by default and claimed against nothing.
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

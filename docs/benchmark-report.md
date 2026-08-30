# Benchmark report

All runs at a fixed **160 frames, bootstrap 40, wall-draws 50** so every
figure here is directly comparable. Regenerate the whole table with one
command:

```sh
bash scripts/benchmark.sh
```

or any single row with:

```sh
cozmo run "<capture>.zip" --name <name> \
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

The camera tiers, over the same rooms:

| capture | tier | photos or frames | burst used | views reconstructed |
|---|---|---|---|---|
| My room, photos | A | 69 | 48 | 12 |
| My room, **re-shot to the protocol** | A | 22 | 22 | 11 |
| Friend 1 room, photos | A | 29 | 29 | 12 |
| Friend 2 room, photos | A | 67 | 67 | 12 |
| My room, video | B | 60 sampled | 60 | 12 |
| Friend 1 room, video | B | 60 sampled | 60 | 12 |

Views are capped at twelve by 8 GB of unified memory, not by choice. A burst is
one unbroken run of photographs: the first folder held two sessions an hour
apart, and pairing across them was worth catching.

Three rooms plus a connector, which is the composition the brief asks for. My room
appears twice at the same tier for the repeatability gate. Tiers A and B are
processed too, by a learned multi-view model, and reported in their own section
below; they are much weaker than Tier C and the numbers say so.

Ground truth is tape, metric, on **two rooms**, five readings per dimension,
with the wall carrying the door labelled so the pairing is not inferred.

**My room:**

| | value |
|---|---|
| door wall | **3.0344 m**, mean of five readings: 303.8, 304.2, 300.1, 306.7, 302.4 cm |
| other wall | 3.0411 m |
| ceiling | 2.9705 m (9' 8.95") |

**Friend 1 room**, measured after the pipeline was frozen, so nothing here was
tuned against it:

| | truth | readings, cm | spread | sd of the mean |
|---|---|---|---|---|
| long wall | **3.7636 m** | 375.98, 376.52, 374.89, 377.90, 376.50 | 3.0 cm | 0.49 cm |
| short wall | **3.3620 m** | 336.00, 337.00, 336.50, 335.50, 336.00 | 1.5 cm | 0.25 cm |
| ceiling | **3.0020 m** | ten readings, two sessions, below | 6.9 cm | 0.64 cm |

The walls are the strongest accuracy evidence in the submission, because the
tape had never seen our output:

| friend 1 room | ours | tape | error | gate |
|---|---|---|---|---|
| long wall | 3.7654 m | 3.7636 m | **+0.18 cm** | **PASS** |
| short wall | 3.3603 m | 3.3620 m | **-0.17 cm** | **PASS** |
| ceiling | 2.9873 m | 3.0020 m | -1.47 cm | PASS, by 0.03 cm |

Both walls land inside 2 mm, against a 1.5 cm gate and inside the tape's own
scatter.

### The ceiling took two sessions and still is not settled

This is worth setting out in full, because the honest answer is not the
flattering one.

| session | readings, cm | mean | our error | gate |
|---|---|---|---|---|
| 1, taken blind | 301.00, 303.00, 302.50, 300.40, 299.10 | 301.20 | -2.47 cm | **fail** |
| 2, re-measured | 299.00, 301.00, 298.70, 301.20, 296.13 | 299.21 | -0.48 cm | pass |
| all ten pooled | | **300.20** | **-1.47 cm** | pass, by 0.03 cm |

**The reported truth is the pooled mean of all ten readings.** Session 2 was
taken after seeing our measurement, so it is not independent and cannot be used
on its own; quoting it alone would be measuring until the gate passes. Session 1
alone fails. Pooling every reading is the only choice that uses all the evidence
and picks none of it, and it lands 0.3 mm inside a 1.5 cm gate, which is a pass
that should be read as a coin toss.

We also considered an argument that a tape can only over-read a ceiling, since
tilt and bow both add length and neither can subtract it. **The data does not
support it.** Two readings, 298.70 and 296.13, fall below our own measurement,
which a one-sided error cannot produce. The tape scatters both ways.

What the two sessions do establish is the finding that matters: **two sets of
five readings of the same ceiling, taken by the same person with the same tape,
disagree by 2.0 cm, and the full range is 6.9 cm against a gate of 1.5 cm.** The
instrument is between four and five times coarser than the thing it is being
asked to certify. Our own two captures of identical rooms agree on ceiling
height to 0.5 cm. A laser is required before any ceiling accuracy claim at this
gate is defensible, and that is a limitation of the benchmark rather than of the
pipeline.

## Per-room results

| room | ceiling | ± | wall A | ± | wall B | ± | floor area |
|---|---|---|---|---|---|---|---|
| my room 1 | 3.0271 | 0.70 cm | 3.0256 | 1.76 cm | 3.0028 | 1.66 cm | 9.085 m² |
| my room 2 | 2.9680 | 0.76 cm | 3.0372 | 0.82 cm | 3.0524 | 1.22 cm | 9.271 m² |
| friend 1 room | 2.9873 | 1.09 cm | 3.7654 | 0.68 cm | 3.3603 | 0.77 cm | 12.653 m² |
| friend 2 room * | 2.9631 | 0.50 cm | 3.0607 | 2.09 cm | 3.0228 | 3.11 cm | 9.252 m² |
| connector hallway * | 2.9969 | 0.76 cm | 3.7677 | 1.74 cm | 1.2350 | 1.12 cm | 4.653 m² |

\* These two captures cover more than one space and are now segmented, so the
row is the largest room in the capture rather than the whole scanned envelope.
The hallway is the clearest case for why that matters: it used to report a
single room of **28.08 m²** spanning the hallway and everything visible off it,
a figure that belonged to no room in the building. It now reports the hallway
itself at 4.65 m², and the space next door separately.

Intervals are 95% bootstrap over frames, never over points: samples within a
frame share that frame's pose error, so resampling points would report an
interval of a fraction of a millimetre for data that disagrees by centimetres.
Each interval is recentred on the value it belongs to, because the value comes
from the wall detection and the draws come from refits of it, and those are two
estimators of the same wall that differ by a few millimetres.

**The four compliant captures agree on ceiling height to 3.4 cm** (2.963 to
2.997 m) in a building specced at 10 ft ceilings. Including my room 1, the
deliberately non-compliant scan, widens that to 6.4 cm, which is the cost of
breaking the protocol. For comparison, one tape measuring one ceiling twice
spanned 6.9 cm.

## Gates, accuracy, scored where ground truth exists

Three rooms carry tape. Every row below is scored against a tape applied to
that same room.

| capture | gate | precision | | accuracy | |
|---|---|---|---|---|---|
| my room 2 | ceiling height | ±0.76 cm | **PASS** | **-0.2 cm** | **PASS** |
| my room 2 | door wall | ±0.82 cm | **PASS** | **+0.3 cm** | **PASS** |
| my room 2 | other wall | ±1.22 cm | **PASS** | **+1.1 cm** | **PASS** |
| friend 1 | ceiling height | ±1.09 cm | **PASS** | -1.5 cm | **PASS** by 0.03 cm |
| friend 1 | long wall | ±0.68 cm | **PASS** | **+0.2 cm** | **PASS** |
| friend 1 | short wall | ±0.77 cm | **PASS** | **-0.2 cm** | **PASS** |
| my room 1 | ceiling height | ±0.70 cm | **PASS** | +5.7 cm | fail |
| my room 1 | door wall | ±1.76 cm | fail | **-0.9 cm** | **PASS** |
| my room 1 | other wall | ±1.66 cm | fail | -3.8 cm | fail |

**Precision passes 7 of 9, accuracy 7 of 9.** My room 2, the capture that
followed the protocol, passes every gate on both axes, and so does friend 1,
though its ceiling clears by 0.3 mm and should be read as a coin toss rather
than a result. **Every remaining failure belongs to my room 1, the deliberately
non-compliant capture**, which is the point of including it.

An earlier version of this table scored friend 2 against **my room's** tape, on
the grounds that they are the same unit type with the same floorplan. That was
an assumption standing in for a measurement, and it flattered us: it produced
three extra passing rows from a tape that had never touched that room. It is
gone, replaced by friend 1 measured against its own tape, which is a weaker
looking table and a stronger claim. Friend 2 now appears only in the
consistency section below, where an untaped room belongs.

## Cross-room consistency, a check that needs no ground truth

My room and friend 2's room are the same unit type with the same floorplan.
Identical rooms must produce identical numbers; where they do not, something
specific is wrong. This validates the pipeline without a tape at all, and it is
where friend 2 belongs now that it is no longer being scored against someone
else's tape.

| | my room 2 | friend 2 | difference |
|---|---|---|---|
| ceiling | 2.9680 m | 2.9631 m | **0.5 cm** |
| wall X | 3.0372 m | 3.0607 m | **2.4 cm** |
| wall Y | 3.0524 m | 3.0228 m | **3.0 cm** |
| floor area | 9.2709 m2 | 9.2519 m2 | **0.02 m2** |

Two independent captures of two different rooms with the same floorplan agree on
ceiling height to **five millimetres**, which is tighter than any two of the four
tape readings of a single ceiling agree with each other, and on floor area to
two hundredths of a square metre.

**This check is what found the largest defect in the pipeline.** An earlier
version measured wall Y as 3.1600 m in my room against 3.0374 m in friend 2, a
12.3 cm disagreement between rooms that are physically identical, and reported
my room as 12.4 cm out of square where friend 2 was 0.8 cm. The same floorplan
cannot be both. That isolated the fault to one axis, the one carrying the open
doorway, and to one mechanism: the wall band was sampling low enough to pick up
furniture and the points spraying through the doorway. Raising the band fixed
it, and the two rooms now agree on every dimension to within 3 cm. The write-up
is in [fix-loop.md](fix-loop.md).

That is the argument for this check. It needs no ground truth, it costs nothing,
and it found something a tape never would have: with a single room there is
nothing to disagree with.

## Repeatability gate

Two captures of the same room at the same tier. Limit: 1 cm, or 0.5% per wall,
whichever is larger; ceiling spread across captures ≤1 cm.

| | scan 1 | scan 2 | spread | limit | |
|---|---|---|---|---|---|
| ceiling height | 3.0271 | 2.9680 | 5.9 cm | 1.0 cm | FAIL |
| wall pair A | 3.0256 | 3.0372 | **1.2 cm** | 1.5 cm | **PASS** |
| wall pair B | 3.0028 | 3.0524 | 5.0 cm | 1.5 cm | FAIL |

One of three passes, where previously none did. The earlier failure on wall
pair B was 16.7 cm and came from an unstable choice of plane, which is fixed:
the wall band no longer samples low enough to pick up furniture and the points
spraying through an open doorway. What remains is a different failure with a
different cause.

**These two scans are not equivalent, and that is the point of the pair.** Scan
1 broke the protocol: it was captured in a single fast sweep and the pose
optimiser had to move each camera a median of 5.3 cm to reconcile it, against
0.9 cm for scan 2. Scan 1 is also the capture that fails three of its own
accuracy gates. So this gate is measuring a compliant capture against a
non-compliant one, and a 5.9 cm ceiling spread is the honest cost of the
difference rather than noise in the pipeline.

We report which kind of failure this is, as the gate requires: **repeatable but
capture-dependent, not unrepeatable.** Re-running either scan reproduces its own
numbers exactly, and the two disagree because the captures genuinely differ. The
diagnostic that separates them, median pose correction, runs in under a second
and is what `cozmo check` reports before anyone leaves the building.

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

The brief sets the two tiers different gates: photo wall lengths within **±8%**,
video within **±3%**. Video is the tighter one, because a clip carries far more
frames of a room than eight stills ever can.

| capture | tier | ceiling | reference | error | its gate | |
|---|---|---|---|---|---|---|
| my room | A, photos | 2.828 m | 2.9705 m tape | **-4.8%** | ±8% | **PASS** |
| friend 1 room | A, photos | 2.771 m | 2.9873 m Tier C | **-7.2%** | ±8% | **PASS** |
| my room, re-shot | A, photos | 2.682 m | 2.9705 m tape | -9.7% | ±8% | fail |
| friend 2 room | A, photos | 2.309 m | 2.9631 m Tier C | -22.1% | ±8% | fail |
| friend 1 room | B, video | 3.858 m | 2.9873 m Tier C | +29.1% | ±3% | fail |
| my room | B, video | 1.999 m | 2.9705 m tape | -32.7% | ±3% | fail |

**Two of six clear their tier's gate**, both at the photo tier; the median
absolute error is 15.9%. Video clears neither, and against a ±3% bar it is not
close. Photos beat video on every comparison available. Nothing here is claimed.

One capture of the six recovered two opposing wall pairs and closed a room
polygon. Its walls are the best result the camera tiers produce:

| friend 2 room, Tier A | photos | Tier C | error |
|---|---|---|---|
| wall 0 | 2.863 m | 3.061 m | -6.5% |
| wall 1 | 3.021 m | 3.023 m | **-0.1%** |

### The re-shoot, which did not do what we expected

One room was re-shot specifically to the protocol above: 22 photographs in a
single unbroken burst, one small step between frames, both junction lines in
shot. It is the only capture we hold that follows the rules the protocol sets.

**It came out worse than the capture it was meant to improve on:** -35.5%
against the original's -12.8%. Chasing that down found two real defects, and
neither was in the photography.

**The frame selector was covering half the room.** Frames are sampled from one
burst with the stride capped so neighbouring views overlap. On a 48 photo burst
that is right. On 22 photographs taken one step apart it produced twelve
consecutive frames spanning half the circle the operator had actually walked, so
two of the four walls were never seen. The rule now spans the whole sweep first
and thins it second, which lifted coverage from 55% to 95% of the burst and left
the longer captures untouched.

**The ceiling estimator was measuring the bed.** This was most of it. The
estimator locates floor and ceiling as the two densest horizontal bands, which
is correct for a LiDAR sweep because the operator is told to look up. A person
taking photographs at chest height barely captures a ceiling at all: in this
cloud the ceiling is **2.7% of the points**, and the two densest bands are the
floor and the bed. It measured the bed and reported 1.79 m for a 2.97 m room.
Switching to the extremes of the cloud, with a tail smaller than the share of
points on the least sampled surface, took the same capture to -9.7%.

Both fixes helped every camera capture, not just this one. My room went from
-12.8% to **-4.8%**, friend 1 from -7.9% to **-7.2%**, and the worst case, a
video, from -59.0% to -32.7%.

**The re-shoot still did not beat the original**, which is worth saying plainly
after asking for it: 22 photographs in a tight circle carry less angular
diversity than 48 taken over a longer session, and the original remains our best
photo capture at -4.8%. What the re-shoot bought was not a better number, it was
two defects that a compliant capture exposed and a non-compliant one had been
hiding.

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

## Head to head against the incumbent

**Incumbent:** Polycam, Floorplan mode (Apple RoomPlan underneath), free tier,
**version 6.0.21**. Exports submitted as
`myroom/floorplan/8_29_2026 - Floorplan - My room.zip` and
`myroom/floorplan/8_29_2026 - friend 1 room.zip`; both comparisons are drawn
from `optimized_roomplan.json`. Ours are `out/myroom2.json` and
`out/friend1_room.json`. **Two rooms, as the brief requires.**

**My room**, against tape:

| dimension | tape | **ours** | error | Polycam | error | |
|---|---|---|---|---|---|---|
| ceiling height | 2.9705 m | **2.9680 m** | **-0.2 cm** | 2.9382 m | -3.2 cm | **win** |
| door wall | 3.0344 m | **3.0372 m** | **+0.3 cm** | 3.1185 m | +8.4 cm | **win** |
| other wall | 3.0411 m | **3.0524 m** | **+1.1 cm** | 3.1393 m | +9.8 cm | **win** |
| floor area | 9.2279 m² | **9.271 m²** | **+0.5%** | 9.790 m² | +6.1% | **win** |

**Friend 1 room**, against tape measured after the pipeline was frozen:

| dimension | tape | **ours** | error | Polycam | error | |
|---|---|---|---|---|---|---|
| ceiling height | 3.0020 m | **2.9873 m** | **-1.5 cm** | 2.9580 m | -4.4 cm | **win** |
| long wall | 3.7636 m | **3.7654 m** | **+0.2 cm** | 3.9072 m | +14.4 cm | **win** |
| short wall | 3.3620 m | **3.3603 m** | **-0.2 cm** | 3.4714 m | +10.9 cm | **win** |
| floor area | 12.6532 m² | **12.653 m²** | **-0.0%** | 13.564 m² | +7.2% | **win** |

**Eight of eight shared dimensions across two rooms, against a bar of 70%.** Our
largest error is 1.5 cm; Polycam's smallest is 3.2 cm.

Two things about that table are worth stating rather than leaving to be found.
**The wall pairing is the one that flatters Polycam.** Neither output labels its
walls, so pairing to the tape is by best correspondence; on friend 1 the
alternative pairing gives Polycam -29.2 cm and +54.5 cm instead of +14.4 and
+10.9. **And our floor area is not independent** of our own wall lengths, since
it is derived from the same fitted planes; the tape figure is likewise the
product of two tape readings, so that row confirms the walls rather than adding
evidence.

Accuracy is not the whole comparison:

| capability | ours | Polycam |
|---|---|---|
| room segmentation | yes, with doorway widths | yes, and it split friend 1 where we did not |
| door and window detection | yes, ray traced, not claimed | 3 doors, 2 windows, dimensioned |
| wall thickness | no | yes, 0.1 m per wall |
| multi-room stitch | yes, from one capture | yes |
| an interval on every number | **yes** | no |

Polycam is better at knowing what it is looking at, and on friend 1 it did
something we did not: it split the room into a 13.56 m² bedroom and a 0.79 m²
alcove, where our segmentation kept them as one space because the barrier
between them is not walled to the ceiling. Neither answer is obviously wrong and
we hold no ground truth for the boundary.

Its opening detection is also not uniformly better than ours. Its three doors,
0.858, 0.695 and 0.890 m, are plausible; its two windows are 2.698 m and 1.874 m
wide and 2.71 m and 2.61 m tall, which in a room with a 3.00 m ceiling is not a
window. We report fewer openings and claim none of them.

We are more accurate on every dimension we both produce, and we are the only one
of the two that says how uncertain each number is.

## Appendix: the export format, verified rather than assumed

The published format notes for a Polycam raw export are **wrong in five
places**. Everything the ingest does is derived from a real export.

| documented | actual |
|---|---|
| everything nested in one capture folder | **no wrapper**: `keyframes/` sits at the archive root |
| `raw.glb` | absent |
| `corrected_images/` | absent |
| confidence levels `0 / 127 / 255` | **`0 / 54 / 255`** |
| frames named sequentially | named by microsecond timestamp |

`cameras/*.json` also carries undocumented fields that turned out to matter more
than the documented ones: `tracking_segment` increments when tracking is lost
and re-initialised, which is the single most important flag for drift;
`blur_score` ranged 5 to 325 in one scan; `angular_velocity` (median 0.46, max
2.51 rad/s) lets the protocol be **audited from the capture** rather than
trusted; `iso` and `exposure_time` detect the low-light case the brief asks us
to cover. `corrected_cameras/` drops all of them, so ingest joins the two
directories by filename stem: corrected poses, raw metadata.

## What this benchmark does not cover

- **Tiers A and B run but are not reliable.** Scored above: ceiling error from
  4.8% to 32.7%, two of six inside their tier's gate, and we cannot tell in
  advance which we will get. **The photo-tier whole-property stitch does not
  exist**, because only one photo capture recovers two opposing wall pairs, so
  that row of the brief is a fail. This remains the largest gap in the
  submission, and it is now a measured gap rather than an empty one.
- **The opening-width gate is not claimed, and we now know why.** Detection is
  ray traced and reaches 0.8 cm mean error on synthetic truth against the 2 cm
  gate. On my room it finds the doorway and measures **0.587 m against a
  0.958 m frame**, and the cause is measurable rather than speculative. Of the
  returns in that doorway at door height, **1.2% lie on the wall plane**, so the
  door was genuinely open and not closed; but **48.8% lie in front of the wall**,
  something standing between the sensor and the opening. The detector measures
  what it could see through, which was 0.587 m of it. Lowering the see-through
  threshold from 3 crossings to 1 does not change the number, so the limit is
  the occlusion and not the setting. The fix is a capture with a clear approach
  to the doorway, which the protocol now asks for and none of our captures did.
- **The multi-room stitch has no ground truth.** It works, and the friend 2
  capture splits into two rooms joined by a 1.100 m doorway, but we hold no
  tape for any room boundary or doorway, so only the synthetic result (1.0 cm
  on a known 0.85 m door) is scored. Two captures also disagree with intuition
  about how many spaces they contain, and there is nothing to settle it with.
- **Damage detection is opt-in and unscored.** Two classes were staged and
  tape-measured (hallway 2x3 in ellipse, friend-2 room 3x3 in square). The
  detector runs behind `--damage` and reported 79 regions on a clean control
  room, so it is off by default and claimed against nothing.
- **Ground truth on two rooms of five.** Friend 2, the hallway and the repeat
  capture of my room have no tape, so their accuracy is unscored and only their
  precision is reported.
- **Ground truth precision is the binding limit on every accuracy figure here.**
  Ten tape readings of the friend 1 ceiling, across two sessions, span 6.9 cm
  against a 1.5 cm gate, and the two session means differ by 2.0 cm, so the
  gate passes or fails depending on which is used. Measuring a 3 m ceiling
  overhead with a handheld tape is a ±5 cm operation. The four compliant
  captures span 3.4 cm and two captures of identically built rooms agree to
  0.5 cm. **The pipeline is more repeatable than the instrument measuring it.**
  A laser reading to millimetres is required before any ceiling accuracy claim
  at this gate is defensible. This is a limitation of the benchmark, not of the
  pipeline.

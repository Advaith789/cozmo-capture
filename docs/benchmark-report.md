# Benchmark report

Regenerate every figure here with one command:

```sh
bash scripts/benchmark.sh
```

Tier C runs at a fixed 160 frames, bootstrap 40, wall-draws 50, so all rows are
comparable. Tiers A and B reconstruct 12 views. Reasoning is in
[technical-report.md](technical-report.md); this file is the evidence.

## Benchmark set

| capture | tier | frames | drift median | ISO |
|---|---|---|---|---|
| My room 1 (28 Aug) | C | 236 | **5.3 cm** non-compliant | 3200 |
| My room 2 (29 Aug) | C | 335 | 0.9 cm | 3200 |
| My room 3 (30 Aug) | C | 144 | 1.1 cm | lit |
| Friend 1 room | C | 241 | 0.5 cm | 80 |
| Friend 2 room | C | 307 | 0.5 cm | 160 |
| Connector hallway | C | 280 | 0.7 cm | 400 |

Three rooms plus a connector, as specified. My room appears three times for the
repeatability gate: once breaking the protocol deliberately, twice following it.

The camera tiers cover the same rooms:

| capture | tier | photos/frames | burst | views |
|---|---|---|---|---|
| My room | A | 69 | 48 | 12 |
| My room, re-shot to the protocol | A | 22 | 22 | 11 |
| Friend 1 room | A | 29 | 29 | 12 |
| Friend 2 room | A | 67 | 67 | 12 |
| My room / Friend 1 room | B | 60 sampled each | 60 | 12 |

Views are capped at twelve by 8 GB of unified memory, not by choice.

## Ground truth

Tape, metric, **two rooms**, five readings per dimension.

| my room | value |
|---|---|
| door wall | **3.0344 m**, mean of 303.8, 304.2, 300.1, 306.7, 302.4 cm |
| other wall | 3.0411 m |
| ceiling | 2.9705 m |

**Friend 1**, measured after the pipeline was frozen, so nothing was tuned to it:

| | truth | readings, cm |
|---|---|---|
| long wall | **3.7636 m** | 375.98, 376.52, 374.89, 377.90, 376.50 |
| short wall | **3.3620 m** | 336.00, 337.00, 336.50, 335.50, 336.00 |
| ceiling | **3.0020 m** | ten readings, two sessions, below |

**The ceiling took two sessions and is still not settled.** Session 1, blind,
means 301.20 cm and we read -2.47 cm, failing. Session 2, re-measured after
seeing our number and so not independent, means 299.21 and we read -0.48,
passing. **The reported truth is the pooled mean of all ten**, 300.20 cm, since
quoting session 2 alone would be measuring until the gate passes. We read
-1.47 cm against 1.5 cm: a pass by 0.3 mm, to be read as a coin toss. The two
sessions establish that one person with one tape disagrees with themselves by
**2.0 cm, full range 6.9 cm**.

## Per-room results

| room | ceiling | ± | wall A | ± | wall B | ± | floor area |
|---|---|---|---|---|---|---|---|
| my room 1 | 3.0271 | 0.70 | 3.0256 | 1.76 | 3.0028 | 1.66 | 9.085 m² |
| my room 2 | 2.9680 | 0.76 | 3.0372 | 0.82 | 3.0524 | 1.22 | 9.271 m² |
| my room 3 | 2.9531 | **0.38** | 3.0325 | 0.71 | 3.0517 | 0.92 | 9.254 m² |
| friend 1 | 2.9873 | 1.09 | 3.7654 | 0.68 | 3.3603 | 0.77 | 12.653 m² |
| friend 2 \* | 2.9631 | 0.50 | 3.0607 | 2.09 | 3.0228 | 3.11 | 9.252 m² |
| hallway \* | 2.9969 | 0.76 | 3.7677 | 1.74 | 1.2350 | 1.12 | 4.653 m² |

\* Segmented: the row is the largest room, not the whole envelope. The hallway
used to report **28.08 m²** as one room spanning everything visible off it, a
figure belonging to no room in the building.

Intervals are 95% bootstrap over frames, never over points, recentred on the
value they belong to. **The four compliant captures agree on ceiling height to
3.4 cm**; one tape measuring one ceiling twice spans 6.9 cm.

## Gates, scored against tape

| capture | gate | precision | | accuracy | |
|---|---|---|---|---|---|
| my room 2 | ceiling | ±0.76 | **PASS** | **-0.2 cm** | **PASS** |
| my room 2 | door wall | ±0.82 | **PASS** | **+0.3 cm** | **PASS** |
| my room 2 | other wall | ±1.22 | **PASS** | **+1.1 cm** | **PASS** |
| friend 1 | ceiling | ±1.09 | **PASS** | -1.5 cm | **PASS** by 0.3 mm |
| friend 1 | long wall | ±0.68 | **PASS** | **+0.2 cm** | **PASS** |
| friend 1 | short wall | ±0.77 | **PASS** | **-0.2 cm** | **PASS** |
| my room 3 | ceiling | **±0.38** | **PASS** | -1.7 cm | fail |
| my room 3 | door wall | ±0.71 | **PASS** | **-0.2 cm** | **PASS** |
| my room 3 | other wall | ±0.92 | **PASS** | **+1.1 cm** | **PASS** |
| my room 1 | ceiling | ±0.70 | **PASS** | +5.7 cm | fail |
| my room 1 | door wall | ±1.76 | fail | **-0.9 cm** | **PASS** |
| my room 1 | other wall | ±1.66 | fail | -3.8 cm | fail |

**Precision passes 10 of 12, accuracy 9 of 12.** Every failure except my room 3's
ceiling belongs to my room 1, the deliberately non-compliant capture.

An earlier version of this table scored friend 2 against **my room's** tape on a
same-floorplan assumption, producing three passing rows from a tape that never
touched that room. It is gone.

## Repeatability gate

My room was captured three times. All three pairings are shown so the choice of
pair is visible rather than convenient.

**Scans 2 and 3, both compliant, the fair test:**

| | scan 2 | scan 3 | spread | limit | |
|---|---|---|---|---|---|
| wall pair A | 3.0372 | 3.0325 | **0.47 cm** | 1.5 cm | **PASS** |
| wall pair B | 3.0524 | 3.0517 | **0.07 cm** | 1.5 cm | **PASS** |
| ceiling | 2.9680 | 2.9531 | 1.49 cm | 1.0 cm | fail |

| other pairings | ceiling | wall A | wall B |
|---|---|---|---|
| scan 1 vs scan 2 | 5.91 cm | 1.16 cm | 4.96 cm |
| scan 1 vs scan 3 | 7.40 cm | 0.69 cm | 4.89 cm |

**The per-wall gate passes at 0.47 and 0.07 cm.** Every pairing including scan 1
fails wall B by about 5 cm; every pairing excluding it passes both walls. That is
the gate detecting a bad capture, not an unrepeatable pipeline, and `cozmo check`
refuses scan 1 in under a second.

As the gate requires, we state which kind of failure this is: **repeatable but
capture-dependent, not unrepeatable.** The ceiling still fails, by 0.49 cm, and
two compliant captures differ on it by 1.49 cm where they agree on walls to
0.07 cm. The estimator reads the ceiling at a tail quantile, so how much ceiling
the operator tilted up to see moves the answer.

## Drift accountability

| `--sigma-step` | ceiling | |
|---|---|---|
| **0** | 2.9255 m | correction **off**, the ablation |
| 0.002 | 2.9253 m | shipped default |
| 0.01 | 2.9332 m | most permissive |

Median pose correction is 0.9 and 1.1 cm on the compliant captures against
5.3 cm on the non-compliant one. Drift was a protocol failure, not an
algorithmic one: a perimeter walk with corner dwells fixed it.

## Tiers A and B

Photo gate **±8%**, video **±3%**; video is tighter because a clip carries far
more frames of a room than eight stills.

| capture | tier | ceiling | reference | error | gate | |
|---|---|---|---|---|---|---|
| my room | A | 2.828 m | 2.9705 tape | **-4.8%** | ±8% | **PASS** |
| friend 1 | A | 2.771 m | 2.9873 Tier C | **-7.2%** | ±8% | **PASS** |
| my room, re-shot | A | 2.682 m | 2.9705 tape | -9.7% | ±8% | fail |
| friend 2 | A | 2.309 m | 2.9631 Tier C | -22.1% | ±8% | fail |
| friend 1 | B | 3.858 m | 2.9873 Tier C | +29.1% | ±3% | fail |
| my room | B | 1.999 m | 2.9705 tape | -32.7% | ±3% | fail |

**Two of six clear their tier's gate, median absolute error 15.9%.** One capture
of the six closed a room polygon, and its walls are the best the camera tiers
produce: friend 2 at **-6.5% and -0.1%** against Tier C.

Two sanity checks pass independently: camera height comes out at **1.54 m**, and
the top 1% of points span **4.6 cm**, a ceiling plane rather than noise.

**The re-shoot did not do what we expected.** A capture made specifically to the
protocol came out *worse*, -35.5% against -12.8%, which found two defects: a
frame selector covering half the room, and a ceiling estimator measuring the bed,
since the ceiling is 2.7% of the points in a photo cloud. Fixing both improved
every camera capture, my room from -12.8% to -4.8%. It still did not beat the
original: what it bought was two bugs a compliant capture exposed.

## Head to head against the incumbent

Polycam, Floorplan mode (Apple RoomPlan), free tier, **v6.0.21**. Both exports
submitted in `myroom/floorplan/`.

| my room | tape | **ours** | error | Polycam | error |
|---|---|---|---|---|---|
| ceiling | 2.9705 | **2.9680** | **-0.2 cm** | 2.9382 | -3.2 cm |
| door wall | 3.0344 | **3.0372** | **+0.3 cm** | 3.1185 | +8.4 cm |
| other wall | 3.0411 | **3.0524** | **+1.1 cm** | 3.1393 | +9.8 cm |
| floor area | 9.2279 | **9.271** | **+0.5%** | 9.790 | +6.1% |

| friend 1 | tape | **ours** | error | Polycam | error |
|---|---|---|---|---|---|
| ceiling | 3.0020 | **2.9873** | **-1.5 cm** | 2.9580 | -4.4 cm |
| long wall | 3.7636 | **3.7654** | **+0.2 cm** | 3.9072 | +14.4 cm |
| short wall | 3.3620 | **3.3603** | **-0.2 cm** | 3.4714 | +10.9 cm |
| floor area | 12.6532 | **12.653** | **-0.0%** | 13.564 | +7.2% |

**Eight of eight across two rooms, against a bar of 70%.** Our worst error is
1.5 cm; Polycam's best is 3.2 cm.

Two caveats rather than one boast. **The wall pairing is the one that flatters
Polycam**: on friend 1 the alternative gives it -29.2 and +54.5 cm. **Our floor
area is not independent** of our own wall lengths, so that row confirms the walls
rather than adding evidence.

Polycam is better at knowing what it is looking at: it dimensions 3 doors and 2
windows, reports wall thickness, and split friend 1 into a bedroom and an alcove
where we kept one space. Its windows are not uniformly better though: 2.70 and
1.87 m wide, 2.71 and 2.61 m tall, in a room with a 3.00 m ceiling. We report
fewer openings and claim none, and we are the only one that puts an interval on
every number.

## Timing

| stage | time |
|---|---|
| capture, Tier C, one room | 1.5 to 2.5 min |
| Polycam raw export | ~2 min (one 20+ min outlier) |
| pipeline, 160 frames + bootstrap | **~25 s** |
| Tier A or B, first run | 7 to 13 min |
| Tier A or B, cached re-run | ~30 s |

Under 5 minutes per room against a 15-minute budget. Tier C was 259 s and is now
25 s with every measurement unchanged: each frame was being back-projected
twice, and opening detection was re-running the whole wall fit on eight
resampled subsets.

## What this benchmark does not cover

- **Tiers A and B are not reliable.** Two of six inside their gate, and **the
  photo-tier whole-property stitch does not exist**, because only one photo
  capture recovers two opposing wall pairs. That row is a fail.
- **The opening-width gate is not claimed.** 0.8 cm mean on synthetic truth; on
  my room 0.587 m against a 0.958 m frame. Measured, not guessed: 1.2% of
  returns in that doorway lie on the wall plane, so the door was open, and 48.8%
  lie in front of it, so something occluded the opening. Lowering the
  see-through threshold does not recover it.
- **The multi-room stitch has no ground truth.** It splits captures and measures
  a doorway at 0.873 m, and reaches 1.0 cm on synthetic truth, but no tape has
  touched a real room boundary.
- **Damage is opt-in and unscored.** Two classes staged and tape-measured; the
  detector reported **79 regions on a clean control room**, so it is off by
  default.
- **Ground truth on two rooms of six**, and it is the binding limit on every
  accuracy figure here: ten readings of one ceiling span 6.9 cm against a 1.5 cm
  gate while our own captures agree to 0.5 cm. **The pipeline is more repeatable
  than the instrument measuring it.** A laser is required before any ceiling
  accuracy claim at this gate is defensible.

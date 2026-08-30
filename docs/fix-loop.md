# Fix loop declaration

All figures below are from runs at a fixed 160 frames, bootstrap 40
wall-draws 50, so before and after are directly comparable.

## 1. The single worst-performing gate, with the failing number

**Repeatability.** Two captures of the same room at the same tier must agree
within 1 cm, or 0.5% per wall. Wall pair B disagreed by **16.7 cm**, eleven times
over, on the one room where we hold tape. Same room, same phone, same app, same
lighting. Nothing in the pipeline differed.

## 2. Root-cause hypothesis, and the evidence for it

**Hypothesis: the variance is in the capture, not the pipeline. Scan 1 did not
follow our own protocol and pose quality collapsed.**

Polycam ships both raw ARKit poses and globally optimised ones, so the distance
the optimiser moved each camera is a direct measurement of drift:

| | scan 1 | scan 2 |
|---|---|---|
| drift, median | **5.3 cm** | **0.9 cm** |
| drift, max | 42.2 cm | 9.2 cm |
| keyframe rate | 95 /min | 194 /min |

Scan 1 was captured standing central and panning, which is close to pure
rotation and constrains translation poorly, so error compounds along the walk.
Scan 2 walked the perimeter with corner dwells.

Two measurements rule out the alternatives. **Not lighting:** ISO was pinned at
3200 in both, so the 6x drift reduction came with no extra light. **Not the
sensor:** within-frame plane residual is 0.55 cm on the floor and 0.80 cm on the
ceiling, while the between-frame spread was 4.22 cm. The error was all in poses.

## 3. The fix shipped, and the number predicted after it

**Shipped:** protocol section 5 rewritten around a perimeter walk with corner
dwells and a loop-back, **and** an automated compliance check at ingest
(`cozmo check`) scoring angular velocity, ISO, tracking breaks, frame budget and
the drift the optimiser had to remove. The protocol could always be ignored;
what changed is that ignoring it is now visible in under a second.

**Predicted:** drift median below 2 cm, and the ceiling-height gate moving from
fail to pass on both precision and accuracy.

**Measured**, both scans re-run with the final pipeline:

| | scan 1, non-compliant | scan 2, compliant | gate |
|---|---|---|---|
| drift, median | 5.3 cm | **0.9 cm** | |
| ceiling precision | ±0.70 cm PASS | ±0.76 cm PASS | 1.5 cm |
| **ceiling accuracy** | +5.7 cm FAIL | **-0.2 cm PASS** | 1.5 cm |
| **wall precision A** | ±1.76 cm FAIL | **±0.82 cm PASS** | 1.5 cm |
| **wall precision B** | ±1.66 cm FAIL | **±1.22 cm PASS** | 1.5 cm |
| **wall accuracy B** | -3.8 cm FAIL | **+1.1 cm PASS** | 1.5 cm |

Prediction met: drift fell 6x and **four gates moved from fail to pass**.

---

*The declaration ends here. What follows is the evidence the brief also asks
for: the second fix, how to regenerate both runs, and the post-mortem.*

## Regenerating both runs

Both are in `scripts/benchmark.sh` and run with everything else, or singly:

```sh
cozmo run "myroom/space_capture/8_28_2026 - My room 1.zip" --name myroom1 \
  --frames 160 --truth-height 2.9705 --truth-walls 3.0344,3.0411

cozmo run "myroom/space_capture/8_29_2026 - My room 2.zip" --name myroom2 \
  --frames 160 --truth-height 2.9705 --truth-walls 3.0344,3.0411
```

The readable diff is `out/myroom1.json` against `out/myroom2.json`: every
measurement carries its interval and the provenance chain that produced it, so
the difference between the two runs is inspectable line by line rather than
summarised. `cozmo check` on each shows the 5.3 cm and 0.9 cm that caused it.

## 4. The second fix, shipped after the first

The protocol fix addressed drift. It could not touch the other half of the
16.7 cm: **wall-length accuracy stayed wrong**, +11.8 cm on the affected pair.

**Root cause.** We measure rooms with the doors open, as the protocol requires.
The scan sees through the doorway and a surface beyond it becomes a candidate
wall outside the real one; which candidate wins shifts with frame count. The
evidence needed no ground truth: on that axis the floor slab spans **4.05 m in a
3.0 m room**, and two physically identical rooms disagreed by 12.3 cm on that one
axis while agreeing within 1 cm on every other.

**Shipped, in two parts.** The wall band was raised above furniture and above
the points spraying through an open doorway, and room segmentation now splits a
capture at its doorways so a surface next door cannot be a candidate here.

*The code fix*, on the identical pairing the declaration used, so only code
changed:

| | before | after | gate | |
|---|---|---|---|---|
| wall pair A, scan 1 vs 2 | 7.3 cm | **1.2 cm** | 1.5 cm | **PASSES** |
| wall pair B, scan 1 vs 2 | 16.7 cm | 5.0 cm | 1.5 cm | still fails |
| affected wall, vs tape | +11.8 cm | **+1.0 cm** | 1.5 cm | **PASSES** |

*A third capture*, taken later and following the protocol, so the gate is finally
measured between two comparable captures:

| | scan 2 | scan 3 | spread | gate | |
|---|---|---|---|---|---|
| wall pair A | 3.0372 | 3.0325 | **0.47 cm** | 1.5 cm | **PASSES** |
| wall pair B | 3.0524 | 3.0517 | **0.07 cm** | 1.5 cm | **PASSES** |
| ceiling | 2.9680 | 2.9531 | 1.49 cm | 1.0 cm | still fails |

**Declared at 16.7 cm, now 0.07 cm on the gate as written.** Both halves are
shown so the reader can see which was engineering and which was a better
capture, and the pairing including the non-compliant scan stays in the benchmark
rather than being dropped.

**Where it still falls short.** Ceiling spread fails at 1.49 cm against 1 cm, and
scan 3's ceiling accuracy is -1.7 cm where scan 2's is -0.2 cm. Two compliant
captures agree on walls to 0.07 cm and on the ceiling only to 1.5 cm, because the
estimator reads the ceiling at a tail quantile and how much ceiling the operator
tilted up to see moves the answer. That is the next thing to fix.

## Post-mortem: a prediction we got wrong

Before the protocol hypothesis we predicted that **fitting planes per frame and
pooling would fix the ceiling gate**. It did not: per-frame fitting made the
interval *worse*, ±2.60 cm against ±1.36 cm pooled, because each frame sees too
little of a surface to fit it well and the spread between frames then dominates.

| hypothesis | test | result |
|---|---|---|
| per-frame plane fitting | `--method per_frame` | **worse**, ±2.60 cm |
| pooled fitting | `--method pooled` | ±1.36 cm |
| plane-anchored drift solve | `--method drift` | ±2.09 cm |

The prediction was wrong in the useful direction. It established that the error
was **between** frames rather than within them, which is what pointed at pose
quality and therefore at the capture, and that became the fix that worked. The
ablation switches are still in the CLI so the wrong answer stays reproducible
alongside the right one.

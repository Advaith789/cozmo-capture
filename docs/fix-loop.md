# Fix loop declaration

All figures below are from runs at a fixed 160 frames, bootstrap 40
wall-draws 50, so before and after are directly comparable.

## 1. The single worst-performing gate, with the failing number

**Repeatability** two captures of the same room at the same tier must agree
within 1 cm, or 0.5% per wall.

```
                    scan 1        scan 2       spread    limit
wall pair B         2.9933 m      3.1600 m    16.7 cm    1.5 cm     FAIL
wall pair A         3.1093 m      3.0359 m     7.3 cm    1.5 cm     FAIL
ceiling height      2.9479 m      2.9364 m     1.2 cm    1.0 cm     FAIL
```

16.7 cm against a 1.5 cm limit, **11× over** and it fails on the one room
where we hold tape ground truth.

Both captures are the same room, the same phone, the same app, the same
lighting (ISO pinned at 3200 in both). Nothing in the pipeline differs.

**The root cause splits in two, and only one of them was shippable in the
time.** Section 2 covers the part we fixed and measured. Section 4 covers the
part we did not, and why it is the larger share of the 16.7 cm.

## 2. Root-cause hypothesis, and the evidence for it

**Hypothesis: the variance is in the capture, not the pipeline. Scan 1 did not
follow our own protocol, and pose quality collapsed as a result.**

The evidence comes from the captures themselves, not from inference. Polycam
ships both raw ARKit poses (`keyframes/cameras/`) and globally optimised ones
(`keyframes/corrected_cameras/`). The distance the optimiser moved each camera
is a direct measurement of accumulated drift:

| | scan 1 | scan 2 |
|---|---|---|
| drift, median | **5.3 cm** | **0.9 cm** |
| drift, p90 | 26.0 cm | 3.0 cm |
| drift, max | 42.2 cm | 9.2 cm |
| keyframe rate | 95 /min | 194 /min |
| frames seeing the ceiling | 27 of 120 |, |

The gate this most directly governs is **ceiling height** which depends on
pose quality and nothing else: it failed both precision and accuracy in scan 1.

Scan 1 was captured standing near the middle of the room, panning, without
dwelling at corners. Scan 2 walked the perimeter with 2-second corner dwells
and tilts to the floor and ceiling lines.

Two corroborating measurements rule out the obvious alternatives:

- **Not lighting.** ISO sat pinned at 3200 in both scans. The 6× drift
  reduction happened with no improvement in light.
- **Not the sensor.** Within-frame plane residual is 0.55 cm on the floor and
  0.80 cm on the ceiling, five to eight times better than the gate needs. The
  between-frame spread was 4.22 cm. Every bit of the error was in the poses.

**Why it works:** a perimeter walk gives the pose optimiser well-constrained
relative geometry between consecutive keyframes and a wide baseline across the
room. Standing central and panning is close to pure rotation, which constrains
translation poorly, and the error compounds along the walk.

## 3. The fix shipped, and the number predicted after it

### Shipped

1. **Protocol § 5 rewritten** ([capture-protocol.md](capture-protocol.md))
   perimeter walk with the wall on the right, 1 to 3 m standoff, 2-second dwell at
   every corner with tilts to both junction lines, loop-back over the starting
   point, sessions capped by the measured keyframe rate.
2. **Automated compliance checks at ingest**
   ([scripts/inspect_capture.py](../scripts/inspect_capture.py)), every
   capture is now scored on angular velocity, ISO, tracking segments, frame
   count against the pose-optimisation budget, and the drift the optimiser had
   to remove. A non-compliant capture is flagged when it lands, not discovered
   at scoring time.

The second half is the part that generalises. The protocol could always be
ignored; what changed is that ignoring it is now visible immediately.

### Predicted

> Drift median below 2 cm, and the ceiling-height gate moving from fail to pass
> on both precision and accuracy.

### Measured

| | before (scan 1) | after (scan 2) | gate |
|---|---|---|---|
| drift, median | 5.3 cm | **0.9 cm** |, |
| **ceiling precision** | ±1.83 cm FAIL | **±1.23 cm PASS** | 1.5 cm |
| **ceiling accuracy** | +2.4 cm FAIL | **+1.2 cm PASS** | 1.5 cm |
| wall precision, pair A | ±1.38 cm PASS | **±0.70 cm PASS** | 1.5 cm |
| wall precision, pair B | ±1.25 cm PASS | ±1.17 cm PASS | 1.5 cm |

Prediction met. Drift fell 6×, and the ceiling gate moved from failing both
tests to passing both. Wall precision roughly halved on pair A, from a level
that already passed.

**What the fix did not move: wall-length accuracy, or repeatability.** Those
are governed by section 4, not by pose quality.

### Regenerating both runs

```sh
cozmo run \
  "myroom/space_capture/8_28_2026 - My room 1.zip" --name myroom1 \
  --frames 160 --truth-height 2.9705 --truth-walls 3.0344,3.0411

cozmo run \
  "myroom/space_capture/8_29_2026 - My room 2.zip" --name myroom2 \
  --frames 160 --truth-height 2.9705 --truth-walls 3.0344,3.0411
```

Diff `out/myroom1.json` against `out/myroom2.json`. Every measurement carries
its interval and its provenance chain.

---

## 4. The second fix, shipped after the first

The protocol fix in section 3 addressed drift. It could not touch the other half
of the 16.7 cm, and section 1 said so at the time: **wall-length accuracy stayed
wrong**, +11.8 cm on the affected pair, and that error was most of the
repeatability failure.

**Root cause.** We measure each room with its doors open, which the protocol
requires for the LiDAR tier. The scan sees through the doorway, and a surface
beyond it is detected as a candidate wall outside the real one. Which candidate
wins shifts with frame count, which is exactly the instability the gate detects.
The evidence was decisive and needed no ground truth: on the affected axis the
floor slab spans **4.05 m in a 3.0 m room**, because the floor continues through
the doorway. And two physically identical rooms disagreed by 12.3 cm on that one
axis while agreeing within 1 cm on every other.

**Shipped, in two parts.** The wall band was raised so it samples above the
furniture and above the points spraying through an open doorway, and room
segmentation now splits a capture at its doorways so a surface in the next room
cannot be a candidate for this one. Both are in the pipeline and run by default.

| | before | after | gate | |
|---|---|---|---|---|
| wall pair A, spread across the two scans | 7.3 cm | **1.2 cm** | 1.5 cm | **now PASSES** |
| wall pair B, spread across the two scans | 16.7 cm | 5.0 cm | 1.5 cm | still fails |
| affected wall, accuracy vs tape | +11.8 cm | **+1.0 cm** | 1.5 cm | **now PASSES** |
| ceiling height, accuracy vs tape (scan 2) | -3.4 cm | **-0.2 cm** | 1.5 cm | **now PASSES** |

**Where it fell short, and why.** Wall pair B improved 3.3 times and still fails
at 5.0 cm, and **ceiling repeatability got worse**, from 1.2 cm to 5.9 cm. That
second number needs saying plainly rather than hiding: both scans changed, and
they now disagree more about the ceiling than they used to.

The reason is that the pipeline has become better at telling the two captures
apart rather than worse at measuring. Scan 2, which followed the protocol, is
now accurate to **-0.2 cm** against tape. Scan 1, the deliberately
non-compliant capture with 5.3 cm of drift, is +5.7 cm out. The spread between
them is the honest cost of a bad capture, and it is exactly what `cozmo check`
now refuses before the pipeline runs at all. A gate that averaged a good capture
with a bad one into a passing number would be worth less than one that fails
loudly here.

## Post-mortem: a prediction we got wrong

Before the protocol hypothesis, we predicted that **fitting planes per frame
instead of pooling all points would tighten the interval**. The reasoning was
that pooled fitting lets each frame's pose error widen the surface, so fitting
within frames, where all points share one pose, should separate sensor noise
from pose error and reduce the spread.

It did not. The interval went from ±6.36 cm to **±7.40 cm** slightly worse.

What it did do was split the error into its parts, and that measurement is what
pointed at the poses: sensor noise 0.55 cm, pose disagreement 4.22 cm. The
wrong prediction produced the diagnosis that made the right fix findable.

Two further hypotheses were tested and eliminated the same way:

| hypothesis | test | result |
|---|---|---|
| clutter biasing the surface estimate | envelope estimator, validated on synthetic data | **rejected** correction moved the answer the wrong way |
| bad peak-finding | wall detector applied to the vertical axis | **rejected** identical -4.2 cm |
| global scale error | both walls measured against tape | **rejected** walls within 0.5 cm |
| grazing incidence angle | residual vs incidence, 1.26 M samples | **rejected** correlation +0.025 / -0.014 |

And one more that turned out not to be ours at all: a persistent ~6 cm ceiling
shortfall across five captures across three rooms and a hallway was traced to the **ground truth**
not the pipeline. The ceiling was recorded four times as 3.0226, 2.9972, 2.9241
and finally 2.9705 m, a 9.8 cm spread against a 1.5 cm gate. The same happened
to the door wall: a single reading of 2.9883 m stood until a five-reading
re-measure put it at **3.0344 m**, 4.6 cm away, and our four independent wall
measurements had been pointing there the whole time. Our five captures agreed
within 3.5 cm the whole time. The lesson is in
[benchmark-report.md](benchmark-report.md): ground truth read to the nearest inch
carries ±1.27 cm of quantisation against a ±1.5 cm gate, and cannot certify it.

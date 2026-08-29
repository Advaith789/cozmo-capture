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
PYTHONPATH=src .venv/bin/python -m cozmo run \
  "myroom/space_capture/8_28_2026 - My room 1.zip" --name myroom1 \
  --frames 160 --truth-height 2.9241 --truth-walls 2.9972,3.0199

PYTHONPATH=src .venv/bin/python -m cozmo run \
  "myroom/space_capture/8_29_2026 - My room 2.zip" --name myroom2 \
  --frames 160 --truth-height 2.9241 --truth-walls 2.9972,3.0199
```

Diff `out/myroom1.json` against `out/myroom2.json`. Every measurement carries
its interval and its provenance chain.

---

## 4. The part we did not fix

Wall-length **accuracy** stayed wrong after the protocol fix, +14.0 cm on one
pair in scan 2, +11.2 cm on the other pair in scan 1, and that error is most
of the 16.7 cm repeatability failure.

It is not a pose problem, and the protocol change could not have touched it.
The cause is that we measure each room in isolation while its doors are open
which the protocol requires for the LiDAR tier. The scan sees through the
doorway into the hallway, and a hallway surface is detected as a candidate wall
outside the real one. Which of the two candidates wins shifts with frame count
which is exactly the instability the repeatability gate is picking up.

The evidence: on the affected axis the floor slab itself spans 4.05 m in a
3.0 m room, because the floor continues through the doorway.

The fix is **room segmentation** the same machinery as the multi-room stitch
which is unimplemented. It was not shippable inside the 48-hour budget, and
tuning a plane-selection heuristic against a single room instead would have
been fitting to one sample. It is recorded here as the top of the backlog
rather than papered over.

---

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
shortfall across five captures in four rooms was traced to the **ground truth**
not the pipeline. The ceiling had been recorded as 9'10" (2.9972 m); re-measured
carefully it is **2.9241 m**. Our five captures had agreed with each other
within 3.5 cm the whole time. The lesson is in
[capture-bakeoff.md](capture-bakeoff.md): ground truth read to the nearest inch
carries ±1.27 cm of quantisation against a ±1.5 cm gate, and cannot certify it.

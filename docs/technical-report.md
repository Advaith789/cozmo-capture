# Technical report

**cozmo-capture** — handheld consumer capture to a dimensioned floor plan with
a calibrated interval on every measurement. Route 2, stock tooling.

Built in 48 hours. Tier C is complete end to end; Tiers A and B are captured
but unprocessed. What follows states what was built, what it measures, and what
it does not do.

---

## 1. Architecture

The three input tiers differ only in how much they know. They converge on one
intermediate representation as early as possible, so everything downstream is
written once:

```
  Polycam raw zip ──→ ingest.lidar ──┐
  .mov walkthrough ─→ ingest.video ──┼──→  Capture[PosedFrame]
  room photo dirs ──→ ingest.photos ─┘            │
                                                  ▼
                                       scale ── (tiers A/B only)
                                                  │
                                                  ▼
                       drift ──→ planes ──→ rooms ──→ openings ──→ stitch
                                                  │
                                                  ▼
                                   uncertainty ──→ contract ──→ JSON + plan
```

`PosedFrame` carries depth, confidence, intrinsics, pose — and, critically, the
*provenance* of each: `depth_source ∈ {MEASURED, INFERRED, NONE}` and
`pose_source ∈ {DEVICE_OPTIMISED, DEVICE_RAW, SFM, NONE}`.

**Three decisions we would defend.**

**Provenance travels with every number.** A measurement is never a bare float;
it carries the chain that produced it. The interval engine is then a function
of `(value, provenance, calibration)`. This makes "intervals widen as sensor
data thins" a structural property rather than three per-tier special cases, and
lets a photo-tier and a LiDAR-tier figure sit in the same JSON without either
misrepresenting itself. Every `Measurement` in the output carries its
provenance list; a fallback interval is labelled `interval:ASSUMED_*` so an
assumed number can never pass as a measured one.

**Drift correction is a stage with a parameter, not a branch.** The ablation the
brief requires is `--ablate`, and the correction strength `σ_step` sweeps
continuously to zero, which *is* the uncorrected case. No code path rots.

**The determinism boundary sits above damage.** Ingest through stitch is
deterministic and offline, which is what the repeatability gate measures. The
`.env` holds an OpenAI key intended for damage classification only; no geometry
path reads it. That layer is unbuilt, so nothing in this submission calls a
model at all.

**Deliberate duplication.** `scripts/inspect_capture.py` re-implements PNG
decoding in pure stdlib so the field tool runs on a clean machine with nothing
installed, the moment a capture lands. The pipeline's copy uses numpy. The two
are held to identical output by test.

---

## 2. Tier design and device matrix

| Tier | Hardware | Tool | What reaches the pipeline | Scale | Status |
|---|---|---|---|---|---|
| A · Photos | iPhone 15+ | native Camera | 6–8 HEIC/JPEG per room, EXIF intrinsics. No depth, no poses. | inferred | **not built** |
| B · Video | iPhone 15+ | native Camera 1080p60 | one continuous clip; poses must be recovered | recovered | **not built** |
| C · LiDAR | iPhone 15 Pro+ | Polycam Space, dev mode | 1024×768 RGB, 256×192 16-bit mm depth, confidence, intrinsics, loop-closed poses, per-frame IMU/exposure metadata | metric | **built** |

Polycam is used **only** at Tier C, and only as a sensor logger — its
reconstruction is never consumed. Tiers A and B use the native camera, which
the brief explicitly permits. That is not a stylistic choice: Polycam's raw
export exists only for LiDAR-mode captures on LiDAR devices, so on a base
iPhone 15 it yields nothing a pipeline can read, and its Image mode uploads to
Polycam's cloud to reconstruct — which would be shipping their product, not
ours. The native camera also gives 5712×4284 against Polycam's downsampled
1024×768.

**The file contract was derived, not assumed.** We opened a real export before
writing any ingest. The published format documentation was wrong in five
places: no wrapping folder, no `raw.glb`, no `corrected_images/`, confidence
levels are 0/54/255 rather than 0/127/255, and frames are named by microsecond
timestamp rather than sequentially. The export also carries nine undocumented
per-frame fields — `tracking_segment`, `angular_velocity`, `blur_score`, `iso`,
`exposure_time`, `thermal_state` among them — and `corrected_cameras/` drops all
of them, so ingest joins the two folders by filename stem: corrected pose, raw
metadata.

Those fields make the capture protocol **auditable**. Compliance is no longer a
request; `inspect_capture.py` scores every capture on panning speed, lighting,
tracking continuity and frame budget when it lands.

---

## 3. Drift handling

Poses are not used as supplied — the brief counts that as an automatic fail,
and Polycam's optimised poses are its correction, not ours.

Measuring the distance Polycam's optimiser moved each camera gives drift
directly. On a non-compliant capture: median 5.3 cm, p90 26.0 cm, max 42.2 cm,
over 2.5 minutes in a single room. Raw ARKit poses are unusable alone.

`geometry/drift.py` implements plane-anchored correction: per-frame vertical
corrections `d_i` solved jointly with the floor and ceiling plane heights,

```
min  Σ_floor w_i(f_i + d_i − F)² + Σ_ceil w_i(c_i + d_i − C)²
   + Σ_i (d_i − d_{i−1})²/σ_step² + gauge
```

weighted by each frame's own plane residual.

**The temporal prior is load-bearing, not decorative.** Of 120 keyframes, 67
saw only the floor, 26 only the ceiling, and **1 saw both**. Without a term
linking frames through time, the floor and ceiling observations form two
disconnected components and the distance between them — the measurement itself
— is unobservable. `σ_step` has physical meaning: metres of drift permitted
between consecutive keyframes.

Ablation, one command:

| σ_step | height | |
|---|---|---|
| 1e-6 | 2.8860 m | correction off |
| 1e-3 | 2.9461 m | |
| 2e-3 | 2.9621 m | shipped default |
| 1e-2 | 3.0206 m | |

13.5 cm of range on the prior strength, reported because it is true: on a
sparse capture the plane separation is only weakly observable. Better ceiling
coverage is what reduces the dependence, which is a *capture* fix, not an
algorithmic one.

---

## 4. Error budget

Decomposed by fitting planes within frames (one shared pose) versus across them:

| source | magnitude |
|---|---|
| depth sensor, within-frame residual | **0.55 cm** floor, 0.80 cm ceiling |
| pose disagreement, between-frame | **4.22 cm** floor, 4.04 cm ceiling |

The sensor is already five to eight times better than the 1.5 cm gate requires.
**Every centimetre of the error is in the poses** — and these are the
loop-closed ones.

This single measurement redirected the project. Four hypotheses were tested
against it and rejected:

| hypothesis | test | result |
|---|---|---|
| clutter biasing surfaces | envelope estimator, validated on synthetic data to +0.18 cm at 35% clutter | rejected — correction moved the answer the wrong way |
| bad peak-finding | wall detector applied to the vertical axis | rejected — identical −4.2 cm |
| global scale error | both walls measured against tape | rejected — walls within 0.5 cm |
| grazing incidence | residual vs incidence, 1.26 M samples | rejected — correlation +0.025 / −0.014 |

---

## 5. Calibration analysis

**Intervals are bootstrapped over frames, never over points.** Samples within a
frame share that frame's pose error; resampling points would treat 2.2 million
correlated measurements as independent and report an interval of a fraction of
a millimetre for data that disagrees by centimetres. That is precisely the
confident garbage the brief caps a submission for.

The distinction has teeth. Our first wall intervals were hard-coded at ±1.5 cm
— an asserted number. Replacing them with resampling first produced ±1 m,
because draws that mistook a wardrobe for a wall polluted every dimension.
**Detection is a model choice and positional uncertainty is a measurement**;
conflating them makes the interval meaningless. Detection now happens once on
the full capture and only plane positions resample, giving ±0.6–2.2 cm.

**Ground truth precision is part of the calibration story.** An early ceiling
figure recorded to the nearest inch (9'10", 2.9972 m) made five captures across
four rooms look ~6 cm biased. Re-measured carefully it is **2.9241 m** — the
pipeline had been right, and the five captures had agreed with each other
within 3.5 cm throughout. A reading quantised to the nearest inch carries
±1.27 cm against a ±1.5 cm gate and cannot certify it. Two successive readings
of the same wall differed by 2.54 cm, and that alone flipped four gates and
changed which estimator scored best — which is why no estimator was ever
selected by which percentile matched the tape.

---

## 6. Results

All runs at 160 frames, bootstrap 40, wall-draws 50. Tape ground truth on one
room: walls 2.9972 / 3.0199 m, ceiling 2.9241 m.

| capture | gate | precision | accuracy |
|---|---|---|---|
| my room 2 | ceiling height | ±1.23 cm **PASS** | +1.2 cm **PASS** |
| my room 2 | wall pair A | ±0.70 cm **PASS** | +3.9 cm FAIL |
| my room 2 | wall pair B | ±1.17 cm **PASS** | +14.0 cm FAIL |
| my room 1 | ceiling height | ±1.83 cm FAIL | +2.4 cm FAIL |
| my room 1 | wall pair A | ±1.38 cm **PASS** | +11.2 cm FAIL |
| my room 1 | wall pair B | ±1.25 cm **PASS** | −2.7 cm FAIL |

Precision passes 5 of 6. Ceiling heights across four rooms cluster at
2.889–2.948 m, agreeing within 5.9 cm and with the taped ceiling within 1.2 cm.

**Repeatability fails** — 16.7 cm on one wall pair against a 1.5 cm limit. As
the gate requires, we state which kind: **unrepeatable, not
repeatable-but-biased.** Which of two candidate planes wins shifts between
captures and with frame count.

**Head to head** (`docs/head-to-head.md`): against Polycam Floorplan mode
(RoomPlan) on the same room, we beat or tie on **3 of 4 shared dimensions**.
Polycam additionally detects 2 doors, a window and a closet as a separate room;
we detect none of those and score zero on the opening gate.

---

## 7. The fix loop

Full declaration in `docs/fix-loop.md`. In brief: the worst gate was
repeatability. Root cause, evidenced from the capture metadata rather than
inferred, was **protocol non-compliance** — scan 1 was captured standing near
the room centre without corner dwells. Shipped: protocol § 5 rewritten, plus
automated compliance scoring at ingest so a bad capture is flagged on arrival.

Predicted: drift median below 2 cm and the ceiling gate moving to pass on both
axes. Measured: drift **5.3 → 0.9 cm**, ceiling precision **±1.83 → ±1.23 cm**,
ceiling accuracy **+2.4 → +1.2 cm**. Both runs regenerable by one command each.

A prior prediction was wrong and is reported as such: per-frame plane fitting
was predicted to tighten the interval and made it slightly worse (±6.36 →
±7.40 cm). It produced the error decomposition in § 4, which is what made the
real fix findable.

---

## 8. Known failure modes

**Room segmentation is absent, and it is the largest measurement defect.** The
protocol requires doors open for the LiDAR tier, so a scan sees through the
doorway; a hallway surface then competes as a candidate wall outside the real
one. On the affected axis the floor slab spans 4.05 m in a 3.0 m room. This
causes the +14 cm wall error and most of the repeatability failure. The fix is
the same machinery as the multi-room stitch. It was not shippable in 48 hours,
and tuning a plane-selection heuristic against one room instead would have been
fitting to a single sample.

**Tiers A and B are captured but unprocessed.** The walk-in test can only be
served at the LiDAR tier. This is the largest scope gap.

**No opening detection**, so the tightest gate in the brief is unscored.

**No stitched multi-room plan.** Five rooms measured individually; the
whole-property plan the brief calls the product surface does not exist.

**No damage detection.** Two classes were staged and tape-measured — hallway
2×3 in ellipse, friend-2 room 3×3 in square — but nothing consumes them.

**Rectangular-room prior.** `square_up=True` snaps wall normals to the room
axes. It moved wall gates from fail to pass, and it will misreport a genuinely
non-rectangular room. `square_up=False` exists and reports wider intervals.

**Reflective surfaces.** Every room has floor-to-ceiling glass. The protocol
requires blinds closed at Tier C for that reason, which starves the camera —
ISO pinned at 3200 in both captures of one room. Tier C survives it because
LiDAR is active; a camera-only tier would not.

**Ground truth covers one room of five.** The other four report precision only.

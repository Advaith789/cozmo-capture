# cozmo-capture

Handheld consumer capture → dimensioned, stitched whole-property floor plan,
with a calibrated confidence interval on every measurement.

Three input tiers — photos, video, LiDAR — resolve to one identical output
contract. Intervals widen as the sensor data thins, and say so.

**Capture route: Route 2 (stock tooling).** Polycam for the LiDAR tier, the
native iOS Camera for video and photos. See
[docs/capture-protocol.md](docs/capture-protocol.md).

---

## Status

Capture route verified across all three tiers. The Tier C pipeline runs end to
end and produces its first measurement; tiers A and B ingest are not written.

| Step | | |
|---|---|---|
| 1 | Repo scaffold, secrets ignored | done |
| 2 | Export bake-off — verify what the export actually contains | Tier C done; A and B outstanding |
| 3 | One-page capture protocol + device matrix | done, file contract verified |
| 4 | Benchmark set + ground truth | blocked on a tape or laser |
| — | Tier C pipeline: ingest → planes → ceiling height | **runs** |
| 5 | Gates, then the fix loop | not started |
| 6 | Head-to-head vs incumbent | not started |

Measured so far: 95 keyframes/min, so the 700-frame pose-optimisation budget
is 7.3 minutes of scanning. Raw ARKit poses drifted a median 5.3 cm and up to
42 cm over a single 2.5-minute room scan.

First pipeline output, on that scan:

```
ceiling height   2.9638 m [2.8524, 2.9796]  (±6.36 cm, n=60)
gate ≤1.5 cm     FAIL
```

Reported as a failure because it is one. The estimate agrees with Polycam's
independent mesh to 7 cm, which validates the ingest chain, but the interval is
four times the gate. The cause is measured, not guessed: the fitted floor and
ceiling planes are 8–9.5 cm thick, where a real floor is flat to a millimetre.
That thickness is pose error smeared across pooled frames — the leading
candidate for the fix loop.

No accuracy claim is made. The interval above is precision. Whether 2.9638 m is
*correct* needs tape or laser ground truth, which the benchmark step is
waiting on.

Nothing in this repo yet claims an accuracy number. The device matrix columns
read *pending* on purpose — quoting an interval we have not measured is the
specific failure the brief scores against.

---

## What runs today

Python 3.12. No dependencies — the inspector is stdlib-only by design, so
step 2 works on a clean machine with no install step between landing a capture
and reading it.

```sh
# inspect whatever came off the phone
python3 scripts/inspect_capture.py ~/Downloads/<export>.zip     # Tier C
python3 scripts/inspect_capture.py ~/Downloads/<photos>/        # Tier A
python3 scripts/inspect_capture.py ~/Downloads/<clip>.mov       # Tier B

# 21 tests, ~0.1s
python3 -m unittest discover -s tests -v
```

`inspect_capture.py` reports the file tree, frame count against the pose
optimisation budget, whether loop closure actually ran, decoded depth range in
millimetres, the confidence-level histogram, intrinsics, EXIF focal length,
capture duration and keyframe rate, tracking breaks, and **how far global
optimisation moved each camera** — the drift our own correction stage has to
beat. It flags the field mistakes that are expensive to discover late:
Developer Mode left off, a scan too long for pose optimisation, tracking lost
mid-walk, HEIC where JPEG was expected, EXIF stripped in transfer.

The first real export disagreed with Polycam's published format in five places
and carried nine undocumented per-frame fields. Findings are recorded in
[docs/capture-bakeoff.md](docs/capture-bakeoff.md); the protocol's file
contract and session cap now come from that run, not from documentation.

The depth decoder is hand-rolled PNG (no Pillow), so
[tests/test_inspect.py](tests/test_inspect.py) round-trips all five PNG row
filters at both bit depths. A wrong filter branch would not crash — it would
return plausible wrong millimetres, and every measurement downstream would
inherit the error silently.

---

## Architecture

> `ingest.lidar`, `geometry` (planes and height) and the CLI exist. `scale`,
> `drift`, `rooms`, `openings`, `stitch`, `damage`, `uncertainty` and
> `contract` are the shape the next steps build into.

The three tiers differ only in how much they know. They converge on one
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
                                               damage
                                                  │
                                                  ▼
                                   uncertainty ──→ contract ──→ JSON + plan
```

### The common representation

```python
@dataclass
class PosedFrame:
    rgb: NDArray            # H×W×3
    depth: NDArray | None   # H×W metres
    confidence: NDArray | None
    K: NDArray              # 3×3 intrinsics
    T_wc: NDArray | None    # 4×4 world ← camera
    depth_source: DepthSource   # MEASURED | INFERRED | NONE
    pose_source: PoseSource     # DEVICE_OPTIMISED | DEVICE_RAW | SFM | NONE
```

Tier C fills every field from the export — joining `corrected_cameras/` for
pose with `cameras/` for the sensor metadata the corrected files drop. Tier B recovers poses by
structure-from-motion and depth from a monocular model. Tier A does the same
from far fewer views. **The fields are the same; only their provenance
differs** — and that is the fact the rest of the system is organised around.

### Three decisions worth defending

**1 · Provenance travels with every number.** A measurement is never a bare
float. It carries the chain that produced it — measured depth or inferred,
device poses or recovered, fiducial scale or a fixture prior. The interval
engine is then a pure function of `(value, provenance, calibration_table)`,
with the tables fit on our own benchmark. This makes *"intervals widen honestly
as sensor data thins"* a structural property rather than three per-tier
special cases, and it means a photo-tier number and a LiDAR-tier number can sit
in the same JSON without either lying about what it is.

**2 · Drift correction is a stage with a switch, not a step inside pose
loading.** The brief requires an ablation showing the stitched footprint with
correction on and off, and treats using supplied poses as-is as an automatic
fail — which includes Polycam's optimised poses, since those are someone else's
correction, not ours. Keeping `drift` as its own toggleable stage makes the
ablation a config flag rather than a code branch that rots.

**3 · The determinism boundary sits above `damage`.** Everything from ingest
through stitch is deterministic and offline: same capture in, identical
geometry out, which is what the repeatability gate measures. The one model call
is confined to `damage`, behind a content-addressed cache with deterministic
replay and an offline fallback. Geometry never depends on it, so a bad venue
network costs us damage classification, not the floor plan.

### Stitching, per tier

LiDAR and video arrive as one continuous session, so adjacency comes from the
trajectory. Photos do not — per-room folders share no visual overlap, and no
feature matcher will register them. There, stitching is a graph problem: rooms
are nodes, openings are edges, and we solve for rigid transforms that mate door
pairs by width and wall normal without overlapping footprints. The connector
shots in § 3.5 of the protocol exist to supply those edges.

### One command per capture

```sh
PYTHONPATH=src .venv/bin/python -m cozmo measure myroom/8_28_2026.zip
```

Tier is detected from the input shape, not passed in — Tier C runs today, A and
B report that they are unimplemented rather than guessing.

---

## Layout

```
docs/
  capture-protocol.md    the one-page field sheet + device matrix   [step 3]
  capture-bakeoff.md     export verification worksheet              [step 2]
scripts/
  inspect_capture.py     read a raw export and report what it holds
src/cozmo/
  types.py               PosedFrame, Measurement, provenance enums
  io/png.py              vectorised depth/confidence decode
  ingest/lidar.py        Polycam raw -> Capture
  geometry/height.py     floor/ceiling planes, frame-bootstrapped interval
  __main__.py            the one command
tests/
  fixtures.py            synthetic captures — no phone required
  test_inspect.py        21 tests, PNG filters + archive layout
src/cozmo/               pipeline — not yet written
```

---

## Setup

```sh
git clone https://github.com/Advaith789/cozmo-capture
cd cozmo-capture
python3 -m unittest discover -s tests    # nothing to install
```

`.env` holds `OPENAI_API_KEY` for the damage-classification layer only, and is
gitignored — see `.env.example`. No geometry path reads it.

---

## Next

Step 4 is the benchmark set, and it is the gating item: three-plus rooms and a
connector, one furnished room with two damage classes, every room at all three
tiers, one room captured twice at the same tier for repeatability, and tape or
laser ground truth on all of it. Capturing it wrong costs a full re-shoot, so
it happens before any pipeline code.

Step 2's 60-second verification scan should happen first — it confirms the file
contract in § 7 of the protocol before the benchmark capture depends on it.

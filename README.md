# cozmo-capture

Handheld consumer capture → dimensioned, stitched whole-property floor plan
with a calibrated confidence interval on every measurement.

Three input tiers, photos, video, LiDAR, resolve to one identical output
contract. Intervals widen as the sensor data thins, and say so.

**Capture route: Route 2 (stock tooling).** Polycam for the LiDAR tier, the
native iOS Camera for video and photos. See
[docs/capture-protocol.md](docs/capture-protocol.md).

---

## Status

Tier C runs end to end: capture → ingest → walls → ceiling → room → JSON +
rendered plan, one command, with a bootstrapped interval on every number.
Validated against tape in **two rooms**, run on five LiDAR captures across three
rooms and a hallway, plus photo and video captures at tiers A and B.

| Deliverable | Where | |
|---|---|---|
| Capture route + device matrix | [docs/capture-protocol.md](docs/capture-protocol.md) | done |
| Compliance matrix | [docs/compliance-matrix.md](docs/compliance-matrix.md) | done |
| Benchmark report | [docs/benchmark-report.md](docs/benchmark-report.md) | Tier C only |
| Technical report | [docs/technical-report.md](docs/technical-report.md) | done |
| Fix loop | [docs/fix-loop.md](docs/fix-loop.md) | done |
| Head-to-head vs Polycam | [docs/head-to-head.md](docs/head-to-head.md) | 1 room |
| Format verification | [docs/capture-bakeoff.md](docs/capture-bakeoff.md) | done |
| Output contract | `out/*.json`, `out/*.svg` | done |

**Headline result**, my room scan 2 against tape:

```
ceiling height   2.9680 m   precision ±0.76 cm PASS   accuracy -0.2 cm PASS
door wall        3.0372 m   precision ±0.82 cm PASS   accuracy +0.3 cm PASS
other wall       3.0524 m   precision ±1.22 cm PASS   accuracy +1.1 cm PASS
```

The capture that followed the protocol passes every gate on both axes. Across
nine gates scored against tape in three rooms, **precision passes 7 and accuracy
7**. A second room was tape-measured after the pipeline was frozen, and both its
walls came in inside 2 mm: **+0.2 cm and -0.2 cm** against a 1.5 cm gate. The
benchmark's ground truth turned out to be less precise than the gate it was
meant to certify, which is written up as a result rather than buried: see
[technical-report.md](docs/technical-report.md) section 3.

**Tiers A and B** reconstruct with a learned multi-view model (MASt3R), run
locally and disclosed. Classical matching could not do it: COLMAP registered 4
photographs of 29, because a bedroom wall is large, flat, blank and dimly lit
and there is nothing to match. The learned model does reconstruct, and camera
height falls out at 1.54 m, which is where a phone is held. Ceiling height
still reads 8 to 15% low and no photo capture recovers two opposing wall pairs,
so no room polygon closes and the ±8% gate is missed. Both tiers report the
ceiling height with an interval that covers their measured error, and say what
they could not produce. Install with `bash scripts/setup_learned.sh`; nothing
else in the pipeline needs it.

**Built since:** multi-room stitching (a capture spanning two rooms is now
segmented and each room measured separately, with doorway widths), ray traced
opening detection, and the damage detector behind `--damage`.

**Still not claimed:** the opening-width gate, the photo-tier stitch, and
damage detection, each for a measured reason rather than a scope decision.
The compliance matrix gives the number in every case.

## On the day: the walk-in runbook

```sh
# 1. the moment the capture lands, before anything else. Takes under a second.
python -m cozmo check "<their-export>.zip"

# 2. if it says GO
python -m cozmo run "<their-export>.zip" --name walkin
```

`check` reads only metadata and a dozen frames, and answers GO or NO GO in
under a second. It catches the failures that cost you the room: developer mode
left off, tracking broken mid-walk, too few keyframes, and above all **drift**,
which is what separates a capture that follows the protocol from one that does
not. On our own benchmark it reads 1.0 cm on the compliant scan and 5.3 cm on
the non-compliant one, and stops on the second.

If it says NO GO, ask to re-capture. That is a far better outcome than running
the pipeline on a capture that cannot support a measurement.

**If Developer Mode was missed**, there is no raw export and the LiDAR tier has
nothing to read. That used to be a total loss. It is now a fallback: ask for a
plain mesh export instead (OBJ or PLY, no Developer Mode needed) and point the
same command at it. Measured against tape on our own room the mesh path landed
at -0.4, +0.5 and +1.5 cm, inside the gate on all three, in 1.3 seconds. What it
cannot do is resample frames, so its intervals are assumed rather than measured
and it says so.

`run` takes about 25 seconds and writes a JSON contract and a dimensioned SVG
plan. It applies a rectangular-room prior only where the walls justify it, and
records in the provenance how far out of square the room actually was.

## What runs today

Python 3.12. No dependencies, the inspector is stdlib-only by design, so
step 2 works on a clean machine with no install step between landing a capture
and reading it.

```sh
# inspect whatever came off the phone
python3 scripts/inspect_capture.py ~/Downloads/<export>.zip     # Tier C
python3 scripts/inspect_capture.py ~/Downloads/<photos>/        # Tier A
python3 scripts/inspect_capture.py ~/Downloads/<clip>.mov       # Tier B

# 69 tests. 34 need numpy and skip on a bare interpreter, so this is ~0.2s
python3 -m unittest discover -s tests -v
```

`inspect_capture.py` reports the file tree, frame count against the pose
optimisation budget, whether loop closure actually ran, decoded depth range in
millimetres, the confidence-level histogram, intrinsics, EXIF focal length
capture duration and keyframe rate, tracking breaks, and **how far global
optimisation moved each camera** the drift our own correction stage has to
beat. It flags the field mistakes that are expensive to discover late:
Developer Mode left off, a scan too long for pose optimisation, tracking lost
mid-walk, HEIC where JPEG was expected, EXIF stripped in transfer.

The first real export disagreed with Polycam's published format in five places
and carried nine undocumented per-frame fields. Findings are recorded in
[docs/capture-bakeoff.md](docs/capture-bakeoff.md); the protocol's file
contract and session cap now come from that run, not from documentation.

The depth decoder is hand-rolled PNG (no Pillow), so
[tests/test_inspect.py](tests/test_inspect.py) round-trips all five PNG row
filters at both bit depths. A wrong filter branch would not crash, it would
return plausible wrong millimetres, and every measurement downstream would
inherit the error silently.

---

## Architecture

> `ingest.lidar`, `geometry` (planes and height) and the CLI exist. `scale`
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

Tier C fills every field from the export, joining `corrected_cameras/` for
pose with `cameras/` for the sensor metadata the corrected files drop. Tier B recovers poses by
structure-from-motion and depth from a monocular model. Tier A does the same
from far fewer views. **The fields are the same; only their provenance
differs** and that is the fact the rest of the system is organised around.

### Three decisions worth defending

**1 · Provenance travels with every number.** A measurement is never a bare
float. It carries the chain that produced it, measured depth or inferred
device poses or recovered, fiducial scale or a fixture prior. The interval
engine is then a pure function of `(value, provenance, calibration_table)`
with the tables fit on our own benchmark. This makes *"intervals widen honestly
as sensor data thins"* a structural property rather than three per-tier
special cases, and it means a photo-tier number and a LiDAR-tier number can sit
in the same JSON without either lying about what it is.

**2 · Drift correction is a stage with a switch, not a step inside pose
loading.** The brief requires an ablation showing the stitched footprint with
correction on and off, and treats using supplied poses as-is as an automatic
fail, which includes Polycam's optimised poses, since those are someone else's
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
trajectory. Photos do not, per-room folders share no visual overlap, and no
feature matcher will register them. There, stitching is a graph problem: rooms
are nodes, openings are edges, and we solve for rigid transforms that mate door
pairs by width and wall normal without overlapping footprints. The connector
shots in § 3.5 of the protocol exist to supply those edges.

### One command per capture

```sh
PYTHONPATH=src .venv/bin/python -m cozmo measure myroom/8_28_2026.zip
PYTHONPATH=src .venv/bin/python -m cozmo measure <capture> --ablate   # drift on/off
```

Tier is detected from the input shape, not passed in, Tier C runs today, A and
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
  ingest/learned.py      photos or video -> Capture, via MASt3R
  ingest/mesh.py         fallback when developer mode was missed
  geometry/height.py     floor/ceiling planes, frame-bootstrapped interval
  geometry/walls.py      room axes and wall planes
  geometry/spaces.py     split a capture into rooms at its doorways
  geometry/openings.py   ray traced doors and windows
  contract/              JSON schema, SVG plan, scope line items
  __main__.py            the one command
tests/                   69 tests, 5 files
scripts/
  inspect_capture.py     stdlib-only field check
  setup_learned.sh       install the tier A/B model
  benchmark.sh           reproduce every number in the benchmark report
```

---

## Setup

```sh
git clone https://github.com/Advaith789/cozmo-capture
cd cozmo-capture
python3 -m unittest discover -s tests    # nothing to install
```

`.env` holds `OPENAI_API_KEY` for the damage-classification layer only, and is
gitignored, see `.env.example`. No geometry path reads it.

---

## Next

Step 4 is the benchmark set, and it is the gating item: three-plus rooms and a
connector, one furnished room with two damage classes, every room at all three
tiers, one room captured twice at the same tier for repeatability, and tape or
laser ground truth on all of it. Capturing it wrong costs a full re-shoot, so
it happens before any pipeline code.

Step 2's 60-second verification scan should happen first, it confirms the file
contract in § 7 of the protocol before the benchmark capture depends on it.

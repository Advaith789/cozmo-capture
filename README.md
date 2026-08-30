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

The eight deliverables, in the brief's own order:

| # | Deliverable | Where |
|---|---|---|
| 1 | Compliance matrix | [docs/compliance-matrix.md](docs/compliance-matrix.md) |
| 2 | Capture route, one page, + device matrix | [docs/capture-protocol.md](docs/capture-protocol.md) |
| 3 | Repo and README | this file |
| 4 | Reproduction bundle | [scripts/benchmark.sh](scripts/benchmark.sh) |
| 5 | Benchmark report, all tiers + head-to-head (2 rooms) | [docs/benchmark-report.md](docs/benchmark-report.md) |
| 6 | Fix loop bundle | [docs/fix-loop.md](docs/fix-loop.md) |
| 7 | Technical report, max 6 pages | [docs/technical-report.md](docs/technical-report.md) |
| 8 | Raw benchmark data | `myroom/`, 1.3 GB, delivered separately |

Output contract per capture: `out/*.json` and `out/*.svg`.

**Headline result**, my room scan 2 against tape:

```
ceiling height   2.9680 m   precision ±0.76 cm PASS   accuracy -0.2 cm PASS
door wall        3.0372 m   precision ±0.82 cm PASS   accuracy +0.3 cm PASS
other wall       3.0524 m   precision ±1.22 cm PASS   accuracy +1.1 cm PASS
```

The capture that followed the protocol passes every gate on both axes. Across
twelve gates scored against tape in four captures, **precision passes 10 and
accuracy 9**, and the **per-wall repeatability gate passes at 0.47 cm and
0.07 cm** between two compliant captures of the same room. A second room was tape-measured after the pipeline was frozen, and both its
walls came in inside 2 mm: **+0.2 cm and -0.2 cm** against a 1.5 cm gate. The
benchmark's ground truth turned out to be less precise than the gate it was
meant to certify, which is written up as a result rather than buried: see
[technical-report.md](docs/technical-report.md) section 3.

**Tiers A and B** reconstruct with a learned multi-view model (MASt3R), run
locally and disclosed. Classical matching could not do it: COLMAP registered 4
photographs of 29, because a bedroom wall is large, flat, blank and dimly lit
and there is nothing to match. The learned model does reconstruct, and camera
height falls out at 1.54 m, which is where a phone is held. Ceiling height
clears the ±8% gate on two of six captures, with a median absolute error of
15.9%, and only one capture recovers two opposing wall pairs and closes a room
polygon. Both tiers report the ceiling height with an interval that covers their
measured error, and say what they could not produce. Install with `bash scripts/setup_learned.sh`; nothing
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
cozmo check "<their-export>.zip"

# 2. if it says GO
cozmo run "<their-export>.zip" --name walkin
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
same command at it. Measured against tape on our own room the mesh path lands at
**-0.2, +0.4 and +1.1 cm on accuracy, inside the gate on all three, in 1.9
seconds**. Precision is a different story and fails: with no frames to resample
there is no bootstrap, so the intervals are assumed (±2.9 cm) rather than
measured, and the provenance says so rather than implying otherwise.
`scripts/benchmark.sh` exports a point cloud and runs this path on it, so the
numbers above are reproducible rather than remembered.

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
[docs/benchmark-report.md](docs/benchmark-report.md); the protocol's file
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
cozmo measure myroom/8_28_2026.zip
cozmo measure <capture> --ablate   # drift on/off
```

Tier is detected from the input shape, not passed in, Tier C runs today, A and
B report that they are unimplemented rather than guessing.

---

## Layout

```
docs/
  capture-protocol.md    the one-page field sheet + device matrix   [step 3]
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

## Defending this live

Every design decision, with the number that justifies it. Tools closed.

| if asked | the answer |
|---|---|
| Why Route 2 and not your own app? | A stock protocol is what a non-engineer can follow on the day, and the brief says the page is followed literally. The engineering went into the pipeline instead of an install flow. |
| Why does the ceiling use a tail quantile? | Clutter sits on floors and fittings hang below ceilings, so the contamination is one-sided and the densest band is biased. It moved the ceiling from **-3.4 cm to -0.2 cm**. |
| Why bootstrap over frames? | Samples inside one frame share that frame's pose error. Resampling points reports a fraction of a millimetre for data that disagrees by centimetres. |
| Why not resample the wall detection too? | A draw that mistakes a wardrobe for a wall says nothing about how precisely a wall sits. Letting detection vary gave intervals of about **a metre**. |
| Why recentre the intervals? | The value comes from detection, the draws from refits of it. They differ by up to 2.5 cm, and one room published an interval containing neither its own estimate nor the tape. |
| Why split rooms before fitting walls? | A two room capture otherwise fits one rectangle across both. The hallway used to report **28.08 m²** as one room. |
| Why must a split be walled to the ceiling? | Furniture leaves a door-width gap in a floor too. Splitting on the floor alone turned one bedroom into three fragments that measured nothing. |
| Why ray trace openings? | A doorway and a wardrobe both stop the sensor reaching the wall. Only the ray tells them apart. **0.8 cm** mean on synthetic truth. |
| Why is the door 0.587 m and the frame 0.958 m? | 1.2% of returns in that doorway lie on the wall plane, so the door was open; 48.8% lie in front of it, so something occluded the opening. The detector measured what it could see through. |
| Why MASt3R and not COLMAP? | COLMAP registered **4 photographs of 29**. A bedroom wall is flat, blank and dim, and matching needs texture. |
| What was actually wrong with tier A? | dust3r's aligner normalises pairwise scale, which discards the metric property the checkpoint exists for. Off: **-50.7%**. On: **-8.1%**. |
| Why is video worse than photos when it has more frames? | Motion blur, and frames sampled across a clip share less scene than stills taken a step apart. It is also held to a tighter gate, ±3% against ±8%. |
| Why is damage off by default? | **79 regions on a clean control room.** The brief scores a phantom as harshly as a miss. |
| Why does the ceiling gate fail on the pairing you report? | Two compliant captures differ by 1.49 cm. Reporting the pairing that passes and hiding the one that does not would be choosing the answer. |
| Why is the ground truth the weak link? | Ten tape readings of one ceiling span **6.9 cm** against a 1.5 cm gate. Our own two captures agree to 0.5 cm. The ruler is coarser than the thing measured. |
| What would you do next? | Buy a laser. It is twenty five dollars and it is the binding constraint on every accuracy figure here. |

**The one thing to concede early.** Tiers A and B are not reliable: two of six
captures inside their gate, median error 15.9%, and no photo capture produces
the whole-property stitch the brief asks for. Every part of that is measured,
written down, and claimed against nothing. Conceding it costs less than
defending it.

## Deliverable 8: the raw benchmark data

**1.4 GB, not in this repo.** It is raw sensor data, and the brief allows large
binaries by script or volume, so it is delivered as a download:

> **[Raw benchmark data (Google Drive, 1.4 GB)](https://drive.google.com/drive/folders/1fLeg9nfBbvPmaraEbVhx7JT-J1ZxJqIO?usp=share_link)**

Place the `myroom` folder at the repository root, which is where
`scripts/benchmark.sh` looks for it. Nothing else needs configuring. If the
whole-folder download stalls, the subfolders below can be taken one at a time;
`space_capture/` alone is enough to reproduce every Tier C number in the
benchmark report.

```
cozmo-capture/
  myroom/          <- unpack here
  src/  docs/  scripts/  out/
```

| folder | files | size | what it is |
|---|---|---|---|
| `space_capture/` | 5 | 458M | Tier C raw exports: 3 rooms, a hallway, and my room twice |
| `my room pics/` | 113 | 267M | Tier A photos, my room |
| `my room video/` | 2 | 183M | Tier B video, my room |
| `last_test_my_room/` | 23 | 120M | the protocol-compliant re-shoot: 22 photos and the third LiDAR scan |
| `friend 2 room vid/` | 1 | 96M | Tier B video |
| `friend 1 room vid/` | 1 | 87M | Tier B video |
| `friend 1 room pics/` | 29 | 73M | Tier A photos |
| `friend 2 room pics/` | 67 | 68M | Tier A photos |
| `floorplan/` | 2 | 50M | Polycam RoomPlan exports for the head-to-head, both rooms |
| `error photos/` | 2 | 4.4M | staged damage, photographed and tape-measured |

Ground truth is not a separate file: every tape reading is in
[benchmark-report.md](docs/benchmark-report.md), individual readings and all,
and the same figures are passed to the pipeline as `--truth-height` and
`--truth-walls` in `scripts/benchmark.sh`, so the numbers scoring the gates and
the numbers in the report cannot drift apart.

With the data in place, one command regenerates every figure in the benchmark:

```sh
bash scripts/benchmark.sh
```

## Setup

```sh
git clone https://github.com/Advaith789/cozmo-capture
cd cozmo-capture

python3 -m unittest discover -s tests    # 69 tests, nothing installed, ~0.2s

python3 -m venv .venv && source .venv/bin/activate
pip install -e .                          # Tier C: numpy, and the `cozmo` command
python -m unittest discover -s tests      # same 69, now with numpy

# Tiers A and B only. 2.7 GB of model weights, ~4 GB of disk, 8 GB of RAM.
bash scripts/setup_learned.sh
```

`pip install -e .` is what makes `cozmo check` and `cozmo run` work
from any directory, which is the point: the walk-in runbook has to be typeable
while standing in someone's hallway, not adjusted for where the repo happens to
sit.

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

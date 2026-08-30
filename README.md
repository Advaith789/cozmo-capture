# cozmo-capture

Handheld consumer capture to a dimensioned, stitched floor plan with a
calibrated confidence interval on every measurement. Three input tiers resolve
to one output contract; intervals widen as sensor data thins, and say so.

**Route 2, stock tooling:** Polycam for LiDAR, the native iOS Camera for photos
and video. The operator's page is [docs/capture-protocol.md](docs/capture-protocol.md).

## The eight deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Compliance matrix | [docs/compliance-matrix.md](docs/compliance-matrix.md) |
| 2 | Capture route, one page, + device matrix | [docs/capture-protocol.md](docs/capture-protocol.md) |
| 3 | Repo and README | this file |
| 4 | Reproduction bundle | [scripts/benchmark.sh](scripts/benchmark.sh) |
| 5 | Benchmark report, all tiers + head-to-head | [docs/benchmark-report.md](docs/benchmark-report.md) |
| 6 | Fix loop bundle | [docs/fix-loop.md](docs/fix-loop.md) |
| 7 | Technical report, 3 pages | [docs/technical-report.md](docs/technical-report.md) |
| 8 | Raw benchmark data, 1.4 GB | [Google Drive](https://drive.google.com/drive/folders/1fLeg9nfBbvPmaraEbVhx7JT-J1ZxJqIO?usp=share_link) |

Output contract per capture: `out/*.json` and `out/*.svg`.

## Headline result

My room scan 2 against tape:

```
ceiling height   2.9680 m   precision ±0.76 cm PASS   accuracy -0.2 cm PASS
door wall        3.0372 m   precision ±0.82 cm PASS   accuracy +0.3 cm PASS
other wall       3.0524 m   precision ±1.22 cm PASS   accuracy +1.1 cm PASS
```

Across **twelve gates scored against tape in four captures, precision passes 10
and accuracy 9**. The per-wall repeatability gate passes at **0.47 and 0.07 cm**
between two compliant captures of one room. Head to head against Polycam
v6.0.21: **8 of 8 dimensions across two rooms**, against a 70% bar.

**Tiers A and B** reconstruct with MASt3R, run locally and disclosed, because
classical matching could not: COLMAP registered 4 photographs of 29 on blank
bedroom walls. They clear their gate on **2 of 6 captures**, median error 15.9%,
and are claimed against nothing. Install with `bash scripts/setup_learned.sh`.

**Not claimed:** the opening-width gate, the photo-tier whole-property stitch,
and damage detection. Each has a measured reason in the compliance matrix.

## Setup

```sh
git clone https://github.com/Advaith789/cozmo-capture && cd cozmo-capture

python3 -m unittest discover -s tests   # 72 tests, nothing installed, ~0.2s

python3 -m venv .venv && source .venv/bin/activate
pip install -e .                        # Tier C, and the `cozmo` command

bash scripts/setup_learned.sh           # Tiers A and B only. 2.7 GB, 8 GB RAM
```

`pip install -e .` is what makes `cozmo` work from any directory, which is the
point: the runbook has to be typeable while standing in someone's hallway.

## On the day: the walk-in runbook

```sh
cozmo check "<their-export>.zip"    # under a second, answers GO or NO GO
cozmo run   "<their-export>.zip" --name walkin
```

`check` reads metadata and a dozen frames. It catches Developer Mode left off,
broken tracking, too few keyframes, and above all **drift**, which is what
separates a capture that followed the protocol from one that did not: it reads
0.9 cm on our compliant scan and 5.3 cm on the non-compliant one, and stops on
the second. If it says NO GO, re-capture while you are still in the room.

**If Developer Mode was missed**, ask for a plain OBJ or PLY export instead and
point the same command at it. Against tape that path lands at **-0.2, +0.4 and
+1.1 cm on accuracy in 1.9 seconds**. Precision fails: with no frames to resample
the intervals are assumed at ±2.9 cm, and the provenance says so.

`run` takes about 25 seconds and writes the JSON contract and a dimensioned SVG.

## Deliverable 8: the raw data

**1.4 GB, not in this repo**, delivered as a download. Place the `myroom` folder
at the repository root, where `scripts/benchmark.sh` looks for it. If the
whole-folder download stalls, `space_capture/` alone reproduces every Tier C
number.

| folder | size | what |
|---|---|---|
| `space_capture/` | 458M | Tier C raw exports: 3 rooms, a hallway, my room three times |
| `my room pics/`, `my room video/` | 450M | Tiers A and B, my room |
| `last_test_my_room/` | 120M | the protocol-compliant re-shoot and third LiDAR scan |
| `friend 1` / `friend 2` pics and vid | 324M | Tiers A and B |
| `floorplan/` | 50M | Polycam RoomPlan exports, both head-to-head rooms |
| `error photos/` | 4.4M | staged damage, tape-measured |

Ground truth is not a separate file: every tape reading is in the benchmark
report, and the same figures are passed to the pipeline in `benchmark.sh`, so
the numbers scoring the gates and the numbers in the report cannot drift apart.

## Layout

```
src/cozmo/
  ingest/      lidar.py, learned.py (MASt3R), mesh.py fallback
  geometry/    height, walls, spaces (room splitting), openings, drift
  contract/    JSON schema, SVG plan, scope line items
  __main__.py  the one command
scripts/       inspect_capture.py (stdlib only), setup_learned.sh, benchmark.sh
tests/         72 tests, 5 files
```

## Defending this live

Every design decision with the number that justifies it.

| if asked | the answer |
|---|---|
| Why a tail quantile for surfaces? | Clutter sits on floors, fittings hang below ceilings: contamination is one-sided. **-3.4 cm to -0.2 cm**. |
| Why bootstrap over frames, not points? | Samples in one frame share its pose error. Points report a fraction of a millimetre for data disagreeing by centimetres. |
| Why not resample detection too? | A draw mistaking a wardrobe for a wall says nothing about where a wall is. It gave intervals of **a metre**. |
| Why recentre the intervals? | Value from detection, draws from refits; they differ by up to 2.5 cm, and one room published an interval containing neither its estimate nor the tape. |
| Why split rooms before fitting walls? | A two-room capture otherwise fits one rectangle across both. The hallway reported **28.08 m²**. |
| Why must a split reach the ceiling? | Furniture leaves door-width gaps in a floor too. Splitting on the floor alone turned one bedroom into three fragments that measured nothing. |
| Why ray trace openings? | A doorway and a wardrobe both stop the sensor reaching the wall. Only the ray separates them. **0.8 cm** on synthetic. |
| Why is the door 0.587 m and the frame 0.958 m? | 1.2% of returns there lie on the wall plane, so it was open; 48.8% lie in front, so it was occluded. |
| Why MASt3R over COLMAP? | COLMAP registered **4 of 29**. Blank dim walls carry no features. |
| What was wrong with tier A? | dust3r's aligner normalises pairwise scale, discarding the metric property. Off **-50.7%**, on **-8.1%**. |
| Why is damage off by default? | **79 regions on a clean control room.** A phantom scores as harshly as a miss. |
| Why report the failing ceiling pairing? | Two compliant captures differ by 1.49 cm. Reporting only the pairing that passes would be choosing the answer. |
| Why is ground truth the weak link? | Ten readings of one ceiling span **6.9 cm** against a 1.5 cm gate; our captures agree to 0.5 cm. |
| What next? | A laser measure. Twenty five dollars, and the binding constraint on every accuracy figure here. |

**Concede early:** tiers A and B are not reliable, and the photo-tier stitch does
not exist. All of it is measured, written down, and claimed against nothing.

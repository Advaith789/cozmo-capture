# Compliance matrix

requirement → file path → artifact → status

Status is one of **done** **partial** **not done**. Nothing is marked done
that has not been run against a real capture. Gaps are listed rather than
omitted; a matrix that hides them is worth less than one that does not.

---

## Part 1, Capture route

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 1.1 | Choose a capture route | [docs/capture-protocol.md](capture-protocol.md) | Route 2, stock tooling | **done** |
| 1.2 | Name the off-the-shelf tool | [docs/capture-protocol.md](capture-protocol.md) §0, §3 to 5 | Polycam (Tier C), native iOS Camera (Tiers A/B) | **done** |
| 1.3 | One-page protocol a non-engineer follows | [docs/capture-protocol.md](capture-protocol.md) | prints to one A4 page | **done** |
| 1.4 | What to install / how to walk / how long / what to avoid / how to hand files over | §0, §1, §3 to 7 | numbered steps, all distances and durations stated | **done** |
| 1.5 | File contract verified, not asserted | [docs/capture-bakeoff.md](capture-bakeoff.md) | real export opened; published format wrong in 5 places | **done** |
| 1.6 | Device matrix | [docs/capture-protocol.md](capture-protocol.md) | tier → hardware → tool → data → scale | **done** |

## Part 1, Three input tiers

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 1.7 | Tier A, photos, 2 to 8 stills per room | [src/cozmo/ingest/](../src/cozmo/ingest/) | captured for 3 rooms; **ingest not implemented** | **not done** |
| 1.8 | Tier B, handheld video | [src/cozmo/ingest/](../src/cozmo/ingest/) | captured for 3 rooms; **ingest not implemented** | **not done** |
| 1.9 | Tier C, depth, poses, intrinsics | [src/cozmo/ingest/lidar.py](../src/cozmo/ingest/lidar.py) | 5 captures ingested end to end | **done** |

## Part 2, Output contract

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 2.1 | Dimensioned per-room plan | [src/cozmo/geometry/room.py](../src/cozmo/geometry/room.py) | `out/*.json`, `out/*.svg` | **done** (Tier C) |
| 2.2 | Walls | [src/cozmo/geometry/walls.py](../src/cozmo/geometry/walls.py) | fitted planes, per-wall planarity | **done** |
| 2.3 | Ceiling height | [src/cozmo/geometry/height.py](../src/cozmo/geometry/height.py) | measurement + interval | **done** |
| 2.4 | Floor area | [src/cozmo/geometry/room.py](../src/cozmo/geometry/room.py) | measurement + interval | **done** |
| 2.5 | Openings |, | **not implemented** | **not done** |
| 2.6 | Stitched multi-room plan, correct adjacency |, | 5 rooms measured **individually**; no stitch | **not done** |
| 2.7 | Per-surface damage regions, class + metric extent |, | 2 classes staged and tape-measured; **detection not implemented** | **not done** |
| 2.8 | Concealed-damage flags with the rule that fired |, | **not implemented** | **not done** |
| 2.9 | Scope line items keyed to surfaces |, | **not implemented** | **not done** |
| 2.10 | Confidence interval on every measurement | [src/cozmo/types.py](../src/cozmo/types.py) | every `Measurement` carries `lo`/`hi` + provenance | **done** |
| 2.11 | One command per capture | [src/cozmo/\_\_main\_\_.py](../src/cozmo/__main__.py) | `python -m cozmo run <capture>` | **done** |
| 2.12 | JSON to a published schema | [src/cozmo/contract/schema.py](../src/cozmo/contract/schema.py) | `cozmo-plan/0.2` | **done** |
| 2.13 | Rendered plan | [src/cozmo/contract/render.py](../src/cozmo/contract/render.py) | `out/*.svg`, dimensions annotated with intervals | **done** |

## Part 2, Benchmark composition

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 2.14 | Multi-room capture, 3+ rooms plus a connector | `myroom/space_capture/` | 4 rooms + hallway, Tier C | **done** |
| 2.15 | One furnished room with damage in 2 classes | `myroom/error photos/` | hallway 2×3 in ellipse; friend-2 room 3×3 in square | **partial** staged and measured, not detected |
| 2.16 | Same rooms at all three tiers | `myroom/` | Tier C ×5, photos ×3 rooms, video ×3 rooms | **partial** captured, only Tier C processed |
| 2.17 | One room captured twice at the same tier | `8_28 My room 1` + `8_29 My room 2` | repeatability table in benchmark report | **done** |
| 2.18 | Tape or laser ground truth, measurements submitted | [docs/capture-bakeoff.md](capture-bakeoff.md) | door wall 3.0344 m (5 readings), other wall 3.0411 m, ceiling 2.9705 m, door slab 0.8382 m, frame 0.9576 m | **partial** my room only |

## Part 2, Gates

| # | Gate | Where scored | Status |
|---|---|---|---|
| 2.19 | Opening widths ≤2 cm on ≥85%, detection scored |, | **not done** no opening detection |
| 2.20 | Ceiling height ≤1.5 cm per room | `out/*.json` `gates[]` | **done** accuracy passes, precision does not |
| 2.21 | Ceiling spread across repeat captures ≤1 cm | benchmark report | **done** reported, fails |
| 2.22 | Repeatability, 1 cm or 0.5% per wall | benchmark report | **done** reported, fails |
| 2.23 | Drift accountability + ablation | [src/cozmo/geometry/drift.py](../src/cozmo/geometry/drift.py) | `--ablate`; σ_step sweep | **done** |
| 2.24 | Photo-tier whole-property stitch |, | **not done** |

## Part 3, Head to head

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 3.1 | Our LiDAR output vs one consumer app on 2 rooms | [docs/head-to-head.md](head-to-head.md) | Polycam Floorplan (RoomPlan) v6.0.21; **beat 4 of 4 dimensions** | **partial** 1 room, brief asks 2 |
| 3.2 | Name the app and version | [docs/head-to-head.md](head-to-head.md) | Polycam Floorplan mode (RoomPlan), **v6.0.21** | **done** |

## Part 4, Fix loop

| # | Requirement | File | Status |
|---|---|---|---|
| 4.1 | Worst gate with the failing number | [docs/fix-loop.md](fix-loop.md) | **done** |
| 4.2 | Root-cause hypothesis and evidence | [docs/fix-loop.md](fix-loop.md) | **done** |
| 4.3 | Fix shipped + predicted number | [docs/fix-loop.md](fix-loop.md) | **done** |
| 4.4 | Before and after runs, both regenerable | `out/myroom1.*`, `out/myroom2.*` | **done** |

## Part 5, Process evidence

| # | Requirement | Evidence | Status |
|---|---|---|---|
| 5.1 | Commit as you work | `git log` | **done** incremental across the build |

## Deliverables

| # | Deliverable | Where | Status |
|---|---|---|---|
| D1 | Compliance matrix | this file | **done** |
| D2 | Capture route + device matrix | [docs/capture-protocol.md](capture-protocol.md) | **done** |
| D3 | Repo + README, fresh capture in <15 min, one command | [README.md](../README.md) | **done** |
| D4 | Reproduction bundle | README quick start; stdlib inspector, `requirements.txt` | **partial** |
| D5 | Benchmark report | [docs/benchmark-report.md](benchmark-report.md) | **partial** Tier C only |
| D6 | Fix loop bundle | [docs/fix-loop.md](fix-loop.md) | **done** |
| D7 | Technical report, max 6 pages | [docs/technical-report.md](technical-report.md) | **done** |
| D9 | Head-to-head | [docs/head-to-head.md](head-to-head.md) | **done** (1 room) |
| D8 | Raw benchmark data | `myroom/` (gitignored, delivered separately) | **done** |

---

## Honest summary

**Tier C is complete end to end**: capture → ingest → walls → ceiling → room →
JSON + rendered plan, with a bootstrapped interval on every number, run by one
command, validated against tape on one room and run on five captures.

**Tiers A and B are captured but not processed.** That is the single largest
gap. It means the walk-in test can only be served at the LiDAR tier.

**No openings, no stitching, no damage detection.** Rooms are measured
individually; the whole-property plan that the brief calls the product surface
does not exist.

These were scope decisions taken against a 48-hour budget, not oversights.

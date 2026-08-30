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
| 1.5 | File contract verified, not asserted | [docs/benchmark-report.md](benchmark-report.md) appendix | real export opened; published format wrong in 5 places | **done** |
| 1.6 | Device matrix | [docs/capture-protocol.md](capture-protocol.md) | tier → hardware → tool → data → scale | **done** |

## Part 1, Three input tiers

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 1.7 | Tier A, photos | [src/cozmo/ingest/learned.py](../src/cozmo/ingest/learned.py) | MASt3R metric multi-view reconstruction, run locally and disclosed. Ceiling height measured; no closed polygon on our captures | **partial** runs end to end; clears the ±8% gate on two of six captures |
| 1.8 | Tier B, handheld video | [src/cozmo/ingest/learned.py](../src/cozmo/ingest/learned.py) | frames sampled across the clip for baseline, then the same reconstruction as Tier A | **partial** runs end to end; clears the ±8% gate on two of six captures |
| 1.9 | Tier C, depth, poses, intrinsics | [src/cozmo/ingest/lidar.py](../src/cozmo/ingest/lidar.py) | 5 captures ingested end to end | **done** |

## Part 2, Output contract

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 2.1 | Dimensioned per-room plan | [src/cozmo/geometry/room.py](../src/cozmo/geometry/room.py) | `out/*.json`, `out/*.svg` | **done** (Tier C) |
| 2.2 | Walls | [src/cozmo/geometry/walls.py](../src/cozmo/geometry/walls.py) | fitted planes, per-wall planarity | **done** |
| 2.3 | Ceiling height | [src/cozmo/geometry/height.py](../src/cozmo/geometry/height.py) | measurement + interval | **done** |
| 2.4 | Floor area | [src/cozmo/geometry/room.py](../src/cozmo/geometry/room.py) | measurement + interval | **done** |
| 2.5 | Openings | [src/cozmo/geometry/openings.py](../src/cozmo/geometry/openings.py) | ray traced: classifies each wall cell as seen-through, wall, or occluded, so furniture no longer reads as a hole. 0.8 cm mean width error on synthetic truth; on the real capture it finds the doorway but reads the clear opening (0.587 m) not the frame (0.958 m) | **partial** built and tested, gate not claimed |
| 2.6 | Stitched multi-room plan, correct adjacency | [src/cozmo/geometry/spaces.py](../src/cozmo/geometry/spaces.py) | floor occupancy eroded until doorways sever, cores flooded back out; each room measured separately with its own interval. Hallway capture splits into 2 rooms with a doorway at 0.873 m [0.853, 0.893]; adjacency in `stitched_plan` | **done** |
| 2.7 | Per-surface damage regions, class + metric extent | [src/cozmo/geometry/damage.py](../src/cozmo/geometry/damage.py) | two rules, metric extent from depth, opt-in via `--damage`. Off by default because it reported 79 regions on a clean control room | **partial** built and measured, not claimed |
| 2.8 | Concealed-damage flags with the rule that fired | [src/cozmo/geometry/concealed.py](../src/cozmo/geometry/concealed.py) | 4 named rules over sensor confidence and range; `concealed_conditions[]` in every JSON. My room fires `low_confidence_surface` on 19% of scanned surface | **done** |
| 2.9 | Scope line items keyed to surfaces | [src/cozmo/contract/scope.py](../src/cozmo/contract/scope.py) | floor covering, ceiling paint, wall paint net of openings, skirting; each inherits the interval of the dimension it came from | **done** |
| 2.10 | Confidence interval on every measurement | [src/cozmo/types.py](../src/cozmo/types.py) | every `Measurement` carries `lo`/`hi` + provenance | **done** |
| 2.11 | One command per capture | [src/cozmo/\_\_main\_\_.py](../src/cozmo/__main__.py) | `cozmo run <capture>` | **done** |
| 2.12 | JSON to a published schema | [src/cozmo/contract/schema.py](../src/cozmo/contract/schema.py) | `cozmo-plan/0.2` | **done** |
| 2.13 | Rendered plan | [src/cozmo/contract/render.py](../src/cozmo/contract/render.py) | `out/*.svg`, dimensions annotated with intervals | **done** |

## Part 2, Benchmark composition

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 2.14 | Multi-room capture, 3+ rooms plus a connector | `myroom/space_capture/` | 4 rooms + hallway, Tier C | **done** |
| 2.15 | One furnished room with damage in 2 classes | `myroom/error photos/` | hallway 2×3 in ellipse; friend-2 room 3×3 in square | **partial** staged and measured, not detected |
| 2.16 | Same rooms at all three tiers | `myroom/` | Tier C x5, photos x3 rooms, video x2, all processed and scored | **done** processed; Tier A/B accuracy is poor and reported as such |
| 2.17 | One room captured twice at the same tier | `8_28 My room 1` + `8_29 My room 2` | repeatability table in benchmark report | **done** |
| 2.18 | Tape or laser ground truth, measurements submitted | [docs/benchmark-report.md](benchmark-report.md) | **two rooms**, five readings each. My room: walls 3.0344 / 3.0411 m, ceiling 2.9705 m, door slab 0.8382 m, frame 0.9576 m. Friend 1: walls 3.7636 / 3.3620 m, ceiling 3.0020 m (ten readings, two sessions), measured after the pipeline was frozen | **done** |

## Part 2, Gates

| # | Gate | Where scored | Status |
|---|---|---|---|
| 2.19 | Opening widths ≤2 cm on ≥85%, detection scored | [src/cozmo/geometry/openings.py](../src/cozmo/geometry/openings.py), `tests/test_openings_rt.py` | **partial** detection built and scored. Meets the 2 cm gate on synthetic truth (0.8 cm mean, 1.3 cm worst); on the real capture it detects the doorway but measures the clear opening rather than the frame, so the gate is reported and not claimed |
| 2.20 | Ceiling height ≤1.5 cm per room | `out/*.json` `gates[]` | **done** precision passes on all five captures (0.50 to 1.09 cm). Accuracy passes on two of the three rooms with tape and fails on the deliberately non-compliant scan |
| 2.21 | Ceiling spread across repeat captures ≤1 cm | benchmark report | **done** reported and **fails** at 5.9 cm. The two captures are the compliant and the deliberately non-compliant scan of the same room |
| 2.22 | Repeatability, 1 cm or 0.5% per wall | benchmark report | **done** reported. One wall pair passes at 1.2 cm, the other fails at 5.0 cm. Was 16.7 cm before the wall-band fix |
| 2.23 | Drift accountability + ablation | [src/cozmo/geometry/drift.py](../src/cozmo/geometry/drift.py) | **done** via `--ablate` and a σ_step sweep to zero, which is the uncorrected case |
| 2.24 | Photo-tier whole-property stitch | n/a | **not done**. The stitch itself is built (2.6) and runs on LiDAR captures, but no photo capture reconstructs a closed room, so there is nothing to stitch at the photo tier |

## Part 3, Head to head

| # | Requirement | File | Artifact | Status |
|---|---|---|---|---|
| 3.1 | Our LiDAR output vs one consumer app on 2 rooms | [docs/benchmark-report.md](benchmark-report.md) | Polycam Floorplan (RoomPlan) v6.0.21, both exports submitted; **beat 8 of 8 dimensions across 2 rooms** against a 70% bar | **done** |
| 3.2 | Name the app and version | [docs/benchmark-report.md](benchmark-report.md) | Polycam Floorplan mode (RoomPlan), **v6.0.21** | **done** |

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

## Deliverables, as the brief numbers them

| # | Deliverable | Where | Status |
|---|---|---|---|
| 1 | Compliance matrix | this file | **done** |
| 2 | Capture route (one-page protocol) + device matrix | [docs/capture-protocol.md](capture-protocol.md) | **done**, one page |
| 3 | Repo, README to a fresh capture in under 15 min, one command | [README.md](../README.md) | **done**, `pip install -e .` then `cozmo run` |
| 4 | Reproduction bundle: regenerate every reported number from raw inputs | [scripts/benchmark.sh](../scripts/benchmark.sh) | **done**. Model outputs cached and the cache replays deterministically; the live path also runs |
| 5 | Benchmark report: gates at all three tiers, repeatability, head-to-head, timing | [docs/benchmark-report.md](benchmark-report.md) | **done**, all three tiers scored |
| 6 | Fix loop bundle | [docs/fix-loop.md](fix-loop.md) | **done**, before and after both regenerable |
| 7 | Technical report, **max 6 pages** | [docs/technical-report.md](technical-report.md) | **done**, within the cap |
| 8 | Raw benchmark data: sensor logs, ground truth, app exports | `myroom/` (1.3 GB, gitignored, delivered separately) | **done** |

## Constraints

| Constraint | How it is met | Status |
|---|---|---|
| Handheld consumer capture only | iPhone 17 Pro, Polycam and the native Camera. No tripod, no rig | **done** |
| Any pretrained model with disclosure | MASt3R (tiers A/B) and Depth Anything V2 (fallback) named in the report and in the provenance of every figure they touch | **done** |
| Runs without calling our infrastructure | Tier C and the whole test suite are offline. Tiers A and B run the model locally. The only network call is an optional last-resort estimator, off the geometry path | **done** |
| Weights and large binaries fetched by script | [scripts/setup_learned.sh](../scripts/setup_learned.sh) fetches the 2.7 GB checkpoint and the vendored model code; nothing large is committed | **done** |
| Mirrors, glass, wet-look surfaces, low light | Reported rather than guessed: `concealed_conditions[]` raises sustained low-confidence regions with the rule that fired and the area. My room flags 19% of scanned surface, about 10.6 m². Two benchmark rooms captured at ISO 3200 | **done** |

---

## Honest summary

**Tier C is complete end to end**: capture → ingest → walls → ceiling → room →
JSON + rendered plan, with a bootstrapped interval on every number, run by one
command, validated against tape in two rooms and run on five LiDAR captures
plus photo and video captures at tiers A and B.

**Tiers A and B run and are scored, and they are not reliable.** Error ranges
from 4.8% to 32.7% on ceiling height, clearing the ±8% gate on two of six
captures, so the walk-in test is still best served at the LiDAR tier. This remains the single largest gap, but it
is now a measured one rather than an empty one.

**Openings, stitching and damage detection all exist.** Openings are ray traced
and meet the 2 cm gate on synthetic truth but are not claimed on real captures.
The stitch splits a capture into rooms and reports doorway widths. Damage runs
behind `--damage`, off by default because it reported 79 regions on a clean
control room.

What is left undone is listed above with a number attached in every case, rather
than as a scope decision.

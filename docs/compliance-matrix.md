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
| 2.5 | Openings | [openings.py](../src/cozmo/geometry/openings.py) | ray traced, so furniture no longer reads as a hole. 0.8 cm on synthetic; 0.587 m against a 0.958 m frame on the real capture | **partial**, gate not claimed |
| 2.6 | Stitched multi-room plan, correct adjacency | [spaces.py](../src/cozmo/geometry/spaces.py) | floor eroded until doorways sever, cores flooded back; each room measured separately. Hallway splits into 2 with a 0.873 m doorway | **done** |
| 2.7 | Per-surface damage regions | [damage.py](../src/cozmo/geometry/damage.py) | two rules, metric extent from depth, opt-in via `--damage`; 79 regions on a clean control room | **partial**, not claimed |
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
| 2.17 | One room captured twice at the same tier | my room, captured **three times**: `8_28` non-compliant, `8_29` and `8_30` compliant | repeatability table in benchmark report, all three pairings | **done** |
| 2.18 | Tape or laser ground truth submitted | [benchmark-report.md](benchmark-report.md) | **two rooms**, five readings each; friend 1 measured after the pipeline was frozen | **done** |

## Part 2, Gates

| # | Gate | Where scored | Status |
|---|---|---|---|
| 2.19 | Opening widths ≤2 cm on ≥85% | [openings.py](../src/cozmo/geometry/openings.py) | **partial**: meets the gate on synthetic truth (0.8 cm mean), measures the clear opening not the frame on real captures. Reported, not claimed |
| 2.20 | Ceiling height ≤1.5 cm per room | `out/*.json` `gates[]` | **done**: precision passes on all six captures (0.38 to 1.09 cm), accuracy on 2 of 4 with tape |
| 2.21 | Ceiling spread across repeat captures ≤1 cm | benchmark report | **done** reported and **fails** at 1.49 cm between the two compliant captures, missing by 0.49 cm. Was 5.9 cm when the pair included the non-compliant scan |
| 2.22 | Repeatability, 1 cm or 0.5% per wall | benchmark report | **PASSES** at **0.47 and 0.07 cm** between the two compliant captures. Was 16.7 cm before the fix |
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
| Mirrors, glass, wet-look, low light | `concealed_conditions[]` raises low-confidence regions with the rule that fired; my room flags 19% of surface, 10.6 m². Two rooms at ISO 3200 | **done** |

---

## Honest summary

**Tier C is complete end to end**, one command, an interval on every number,
validated against tape in two rooms across six captures.

**Tiers A and B run and are scored, and are not reliable**: 4.8% to 32.7% on
ceiling height, two of six inside their gate. **The photo-tier whole-property
stitch does not exist** and that row is a fail. This is the largest gap, and it
is now measured rather than empty.

**Openings, stitching and damage detection all exist.** Openings meet the 2 cm
gate on synthetic truth but are not claimed on real captures; the stitch splits
captures and reports doorway widths; damage runs behind `--damage`, off by
default. Everything left undone above carries a number rather than an excuse.

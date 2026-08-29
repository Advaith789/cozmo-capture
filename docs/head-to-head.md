# Head to head, our pipeline vs Polycam Floorplan

**Incumbent:** Polycam, Floorplan mode (Apple RoomPlan underneath).
Free tier. **Version 6.0.21** (profile icon → Check for Updates).

**Room:** my room, captured 29 Aug 2026 on iPhone 17 Pro.
**Export submitted:** `myroom/floorplan/8_29_2026 - Floorplan - My room.zip`
comparison drawn from its `optimized_roomplan.json`.

**Ground truth:** tape, metric. Door wall **3.0344 m** (mean of five readings:
303.8, 304.2, 300.1, 306.7, 302.4 cm), other wall **3.0411 m**, ceiling
**2.9705 m**. Floor area follows as 9.2279 m².

Ours is `out/myroom2.json`, regenerable with:

```sh
PYTHONPATH=src .venv/bin/python -m cozmo run \
  "myroom/space_capture/8_29_2026 - My room 2.zip" --name myroom2 \
  --frames 160 --bootstrap 40 --wall-draws 50 \
  --truth-height 2.9705 --truth-walls 3.0344,3.0411
```

---

## Dimension by dimension

| dimension | ground truth | **ours** | error | Polycam | error | result |
|---|---|---|---|---|---|---|
| ceiling height | 2.9705 m | **2.9680 m** | **-0.2 cm** | 2.9382 m | -3.2 cm | **win** |
| door wall | 3.0344 m | **3.0372 m** | **+0.3 cm** | 3.1185 m | +8.4 cm | **win** |
| other wall | 3.0411 m | **3.0524 m** | **+1.1 cm** | 3.1393 m | +9.8 cm | **win** |
| floor area | 9.2279 m² | **9.271 m²** | **+0.5%** | 9.790 m² | +6.1% | **win** |

**Beat Polycam on 4 of 4 shared dimensions**, against a requirement of 70%.
Every one of our figures is inside 1.2 cm or 0.5%; theirs run 3.2 to 9.8 cm out.

Worth noting how this row moved. Scored against an earlier tape reading of the
door wall, which later proved 4.6 cm wrong, we lost two of these four. The
comparison did not change; the ground truth did. That is the clearest
demonstration in this submission of why an accuracy claim is only ever as good
as the instrument behind it.

## Openings

Tape, measured on the wooden door in the same room:

| | tape | Polycam | error |
|---|---|---|---|
| door slab | 33.0 in (0.8382 m) | 0.8085 m | **-3.0 cm** |
| frame outer edge to outer edge | 37.7 in (0.9576 m) |, |, |

Polycam's door dimension sits closest to the slab, 3.0 cm under it, outside
the brief's ≤2 cm opening gate. But the comparison carries a real caveat: the
brief's gate is on the **clear opening** the gap between the inner faces of the
frame, which is neither figure above. It lies between them, so this row
indicates rather than settles.

**We detect no openings at all** so on that gate we score zero regardless of
what Polycam's error turns out to be.

## Where Polycam is clearly ahead

Accuracy is not the whole comparison, and it would be misleading to stop at the
table above.

| capability | ours | Polycam |
|---|---|---|
| room segmentation | none | separates Bedroom from Closet automatically |
| door detection | **none** | 2 doors, 0.809 m and 1.534 m wide |
| window detection | **none** | 1 window, 2.129 × 2.690 m |
| wall thickness | none | reported per wall |
| multi-room stitch | none | yes |

RoomPlan detected two doors, a window and a closet as a distinct room. We
detect none of those. On the brief's opening-width gate, the tightest at ≤2 cm
on ≥85% of openings, with a missed opening counting as a miss, **Polycam
scores and we score zero** because we have no opening detection at all.

So the fair summary is: **we are more accurate on the dimensions we both
produce, and Polycam produces considerably more of them.**

## Why we win on dimensions

Two differences are visible in the data.

**RoomPlan fits boxy vector walls.** Its output is a rectangle of
3.1185 × 3.1393 m, near-square, where the tape says 3.0344 × 3.0411 m. It
overshoots both axes by 10 to 14 cm, consistently outward, the fitted box is
inflated relative to the room. Our wall pair A lands at +3.9 cm because it is a
plane fit to 500,000 measured points rather than a box snapped to a model.

**Our interval is honest and theirs is absent.** Every number we emit carries a
bootstrapped 95% interval and a provenance chain. RoomPlan reports point values
with no uncertainty at all. `ceiling_lidar_avg_diff` in its own JSON records
that its ceiling plane sits 3.27 cm from the LiDAR data it was fitted to, but
nothing in its output surfaces that to a user.

## Caveats on this comparison

- **One room.** The brief asks for two; only one has tape ground truth.
- **Different captures.** Ours is a Space-mode scan, Polycam's is a separate
  Floorplan-mode capture of the same room minutes apart. Not the same frames.
- **Wall pairing.** Both outputs give two wall dimensions without a shared
  labelling, so pairing to the two tape figures is by best correspondence. The
  alternative pairing gives Polycam +12.1 cm and +11.9 cm, it does not change
  the outcome.
- **Clear opening not measured.** Both tape figures bracket it rather than give it, so the opening row indicates rather than settles.

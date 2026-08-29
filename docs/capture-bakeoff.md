# Capture bake-off

Purpose: derive the delivery contract from a real export instead of asserting it.
Whatever comes out of these zips **is** the contract we publish in the protocol.

Device: iPhone 17 Pro (LiDAR) · Polycam version: `____` · Date: `____`

---

## Before you capture — two iPhone settings

These two decide whether the files survive the trip to the laptop. Both must be
set *before* the capture, not after.

| Setting | Path | Value | Why |
|---|---|---|---|
| Polycam Developer Mode | Polycam → profile icon (bottom right) → Settings → General → Developer Mode | **on** | Raw export does not exist without it, and it only applies to captures made *after* the toggle. Retroactive is not an option. |
| Photo transfer | iOS Settings → Photos → Transfer to Mac or PC | **Keep Originals** | "Automatic" transcodes HEIC→JPEG and HEVC→H.264 on the way out, silently re-encoding the tier-A and tier-B inputs. |

Optional third: iOS Settings → Camera → Formats → **Most Compatible** makes the
phone shoot JPEG natively, so nothing can convert anything later. Our contract
says `.jpeg`; this is the cheapest way to make that true at the source.

---

## Capture — one room, all three tiers

Same room for all three, back to back. A small-to-medium room with at least one
door, one window, and ideally one non-rectangular feature (alcove, island,
angled wall). That last one matters later for the head-to-head.

While you are standing in it, tape-measure and write down: three wall lengths,
ceiling height, one door width. Five numbers, two minutes. This room becomes a
free sanity check and saves a second trip.

- [ ] **Tier C — Polycam Space.** Developer Mode confirmed on. Walk the
      perimeter, 1–3 m off the walls, hold at each corner. Deliberately loop
      back over your start point at the end — we want to see whether loop
      closure fires. Let it process. Export → Raw.
- [ ] **Tier B — native Camera, 4K30.** Continuous, unpaused, same room.
- [ ] **Tier A — native Camera stills.** 5 or 6 overlapping shots, ~70% overlap.
      Put them in a folder named for the room.

Ground truth measured:

| What | Tape (cm) |
|---|---|
| Wall A | |
| Wall B | |
| Wall C | |
| Ceiling height | |
| Door width | |

---

## Getting the files off the phone

Tier C does not need a cable. Tiers A and B are better with one.

- **Tier C (zip):** Polycam share sheet → AirDrop → your Mac. The zip is opaque
  to iOS so nothing re-encodes it. Lands in `~/Downloads`.
- **Tiers A and B:** USB-C cable, then **Image Capture** (built into macOS) →
  select the phone → import to a folder. This is the only path that reliably
  gives untouched originals with EXIF intact. AirDrop also works *if* Keep
  Originals is set, but Image Capture removes the doubt.

---

## Inspect

```sh
python3 scripts/inspect_capture.py ~/Downloads/<polycam-export>.zip
python3 scripts/inspect_capture.py ~/Downloads/<photo-folder>/
python3 scripts/inspect_capture.py ~/Downloads/<walkthrough>.mov
```

Paste each full output below, unedited, including any `[!]` lines. The warnings
are findings, not noise — a low-confidence percentage or an empty
`corrected_cameras/` is exactly what this exercise exists to surface.

### Tier C — Polycam raw export

```
(paste)
```

### Tier A — photo set

```
(paste)
```

### Tier B — video

```
(paste)
```

---

## Findings

Fill in from the output above. These lines become the protocol's delivery
contract and the device matrix in the technical report.

- Exact top-level tree of the raw export:
- Frame count, and whether `corrected_cameras/` was populated:
- Depth: resolution, bit depth, units, observed range:
- Confidence: distribution across 0/127/255, and where the low ones cluster:
- Intrinsics: which keys carry `fx/fy/cx/cy`, and at what image resolution:
- EXIF fields that survived transfer on the photo tier:
- Anything in the export we did not expect:

## Open question carried forward

We only have a Pro phone. The walk-in test may hand us a base iPhone 15, which
has no LiDAR — so tiers A and B must be validated as if captured on a base
device. Check that neither tier's ingest path reads depth, ProRAW, or any other
Pro-only field that would be absent on the day.

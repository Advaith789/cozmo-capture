# Field Capture Protocol

One page. Follow it literally. Reasoning is in the technical report, not here.

**Install first, before you travel.** Polycam (App Store, free). Open
Settings and turn **Developer Mode ON**. It cannot be switched on afterwards,
and without it a LiDAR capture cannot be measured.

## 1. Prepare the room, 2 minutes

Turn on **every light** and open every curtain. Pick up anything on the floor
you can move in a minute. Open all internal doors **fully** against the wall.
Leave mirrors and glass as they are; do not cover them.

## 2. Pick your tier

| phone | tier | tool |
|---|---|---|
| iPhone 15 Pro / 16 Pro / 17 Pro (any Pro) | **C, LiDAR** | Polycam, LiDAR mode |
| iPhone 15 / 16 / 17, non-Pro | **B, video** | native Camera |
| any iPhone, or Tier C failed | **A, photos** | native Camera |

## 3. Tier C, LiDAR. Under 7 minutes per room

1. Polycam → **LiDAR** mode → Space.
2. Stand in a corner. Start. **Walk the perimeter with the wall on your right**,
   one step per second. Count the steps out loud.
3. **Stop for 3 seconds at every corner.**
4. Tilt slowly **up to the ceiling line and down to the floor line** on each wall.
5. In a doorway, stop, show both rooms, then walk through.
6. **Finish where you started.** Walk past your starting corner by two steps.
7. Stop before 700 frames. If the counter passes 700, stop and start a new scan.

## 4. Tier B, video. Under 10 minutes per floor

1. Camera → **Video**, **4K 30fps**. If the room is dim, **1080p 60fps**.
2. Hold the phone **upright, both hands, chest height**, elbows against ribs.
3. Start at the entrance. **Say each room's name out loud** as you enter it.
4. Walk **one step per second**. Sweep each wall over about 3 seconds, tilting
   down to the floor line and up to the ceiling line.
5. Stop for 3 seconds in every doorway and show both rooms.
6. **Return to the entrance and stop there.** One unbroken recording per floor.

## 5. Tier A, photos. 2 minutes per room

1. Camera → **Photo**. No flash, no zoom, no Portrait mode.
2. Put a sheet of **A4 or Letter paper flat on the floor**, in shot. Not optional.
3. Hold the phone **level and upright**. Do not tilt it up or down.
4. Take **6 to 8 photos**, one from each corner, each aimed at the opposite corner.
5. In every shot keep **both junction lines in frame**: wall to floor, and wall
   to ceiling.
6. **If you can take more, take 25 to 30 in a slow circle**, one small step
   between shots. This measures better than eight.
7. Stand in each doorway and take one photo into each room it joins.

## 6. Never

- Never switch Developer Mode on after capturing. It does not backfill.
- Never pause and resume a recording. Start again instead.
- Never zoom, and never use Portrait mode.
- Never walk faster than one step per second.
- Never stop a LiDAR scan somewhere other than where you began.
- Never scan more than one room per Tier C capture.

## 7. Hand the files over, allow 30 minutes

**Tier C:** Polycam → your scan → Export → **Raw Data (.zip)**. Export can take
20 minutes; leave the app open and the screen awake.
**If Developer Mode was off,** export **OBJ** or **PLY** instead. It still measures.
**Tiers A and B:** the photo folder, or the clip, unmodified.

AirDrop to the laptop. Name each folder in lower case with underscores, one room
per folder: `bedroom_1`, `living_room`, `hallway`.

## 8. Check before you leave the property

```sh
cozmo check "<the file you just exported>"
```

Under a second. If it says **NO GO**, re-capture the room now, while you are
still standing in it. That is the whole reason this step exists.

## Device matrix

| tier | hardware | data | scale from | honest accuracy |
|---|---|---|---|---|
| C, LiDAR | iPhone 12 Pro and newer, any Pro | depth, poses, intrinsics | sensor | **walls ±0.2 cm, ceiling ±1.5 cm** |
| C fallback | as above, Developer Mode missed | mesh only | sensor | walls ±1.1 cm, intervals assumed |
| B, video | iPhone 15 and newer | frames only | learned model | poor: 33% low to 29% high |
| A, photos | any iPhone | frames only | learned model | 5 to 22% low, 2 of 4 inside ±8% |

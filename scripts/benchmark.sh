#!/usr/bin/env bash
# Re-run every capture in the benchmark and print the gate table.
#
# One command, so the numbers in docs/benchmark-report.md can be reproduced
# rather than trusted. Tier C runs anywhere; tiers A and B need the learned
# model (scripts/setup_learned.sh) and are skipped with a note if it is absent.
#
#   bash scripts/benchmark.sh [outdir]
#
# Ground truth is tape, on two rooms, five readings per dimension:
#   my room   ceiling 2.9705 m, walls 3.0344 and 3.0411 m
#   friend 1  ceiling 3.0020 m (10 readings), walls 3.7636 and 3.3620 m
# The remaining rooms are scored for precision but have no accuracy column,
# which the table says rather than hides.

set -uo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-out}"
export PYTHONPATH=src
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

S="myroom/space_capture"
TRUTH_H=2.9705
TRUTH_W=3.0344,3.0411
# Friend 1 room. Walls are five readings; the ceiling is ten across two
# sessions, because one session could not settle it. See the benchmark report.
F1_H=3.0020
F1_W=3.7636,3.3620

run() {  # name  capture  [truth args...]
  local name="$1"; shift
  local cap="$1"; shift
  if [ ! -e "$cap" ]; then echo "skip  $name (missing: $cap)"; return; fi
  echo "=== $name ==="
  $PY -m cozmo run "$cap" --name "$name" --out "$OUT" "$@" 2>&1 \
    | grep -aE "^(tier|frames|views|spaces|  doorway|floor area|perimeter|ceiling height|  wall [0-9]|openings|  wall_length|  ceiling_height|elapsed)" \
    || echo "  (failed)"
  echo
}

echo "################ Tier C, LiDAR ################"
run myroom2 "$S/8_29_2026 - My room 2.zip"        --truth-height $TRUTH_H --truth-walls $TRUTH_W
run myroom1 "$S/8_28_2026 - My room 1.zip"        --truth-height $TRUTH_H --truth-walls $TRUTH_W
# Third capture of the same room, compliant. Scans 2 and 3 are the fair
# repeatability pair; scan 1 broke the protocol deliberately.
run myroom3 "myroom/last_test_my_room/lidarscan/8_30_2026.zip" --truth-height $TRUTH_H --truth-walls $TRUTH_W
run friend1 "$S/8_29_2026 - Friend - 1 Room.zip"  --truth-height $F1_H --truth-walls $F1_W
run friend2 "$S/8_29_2026 - Friend 2 Room.zip"
run hallway "$S/8_29_2026 - Connecter Hallway.zip"

echo "################ Tier A, photographs ################"
run photoA_myroom  "myroom/my room pics"      --truth-height $TRUTH_H --truth-walls $TRUTH_W
# Re-shot to the protocol: one continuous burst, one step between frames, both
# junction lines in shot. This is the only photo capture that follows it.
run photoA_reshoot "myroom/last_test_my_room"  --truth-height $TRUTH_H --truth-walls $TRUTH_W
run photoA_friend1 "myroom/friend 1 room pics"
run photoA_friend2 "myroom/friend 2 room pics"

echo "################ Tier B, video ################"
run videoB_myroom  "myroom/my room video/IMG_8486.MOV"  --truth-height $TRUTH_H --truth-walls $TRUTH_W
run videoB_friend1 "myroom/friend 1 room vid/IMG_8566.MOV"

echo "################ Fallback path, mesh export ################"
# This has to run on a real mesh or it proves nothing. Earlier versions pointed
# the mesh row at the same zip, which simply ran Tier C again and labelled it a
# fallback. So a point cloud is exported first, and the fallback then reads it
# with no poses, no depth and no confidence, exactly as it would if the operator
# had missed Developer Mode.
MESH="$OUT/myroom2_export.ply"
mkdir -p "$OUT"
$PY - "$S/8_29_2026 - My room 2.zip" "$MESH" <<'PY'
import sys
sys.path.insert(0, "src")
import numpy as np
from cozmo.ingest import lidar
cap = lidar.load(sys.argv[1], max_frames=160)
pts = np.vstack([lidar.to_world_points(f) for f in cap.frames])
rng = np.random.default_rng(0)
if len(pts) > 600_000:
    pts = pts[rng.choice(len(pts), 600_000, replace=False)]
with open(sys.argv[2], "wb") as fh:
    fh.write(b"ply\nformat binary_little_endian 1.0\n")
    fh.write(f"element vertex {len(pts)}\n".encode())
    fh.write(b"property float x\nproperty float y\nproperty float z\nend_header\n")
    fh.write(pts.astype("<f4").tobytes())
print(f"  exported {len(pts):,} vertices to {sys.argv[2]}")
PY
run meshtest "$MESH" --truth-height $TRUTH_H --truth-walls $TRUTH_W

echo "done. JSON and SVG in $OUT/"

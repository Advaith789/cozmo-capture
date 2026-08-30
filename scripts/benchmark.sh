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
#   friend 1  ceiling 3.0120 m, walls 3.7636 and 3.3620 m
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
# Friend 1 room, five tape readings per dimension, means below.
F1_H=3.0120
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
run friend1 "$S/8_29_2026 - Friend - 1 Room.zip"  --truth-height $F1_H --truth-walls $F1_W
run friend2 "$S/8_29_2026 - Friend 2 Room.zip"
run hallway "$S/8_29_2026 - Connecter Hallway.zip"

echo "################ Tier A, photographs ################"
run photoA_myroom  "myroom/my room pics"      --truth-height $TRUTH_H --truth-walls $TRUTH_W
run photoA_friend1 "myroom/friend 1 room pics"
run photoA_friend2 "myroom/friend 2 room pics"

echo "################ Tier B, video ################"
run videoB_myroom  "myroom/my room video/IMG_8486.MOV"  --truth-height $TRUTH_H --truth-walls $TRUTH_W
run videoB_friend1 "myroom/friend 1 room vid/IMG_8566.MOV"

echo "################ Fallback path, mesh export ################"
run meshtest "$S/8_29_2026 - My room 2.zip"

echo "done. JSON and SVG in $OUT/"

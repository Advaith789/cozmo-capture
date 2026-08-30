"""The output contract: JSON with a confidence interval on every measurement.

Every number carries its interval and the provenance chain that produced it, so
a photo-tier figure and a LiDAR-tier figure can sit in the same document
without either misrepresenting what it is. That is the whole point of tracking
provenance from ingest onward — the interval is derived from how the number was
made, not attached to it afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..geometry.room import Room
from ..types import Capture, Measurement

SCHEMA_VERSION = "cozmo-plan/0.2"


def measurement(m: Measurement) -> dict[str, Any]:
    return {
        "value": round(m.value, 4),
        "ci_low": round(m.lo, 4),
        "ci_high": round(m.hi, 4),
        "ci_half_width": round(m.half_width, 4),
        "unit": m.unit,
        "provenance": list(m.provenance),
        "samples": m.n,
    }


def gate(name: str, m: Measurement, limit_m: float,
         truth: float | None = None) -> dict[str, Any]:
    """A gate reports precision always, and accuracy only when truth exists."""
    row: dict[str, Any] = {
        "gate": name,
        "limit_m": limit_m,
        "interval_half_width_m": round(m.half_width, 4),
        "precision_pass": bool(m.half_width <= limit_m),
    }
    if truth is not None:
        err = m.value - truth
        row.update(ground_truth_m=round(truth, 4),
                   error_m=round(err, 4),
                   accuracy_pass=bool(abs(err) <= limit_m))
    return row


def room_json(room: Room) -> dict[str, Any]:
    return {
        "name": room.name,
        "footprint": [[round(float(x), 4), round(float(z), 4)]
                      for x, z in room.corners],
        "floor_area": measurement(room.floor_area),
        "perimeter": measurement(room.perimeter),
        "ceiling_height": measurement(room.ceiling_height),
        "wall_lengths": [measurement(m) for m in room.wall_lengths],
        "walls": [
            {
                "normal": [round(float(w.normal[0]), 5),
                           round(float(w.normal[1]), 5)],
                "offset_m": round(w.offset, 4),
                "points": w.n_points,
                "planarity_cm": round(w.residual_cm, 2),
            }
            for w in room.walls
        ],
        "openings_status": "experimental, not claimed against the opening gate: "
                            "widths vary by a factor of two across frame counts",
        "openings": [
            {
                "wall_index": idx,
                "kind": o.kind,
                "width_m": round(o.width, 4),
                "height_m": round(o.height, 4),
                "sill_m": round(o.sill, 4),
                "width_ci": [round(room.opening_ci[k][0], 4),
                             round(room.opening_ci[k][1], 4)]
                if k < len(room.opening_ci) else None,
                "border_confidence": round(o.confidence, 2),
                "provenance": ["depth:measured", "method:wall_plane_hole",
                               "status:EXPERIMENTAL"],
            }
            for k, (idx, o) in enumerate(room.openings)
        ],
    }


def stitched_plan(rooms: list[Room],
                  stitched: dict[str, Any] | None) -> dict[str, Any]:
    """The multi-room plan, when the capture actually held more than one room.

    Adjacency is the doorway list from the floor segmentation: two rooms are
    adjacent when their flooded regions share a seam wide enough to walk
    through. That is a stronger claim than "their rectangles touch", which is
    true of any two rooms in a badly split capture.
    """
    if not stitched:
        return {
            "spaces_found": len(rooms),
            "rooms_measured": len(rooms),
            "adjacency": [],
            "status": "single-room capture; nothing to stitch",
        }
    return {
        # These differ, and conflating them made the contract contradict
        # itself: a capture can be segmented into three spaces of which only
        # one closes a polygon, and the adjacency below is numbered by space,
        # not by room measured.
        "spaces_found": stitched["spaces"],
        "rooms_measured": len(rooms),
        "room_names": [r.name for r in rooms],
        "adjacency": [{
            "between": d["connects"],
            "via": "doorway",
            "clear_width_m": d["clear_width_m"],
            "ci_low": d["ci_low"],
            "ci_high": d["ci_high"],
            "centre_xz": d["centre_xz"],
        } for d in stitched["doorways"]],
        "method": stitched["note"],
        "status": "segmented from one capture by eroding the floor occupancy "
                  "until doorways sever, then flooding the cores back out",
    }


def build(capture: Capture, rooms: list[Room],
          gates: list[dict[str, Any]] | None = None,
          notes: list[str] | None = None,
          scope_items: list[dict[str, Any]] | None = None,
          concealed: list[dict[str, Any]] | None = None,
          stitched: dict[str, Any] | None = None,
          damage: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capture": {
            "source": Path(capture.source).name,
            "tier": capture.tier,
            "frames_used": capture.meta.get("loaded"),
            "frames_total": capture.meta.get("total_keyframes"),
            "loop_closed": capture.meta.get("loop_closed"),
            "tracking_segments": capture.meta.get("tracking_segments"),
        },
        "rooms": [room_json(r) for r in rooms],
        "stitched_plan": stitched_plan(rooms, stitched),
        "damage": {
            "regions": damage or [],
            "status": ("opt-in via --damage; measured 79 false positives on a "
                       "clean control room, so it is off by default and "
                       "claimed against no gate"
                       if damage is None else
                       "EXPERIMENTAL, opt-in: every region is a candidate for "
                       "a human to confirm, not a finding"),
        },
        "concealed_conditions": concealed or [],
        "scope_line_items": scope_items or [],
        "gates": gates or [],
        "known_limitations": notes or [],
    }


def write(doc: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    def default(o: Any) -> Any:
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o))

    path.write_text(json.dumps(doc, indent=2, default=default))
    return path

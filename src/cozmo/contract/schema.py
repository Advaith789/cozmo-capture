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
        "openings": [],   # populated once opening detection lands
    }


def build(capture: Capture, rooms: list[Room],
          gates: list[dict[str, Any]] | None = None,
          notes: list[str] | None = None) -> dict[str, Any]:
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
        "stitched_plan": {
            "rooms": len(rooms),
            "adjacency": [],
            "status": "single-room capture; adjacency requires a multi-room "
                      "capture and opening detection",
        },
        "damage": {"regions": [], "status": "not implemented"},
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

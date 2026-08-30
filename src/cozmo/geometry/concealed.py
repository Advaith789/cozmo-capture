"""Concealed-condition flags, each naming the rule that fired.

The brief asks for concealed-damage flags "with the rule that fired". A flag
that cannot say why it fired is not inspectable, so this is deliberately a set
of named rules over measurements we already have, not a classifier.

What a depth sensor cannot see is as informative as what it can. The LiDAR
returns a confidence value per pixel, and the places it gives up are not random:
glass, mirrors, gloss paint, wet-look flooring and dark surfaces all defeat a
time-of-flight sensor. Those are exactly the surfaces where a condition can hide
from a visual inspection too, so a sustained low-confidence region is worth
raising even though we cannot say what is behind it.

Each flag states what was observed, which rule caught it, and what a surveyor
should do about it. None of them claims to have found damage. They say the
capture could not see a surface properly, and where.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A wall that returns this little high-confidence depth is not being measured,
# it is being guessed at.
LOW_CONF_FRACTION = 0.12
MIN_AREA_M2 = 0.25
RANGE_LIMIT_M = 5.0


@dataclass(frozen=True)
class Flag:
    rule: str                 # short identifier
    surface: str
    finding: str              # what was observed, in plain words
    action: str               # what a person should do about it
    extent_m2: float
    severity: str             # note | check | inspect


def _frame_area_per_pixel(frame, depth_m: float) -> float:
    fx = float(frame.K[0, 0])
    return (depth_m / fx) ** 2


def detect(frames, floor_y: float, ceiling_y: float,
           room_surface_m2: float | None = None) -> list[Flag]:
    """Flags for one capture.

    Areas are expressed as a share of the room's own surface, not as a sum over
    frames. A wall seen from forty keyframes would otherwise be counted forty
    times, which is how an early version reported 151 square metres of suspect
    surface in a nine square metre room.
    """
    usable = [f for f in frames if f.depth is not None and f.confidence is not None]
    if not usable:
        return []

    low_area = 0.0
    total_area = 0.0
    beyond_range = 0.0
    no_return = 0.0

    for f in usable:
        d, c = f.depth, f.confidence
        finite = np.isfinite(d) & (d > 0)
        if not finite.any():
            continue
        med = float(np.median(d[finite]))
        px = _frame_area_per_pixel(f, med)

        total_area += finite.sum() * px
        # Only the bottom confidence level counts. ARKit's middle level is
        # ordinary for a surface at an angle and flagging it would fire on
        # every room.
        low_area += ((c < 1) & finite).sum() * px
        beyond_range += (finite & (d > RANGE_LIMIT_M)).sum() * px
        no_return += (~finite).sum() * px

    if total_area <= 0:
        return []

    flags: list[Flag] = []
    low_frac = low_area / total_area
    # Convert shares to real area using the room's own surfaces where we know
    # them, since the per-frame totals count each wall once per sighting.
    surface = room_surface_m2 if room_surface_m2 else total_area / max(len(usable), 1)
    low_m2 = low_frac * surface

    if low_frac > LOW_CONF_FRACTION and low_m2 > MIN_AREA_M2:
        flags.append(Flag(
            rule="low_confidence_surface",
            surface="unspecified",
            finding=f"{low_frac * 100:.0f}% of the scanned surface returned "
                    f"the lowest confidence depth, about {low_m2:.1f} m2 "
                    f"of this room",
            action="Inspect by hand. A time-of-flight sensor loses confidence "
                   "on glass, mirrors, gloss paint and wet-look flooring, which "
                   "are also the surfaces a visual inspection reads poorly.",
            extent_m2=round(low_m2, 2),
            severity="inspect"))

    nr_frac = no_return / (total_area + no_return)
    nr_m2 = nr_frac * surface
    if nr_frac > 0.15 and nr_m2 > MIN_AREA_M2:
        flags.append(Flag(
            rule="no_depth_return",
            surface="unspecified",
            finding=f"{nr_frac * 100:.0f}% of pixels returned no depth at all, "
                    f"about {nr_m2:.1f} m2 of this room",
            action="Usually glazing or a mirror. Confirm what is there and "
                   "measure it by hand; the plan cannot bound it.",
            extent_m2=round(nr_m2, 2),
            severity="inspect"))

    beyond_m2 = (beyond_range / total_area) * surface if total_area else 0.0
    if beyond_m2 > MIN_AREA_M2:
        flags.append(Flag(
            rule="beyond_sensor_range",
            surface="unspecified",
            finding=f"about {beyond_m2:.1f} m2 was measured beyond "
                    f"{RANGE_LIMIT_M:.0f} m, where this sensor degrades",
            action="Re-capture standing closer, 1 to 3 m from the surface. "
                   "Dimensions relying on this region are weaker than their "
                   "interval suggests.",
            extent_m2=round(beyond_m2, 2),
            severity="check"))

    height = ceiling_y - floor_y
    if height < 2.20 or height > 3.40:
        flags.append(Flag(
            rule="implausible_ceiling_height",
            surface="ceiling",
            finding=f"ceiling measured at {height:.2f} m, outside the usual "
                    f"2.20 to 3.40 m for a dwelling",
            action="Check the floor and ceiling were both captured. A dropped "
                   "soffit or an unscanned floor both produce this.",
            extent_m2=0.0,
            severity="check"))

    return flags


def to_json(flags: list[Flag]) -> list[dict]:
    return [{
        "rule": f.rule,
        "surface": f.surface,
        "finding": f.finding,
        "recommended_action": f.action,
        "extent_m2": f.extent_m2,
        "severity": f.severity,
    } for f in flags]

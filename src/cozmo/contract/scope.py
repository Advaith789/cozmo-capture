"""Scope line items, keyed to the surface each one belongs to.

The brief asks for line items keyed to surfaces, which is a quantity takeoff:
how much paint, how much flooring, how many metres of skirting. Every quantity
here is derived from geometry already measured, so nothing new is estimated and
nothing is guessed. A line item inherits the interval of the dimension it came
from, which means a wall area computed from a perimeter good to 4 cm carries
that through rather than presenting a tidy number.

Openings are subtracted from wall area where we have them, and the line says so.
Without opening detection the wall area is gross rather than net, which is an
overestimate and is labelled as one: a trade quoting from this should know
which they are looking at.

Rates and materials are deliberately absent. This is a measurement pipeline and
what a job costs is not a thing it can know.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry.room import Room
from ..types import Measurement


@dataclass(frozen=True)
class LineItem:
    surface: str          # floor | ceiling | walls | perimeter
    item: str             # what the work is
    quantity: float
    lo: float
    hi: float
    unit: str
    basis: str            # which measurements it was derived from
    note: str = ""


def _rel(m: Measurement) -> float:
    """Relative half width, used to carry uncertainty through a product."""
    return m.half_width / m.value if m.value else 0.0


def build(room: Room) -> list[LineItem]:
    """Line items for one room, each carrying the interval of its source."""
    floor = room.floor_area
    per = room.perimeter
    ceil = room.ceiling_height

    items: list[LineItem] = []

    items.append(LineItem(
        surface="floor", item="floor covering", quantity=floor.value,
        lo=floor.lo, hi=floor.hi, unit="m2",
        basis="floor area from the wall polygon"))

    items.append(LineItem(
        surface="ceiling", item="ceiling paint", quantity=floor.value,
        lo=floor.lo, hi=floor.hi, unit="m2",
        basis="same footprint as the floor",
        note="assumes a flat ceiling at one level"))

    # Wall area is perimeter times height, so its relative uncertainty is the
    # two added in quadrature rather than either one alone.
    gross = per.value * ceil.value
    rel = (_rel(per) ** 2 + _rel(ceil) ** 2) ** 0.5
    opening_area = sum(o.width * o.height for _, o in room.openings)
    net = max(gross - opening_area, 0.0)

    if room.openings:
        items.append(LineItem(
            surface="walls", item="wall paint, net of openings", quantity=net,
            lo=net * (1 - rel), hi=net * (1 + rel), unit="m2",
            basis="perimeter x ceiling height, less detected openings",
            note=f"{len(room.openings)} opening(s) subtracted, "
                 f"{opening_area:.2f} m2; opening detection is experimental"))
    else:
        items.append(LineItem(
            surface="walls", item="wall paint, gross", quantity=gross,
            lo=gross * (1 - rel), hi=gross * (1 + rel), unit="m2",
            basis="perimeter x ceiling height",
            note="GROSS: no openings detected to subtract, so this "
                 "overestimates by the area of every door and window"))

    items.append(LineItem(
        surface="perimeter", item="skirting board", quantity=per.value,
        lo=per.lo, hi=per.hi, unit="m",
        basis="room perimeter",
        note="full perimeter; door openings not deducted"))

    return items


def to_json(items: list[LineItem]) -> list[dict]:
    return [{
        "surface": i.surface,
        "item": i.item,
        "quantity": round(i.quantity, 3),
        "ci_low": round(i.lo, 3),
        "ci_high": round(i.hi, 3),
        "unit": i.unit,
        "basis": i.basis,
        **({"note": i.note} if i.note else {}),
    } for i in items]

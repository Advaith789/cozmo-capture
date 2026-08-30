"""Assemble fitted wall planes into a room: polygon, area, perimeter.

Corners are the intersections of adjacent wall planes, not clusters of points.
A corner is where two walls meet whether or not the scanner ever saw that spot,
and in a furnished room it usually did not — the point cloud is occluded
exactly where the geometry is best defined.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..types import Measurement
from .openings import Opening
from .walls import RoomAxes, Wall


@dataclass(frozen=True)
class Room:
    name: str
    corners: np.ndarray             # (n, 2) floorplan polygon, ordered
    walls: list[Wall]
    floor_area: Measurement
    perimeter: Measurement
    ceiling_height: Measurement
    wall_lengths: list[Measurement]
    openings: list[tuple[int, Opening]] = field(default_factory=list)
    opening_ci: list[tuple[float, float]] = field(default_factory=list)


def _intersect(a: Wall, b: Wall) -> np.ndarray | None:
    """Point where two wall planes meet in the floorplan."""
    A = np.stack([a.normal, b.normal])
    if abs(np.linalg.det(A)) < 1e-6:      # parallel walls never meet
        return None
    return np.linalg.solve(A, np.array([a.offset, b.offset]))


def polygon(axes: RoomAxes, square_up: bool = True) -> np.ndarray | None:
    """Corners from two opposing wall pairs, ordered around the room.

    Each fitted wall normal lands about a degree off the room axis it belongs
    to. Intersecting the raw planes propagates that tilt into every corner, and
    measured against tape the resulting edges were 3-5 cm out where the direct
    plane-to-plane distances were within half a centimetre.

    `square_up` therefore snaps each wall's normal onto its own axis, keeping
    the fitted offset. The two axes are perpendicular by construction, so the
    room becomes an exact rectangle whose edges are the plane separations. It
    is a rectangular-room prior and it is stated as one: a genuinely
    non-rectangular room should be built with square_up=False and will report
    wider intervals for it.
    """
    if len(axes.walls_a) < 2 or len(axes.walls_b) < 2:
        return None
    a0, a1 = axes.walls_a[0], axes.walls_a[-1]
    b0, b1 = axes.walls_b[0], axes.walls_b[-1]

    if square_up:
        def snap(w: Wall, axis: np.ndarray) -> Wall:
            # Keep the plane where the fit put it; align only its direction.
            sign = 1.0 if w.normal @ axis >= 0 else -1.0
            return Wall(normal=axis * sign, offset=w.offset * sign * sign,
                        n_points=w.n_points, residual_cm=w.residual_cm)
        a0, a1 = snap(a0, axes.axis_a), snap(a1, axes.axis_a)
        b0, b1 = snap(b0, axes.axis_b), snap(b1, axes.axis_b)

    corners = [_intersect(a0, b0), _intersect(a1, b0),
               _intersect(a1, b1), _intersect(a0, b1)]
    if any(c is None for c in corners):
        return None
    return np.array(corners)


def _area(poly: np.ndarray) -> float:
    """Shoelace."""
    x, z = poly[:, 0], poly[:, 1]
    return float(abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1))) / 2)


def _perimeter(poly: np.ndarray) -> float:
    d = poly - np.roll(poly, -1, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def out_of_square_deg(axes: RoomAxes) -> float:
    """Worst angle between a fitted wall normal and the axis it belongs to.

    The rectangular prior is safe when the room really is rectangular. On the
    benchmark's rooms every wall sat within 0.7 degrees of its axis. A bay
    window, an angled wall or a room that is simply not a box would show far
    more, and snapping those to the axes would report a room that is not there.
    """
    worst = 0.0
    for axis, wl in ((axes.axis_a, axes.walls_a), (axes.axis_b, axes.walls_b)):
        for w in wl:
            cosang = abs(float(np.clip(w.normal @ axis, -1.0, 1.0)))
            worst = max(worst, float(np.degrees(np.arccos(cosang))))
    return worst


def measure(axes: RoomAxes, square_up: bool = True
            ) -> tuple[np.ndarray, list[float], float, float] | None:
    """Polygon, its edge lengths, area and perimeter — one draw's worth."""
    poly = polygon(axes, square_up=square_up)
    if poly is None:
        return None
    edges = [float(np.hypot(*(poly[(i + 1) % len(poly)] - poly[i])))
             for i in range(len(poly))]
    return poly, edges, _area(poly), _perimeter(poly)


# Beyond this the room is not a box, and forcing it into one would invent
# geometry. Real rooms in the benchmark measured under 0.7 degrees.
SQUARE_LIMIT_DEG = 3.0


def build(axes: RoomAxes, height: Measurement, name: str = "room",
          draws: list[RoomAxes] | None = None,
          fallback_sigma_cm: float = 2.0) -> Room | None:
    """Assemble a room, with intervals resampled over frames where possible.

    `draws` are wall detections from bootstrap resamples of the capture's
    frames. Their spread is the interval: it carries the pose disagreement that
    dominates our error, which no residual of a single fit can see. Without
    draws the room still builds, but the interval falls back to an assumed
    plane uncertainty and says so in its provenance — an assumed interval is
    worth reporting only if it is labelled as one.
    """
    skew = out_of_square_deg(axes)
    square = skew <= SQUARE_LIMIT_DEG
    base = measure(axes, square_up=square)
    if base is None:
        return None
    poly, edges, area, per = base

    s = fallback_sigma_cm / 100.0
    centre = poly.mean(axis=0)

    def scaled(delta: float) -> np.ndarray:
        """Offset every wall by delta along its outward direction."""
        out = poly - centre
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return centre + out * (1 + delta / np.maximum(norms, 1e-6))

    prov = ["depth:measured", "pose:device_optimised", "scale:sensor",
            "method:wall_plane_intersection",
            f"prior:rectangular_room({skew:.1f}deg_skew)" if square
            else f"prior:none_room_is_{skew:.1f}deg_out_of_square"]

    sampled = [measure(d, square_up=square) for d in (draws or [])]
    sampled = [x for x in sampled if x is not None and len(x[1]) == len(edges)]

    if len(sampled) >= 20:
        prov.append(f"interval:bootstrap_frames×{len(sampled)}")
        n_draws = len(sampled)
        areas = np.array([x[2] for x in sampled])
        pers = np.array([x[3] for x in sampled])
        edge_draws = np.array([x[1] for x in sampled])
        # Recentre the bootstrap on the number actually reported.
        #
        # The value comes from the wall detection; the draws come from refits
        # of that detection on resampled frames, and those are two different
        # estimators of the same wall. They differ by a few millimetres, and on
        # the friend 1 capture by 2.5 cm, which was enough to publish an
        # interval that did not contain its own point estimate, or the tape.
        # An interval that excludes the number it belongs to is not a weaker
        # claim than one that includes it, it is an incoherent one.
        #
        # Resampling the detection instead would fix the centring and break
        # something worse: a draw that mistakes a wardrobe for a wall does not
        # tell us how precisely a wall is located, and letting detection vary
        # gave intervals of about a metre. So detection stays fixed, the
        # bootstrap keeps its job of measuring dispersion, and its percentiles
        # are shifted onto the estimate. Width is unchanged; only the centre
        # moves, which is the standard recentred percentile interval.
        def recentre(draw_vals: np.ndarray, value: float):
            lo, hi = np.percentile(draw_vals, [2.5, 97.5])
            shift = value - float(np.median(draw_vals))
            return lo + shift, hi + shift

        area_lo, area_hi = recentre(areas, area)
        per_lo, per_hi = recentre(pers, per)
        edge_ci = [recentre(edge_draws[:, i], edges[i])
                   for i in range(len(edges))]
    else:
        prov.append(f"interval:ASSUMED_plane_sigma_{fallback_sigma_cm}cm")
        n_draws = 0
        area_lo, area_hi = _area(scaled(-s)), _area(scaled(+s))
        per_lo, per_hi = _perimeter(scaled(-s)), _perimeter(scaled(+s))
        edge_ci = [(L - s, L + s) for L in edges]

    prov_t = tuple(prov)
    lengths = [
        Measurement(value=L, lo=float(ci[0]), hi=float(ci[1]), unit="m",
                    provenance=prov_t, n=n_draws)
        for L, ci in zip(edges, edge_ci)]

    return Room(
        name=name,
        corners=poly,
        walls=list(axes.walls_a) + list(axes.walls_b),
        floor_area=Measurement(area, float(area_lo), float(area_hi), "m2",
                               prov_t, n_draws),
        perimeter=Measurement(per, float(per_lo), float(per_hi), "m",
                              prov_t, n_draws),
        ceiling_height=height,
        wall_lengths=lengths,
    )

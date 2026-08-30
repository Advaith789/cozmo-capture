"""Wall detection: find the planes, don't measure the point spread.

Measuring a room by the extent of its points was wrong in both directions at
once. Percentile-trimming the floor slab cuts into the room, because furniture
occludes the floor before it reaches the wall. Taking the outer extent instead
picks up whatever sprays past the wall — noise, the open doorway, points
through glass. On a 3.00 m room those two failures spanned 2.37 m to 4.10 m
depending on which trim was chosen.

A wall is not the edge of a point cloud. It is a plane with thousands of points
on it, and fitting that plane is both far more precise than any percentile and
immune to whatever lies beyond it.

Rooms are found in two stages:

  orientation   Project the wall-band points onto every candidate direction.
                A wall perpendicular to that direction collapses to a sharp
                spike; walls parallel to it smear out. Summing the squared
                histogram over a direction and its perpendicular therefore
                peaks when the axes line up with the room, which recovers the
                room's own orientation without assuming it matches the world.

  planes        Along each axis the spikes are candidate walls. Each is refit
                by total least squares on its own points, and opposing pairs
                give the room dimension as the distance between two planes.

Two checks fall out for free and need no ground truth: the recovered axes must
be perpendicular, and the two fitted planes of a pair must be parallel. Both
are properties of the room rather than of our estimate, so failing either means
the detection is wrong regardless of what any tape says.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Wall:
    """A vertical plane, expressed in the floorplan."""
    normal: np.ndarray     # unit (x, z), pointing into the room
    offset: float          # metres along the normal from the origin
    n_points: int
    residual_cm: float     # TLS residual, how planar it really is


@dataclass(frozen=True)
class RoomAxes:
    """The room's own orientation and the walls found along it."""
    theta_deg: float
    axis_a: np.ndarray
    axis_b: np.ndarray
    walls_a: list[Wall]
    walls_b: list[Wall]


def wall_band(points: np.ndarray, floor_y: float, ceiling_y: float,
              lower: float = 1.30, upper: float = 0.30) -> np.ndarray:
    """The clean upper part of the wall, projected to the floorplan.

    A wall is only bare above the things standing against it. Beds, desks,
    wardrobes and skirting occupy roughly the lowest 1.2 m, and doorways are
    holes through the lowest 2 m — so sampling a wall from just above the floor
    measures furniture and neighbouring rooms as much as it measures the wall.

    Measured on a real capture, wall separation varied from 2.74 m at 15-30 cm
    above the floor to 3.03 m at 90-160 cm, in a room whose walls are ~3.03 m
    apart: the low bands were badly occluded. Raising the sample to `lower`
    metres above the floor cut one room's error from +11.8 cm to +1.0 cm, and
    brought two captures of *identical* rooms from 12.3 cm apart to 1.0 cm.

    `lower` is a property of how rooms are furnished, not a tuned constant. On a
    room too short to leave a usable band it falls back proportionally.
    """
    y = points[:, 1]
    height = ceiling_y - floor_y
    lo = lower if height - lower - upper > 0.5 else max(0.35, 0.45 * height)
    keep = (y > floor_y + lo) & (y < ceiling_y - upper)
    return points[keep][:, [0, 2]]

    # Tried and rejected: sampling above the door head at 2.10 m, on the theory
    # that a doorway is a hole through the lower wall. It did cut the door-wall
    # error from +4.9 to +3.2 cm, but the thinner band widened the interval
    # from ±0.82 to ±2.09 cm and turned a passing precision gate into a failing
    # one. Net loss of one gate, so the sample stays at 1.30 m.


def find_orientation(xz: np.ndarray, bin_m: float = 0.02,
                     step_deg: float = 0.25) -> tuple[float, np.ndarray, np.ndarray]:
    """Recover the room's own axes from the floorplan points.

    Scores each candidate rotation by how concentrated the projections become.
    A rectangular room maximises this when the axes align with its walls.
    """
    best = (-1.0, 0.0)
    centred = xz - xz.mean(axis=0)
    for deg in np.arange(0.0, 90.0, step_deg):
        t = np.radians(deg)
        u = np.array([np.cos(t), np.sin(t)])
        v = np.array([-np.sin(t), np.cos(t)])
        score = 0.0
        for axis in (u, v):
            proj = centred @ axis
            bins = max(int((proj.max() - proj.min()) / bin_m), 8)
            hist, _ = np.histogram(proj, bins=bins)
            hist = hist / hist.sum()
            score += float((hist ** 2).sum())
        if score > best[0]:
            best = (score, float(deg))

    deg = best[1]
    t = np.radians(deg)
    return deg, np.array([np.cos(t), np.sin(t)]), np.array([-np.sin(t), np.cos(t)])


def _fit_line(pts: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Total-least-squares line in the floorplan. Returns (normal, offset, rms)."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    normal = vt[-1] / np.linalg.norm(vt[-1])
    offset = float(normal @ c)
    rms = float(np.sqrt(np.mean(((pts - c) @ normal) ** 2)))
    return normal, offset, rms


def find_walls(xz: np.ndarray, axis: np.ndarray, bin_m: float = 0.02,
               min_rel: float = 0.30, min_separation: float = 1.0,
               refit_band: float = 0.06, smooth_m: float = 0.08) -> list[Wall]:
    """Walls perpendicular to `axis`, as refit planes rather than histogram peaks."""
    proj = xz @ axis
    bins = max(int((proj.max() - proj.min()) / bin_m), 8)
    hist, edges = np.histogram(proj, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2

    # A wall does not land in one bin: depth noise spreads it over several
    # centimetres, so its share per bin is diluted below any fixed threshold
    # while the wall itself is unmistakable. Smooth over roughly the noise
    # width first, then look for peaks.
    width = max(int(smooth_m / bin_m), 1)
    kernel = np.ones(width) / width
    smoothed = np.convolve(hist.astype(float), kernel, mode="same")
    # Threshold relative to the strongest peak, not as an absolute share.
    # Smoothing spreads a peak and lowers its per-bin share, and how much
    # depends on the bin size and the room, so a fixed share is not a property
    # of anything real.
    peak_rel = smoothed / smoothed.max()

    peaks = [i for i in range(1, len(smoothed) - 1)
             if peak_rel[i] >= min_rel
             and smoothed[i] >= smoothed[i - 1] and smoothed[i] >= smoothed[i + 1]]
    peaks.sort(key=lambda i: -smoothed[i])

    chosen: list[int] = []
    for i in peaks:
        if all(abs(centres[i] - centres[j]) >= min_separation for j in chosen):
            chosen.append(i)

    walls: list[Wall] = []
    for i in chosen:
        near = xz[np.abs(proj - centres[i]) < refit_band]
        if len(near) < 200:
            continue
        normal, offset, rms = _fit_line(near)
        if normal @ axis < 0:            # keep normals consistently oriented
            normal, offset = -normal, -offset
        walls.append(Wall(normal=normal, offset=offset,
                          n_points=len(near), residual_cm=rms * 100))
    return sorted(walls, key=lambda w: w.offset)


def detect(points: np.ndarray, floor_y: float, ceiling_y: float,
           axes: tuple[np.ndarray, np.ndarray] | None = None,
           theta_deg: float = 0.0) -> RoomAxes:
    """Detect walls. Pass `axes` to reuse an orientation already solved for.

    The orientation search sweeps 360 rotations across the whole cloud, which
    dominates the runtime. Bootstrap resamples of the same capture describe the
    same room, so its orientation is not what varies between them — the wall
    offsets are. Reusing the axes makes resampling affordable.
    """
    xz = wall_band(points, floor_y, ceiling_y)
    # A region can be too thin to hold a wall band at all: segmentation may
    # hand us a two square metre corner, and the orientation search then
    # reduces over an empty array and raises. Declining is the right answer,
    # and the caller already knows what to do with a room it cannot fit.
    if len(xz) < 200:
        return None
    if axes is None:
        theta_deg, a, b = find_orientation(xz)
    else:
        a, b = axes
    return RoomAxes(theta_deg=theta_deg, axis_a=a, axis_b=b,
                    walls_a=find_walls(xz, a), walls_b=find_walls(xz, b))


def scaled(base: RoomAxes, factor: float) -> RoomAxes:
    """The same room under a uniform change of scale.

    The camera tiers do not know their own scale to better than the prior the
    ingest declares, and that prior swamps every other source of error, so the
    interval is the prior propagated through the geometry. Propagating it by
    re-fitting the walls on a scaled cloud looks reasonable and cannot work: a
    scaled cloud's projections move by up to 18% of the room, which is half a
    metre, while the fitter looks for points within 6 cm of the offset it was
    given. It matched nothing, every draw came back empty, and the camera tiers
    silently reported a fixed fallback interval instead of a propagated one.

    Under a uniform scaling a plane at offset d moves to offset s*d exactly, so
    there is nothing to fit. This is the closed form of what that loop was
    trying to approximate.
    """
    def s(ws: list[Wall]) -> list[Wall]:
        return [Wall(normal=w.normal, offset=w.offset * factor,
                     n_points=w.n_points, residual_cm=w.residual_cm * factor)
                for w in ws]
    return RoomAxes(theta_deg=base.theta_deg, axis_a=base.axis_a,
                    axis_b=base.axis_b, walls_a=s(base.walls_a),
                    walls_b=s(base.walls_b))


def span(walls: list[Wall]) -> float | None:
    """Distance between the outermost opposing pair of parallel walls."""
    if len(walls) < 2:
        return None
    lo, hi = walls[0], walls[-1]
    # Only meaningful if they really are parallel.
    if abs(lo.normal @ hi.normal) < 0.98:
        return None
    return float(abs(hi.offset - lo.offset))


def refit(base: RoomAxes, points: np.ndarray, floor_y: float, ceiling_y: float,
          band: float = 0.06) -> RoomAxes | None:
    """Re-fit an already-identified set of walls on a different sample.

    Detection — deciding which planes are walls at all — is a model choice, and
    it is made once on the whole capture. Resampling it as well conflates two
    different uncertainties: a draw that mistakes a wardrobe for a wall does
    not tell us how precisely we know where a wall is, it tells us the detector
    is unstable, which is worth reporting on its own rather than smearing into
    every dimension.

    So this holds the wall set fixed and re-fits each plane's position.
    """
    xz = wall_band(points, floor_y, ceiling_y)

    def again(ws: list[Wall], axis: np.ndarray) -> list[Wall] | None:
        proj = xz @ axis
        out = []
        for w in ws:
            near = xz[np.abs(proj - w.offset) < band]
            if len(near) < 200:
                return None
            normal, offset, rms = _fit_line(near)
            if normal @ axis < 0:
                normal, offset = -normal, -offset
            out.append(Wall(normal=normal, offset=offset,
                            n_points=len(near), residual_cm=rms * 100))
        return out

    wa, wb = again(base.walls_a, base.axis_a), again(base.walls_b, base.axis_b)
    if wa is None or wb is None:
        return None
    return RoomAxes(theta_deg=base.theta_deg, axis_a=base.axis_a,
                    axis_b=base.axis_b, walls_a=wa, walls_b=wb)


def skirting_inset(points: np.ndarray, wall: Wall, floor_y: float,
                   low: float = 0.02, high: float = 0.12,
                   band: float = 0.15) -> float | None:
    """How far the surface at floor level sits inside the fitted wall face.

    Skirting board stands proud of the wall, so a tape laid along the floor
    stops against it and measures a smaller room than the wall faces enclose.
    We fit walls well above it, at 1.3 m and up, and therefore report the wall
    face. Both numbers are real and they answer different questions: drywall and
    paint go on the wall face, flooring and skirting fit the clear span.

    Measured on this benchmark, all four walls of one room sat 3.3 to 4.0 cm
    inside the fitted plane at floor level and within 2 cm of it above 12 cm,
    which accounts for most of the standing disagreement with tape.
    """
    proj = points[:, [0, 2]] @ wall.normal
    near = np.abs(proj - wall.offset) < band
    y = points[:, 1]
    sel = near & (y > floor_y + low) & (y < floor_y + high)
    if sel.sum() < 800:
        return None
    d = (proj[sel] - wall.offset) * np.sign(wall.offset)
    return float(np.median(d))


def spans_multiple_spaces(points: np.ndarray, floor_y: float,
                          axes: "RoomAxes", gap_m: float = 0.45,
                          floor_slab: float = 0.10) -> tuple[bool, str]:
    """Whether the floor is one continuous room or several joined together.

    The wall detector fits the outermost planes it finds, so a capture covering
    two rooms and the doorway between them yields one rectangle spanning both
    and an area that belongs to no real room. Nothing downstream notices,
    because a fictitious room is geometrically well formed.

    A real room's floor is continuous. Two rooms joined by a doorway are two
    dense regions with a thin neck between them, so a run of near-empty bins
    across the floor is the signature.

    This is now a cheap first look rather than the last word: `geometry.spaces`
    does the actual segmentation, and the pipeline measures each room it finds
    separately. This stays because it is a projection along two axes and costs
    almost nothing, which makes it a useful sanity check on a segmentation that
    grids the whole floor.
    """
    y = points[:, 1]
    floor = points[np.abs(y - floor_y) < floor_slab][:, [0, 2]]
    if len(floor) < 5000:
        return False, ""

    for name, axis in (("A", axes.axis_a), ("B", axes.axis_b)):
        proj = floor @ axis
        lo, hi = np.percentile(proj, [1, 99])
        bins = max(int((hi - lo) / 0.15), 8)
        hist, edges = np.histogram(proj, bins=bins, range=(lo, hi))
        thin = hist < hist.max() * 0.06
        run = best = 0
        for t in thin:
            run = run + 1 if t else 0
            best = max(best, run)
        gap = best * (hi - lo) / bins
        if gap >= gap_m:
            return True, (f"a {gap * 100:.0f} cm stretch of axis {name} has "
                          f"almost no floor, so this capture looks like more "
                          f"than one space joined by a doorway")
    return False, ""

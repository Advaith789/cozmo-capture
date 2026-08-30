"""Split a capture that covers several rooms into the rooms it actually covers.

`walls.spans_multiple_spaces` could already tell that a capture was more than
one room, but it could only say so and stop, because the wall detector fits the
outermost planes it finds and a two room capture yields one rectangle spanning
both. The area that comes out belongs to no real room, and nothing downstream
notices, because a fictitious room is still geometrically well formed.

The method here is the standard one from the indoor mapping literature, and it
is worth saying why it is standard, because the obvious alternatives are worse:

  **Project the floor to a 2D occupancy image.** A room is a region of floor you
  can stand on. Walls are where floor is absent. Everything above the floor slab
  is furniture and is exactly the noise we do not want, so it is dropped.

  **Fill the holes by connectivity, not by closing.** A chair leg, a bed, a rug
  the sensor skipped: all of them punch holes in the floor that are not walls.
  The obvious fix is a morphological closing, and it is wrong. A closing at a
  hand's width bridges any gap up to twice that, which is thicker than an
  interior wall, so it dissolves the wall it was supposed to preserve. What
  separates furniture from walls is not size but connectivity: a furniture
  shadow is enclosed by floor, whereas a wall reaches the outside. So the
  background is flooded inward from the border and whatever it fails to reach
  is a hole and gets filled. That handles a shadow of any size and cannot
  bridge a wall however thin.

  **Erode until the doorways snap.** This is the whole trick. A doorway is a
  neck about 0.8 m across; a room is metres across. Eroding by a little over
  half a door width severs every doorway and leaves every room as a separate
  island, still comfortably large. Rooms fall out as connected components of
  the eroded image.

  **Grow the islands back.** Each surviving core is a seed, and the seeds are
  grown back over the original floor by nearest-first flooding, so every floor
  cell ends up assigned to the room it belongs to and the room keeps its true
  extent rather than the eroded one.

  **The doorway is the seam.** Where two grown regions meet is the passage
  between them, and the distance transform at the widest point of that seam is
  half the clear opening, which is the critical point method. That gives a
  doorway position and width for free, from geometry we already needed.

Everything is done on a grid with numpy, no scipy, because the distance
transform and the flooding are both a few lines each and a dependency that
exists only for two morphology calls is not worth carrying.

Tried and rejected: k means on the floor points, which has no notion of
connectivity and happily cuts a long room in half; and splitting on the wall
histogram gaps that `spans_multiple_spaces` already finds, which works for two
rooms side by side on an axis and fails the moment a third room is off a
corridor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GRID_M = 0.02           # cell size; 2 cm resolves a doorway jamb comfortably
FLOOR_SLAB_M = 0.12     # how far above the floor plane still counts as floor
PINHOLE_M = 0.03        # single stray cells, closed before the holes are filled
ERODE_M = 0.55          # a little over half a door, so doorways sever and rooms do not
MARGIN_M = 0.35         # how far a room's label reaches past its own floor
HIGH_BAND = (0.75, 0.97)   # the top of the wall, as a share of room height
WALL_EVIDENCE = 0.35       # share of the barrier that must reach up there
BARRIER_M = 0.30           # how far to look either side for the barrier
MIN_ROOM_M2 = 1.2       # below this is reconstruction noise, not even a cupboard
MIN_CORE_CELLS = 12     # an eroded core smaller than this is noise, not a room


@dataclass(frozen=True)
class Doorway:
    """A passage between two segmented spaces.

    The width carries an interval of one grid cell, which is where essentially
    all of its error lives: see `_debias` for why, and why it is not noise.
    """
    room_a: int
    room_b: int
    width_m: float
    lo: float
    hi: float
    centre_xz: tuple[float, float]


@dataclass(frozen=True)
class Space:
    """One room carved out of a larger capture."""
    index: int
    points: np.ndarray      # the full 3D points belonging to this room
    floor_area_m2: float
    centre_xz: tuple[float, float]


@dataclass(frozen=True)
class Segmentation:
    spaces: list[Space]
    doorways: list[Doorway]
    note: str
    labels: np.ndarray | None = None      # the grid every point was assigned on
    origin: tuple[float, float] | None = None
    cell: float = GRID_M

    @property
    def count(self) -> int:
        return len(self.spaces)

    def assign(self, points: np.ndarray) -> np.ndarray:
        """Which room each of an arbitrary set of points stands in.

        Kept so the bootstrap can be run per room: each frame's cloud is
        filtered to one room and refitted there, which is what makes a
        multi-room capture produce a real interval per room rather than one
        interval for the whole envelope.
        """
        if self.labels is None or self.origin is None:
            return np.ones(len(points), dtype=np.int64)
        nz, nx = self.labels.shape
        j = np.clip(((points[:, 0] - self.origin[0]) / self.cell).astype(int),
                    0, nx - 1)
        i = np.clip(((points[:, 2] - self.origin[1]) / self.cell).astype(int),
                    0, nz - 1)
        return self.labels[i, j]


def _shifts(a: np.ndarray):
    """The four orthogonal neighbours, padded with the array's own edge value."""
    yield np.pad(a, ((1, 0), (0, 0)), mode="edge")[:-1, :]
    yield np.pad(a, ((0, 1), (0, 0)), mode="edge")[1:, :]
    yield np.pad(a, ((0, 0), (1, 0)), mode="edge")[:, :-1]
    yield np.pad(a, ((0, 0), (0, 1)), mode="edge")[:, 1:]


def _dilate(mask: np.ndarray, r_cells: int) -> np.ndarray:
    """Binary dilation by a square of radius r, done as separable max filters."""
    out = mask.copy()
    for _ in range(r_cells):
        nxt = out.copy()
        for s in _shifts(out):
            nxt |= s
        out = nxt
    return out


def _erode(mask: np.ndarray, r_cells: int) -> np.ndarray:
    return ~_dilate(~mask, r_cells)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Fill background regions that do not reach the border.

    Walls touch the outside of the capture; the shadow under a bed does not.
    So flooding the background inward from the border reaches every wall and
    no furniture, and everything it misses is floor that was occluded.
    """
    free = ~mask
    reach = np.zeros_like(mask)
    reach[0, :] = free[0, :]
    reach[-1, :] = free[-1, :]
    reach[:, 0] = free[:, 0]
    reach[:, -1] = free[:, -1]
    while True:
        nxt = reach.copy()
        for s in _shifts(reach):
            nxt |= s & free
        if np.array_equal(nxt, reach):
            break
        reach = nxt
    return mask | (free & ~reach)


def _distance_transform(mask: np.ndarray) -> np.ndarray:
    """Chamfer distance in cells from each True cell to the nearest False cell.

    A 3-4 chamfer rather than an exact Euclidean transform: it is two passes
    and its worst case error is a couple of percent, which on a doorway width
    is under a centimetre and well inside the interval we would quote anyway.
    """
    big = mask.size + 1
    d = np.where(mask, big, 0).astype(np.int32)
    h, w = d.shape

    for i in range(h):                                  # forward pass
        row, prev = d[i], d[i - 1] if i else None
        for j in range(w):
            if row[j] == 0:
                continue
            best = row[j]
            if j:
                best = min(best, row[j - 1] + 3)
            if prev is not None:
                best = min(best, prev[j] + 3)
                if j:
                    best = min(best, prev[j - 1] + 4)
                if j + 1 < w:
                    best = min(best, prev[j + 1] + 4)
            row[j] = best

    for i in range(h - 1, -1, -1):                      # backward pass
        row = d[i]
        nxt = d[i + 1] if i + 1 < h else None
        for j in range(w - 1, -1, -1):
            if row[j] == 0:
                continue
            best = row[j]
            if j + 1 < w:
                best = min(best, row[j + 1] + 3)
            if nxt is not None:
                best = min(best, nxt[j] + 3)
                if j + 1 < w:
                    best = min(best, nxt[j + 1] + 4)
                if j:
                    best = min(best, nxt[j - 1] + 4)
            row[j] = best

    return d.astype(np.float64) / 3.0


def _label(mask: np.ndarray) -> np.ndarray:
    """Connected components, by propagating the largest id until nothing moves.

    Each cell starts as its own id and takes the maximum of its neighbourhood
    on every sweep, so a component converges to the largest id it contains in
    as many sweeps as it is wide. Vectorised, so the sweeps are cheap.
    """
    lab = np.where(mask, np.arange(1, mask.size + 1).reshape(mask.shape), 0)
    lab = lab.astype(np.int64)
    while True:
        nxt = lab.copy()
        for s in _shifts(lab):
            nxt = np.maximum(nxt, np.where(mask, s, 0))
        nxt = np.where(mask, nxt, 0)
        if np.array_equal(nxt, lab):
            break
        lab = nxt
    # Renumber to 1..n so callers can index without gaps.
    out = np.zeros_like(lab)
    for new, old in enumerate(sorted(set(lab[lab > 0].tolist())), start=1):
        out[lab == old] = new
    return out


def _flood(seeds: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Grow labelled seeds outward over mask, nearest seed first."""
    lab = seeds.copy()
    while True:
        nxt = lab.copy()
        for s in _shifts(lab):
            take = (nxt == 0) & (s > 0) & mask
            nxt = np.where(take, s, nxt)
        if np.array_equal(nxt, lab):
            break
        lab = nxt
    return lab


def _debias(raw_width: float, cell: float) -> float:
    """Take one cell back off a width measured on an occupancy grid.

    A cell is marked as floor if any point at all lands in it, so a doorway is
    rounded outward at both jambs by however far the first point sits into the
    edge cell: half a cell each side on average, one cell in total. Measured
    against a synthetic 0.85 m door the raw error is +11, +5, +3 and +2 cm at
    cell sizes of 4, 3, 2 and 1.5 cm, which is proportional to the cell and so
    is quantisation rather than noise. Subtracting a cell removes the mean of
    it; the remaining spread is inside the one cell interval quoted.
    """
    return max(raw_width - cell, 0.0)


def _seam_width(lab, dist, a: int, b: int, cell: float) -> float:
    """Clear width where two labelled regions meet, at their widest point."""
    h, w = lab.shape
    best = 0.0
    for di, dj in ((1, 0), (0, 1)):
        p = lab[:h - di, :w - dj]
        q = lab[di:, dj:]
        touch = ((p == a) & (q == b)) | ((p == b) & (q == a))
        if touch.any():
            best = max(best, float(dist[:h - di, :w - dj][touch].max()))
    return 2.0 * best * cell


def _merge_unwalled(lab: np.ndarray, occ: np.ndarray, high: np.ndarray,
                    r: int) -> np.ndarray:
    """Undo any split that is not actually separated by a wall.

    Eroding the floor finds narrow necks, and a doorway is one. So is the gap
    between a bed and a desk. On the floor alone those are the same shape, and
    treating them alike over-segmented two ordinary bedrooms: one came back as
    three rooms, none of which held enough wall to close a polygon, so a
    capture that had measured cleanly measured nothing at all. That is a worse
    failure than not segmenting.

    The test is not on the seam. The seam between two flooded regions is the
    doorway itself, and a doorway is the one place there is no wall, so asking
    whether the seam is walled always answers no. What must be walled is the
    barrier either side of it: the non-floor cells that lie between the two
    regions. And what separates a wall from a wardrobe there is height. A wall
    runs to the ceiling; furniture stops below it. So the barrier is checked in
    the top quarter of the room, where only building fabric reaches.
    """
    lab = lab.copy()
    changed = True
    while changed:
        changed = False
        labels = sorted({int(v) for v in np.unique(lab) if v > 0})
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                A, B = _dilate(lab == a, r), _dilate(lab == b, r)
                barrier = A & B & ~occ
                n = int(barrier.sum())
                if n < 4:
                    continue                       # not really adjacent
                if float(high[barrier].sum()) / n >= WALL_EVIDENCE:
                    continue                       # a wall stands between them
                lab[lab == b] = a
                changed = True
                break
            if changed:
                break

    out = np.zeros_like(lab)
    for new, old in enumerate(sorted({int(v) for v in np.unique(lab) if v > 0}),
                              start=1):
        out[lab == old] = new
    return out


def _absorb_slivers(lab: np.ndarray, min_cells: int, dist: np.ndarray,
                    cell: float, door_max: float = 1.30) -> np.ndarray:
    """Fold regions too small to be rooms into the room they most adjoin.

    Erosion and flooding can leave a corner or an alcove standing as its own
    region. Discarding those loses more than the sliver: the doorway that led
    into it goes too, because a passage is only reported between two surviving
    rooms, and on the hallway capture that threw away a correctly measured
    0.87 m door.

    Size alone cannot decide this, and trying it removed that door: a small
    region behind a doorway is a small room, and a small region joined to a
    hall by a two metre opening is part of the hall. So the seam decides. A
    region is folded into a neighbour only where what joins them is wider than
    any door, which means it was never a separate space. A region reached
    through a door-width neck keeps its own identity however small it is,
    because that is what a cupboard, an ensuite and a box room all look like.
    """
    lab = lab.copy()
    settled: set[int] = set()
    while True:
        vals, counts = np.unique(lab[lab > 0], return_counts=True)
        if len(vals) <= 1:
            break
        order = np.argsort(counts)
        small = [int(vals[i]) for i in order
                 if counts[i] < min_cells and int(vals[i]) not in settled]
        if not small:
            break
        target = small[0]
        m = lab == target
        neighbours = set()
        for sh in _shifts(lab):
            edge = sh[m]
            neighbours |= {int(v) for v in np.unique(edge)
                           if v > 0 and v != target}
        # Widest opening wins, and only if it is wider than a door.
        widths = {v: _seam_width(lab, dist, target, v, cell)
                  for v in neighbours}
        best = max(widths, key=widths.get) if widths else None
        if best is None:
            lab[m] = 0
        elif widths[best] > door_max:
            lab[m] = best
        else:
            settled.add(target)   # reached through a door: a real small room

    out = np.zeros_like(lab)
    for new, old in enumerate(sorted(set(lab[lab > 0].tolist())), start=1):
        out[lab == old] = new
    return out


def _doorways(lab: np.ndarray, dist: np.ndarray, origin, cell) -> list[Doorway]:
    """Seams between grown regions, measured at their widest point.

    The distance transform at a seam cell is the distance to the nearest wall,
    so twice it is the clear width there. The widest point along a seam is the
    middle of the opening, which is the critical point the Voronoi based room
    segmentation methods look for.
    """
    found: dict[tuple[int, int], list] = {}
    h, w = lab.shape
    for di, dj in ((1, 0), (0, 1)):
        a = lab[:h - di, :w - dj]
        b = lab[di:, dj:]
        touch = (a > 0) & (b > 0) & (a != b)
        for i, j in zip(*np.nonzero(touch)):
            key = (int(min(a[i, j], b[i, j])), int(max(a[i, j], b[i, j])))
            found.setdefault(key, []).append((float(dist[i, j]), i, j))

    out = []
    for (ra, rb), cells in found.items():
        d, i, j = max(cells)
        width = _debias(2.0 * d * cell, cell)
        # A seam only a cell or two long is two rooms brushing past each other,
        # not a passage between them.
        if len(cells) < 3 or width < 0.35:
            continue
        out.append(Doorway(
            room_a=ra, room_b=rb, width_m=round(width, 3),
            lo=round(width - cell, 3), hi=round(width + cell, 3),
            centre_xz=(round(origin[0] + j * cell, 3),
                       round(origin[1] + i * cell, 3))))
    return sorted(out, key=lambda d: (d.room_a, d.room_b))


def segment(points: np.ndarray, floor_y: float) -> Segmentation:
    """Carve a point cloud into the rooms it covers.

    Returns a single space covering everything when the capture is one room,
    which is the common case and costs one erosion to establish.
    """
    y = points[:, 1]
    floor_mask = (y > floor_y - FLOOR_SLAB_M) & (y < floor_y + FLOOR_SLAB_M)
    floor = points[floor_mask][:, [0, 2]]
    if len(floor) < 2000:
        return Segmentation([_whole(points, 0.0)], [],
                            "too little floor to segment; treated as one space")

    lo = floor.min(axis=0) - GRID_M
    hi = floor.max(axis=0) + GRID_M
    nx = int(np.ceil((hi[0] - lo[0]) / GRID_M)) + 1
    nz = int(np.ceil((hi[1] - lo[1]) / GRID_M)) + 1
    if nx * nz > 4_000_000:                    # keep the sweeps affordable
        return Segmentation([_whole(points, 0.0)], [],
                            "floor extent too large to grid; treated as one space")

    occ = np.zeros((nz, nx), dtype=bool)
    jj = ((floor[:, 0] - lo[0]) / GRID_M).astype(int)
    ii = ((floor[:, 1] - lo[1]) / GRID_M).astype(int)
    occ[ii, jj] = True

    r_pin = max(1, int(round(PINHOLE_M / GRID_M)))
    occ = _erode(_dilate(occ, r_pin), r_pin)              # close single-cell gaps
    occ = _fill_holes(occ)                                # then furniture shadows

    r_erode = max(1, int(round(ERODE_M / GRID_M)))
    cores = _erode(occ, r_erode)
    if not cores.any():
        return Segmentation([_whole(points, occ.sum() * GRID_M ** 2)], [],
                            "one space; erosion left no separate cores")

    lab_core = _label(cores)
    keep = [k for k in range(1, lab_core.max() + 1)
            if (lab_core == k).sum() >= MIN_CORE_CELLS]
    if len(keep) <= 1:
        return Segmentation([_whole(points, occ.sum() * GRID_M ** 2)], [],
                            "one space")

    seeds = np.zeros_like(lab_core)
    for new, k in enumerate(keep, start=1):
        seeds[lab_core == k] = new
    lab = _flood(seeds, occ)

    # Only building fabric reaches the top of a room, so that is where a
    # barrier is asked whether it is a wall.
    wy = points[:, 1]
    ceil = float(np.percentile(wy, 99.0))
    height = max(ceil - floor_y, 0.5)
    band = points[(wy > floor_y + HIGH_BAND[0] * height)
                  & (wy < floor_y + HIGH_BAND[1] * height)]
    high = np.zeros_like(occ)
    if len(band):
        bj = np.clip(((band[:, 0] - lo[0]) / GRID_M).astype(int), 0, nx - 1)
        bi = np.clip(((band[:, 2] - lo[1]) / GRID_M).astype(int), 0, nz - 1)
        high[bi, bj] = True
    lab = _merge_unwalled(lab, occ, _dilate(high, 2),
                          max(1, int(round(BARRIER_M / GRID_M))))
    if lab.max() <= 1:
        return Segmentation([_whole(points, occ.sum() * GRID_M ** 2)], [],
                            "one space; the splits found were not separated "
                            "by a wall")

    dist = _distance_transform(occ)
    lab = _absorb_slivers(lab, int(MIN_ROOM_M2 / GRID_M ** 2), dist, GRID_M)
    if lab.max() <= 1:
        return Segmentation([_whole(points, occ.sum() * GRID_M ** 2)], [],
                            "one space after folding in regions too small "
                            "to be rooms")

    doors = _doorways(lab, dist, (lo[0], lo[1]), GRID_M)

    # Reach each room's label a little past its own floor before assigning
    # points to it. A wall stands at the edge of the floor, not on it, so a
    # label grid that stops where the floor stops excludes every point the
    # wall fitting actually needs: an early version dropped them and the
    # bootstrap came back with no valid draws at all, because no resample ever
    # had enough points left on a wall to refit it.
    r_margin = max(1, int(round(MARGIN_M / GRID_M)))
    reach = _flood(lab, _dilate(occ, r_margin))

    # Assign every 3D point to a room by the cell it stands over, so walls and
    # ceiling travel with the floor beneath them.
    pj = np.clip(((points[:, 0] - lo[0]) / GRID_M).astype(int), 0, nx - 1)
    pi = np.clip(((points[:, 2] - lo[1]) / GRID_M).astype(int), 0, nz - 1)
    owner = reach[pi, pj]

    spaces = []
    for new in range(1, int(lab.max()) + 1):
        cells = (lab == new)                  # floor only, for a true area
        area = float(cells.sum()) * GRID_M ** 2
        if area < MIN_ROOM_M2:
            continue
        sel = points[owner == new]
        if len(sel) < 2000:
            continue
        ci, cj = np.nonzero(cells)
        # The index IS the label on the grid, not this room's position in the
        # list. Those diverge the moment a region is dropped for being too
        # small, and then `assign` hands back a label that matches no room:
        # on the hallway capture room 1 was filtered against room 2's cells and
        # kept 5,022 points of its 4.9 million, so every bootstrap draw failed
        # and the intervals silently fell back to a fixed width.
        spaces.append(Space(
            index=new, points=sel, floor_area_m2=round(area, 3),
            centre_xz=(round(lo[0] + cj.mean() * GRID_M, 3),
                       round(lo[1] + ci.mean() * GRID_M, 3))))

    if len(spaces) <= 1:
        return Segmentation([_whole(points, occ.sum() * GRID_M ** 2)], [],
                            "one space after discarding cores too small to be rooms")

    live = {s.index for s in spaces}
    doors = [d for d in doors if d.room_a in live and d.room_b in live]
    return Segmentation(
        spaces, doors,
        f"{len(spaces)} spaces separated at {len(doors)} doorway(s) by eroding "
        f"the floor by {ERODE_M * 100:.0f} cm",
        labels=reach, origin=(float(lo[0]), float(lo[1])), cell=GRID_M)


def _whole(points: np.ndarray, area: float) -> Space:
    xz = points[:, [0, 2]]
    return Space(index=1, points=points, floor_area_m2=round(area, 3),
                 centre_xz=(round(float(xz[:, 0].mean()), 3),
                            round(float(xz[:, 1].mean()), 3)))


def to_json(seg: Segmentation) -> dict:
    return {
        "spaces": seg.count,
        "note": seg.note,
        "doorways": [{
            "connects": [d.room_a, d.room_b],
            "clear_width_m": d.width_m,
            "ci_low": d.lo,
            "ci_high": d.hi,
            "centre_xz": list(d.centre_xz),
            "method": "distance transform maximum along the seam between "
                      "two flooded regions",
        } for d in seg.doorways],
    }

"""Openings: doors and windows in a fitted wall.

Two methods live here, and the second one supersedes the first. `find` treats
an opening as a hole in the wall's points; `find_raytraced` treats it as
something the camera could see through. The pipeline uses the ray traced one
wherever it has poses, which is every LiDAR capture. The hole based method is
kept because it needs nothing but a point cloud, so it still runs on a bare
mesh import, and because the tests use it to document the failure the rewrite
removed.

The hole based method, and why it is not enough:

A wall we have already fitted is a plane with several hundred thousand points
on it. A doorway is not a thing to detect in the abstract, it is a region of
that plane where the sensor got no return from the wall because there was no
wall there. So we look for absence bounded by presence.

Method, per wall:

  1. Take the points lying near the wall plane and project them into the
     plane's own 2D frame, horizontal along the wall and vertical up.
  2. Bin them into an occupancy grid at 4 cm.
  3. A column of that grid is "open" where it is empty between the floor and
     some height, with occupied cells either side of it.
  4. Group adjacent open columns, and take the run's width.

Doors and windows are then separated by geometry rather than by a classifier: a
door's opening reaches the floor, a window has wall underneath it. That is a
definition, not a guess, which matters because the brief scores a phantom
opening as harshly as a missed one.

The width reported is the clear opening, edge to edge of the surrounding wall,
which is what the gate measures. It is not the door leaf.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .walls import Wall

CELL = 0.04            # grid resolution, metres
MIN_WIDTH = 0.45       # narrower than this is not an opening, it is a gap in data
MAX_WIDTH = 3.00
MIN_HEIGHT = 0.80


@dataclass(frozen=True)
class Opening:
    kind: str              # "door" | "window"
    width: float           # metres, clear opening
    height: float
    sill: float            # height of the lower edge above the floor
    centre: float          # position along the wall, from its low end
    confidence: float      # fraction of the opening's border that is real wall


def _plane_frame(wall: Wall) -> tuple[np.ndarray, np.ndarray]:
    """In-plane horizontal direction, and the wall's 3D normal."""
    n = np.array([wall.normal[0], 0.0, wall.normal[1]])
    n /= np.linalg.norm(n)
    horiz = np.cross(np.array([0.0, 1.0, 0.0]), n)
    return horiz / np.linalg.norm(horiz), n


def find(points: np.ndarray, wall: Wall, floor_y: float, ceiling_y: float,
         band: float = 0.08) -> list[Opening]:
    """Openings in one wall."""
    horiz, n = _plane_frame(wall)

    d = points[:, [0, 2]] @ wall.normal
    near = points[np.abs(d - wall.offset) < band]
    if len(near) < 2000:
        return []

    u = near @ horiz                       # along the wall
    v = near[:, 1] - floor_y               # height above the floor
    keep = (v > 0.05) & (v < ceiling_y - floor_y - 0.05)
    u, v = u[keep], v[keep]
    if len(u) < 2000:
        return []

    u0, u1 = np.percentile(u, [0.5, 99.5])
    height = ceiling_y - floor_y
    nu = max(int((u1 - u0) / CELL), 8)
    nv = max(int(height / CELL), 8)
    grid, _, _ = np.histogram2d(u, v, bins=[nu, nv],
                                range=[[u0, u1], [0.0, height]])
    occupied = grid > 0

    # The scan misses cells it never got a clean return from, which punches
    # false holes through solid wall and fragments the real ones. Close gaps of
    # a single cell in both directions before looking for openings: a real
    # doorway is 20 cells wide, so this cannot invent or erase one.
    filled = occupied.copy()
    filled[1:-1, :] |= occupied[:-2, :] & occupied[2:, :]
    filled[:, 1:-1] |= occupied[:, :-2] & occupied[:, 2:]
    occupied = filled

    # A wall column is one that has returns over most of its height. A column
    # crossing an opening is empty over a contiguous run instead.
    col_fill = occupied.mean(axis=1)
    solid = col_fill > 0.45
    if solid.sum() < nu * 0.25:
        return []                          # too little wall to judge holes by

    openings: list[Opening] = []
    i = 0
    while i < nu:
        if solid[i]:
            i += 1
            continue
        j = i
        while j < nu and not solid[j]:
            j += 1
        # a run of non-solid columns, bounded by wall on both sides
        bounded = i > 0 and j < nu
        width = (j - i) * CELL
        if bounded and MIN_WIDTH <= width <= MAX_WIDTH:
            rows = occupied[i:j].mean(axis=0)

            # The opening is the tallest continuous run of empty rows in these
            # columns. A door has wall above its header, a window has wall both
            # above and below, so taking the run rather than "everything from
            # the floor up" is what separates the two.
            empty = rows < 0.30
            best_len = best_lo = 0
            k = 0
            while k < nv:
                if not empty[k]:
                    k += 1
                    continue
                m = k
                while m < nv and empty[m]:
                    m += 1
                if m - k > best_len:
                    best_len, best_lo = m - k, k
                k = m + 1

            sill = best_lo * CELL
            open_h = best_len * CELL
            if open_h >= MIN_HEIGHT:
                kind = "door" if sill < 0.15 else "window"
                border = float(solid[max(i - 1, 0)]) + float(solid[min(j, nu - 1)])
                openings.append(Opening(
                    kind=kind, width=float(width), height=float(open_h),
                    sill=float(sill), centre=float(u0 + (i + j) / 2 * CELL),
                    confidence=border / 2))
        i = j + 1

    return openings


def find_all(points: np.ndarray, wall_list: list[Wall], floor_y: float,
             ceiling_y: float) -> list[tuple[int, Opening]]:
    out: list[tuple[int, Opening]] = []
    for idx, w in enumerate(wall_list):
        for o in find(points, w, floor_y, ceiling_y):
            out.append((idx, o))
    return out


def find_stable(clouds: list[np.ndarray], wall_list: list[Wall], floor_y: float,
                ceiling_y: float, draws: int = 6, agree: float = 0.7,
                seed: int = 0) -> list[tuple[int, Opening, float, float]]:
    """Only report openings that survive resampling the frames.

    A single pass invents openings wherever the scan happened to miss a patch of
    wall, and the brief scores a phantom exactly as harshly as a miss. So the
    detector runs on several resamples of the capture and keeps only the
    openings that show up in most of them, at the same place on the same wall.

    Returns (wall index, representative opening, width low, width high), the
    last two being the 5th and 95th percentile of the width across draws, so an
    opening carries an interval like every other measurement in the contract.
    """
    rng = np.random.default_rng(seed)
    n = len(clouds)
    seen: list[list[tuple[int, Opening]]] = []
    for _ in range(draws):
        pts = np.vstack([clouds[i] for i in rng.integers(0, n, n)])
        seen.append(find_all(pts, wall_list, floor_y, ceiling_y))

    # Cluster by wall and position along it. Two detections are the same
    # opening if their centres land within a quarter metre.
    clusters: list[dict] = []
    for pass_idx, found in enumerate(seen):
        for idx, o in found:
            for c in clusters:
                if c["wall"] == idx and abs(c["centre"] - o.centre) < 0.25:
                    c["items"].append(o)
                    c["passes"].add(pass_idx)
                    break
            else:
                clusters.append({"wall": idx, "centre": o.centre,
                                 "items": [o], "passes": {pass_idx}})

    out = []
    for c in clusters:
        if len(c["passes"]) / draws < agree:
            continue
        widths = np.array([o.width for o in c["items"]])
        rep = c["items"][int(np.argsort(widths)[len(widths) // 2])]
        lo, hi = np.percentile(widths, [5, 95])
        out.append((c["wall"], rep, float(lo), float(hi)))
    return out


# ---------------------------------------------------------------------------
# Ray traced openings
#
# Everything above finds an opening as absence bounded by presence, and that is
# the method the indoor mapping literature specifically warns against. It holds
# for a building facade scanned from outside, where the only thing that makes a
# hole in the wall is a hole in the wall. Indoors it is false: a wardrobe, a
# bed, a person standing still all stop the sensor reaching the wall, and the
# result is a hole in exactly the same sense. That is why our widths swung by a
# factor of two between frame counts, and it is not a tuning problem, because
# the two cases are genuinely identical in the data the method looks at.
#
# What separates them is the ray, not the hole. For every depth sample we know
# where the camera was and where the return came from, so we know whether the
# line between them crossed the wall plane:
#
#   the return is past the wall   -> we saw through it, so there is a hole
#   the return is on the wall     -> there is wall there
#   the return is short of the wall -> something was in the way, and we
#                                      learned nothing about the wall behind it
#
# The third case is the whole point. The old method scored it as evidence of an
# opening; here it is scored as no evidence at all, which is what it is. A cell
# has to be seen through repeatedly, and never seen as wall, before it counts.
# ---------------------------------------------------------------------------

RT_CELL = 0.02         # ray traced grid; finer than the hole based one
WALL_BAND = 0.06       # a return within this of the plane is the wall itself
MIN_SEETHROUGH = 3     # a cell must be seen through from this many frames
MAX_WALL_VOTES = 0.10  # and be wall in at most this share of its sightings


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """Connected regions of a small boolean grid, as index arrays."""
    lab = np.zeros(mask.shape, dtype=np.int32)
    out, cur = [], 0
    h, w = mask.shape
    for si in range(h):
        for sj in range(w):
            if not mask[si, sj] or lab[si, sj]:
                continue
            cur += 1
            stack, cells = [(si, sj)], []
            lab[si, sj] = cur
            while stack:
                i, j = stack.pop()
                cells.append((i, j))
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    a, b = i + di, j + dj
                    if 0 <= a < h and 0 <= b < w and mask[a, b] and not lab[a, b]:
                        lab[a, b] = cur
                        stack.append((a, b))
            out.append(np.array(cells))
    return out


def _soft_width(seen: np.ndarray, cells: np.ndarray, nu: int,
                cell: float) -> float:
    """Clear width of one opening, measured between the cells rather than in them.

    Counting cells can only ever answer to the nearest cell, and it is wrong in
    both directions at once: a cell counts as open if any ray crossed it, which
    widens the opening by up to a cell, while the requirement to be crossed
    several times drops the part-covered cells at each jamb, which narrows it
    by about the same. Those two very nearly cancelled at a 2 cm grid and did
    not at 3 or 4 cm, which is the kind of agreement that is luck rather than
    method.

    A jamb that covers half a cell is crossed by about half as many rays as the
    open middle, so the vote count carries the sub-cell position directly. The
    first attempt summed the whole profile against the plateau, and it shrank
    the opening by more the wider it got, because ray density across a doorway
    is not flat: normalising by a middling value clips the busy middle to one
    and scores the quieter parts of a perfectly open span as fractions of a
    cell. So only the two edges are used. The jamb is placed where the profile
    crosses half the plateau, interpolated between the cell either side, which
    is the standard half maximum edge and is indifferent to whatever the
    interior does.
    """
    rows: dict[int, list[int]] = {}
    for i, j in cells:
        rows.setdefault(int(i), []).append(int(j))
    row = max(rows, key=lambda r: len(rows[r]))
    js = np.array(sorted(rows[row]))
    lo = max(js.min() - 3, 0)
    hi = min(js.max() + 4, nu)
    prof = seen[row, lo:hi].astype(float)
    inside = prof[prof > 0]
    if inside.size < 2:
        return (js.max() - js.min() + 1) * cell
    plateau = float(np.percentile(inside, 90))
    half = 0.5 * plateau
    idx = np.nonzero(prof >= half)[0]
    if len(idx) < 2:
        return (js.max() - js.min() + 1) * cell
    a, b = int(idx[0]), int(idx[-1])

    def cross(outside: int, inside_i: int) -> float:
        y0, y1 = prof[outside], prof[inside_i]
        if y1 == y0:
            return float(inside_i)
        return outside + (half - y0) / (y1 - y0) * (inside_i - outside)

    left = cross(a - 1, a) if a > 0 else a - 0.5
    right = cross(b + 1, b) if b + 1 < len(prof) else b + 0.5
    return float(right - left) * cell


def find_raytraced(views: list[tuple[np.ndarray, np.ndarray]], wall: Wall,
                   floor_y: float, ceiling_y: float,
                   cell: float = RT_CELL) -> list[Opening]:
    """Openings in one wall, from what the camera could and could not see through.

    `views` is one entry per frame: the world points it returned, and the world
    position of the camera that returned them.
    """
    horiz, n3 = _plane_frame(wall)
    n2 = wall.normal / np.linalg.norm(wall.normal)
    height = ceiling_y - floor_y
    if height <= 0:
        return []

    # Grid extent comes from the wall's own points, so u starts at its low end.
    nv = max(int(height / cell) + 1, 4)
    u_all = []
    for pts, _ in views:
        if len(pts):
            u_all.append(pts @ np.array([horiz[0], horiz[1], horiz[2]]))
    if not u_all:
        return []
    u_cat = np.concatenate(u_all)
    u0, u1 = float(np.percentile(u_cat, 0.5)), float(np.percentile(u_cat, 99.5))
    nu = max(int((u1 - u0) / cell) + 1, 4)
    if nu * nv > 400_000:
        return []

    seen = np.zeros((nv, nu), dtype=np.int32)   # times seen through
    solid = np.zeros((nv, nu), dtype=np.int32)  # times seen as wall

    for pts, centre in views:
        if not len(pts):
            continue
        s_c = float(centre[[0, 2]] @ n2 - wall.offset)
        if s_c <= 0.05:                       # camera on or behind the wall
            continue
        s_p = pts[:, [0, 2]] @ n2 - wall.offset

        on = np.abs(s_p) <= WALL_BAND
        if on.any():
            q = pts[on]
            ui = ((q @ horiz - u0) / cell).astype(int)
            vi = ((q[:, 1] - floor_y) / cell).astype(int)
            ok = (ui >= 0) & (ui < nu) & (vi >= 0) & (vi < nv)
            np.add.at(solid, (vi[ok], ui[ok]), 1)

        # Beyond the plane by more than the band: the ray went through.
        thru = s_p < -WALL_BAND
        if thru.any():
            q = pts[thru]
            t = s_c / (s_c - (q[:, [0, 2]] @ n2 - wall.offset))
            x = centre[None, :] + t[:, None] * (q - centre[None, :])
            ui = ((x @ horiz - u0) / cell).astype(int)
            vi = ((x[:, 1] - floor_y) / cell).astype(int)
            ok = (ui >= 0) & (ui < nu) & (vi >= 0) & (vi < nv)
            np.add.at(seen, (vi[ok], ui[ok]), 1)

    total = seen + solid
    with np.errstate(invalid="ignore", divide="ignore"):
        wall_share = np.where(total > 0, solid / np.maximum(total, 1), 1.0)
    opening = (seen >= MIN_SEETHROUGH) & (wall_share <= MAX_WALL_VOTES)
    if not opening.any():
        return []

    out = []
    for cells in _components(opening):
        vi, ui = cells[:, 0], cells[:, 1]
        w_m = _soft_width(seen, cells, nu, cell)
        h_m = (vi.max() - vi.min() + 1) * cell
        sill = vi.min() * cell
        if not (MIN_WIDTH <= w_m <= MAX_WIDTH) or h_m < MIN_HEIGHT:
            continue
        if len(cells) < 0.45 * (w_m / cell) * (h_m / cell):
            continue                          # too ragged to be an opening
        # How much of the border is real wall rather than the edge of what we
        # scanned. An opening bounded by wall is a door; one bounded by nothing
        # is the end of the data.
        border = 0
        real = 0
        for i, j in cells:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if 0 <= a < nv and 0 <= b < nu and not opening[a, b]:
                    border += 1
                    real += int(solid[a, b] > 0)
        conf = real / border if border else 0.0
        if conf < 0.50:
            continue
        out.append(Opening(
            kind="door" if sill < 0.20 else "window",
            width=round(w_m, 3),              # already sub-cell, see _soft_width
            height=round(h_m - cell, 3),      # height still rounds outward
            sill=round(sill, 3),
            centre=round(u0 + (ui.min() + ui.max()) / 2 * cell - u0, 3),
            confidence=round(conf, 3)))
    return sorted(out, key=lambda o: -o.width)

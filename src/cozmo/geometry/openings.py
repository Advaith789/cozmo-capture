"""Openings: doors and windows, found as holes in a fitted wall.

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

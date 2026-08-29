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
              margin: float = 0.35) -> np.ndarray:
    """Points clear of the floor and ceiling, projected to the floorplan."""
    y = points[:, 1]
    keep = (y > floor_y + margin) & (y < ceiling_y - margin)
    return points[keep][:, [0, 2]]


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


def detect(points: np.ndarray, floor_y: float, ceiling_y: float) -> RoomAxes:
    xz = wall_band(points, floor_y, ceiling_y)
    deg, a, b = find_orientation(xz)
    return RoomAxes(theta_deg=deg, axis_a=a, axis_b=b,
                    walls_a=find_walls(xz, a), walls_b=find_walls(xz, b))


def span(walls: list[Wall]) -> float | None:
    """Distance between the outermost opposing pair of parallel walls."""
    if len(walls) < 2:
        return None
    lo, hi = walls[0], walls[-1]
    # Only meaningful if they really are parallel.
    if abs(lo.normal @ hi.normal) < 0.98:
        return None
    return float(abs(hi.offset - lo.offset))

"""Room segmentation against floors whose shape is known exactly.

The thing worth testing here is not that two rooms come out as two rooms. It is
that the cases which *look* like two rooms do not: an L shaped room, a room with
a wardrobe sized hole in the floor, a room the sensor sampled unevenly. A
segmenter that splits eagerly is worse than none, because every dimension
downstream is then measured on a region that is not a room.

Three things these tests pin that were not obvious beforehand:

  * Doorway width error is quantisation, not noise. It scales with the cell
    size, which is why it is corrected by subtracting a cell rather than by
    averaging more data.
  * A furniture shadow must not split a room, however large. This is why holes
    are filled by connectivity rather than by a morphological closing, which at
    any radius wide enough to fill a wardrobe shadow also dissolves a wall.
  * Labels have to reach past the floor or the walls are lost. The wall points
    that every dimension depends on sit at the floor's edge, outside the floor
    itself.

Needs numpy, so it skips on the bare stdlib run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import numpy as np

    from cozmo.geometry import spaces
    HAVE = True
except ImportError:                                     # pragma: no cover
    HAVE = False

DOOR = 0.85


def _floor(x0, x1, z0, z1, n=60000, seed=0):
    rng = np.random.default_rng(seed)
    return np.c_[rng.uniform(x0, x1, n), rng.normal(0, 0.004, n),
                 rng.uniform(z0, z1, n)]


def _wall_face(x0, x1, z, n=30000, seed=10):
    """One face of a wall: a surface, which is all a sensor ever sees.

    Built as two faces rather than a solid block of points. A block is not what
    a depth sensor returns, and it also puts points inside the floor slab,
    which fills the wall in on the occupancy grid and joins the two rooms
    straight through it.
    """
    rng = np.random.default_rng(seed)
    return np.c_[rng.uniform(x0, x1, n), rng.uniform(0.15, 2.60, n),
                 np.full(n, z) + rng.normal(0, 0.004, n)]


def _two_rooms(door=DOOR, wall=0.15, walled=True):
    """Two 3 m rooms back to back, joined by one doorway.

    The dividing wall is built as well as the floor, because a split is only
    accepted where the seam has wall standing either side of it. A fixture with
    floor and nothing else describes a room with no walls, and asking a
    segmenter to find a doorway in it is asking the wrong question.
    """
    parts = [
        _floor(0, 3.0, 0, 3.0, 120000, 1),
        _floor(0, 3.0, 3.0 + wall, 6.0 + wall, 120000, 2),
        _floor(1.5 - door / 2, 1.5 + door / 2, 3.0, 3.0 + wall, 8000, 3),
    ]
    if walled:
        # The dividing wall: both faces, on each side of the doorway.
        for k, (x0, x1) in enumerate(((0.0, 1.5 - door / 2),
                                      (1.5 + door / 2, 3.0))):
            parts += [_wall_face(x0, x1, 3.0, seed=11 + k),
                      _wall_face(x0, x1, 3.0 + wall, seed=21 + k)]
    return np.vstack(parts)


@unittest.skipUnless(HAVE, "needs numpy")
class Splits(unittest.TestCase):
    def test_two_rooms_become_two(self):
        seg = spaces.segment(_two_rooms(), 0.0)
        self.assertEqual(seg.count, 2, seg.note)
        self.assertEqual(len(seg.doorways), 1)

    def test_doorway_width_within_two_centimetres(self):
        seg = spaces.segment(_two_rooms(), 0.0)
        w = seg.doorways[0].width_m
        self.assertLess(abs(w - DOOR), 0.02,
                        f"doorway measured {w:.3f} m against {DOOR} m")

    def test_doorway_interval_covers_the_truth(self):
        d = spaces.segment(_two_rooms(), 0.0).doorways[0]
        self.assertLessEqual(d.lo, DOOR)
        self.assertGreaterEqual(d.hi, DOOR)

    def test_wider_doors_measure_wider(self):
        for door in (0.75, 0.90, 1.10):
            with self.subTest(door=door):
                seg = spaces.segment(_two_rooms(door=door), 0.0)
                self.assertEqual(seg.count, 2)
                self.assertLess(abs(seg.doorways[0].width_m - door), 0.03)

    def test_rooms_keep_their_own_area(self):
        seg = spaces.segment(_two_rooms(), 0.0)
        for s in seg.spaces:
            self.assertLess(abs(s.floor_area_m2 - 9.0), 0.6,
                            f"room {s.index} came out at {s.floor_area_m2} m2")


@unittest.skipUnless(HAVE, "needs numpy")
class DoesNotSplitEagerly(unittest.TestCase):
    """The failure that matters: inventing a room that is not there."""

    def test_one_room_stays_one(self):
        self.assertEqual(spaces.segment(_floor(0, 3.0, 0, 3.0, 120000), 0.0).count, 1)

    def test_l_shape_stays_one(self):
        pts = np.vstack([_floor(0, 4.0, 0, 2.0, 90000, 4),
                         _floor(0, 2.0, 2.0, 4.0, 90000, 5)])
        self.assertEqual(spaces.segment(pts, 0.0).count, 1)

    def test_a_wardrobe_sized_hole_does_not_split_a_room(self):
        """A closing wide enough to fill this would dissolve a wall."""
        pts = _floor(0, 4.0, 0, 4.0, 200000, 6)
        keep = ~((pts[:, 0] > 1.2) & (pts[:, 0] < 2.8)
                 & (pts[:, 2] > 1.2) & (pts[:, 2] < 2.8))
        seg = spaces.segment(pts[keep], 0.0)
        self.assertEqual(seg.count, 1, seg.note)

    def test_furniture_leaving_a_gap_is_not_a_doorway(self):
        """The regression that made this check necessary.

        Two halves of one room, pinched to a door-width gap by furniture, with
        no wall anywhere near the pinch. On the floor alone this is exactly a
        doorway, and treating it as one turned two real bedrooms into five
        fragments that could not close a polygon between them.
        """
        seg = spaces.segment(_two_rooms(walled=False), 0.0)
        self.assertEqual(seg.count, 1, seg.note)

    def test_a_long_corridor_stays_one_room(self):
        self.assertEqual(spaces.segment(_floor(0, 1.2, 0, 8.0, 120000), 0.0).count, 1)


@unittest.skipUnless(HAVE, "needs numpy")
class PointAssignment(unittest.TestCase):
    def test_labels_reach_past_the_floor_to_the_walls(self):
        """Wall points sit outside the floor, and are the ones that matter."""
        seg = spaces.segment(_two_rooms(), 0.0)
        rng = np.random.default_rng(7)
        # A wall standing at x = 0 in room 1, just outside the floor extent.
        wall = np.c_[rng.uniform(-0.05, 0.0, 4000),
                     rng.uniform(0.0, 2.9, 4000),
                     rng.uniform(0.2, 2.8, 4000)]
        lab = seg.assign(wall)
        self.assertGreater((lab == 1).mean(), 0.9,
                           "wall points were not assigned to the room they bound")

    def test_every_room_gets_points(self):
        seg = spaces.segment(_two_rooms(), 0.0)
        for s in seg.spaces:
            self.assertGreater(len(s.points), 5000)


@unittest.skipUnless(HAVE, "needs numpy")
class Deterministic(unittest.TestCase):
    def test_same_cloud_twice_gives_the_same_split(self):
        pts = _two_rooms()
        a, b = spaces.segment(pts, 0.0), spaces.segment(pts, 0.0)
        self.assertEqual(a.count, b.count)
        self.assertEqual([d.width_m for d in a.doorways],
                         [d.width_m for d in b.doorways])


if __name__ == "__main__":
    unittest.main(verbosity=2)

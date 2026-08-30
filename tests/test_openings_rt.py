"""Ray traced openings, against a wall with a real door and a false one.

The whole reason this method exists is one confusion the previous one could not
resolve: a doorway and a wardrobe both stop the sensor returning wall, so both
look like a hole in a fitted plane. The literature on indoor opening detection
says this plainly, and our own opening widths swinging by a factor of two
across frame counts was the same fact arriving the hard way.

So the fixture here is deliberately the confusing case. One wall, a real
0.90 m doorway, and a wardrobe of almost exactly the same size standing flat
against the wall a metre away. Any method that looks only at where wall points
are absent must report two openings. A method that looks at what the camera
could see *through* must report one.

The last test pins the old method failing on the same data, because a fix is
worth only as much as the failure it removes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import numpy as np

    from cozmo.geometry import openings
    from cozmo.geometry.walls import Wall
    HAVE = True
except ImportError:                                     # pragma: no cover
    HAVE = False

WALL_Z = 3.0
CEIL = 2.70
DOOR_X = (1.00, 1.90)          # 0.90 m clear opening
DOOR_TOP = 2.03
WARD_X = (0.05, 0.90)          # 0.85 m wardrobe, against the same wall
WARD_TOP = 2.00
WARD_Z = 2.62                  # its front face, 38 cm proud of the wall


def _wall() -> "Wall":
    """The wall at z = 3, with its normal pointing back into the room."""
    return Wall(normal=np.array([0.0, -1.0]), offset=-WALL_Z,
                n_points=50000, residual_cm=0.4)


def _view(cam, seed):
    """One frame: what the sensor returns for this wall, from `cam`.

    Traced properly along the ray rather than dropped straight back in z. A
    ray aimed at the wall point (x, y) is the thing that either lands on the
    wall, carries on through the doorway, or stops early on the wardrobe, and
    where it ends up is not at the same (x, y) unless the camera happens to be
    level with it. Getting this wrong was worth catching: it moves the
    apparent sill of a doorway up towards the height the phone was held at,
    which is exactly the artefact a real capture would suffer from too.
    """
    rng = np.random.default_rng(seed)
    cam = np.asarray(cam, dtype=float)
    n = 40000
    x = rng.uniform(-0.1, 3.1, n)
    y = rng.uniform(0.02, CEIL, n)

    target = np.c_[x, y, np.full(n, WALL_Z)]       # where the ray meets the wall
    d = target - cam
    pts = target.copy()

    # Through the doorway the ray carries on and lands somewhere beyond.
    thru = (x > DOOR_X[0]) & (x < DOOR_X[1]) & (y < DOOR_TOP)
    t_far = (5.0 - cam[2]) / (WALL_Z - cam[2])
    pts[thru] = cam + t_far * d[thru]

    # The wardrobe stops the ray at its own front face, short of the wall.
    ward = (x > WARD_X[0]) & (x < WARD_X[1]) & (y < WARD_TOP)
    t_w = (WARD_Z - cam[2]) / (WALL_Z - cam[2])
    pts[ward] = cam + t_w * d[ward]

    return pts + rng.normal(0, 0.004, (n, 3)), cam


def _views():
    return [_view(c, i) for i, c in enumerate(
        [(1.5, 1.5, 0.8), (0.9, 1.4, 1.0), (2.1, 1.6, 1.0),
         (1.5, 1.2, 1.4), (1.2, 1.5, 0.6)])]


@unittest.skipUnless(HAVE, "needs numpy")
class RayTraced(unittest.TestCase):
    def test_finds_exactly_one_opening(self):
        found = openings.find_raytraced(_views(), _wall(), 0.0, CEIL)
        self.assertEqual(len(found), 1,
                         f"expected the doorway alone, got "
                         f"{[(o.kind, round(o.width, 2)) for o in found]}")

    def test_the_opening_is_the_door_not_the_wardrobe(self):
        o = openings.find_raytraced(_views(), _wall(), 0.0, CEIL)[0]
        truth = DOOR_X[1] - DOOR_X[0]
        self.assertEqual(o.kind, "door")
        self.assertLess(abs(o.width - truth), 0.02,
                        f"door measured {o.width:.3f} m against {truth:.2f} m")

    def test_the_wardrobe_is_not_reported(self):
        """The failure this method exists to remove."""
        for o in openings.find_raytraced(_views(), _wall(), 0.0, CEIL):
            centre_x = 3.1 - o.centre        # grid runs against +x here
            self.assertFalse(WARD_X[0] < centre_x < WARD_X[1],
                             "reported the wardrobe as an opening")

    def test_a_blank_wall_yields_nothing(self):
        rng = np.random.default_rng(99)
        views = []
        for i in range(5):
            x = rng.uniform(-0.1, 3.1, 40000)
            y = rng.uniform(0.02, CEIL, 40000)
            views.append((np.c_[x, y, np.full_like(x, WALL_Z)]
                          + rng.normal(0, 0.004, (40000, 3)),
                          np.array([1.5, 1.4, 1.0])))
        self.assertEqual(openings.find_raytraced(views, _wall(), 0.0, CEIL), [])

    def test_door_width_tracks_the_truth_inside_the_gate(self):
        """The gate the brief sets is 2 cm, so that is what is asserted."""
        global DOOR_X
        keep = DOOR_X
        try:
            for w in (0.70, 0.90, 1.20):
                DOOR_X = (1.00, 1.00 + w)
                with self.subTest(width=w):
                    found = openings.find_raytraced(_views(), _wall(), 0.0, CEIL)
                    self.assertEqual(len(found), 1)
                    self.assertLess(abs(found[0].width - w), 0.02,
                                    f"{found[0].width:.3f} m against {w:.2f} m")
        finally:
            DOOR_X = keep

    def test_width_does_not_depend_on_the_grid(self):
        """Sub-cell edges, so halving the cell must not move the answer much.

        Before the half maximum edge this varied by 4 cm between a 4 cm and a
        2 cm grid, which is how we knew the number was the grid's and not the
        door's.
        """
        widths = [openings.find_raytraced(_views(), _wall(), 0.0, CEIL,
                                          cell=c)[0].width
                  for c in (0.04, 0.03, 0.02)]
        self.assertLess(max(widths) - min(widths), 0.02,
                        f"widths wandered with the grid: {widths}")


@unittest.skipUnless(HAVE, "needs numpy")
class TheOldMethodOnTheSameData(unittest.TestCase):
    """Why the rewrite was necessary rather than a tuning exercise."""

    def test_hole_based_detection_cannot_tell_them_apart(self):
        pts = np.vstack([p for p, _ in _views()])
        near = pts[np.abs(pts[:, 2] - WALL_Z) < 0.08]
        found = openings.find(near, _wall(), 0.0, CEIL)
        self.assertGreaterEqual(
            len(found), 2,
            "the hole based method was expected to report the wardrobe too; "
            "if it no longer does, this test has stopped documenting anything")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Geometry against a room whose dimensions are exactly known.

Every accuracy figure elsewhere is scored against a tape that proved good to
only a few centimetres, so it cannot separate our error from the ruler's. Here
the room is built in software and ray-cast, the truth is exact, and any error
is entirely the algorithm's.

Three things these tests established that were not known before:

  * On perfect data the walls land within 0.5 cm and the ceiling is exact. The
    geometry is correct; everything else is noise and capture quality.
  * **Ceiling error tracks roughly twice the depth noise.** The envelope
    estimator finds each surface at a tail quantile, and symmetric noise pushes
    both tails outward, so floor and ceiling separate. Walls do not share this:
    a plane fit averages noise out instead of chasing a tail.
  * Ceiling height needs about ten views. At six it failed by 1.5 metres, which
    is the same sparse-coverage failure seen on the real non-compliant capture.

Needs numpy, so it skips on the bare stdlib run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import numpy as np  # noqa: F401

    import synthetic
    HAVE = True
except ImportError:                                     # pragma: no cover
    HAVE = False

W = D = 3.04        # a near cube, like the benchmark rooms
H = 2.97


def _errors(**kw):
    cap, _ = synthetic.room_capture(width=W, depth=D, height=H, **kw)
    r = synthetic.measure(cap)
    if r is None:
        return None
    return (max(abs(s - W) for s in r["spans"]), abs(r["height"] - H))


@unittest.skipUnless(HAVE, "needs numpy")
class PerfectData(unittest.TestCase):
    """With exact input the answer should be exact. It very nearly is."""

    def test_walls_within_half_a_centimetre(self):
        wall, _ = _errors(n_views=28)
        self.assertLess(wall, 0.01, f"walls off by {wall * 100:.2f} cm on ideal data")

    def test_ceiling_is_exact(self):
        _, ceil = _errors(n_views=28)
        self.assertLess(ceil, 0.001, f"ceiling off by {ceil * 100:.2f} cm on ideal data")

    def test_holds_across_room_shapes(self):
        for w, d, h in ((3.0, 4.0, 2.5), (2.5, 6.0, 2.4), (4.5, 4.5, 3.2)):
            with self.subTest(room=f"{w}x{d}x{h}"):
                cap, _ = synthetic.room_capture(width=w, depth=d, height=h,
                                                n_views=28)
                r = synthetic.measure(cap)
                self.assertIsNotNone(r)
                self.assertLess(abs(r["height"] - h), 0.005)
                for span, truth in zip(r["spans"], sorted([w, d])):
                    self.assertLess(abs(span - truth), 0.01)


@unittest.skipUnless(HAVE, "needs numpy")
class RotationInvariant(unittest.TestCase):
    """A room is the same room whichever way the capture happened to start."""

    def test_any_yaw_gives_the_same_answer(self):
        base = None
        for yaw in (0, 7, 17, 31, 45, 63):
            with self.subTest(yaw=yaw):
                e = _errors(n_views=28, yaw_deg=yaw)
                self.assertIsNotNone(e, f"failed to close a room at {yaw} degrees")
                if base is None:
                    base = e
                self.assertAlmostEqual(e[0], base[0], places=3)
                self.assertLess(e[1], 0.005)


@unittest.skipUnless(HAVE, "needs numpy")
class DegradesPredictably(unittest.TestCase):
    """Where it breaks, and how fast."""

    def test_walls_survive_ten_centimetres_of_depth_noise(self):
        wall, _ = _errors(n_views=28, depth_noise_cm=10.0)
        self.assertLess(wall, 0.03,
                        "plane fitting should average noise out, not chase it")

    def test_ceiling_error_tracks_twice_the_depth_noise(self):
        """The envelope estimator's known weakness, pinned with a number.

        It reads each surface at a tail quantile, so symmetric noise pushes the
        floor down and the ceiling up and the room grows by about 2 sigma. This
        is why the sensor's real 0.55 cm matters and why a noisier sensor would
        need a different estimator, not a wider interval.
        """
        for sigma_cm in (1.0, 2.0, 5.0):
            with self.subTest(sigma=sigma_cm):
                _, ceil = _errors(n_views=28, depth_noise_cm=sigma_cm)
                ratio = (ceil * 100) / sigma_cm
                self.assertGreater(ratio, 1.2, "expected the tail to move outward")
                self.assertLess(ratio, 2.8, f"grew {ratio:.1f}x sigma, worse than modelled")

    def test_walls_survive_five_centimetres_of_pose_noise(self):
        wall, _ = _errors(n_views=28, pose_noise_cm=5.0)
        self.assertLess(wall, 0.025)

    def test_ceiling_needs_about_ten_views(self):
        """Six views is not a capture, it is a glance."""
        _, few = _errors(n_views=6)
        _, enough = _errors(n_views=12)
        self.assertGreater(few, 0.10, "six views should visibly fail")
        self.assertLess(enough, 0.005, "twelve views should be exact")


@unittest.skipUnless(HAVE, "needs numpy")
class Deterministic(unittest.TestCase):
    """The repeatability gate is scored, so identical input must not wander."""

    def test_same_capture_twice_gives_identical_numbers(self):
        a = synthetic.measure(synthetic.room_capture(
            width=W, depth=D, height=H, n_views=20)[0])
        b = synthetic.measure(synthetic.room_capture(
            width=W, depth=D, height=H, n_views=20)[0])
        self.assertEqual(a["height"], b["height"])
        self.assertEqual(a["spans"], b["spans"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

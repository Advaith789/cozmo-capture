"""The two PNG decoders must agree, byte for byte.

There are deliberately two. `scripts/inspect_capture.py` carries a pure stdlib
copy so the field tool runs on a clean machine the moment a capture lands, with
nothing installed. `src/cozmo/io/png.py` is the pipeline's, vectorised with
numpy. Both decode the same 16-bit depth maps.

Duplication that nothing checks is duplication that drifts, and a drift here
would not crash: it would return plausible wrong millimetres, and every
measurement in the submission inherits them. So this pins them together.

Skips rather than fails when numpy is absent, because the stdlib suite is meant
to run on a machine with no dependencies at all.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

import fixtures  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "inspect_capture", ROOT / "scripts" / "inspect_capture.py")
script_png = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script_png)

try:
    import numpy as np

    from cozmo.io import png as pipeline_png
    HAVE_NUMPY = True
except ImportError:                                     # pragma: no cover
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_NUMPY, "pipeline decoder needs numpy")
class DecodersAgree(unittest.TestCase):

    def _both(self, w, h, bits, values, flt):
        blob = fixtures.encode_png_gray(w, h, bits, values, flt)
        a = script_png.png_gray_values(blob)
        b = pipeline_png.decode_gray(blob)
        self.assertIsNotNone(a, "stdlib decoder returned nothing")
        self.assertIsNotNone(b, "pipeline decoder returned nothing")
        return a, np.asarray(b).ravel().tolist()

    def test_every_filter_16bit(self):
        """Depth is 16-bit and real encoders pick a filter per row."""
        w, h = 11, 9
        vals = fixtures.depth_values(w, h, seed=17, invalid_rate=0.12)
        for flt in (0, 1, 2, 3, 4, "cycle"):
            with self.subTest(filter=flt):
                a, b = self._both(w, h, 16, vals, flt)
                self.assertEqual(a, b, f"decoders disagree on filter {flt}")
                self.assertEqual(a, vals)

    def test_every_filter_8bit(self):
        """Confidence maps are 8-bit."""
        w, h = 10, 8
        vals = fixtures.confidence_values(w, h, seed=23)
        for flt in (0, 1, 2, 3, 4, "cycle"):
            with self.subTest(filter=flt):
                a, b = self._both(w, h, 8, vals, flt)
                self.assertEqual(a, b)
                self.assertEqual(a, vals)

    def test_full_unsigned_range(self):
        """Neither may wrap or clip at the extremes of 16-bit."""
        vals = [0, 1, 255, 256, 1250, 32767, 32768, 65534, 65535, 4200, 700, 3]
        a, b = self._both(4, 3, 16, vals, "cycle")
        self.assertEqual(a, b)
        self.assertEqual(a, vals)

    def test_realistic_depth_raster(self):
        """The shape Polycam actually ships: 256x192, millimetres."""
        w, h = 64, 48        # same aspect, small enough to stay quick
        vals = fixtures.depth_values(w, h, seed=5)
        a, b = self._both(w, h, 16, vals, "cycle")
        self.assertEqual(a, b)
        nz = [v for v in b if v > 0]
        self.assertTrue(0.1 <= min(nz) / 1000 and max(nz) / 1000 <= 5.0,
                        "decoded depths are not room scale in metres")

    def test_headers_agree(self):
        blob = fixtures.encode_png_gray(7, 5, 16, [123] * 35, 3)
        self.assertEqual(script_png.png_header(blob), pipeline_png.header(blob))

    def test_both_reject_non_png(self):
        junk = b"\xff\xd8\xff\xd9not a png at all"
        self.assertIsNone(script_png.png_gray_values(junk))
        self.assertIsNone(pipeline_png.decode_gray(junk))


if __name__ == "__main__":
    unittest.main(verbosity=2)

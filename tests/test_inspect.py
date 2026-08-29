"""Tests for the capture inspector.

Run:  python3 -m unittest discover -s tests -v

The load-bearing case is PNG filter coverage. Depth arrives as filtered 16-bit
PNG and our decoder is hand-rolled, so a wrong Paeth or Average branch would
not crash — it would return plausible-looking wrong millimetres, and every
measurement downstream would inherit the error.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import fixtures  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "inspect_capture", ROOT / "scripts" / "inspect_capture.py")
inspect_capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inspect_capture)


class PngDecoding(unittest.TestCase):
    """Every filter type, both bit depths, exact round-trip."""

    def test_all_filters_16bit(self):
        w, h = 9, 7
        vals = fixtures.depth_values(w, h, seed=3, invalid_rate=0.15)
        for flt in (0, 1, 2, 3, 4, "cycle"):
            with self.subTest(filter=flt):
                png = fixtures.encode_png_gray(w, h, 16, vals, flt)
                got = inspect_capture.png_gray_values(png)
                self.assertEqual(got, vals, f"16-bit filter {flt} decoded wrong")

    def test_all_filters_8bit(self):
        w, h = 8, 6
        vals = fixtures.confidence_values(w, h, seed=5)
        for flt in (0, 1, 2, 3, 4, "cycle"):
            with self.subTest(filter=flt):
                png = fixtures.encode_png_gray(w, h, 8, vals, flt)
                self.assertEqual(inspect_capture.png_gray_values(png), vals)

    def test_full_16bit_range_survives(self):
        """Depth is unsigned 16-bit; the extremes must not wrap or clip."""
        vals = [0, 1, 255, 256, 1250, 32767, 32768, 65534, 65535, 4200, 700, 3]
        png = fixtures.encode_png_gray(4, 3, 16, vals, "cycle")
        self.assertEqual(inspect_capture.png_gray_values(png), vals)

    def test_header_reports_16bit_grayscale(self):
        png = fixtures.encode_png_gray(5, 4, 16, [100] * 20, 2)
        head = inspect_capture.png_header(png)
        self.assertEqual(head, {"width": 5, "height": 4,
                                "bit_depth": 16, "color_type": 0})

    def test_rejects_non_png(self):
        self.assertIsNone(inspect_capture.png_header(b"\xff\xd8\xff\xd9"))
        self.assertIsNone(inspect_capture.png_gray_values(b"not a png"))


class Exif(unittest.TestCase):

    def test_focal_length_round_trips(self):
        jpeg = fixtures.encode_jpeg_with_exif(focal_mm=6.765)
        exif = inspect_capture.read_exif(jpeg)
        self.assertAlmostEqual(exif["FocalLength"], 6.765, places=3)
        self.assertEqual(exif["FocalLengthIn35mmFilm"], 28)
        self.assertEqual(exif["Make"], "Apple")
        self.assertEqual(exif["Model"], "iPhone 17 Pro")
        self.assertEqual(exif["PixelXDimension"], 8064)
        self.assertEqual(exif["PixelYDimension"], 6048)

    def test_stripped_exif_returns_empty_not_crash(self):
        """A re-encoded transfer loses EXIF; we must report it, not blow up."""
        bare = b"\xff\xd8" + b"\xff\xda\x00\x02\x00" + b"\x00" * 32 + b"\xff\xd9"
        self.assertEqual(inspect_capture.read_exif(bare), {})

    def test_non_jpeg_returns_empty(self):
        self.assertEqual(inspect_capture.read_exif(b"\x00" * 64), {})


class SourceAccess(unittest.TestCase):
    """A zip and an unpacked directory must present identically."""

    def test_zip_and_directory_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            z = fixtures.build_polycam_zip(tmp / "scan.zip", frames=4,
                                           wrapper=None)

            import zipfile
            unpacked = tmp / "unpacked"
            with zipfile.ZipFile(z) as zf:
                zf.extractall(unpacked)

            from_zip = inspect_capture.Source(z)
            from_dir = inspect_capture.Source(unpacked)
            self.assertEqual(from_zip.files(), from_dir.files())
            self.assertEqual(from_zip.read("keyframes/cameras/00000.json"),
                             from_dir.read("keyframes/cameras/00000.json"))

    def test_strips_single_root_folder(self):
        """A wrapped archive still presents paths relative to the capture."""
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "scan.zip", frames=2,
                                           wrapper="scan-01")
            files = inspect_capture.Source(z).files()
            self.assertIn("mesh_info.json", files)
            self.assertIn("keyframes/depth/00000.png", files)
            self.assertFalse(any(f.startswith("scan-01/") for f in files))


class ArchiveLayout(unittest.TestCase):
    """Both shipping layouts must read identically.

    Regression: the observed export has no wrapping folder, and the root-strip
    heuristic mistook keyframes/ for one — silently removing it from every path
    so nothing downstream found the capture at all.
    """

    def test_no_wrapper_folder_keeps_keyframes(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "s.zip", frames=3,
                                           wrapper=None)
            files = inspect_capture.Source(z).files()
            self.assertIn("mesh_info.json", files)
            self.assertIn("keyframes/depth/00000.png", files)
            self.assertIn("keyframes/corrected_cameras/00000.json", files)

    def test_both_layouts_expose_the_same_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            flat = fixtures.build_polycam_zip(Path(tmp) / "a.zip", frames=3,
                                              wrapper=None)
            wrapped = fixtures.build_polycam_zip(Path(tmp) / "b.zip", frames=3,
                                                 wrapper="scan-01")
            self.assertEqual(inspect_capture.Source(flat).files(),
                             inspect_capture.Source(wrapped).files())

    def test_sizes_resolve_without_wrapper(self):
        """The original failure surfaced as a KeyError from size() lookups."""
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "s.zip", frames=3,
                                           wrapper=None)
            src = inspect_capture.Source(z)
            for f in src.files():
                self.assertGreaterEqual(src.size(f), 0)


class DepthSemantics(unittest.TestCase):
    """Decoded depth has to land in room-scale millimetres."""

    def test_values_are_plausible_room_distances(self):
        w, h = 16, 12
        vals = fixtures.depth_values(w, h)
        png = fixtures.encode_png_gray(w, h, 16, vals, "cycle")
        got = inspect_capture.png_gray_values(png)
        nonzero = [v for v in got if v > 0]
        self.assertTrue(nonzero)
        self.assertGreaterEqual(min(nonzero) / 1000, 0.1)
        self.assertLessEqual(max(nonzero) / 1000, 5.0)

    def test_zero_marks_invalid_not_touching_the_lens(self):
        vals = [0, 0, 1200, 3400]
        png = fixtures.encode_png_gray(2, 2, 16, vals, 4)
        got = inspect_capture.png_gray_values(png)
        self.assertEqual(got.count(0), 2)


class Reporting(unittest.TestCase):
    """End-to-end: the warnings that exist to catch field mistakes must fire."""

    def _run(self, target: Path) -> str:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            src = inspect_capture.Source(target)
            groups = inspect_capture.print_tree(src)
            if any(d.startswith("keyframes") for d in groups):
                inspect_capture.report_polycam(src, groups)
            else:
                inspect_capture.report_photos(src, groups)
        return buf.getvalue()

    def test_missing_loop_closure_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "s.zip", frames=6,
                                           corrected=False)
            out = self._run(z)
            self.assertIn("corrected_cameras/ is EMPTY", out)
            self.assertIn("drift", out)

    def test_healthy_capture_reports_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "s.zip", frames=120)
            out = self._run(z)
            self.assertIn("[ok]", out)
            self.assertNotIn("corrected_cameras/ is EMPTY", out)

    def test_frame_count_over_auto_threshold_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(
                Path(tmp) / "s.zip",
                frames=inspect_capture.POSE_OPT_AUTO + 5, corrected=False)
            self.assertIn("custom processing panel", self._run(z))

    def test_intrinsics_are_surfaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "s.zip", frames=4)
            out = self._run(z)
            for key in ("fx", "fy", "cx", "cy"):
                self.assertIn(key, out)
            self.assertNotIn("no intrinsics under", out)

    def test_depth_reported_in_metres(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = fixtures.build_polycam_zip(Path(tmp) / "s.zip", frames=4)
            out = self._run(z)
            self.assertIn("as millimetres:", out)
            self.assertIn("% valid", out)

    def test_heic_and_room_counts_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fixtures.build_photo_set(
                Path(tmp) / "photos",
                rooms={"kitchen": 5, "hallway": 11},
                heic_room="bedroom_1")
            out = self._run(root)
            self.assertIn("HEIC/HEIF", out)
            self.assertIn("outside the 2–8 per room range", out)
            self.assertIn("iPhone 17 Pro", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

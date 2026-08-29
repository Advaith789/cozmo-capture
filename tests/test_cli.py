"""Tier detection and failure behaviour.

These exist because of the walk-in test. The pipeline gets pointed at a capture
nobody has seen, on someone else's phone, in front of people. A stack trace
there is indistinguishable from the tool being broken, so every input we can
anticipate has to produce a sentence and an exit code instead.

Two real crashes were found this way and are pinned below: a folder holding a
video was classified as "unknown" rather than tier B, and a truncated archive
raised out of the ingest.

Runs on stdlib alone. `detect_tier` and the argument parser import no numpy;
the geometry does, and is covered by the venv suite.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "cozmo_main", ROOT / "src" / "cozmo" / "__main__.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def _polycam_zip(path: Path, wrapper: str = "") -> Path:
    pre = f"{wrapper}/" if wrapper else ""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{pre}mesh_info.json", "{}")
        z.writestr(f"{pre}keyframes/cameras/1.json", "{}")
        z.writestr(f"{pre}keyframes/depth/1.png", b"\x00")
    return path


class TierDetection(unittest.TestCase):
    """The tier comes from the shape of the input, never from a flag."""

    def test_polycam_zip_is_tier_c(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.detect_tier(_polycam_zip(Path(t) / "s.zip")), "C")

    def test_unpacked_polycam_folder_is_tier_c(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "keyframes").mkdir()
            self.assertEqual(cli.detect_tier(Path(t)), "C")

    def test_video_file_is_tier_b(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "walk.mov"
            f.write_bytes(b"\x00" * 32)
            self.assertEqual(cli.detect_tier(f), "B")

    def test_folder_holding_a_video_is_tier_b(self):
        """Regression: this used to raise instead of classifying."""
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "IMG_1.MOV").write_bytes(b"\x00" * 32)
            self.assertEqual(cli.detect_tier(Path(t)), "B")

    def test_photo_folder_is_tier_a(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "kitchen").mkdir()
            (Path(t) / "kitchen" / "a.HEIC").write_bytes(b"\x00" * 16)
            self.assertEqual(cli.detect_tier(Path(t)), "A")

    def test_video_wins_over_stray_thumbnails(self):
        """A walkthrough folder often also holds a poster frame."""
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "clip.mp4").write_bytes(b"\x00" * 32)
            (Path(t) / "thumb.jpg").write_bytes(b"\x00" * 16)
            self.assertEqual(cli.detect_tier(Path(t)), "B")

    def test_unrecognisable_input_raises_rather_than_guessing(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "notes.txt").write_text("hello")
            with self.assertRaises(ValueError):
                cli.detect_tier(Path(t))


class FailsCleanly(unittest.TestCase):
    """Every anticipated bad input exits with a message, never a traceback."""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(argv)
            except SystemExit as e:            # argparse
                code = int(e.code or 0)
        return code, out.getvalue() + err.getvalue()

    def test_missing_path_is_reported_not_raised(self):
        code, text = self._run(["run", "/definitely/not/here.zip"])
        self.assertEqual(code, 1)
        self.assertIn("does not exist", text)
        self.assertNotIn("Traceback", text)

    def test_unrecognisable_input_explains_what_was_expected(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "notes.txt").write_text("hello")
            code, text = self._run(["run", t])
        self.assertEqual(code, 1)
        self.assertIn("expected", text)
        self.assertNotIn("Traceback", text)

    def test_unreadable_video_fails_cleanly(self):
        """Tier B runs structure from motion; a stub file must not crash it."""
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "clip.mov").write_bytes(b"\x00" * 32)
            code, text = self._run(["run", t])
        self.assertNotEqual(code, 0)
        self.assertNotIn("Traceback", text)

    def test_truncated_archive_does_not_raise(self):
        """Regression: a half-copied export used to raise out of ingest."""
        with tempfile.TemporaryDirectory() as t:
            good = _polycam_zip(Path(t) / "s.zip")
            bad = Path(t) / "half.zip"
            bad.write_bytes(good.read_bytes()[: len(good.read_bytes()) // 2])
            code, text = self._run(["run", str(bad)])
        self.assertNotEqual(code, 0)
        self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

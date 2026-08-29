#!/usr/bin/env python3
"""Inspect a raw capture export and report what it actually contains.

Step 2 of the capture route: the delivery contract in our protocol has to be
derived from a real export, not from a vendor's marketing page. Point this at
whatever comes off the phone and paste the output into docs/capture-bakeoff.md.

    python3 scripts/inspect_capture.py ~/Downloads/polycam-export.zip
    python3 scripts/inspect_capture.py ~/Downloads/photos/kitchen/
    python3 scripts/inspect_capture.py ~/Downloads/walkthrough.mov

Stdlib only, so it runs on a clean machine with no install step.
"""

from __future__ import annotations

import json
import statistics
import struct
import sys
import zipfile
import zlib
from collections import Counter
from pathlib import Path

# Polycam runs global pose optimisation automatically below this many frames,
# and can be pushed to ~1400 from the custom processing panel. Above that we
# are on raw ARKit tracking and own the drift entirely.
POSE_OPT_AUTO = 700
POSE_OPT_MAX = 1400

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
VIDEO_EXT = {".mov", ".mp4", ".m4v"}


# --------------------------------------------------------------------------
# a filesystem-ish view that works the same for a zip and a directory
# --------------------------------------------------------------------------


class Source:
    """Uniform read access to either a zip archive or a directory tree."""

    def __init__(self, path: Path):
        self.path = path
        self._zip = zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
        if self._zip:
            names = [n for n in self._zip.namelist() if not n.endswith("/")]
            # Exports usually nest everything under one folder; drop that prefix
            # so paths read the same as they do on disk.
            roots = {n.split("/", 1)[0] for n in names if "/" in n}
            self._strip = f"{roots.pop()}/" if len(roots) == 1 else ""
            self._names = names
        else:
            self._strip = ""
            self._names = [
                str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()
            ]

    @property
    def kind(self) -> str:
        return "zip archive" if self._zip else "directory"

    def rel(self, name: str) -> str:
        return name[len(self._strip):] if name.startswith(self._strip) else name

    def files(self) -> list[str]:
        return sorted(self.rel(n) for n in self._names)

    def read(self, rel_name: str) -> bytes:
        if self._zip:
            return self._zip.read(self._strip + rel_name)
        return (self.path / rel_name).read_bytes()

    def size(self, rel_name: str) -> int:
        if self._zip:
            return self._zip.getinfo(self._strip + rel_name).file_size
        return (self.path / rel_name).stat().st_size


# --------------------------------------------------------------------------
# PNG: depth and confidence maps arrive as single-channel PNGs
# --------------------------------------------------------------------------


def png_header(data: bytes) -> dict | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return {"width": w, "height": h, "bit_depth": bit_depth, "color_type": color_type}


def png_gray_values(data: bytes) -> list[int] | None:
    """Decode a single-channel 8- or 16-bit PNG to a flat list of samples."""
    head = png_header(data)
    if not head or head["color_type"] != 0 or head["bit_depth"] not in (8, 16):
        return None

    idat, pos = b"", 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        if ctype == b"IDAT":
            idat += data[pos + 8:pos + 8 + length]
        elif ctype == b"IEND":
            break
        pos += 12 + length

    raw = zlib.decompress(idat)
    w, h, bpp = head["width"], head["height"], head["bit_depth"] // 8
    stride = w * bpp
    out, prev = bytearray(), bytearray(stride)

    for row in range(h):
        start = row * (stride + 1)
        flt = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if flt == 1:
                line[i] = (line[i] + a) & 0xFF
            elif flt == 2:
                line[i] = (line[i] + b) & 0xFF
            elif flt == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif flt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        out += line
        prev = line

    if bpp == 1:
        return list(out)
    return [v for (v,) in struct.iter_unpack(">H", bytes(out))]


# --------------------------------------------------------------------------
# EXIF: the photo tier's only route to camera intrinsics
# --------------------------------------------------------------------------

EXIF_TAGS = {
    0x010F: "Make",
    0x0110: "Model",
    0x829A: "ExposureTime",
    0x920A: "FocalLength",
    0xA405: "FocalLengthIn35mmFilm",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
}


def read_exif(data: bytes) -> dict:
    """Minimal EXIF reader: enough to confirm focal length survived transfer."""
    if data[:2] != b"\xff\xd8":
        return {}
    pos = 2
    while pos < len(data) - 4:
        if data[pos] != 0xFF:
            break
        marker, seg_len = data[pos + 1], struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if marker == 0xE1 and data[pos + 4:pos + 10] == b"Exif\x00\x00":
            return _parse_tiff(data[pos + 10:pos + 2 + seg_len])
        if marker == 0xDA:  # start of scan; no more metadata past here
            break
        pos += 2 + seg_len
    return {}


def _parse_tiff(tiff: bytes) -> dict:
    if len(tiff) < 8:
        return {}
    endian = "<" if tiff[:2] == b"II" else ">"
    (ifd_off,) = struct.unpack(endian + "I", tiff[4:8])
    found: dict = {}

    def walk(offset: int, depth: int = 0) -> None:
        if depth > 2 or offset <= 0 or offset + 2 > len(tiff):
            return
        (count,) = struct.unpack(endian + "H", tiff[offset:offset + 2])
        for i in range(count):
            e = offset + 2 + i * 12
            if e + 12 > len(tiff):
                return
            tag, typ, n = struct.unpack(endian + "HHI", tiff[e:e + 8])
            val_bytes = tiff[e + 8:e + 12]
            if tag == 0x8769:  # pointer to the Exif sub-IFD
                walk(struct.unpack(endian + "I", val_bytes)[0], depth + 1)
                continue
            if tag not in EXIF_TAGS:
                continue
            size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}.get(typ, 0) * n
            if size > 4:
                (ptr,) = struct.unpack(endian + "I", val_bytes)
                val_bytes = tiff[ptr:ptr + size]
            name = EXIF_TAGS[tag]
            if typ == 2:
                found[name] = val_bytes.rstrip(b"\x00").decode("utf-8", "replace")
            elif typ == 3:
                found[name] = struct.unpack(endian + "H", val_bytes[:2])[0]
            elif typ == 4:
                found[name] = struct.unpack(endian + "I", val_bytes[:4])[0]
            elif typ == 5 and len(val_bytes) >= 8:
                num, den = struct.unpack(endian + "II", val_bytes[:8])
                found[name] = round(num / den, 3) if den else None

    walk(ifd_off)
    return found


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def print_tree(src: Source) -> dict[str, list[str]]:
    """Group files by directory and print counts, not 3000 filenames."""
    groups: dict[str, list[str]] = {}
    for f in src.files():
        groups.setdefault(str(Path(f).parent), []).append(f)

    print("FILE TREE")
    print(f"  source: {src.path.name}  ({src.kind})")
    total = sum(src.size(f) for f in src.files())
    print(f"  total:  {len(src.files())} files, {human(total)}\n")
    for d in sorted(groups):
        files = sorted(groups[d])
        exts = Counter(Path(f).suffix.lower() for f in files)
        ext_str = ", ".join(f"{n}× {e or '(no ext)'}" for e, n in exts.most_common(4))
        label = "." if d == "." else d + "/"
        print(f"  {label:<28} {len(files):>5} files   {ext_str}")
        for f in files[:2] if len(files) <= 6 else files[:1]:
            print(f"  {'':<28}   e.g. {Path(f).name}  ({human(src.size(f))})")
    print()
    return groups


def report_polycam(src: Source, groups: dict[str, list[str]]) -> None:
    print("=" * 74)
    print("POLYCAM RAW EXPORT")
    print("=" * 74 + "\n")

    def pick(sub: str) -> list[str]:
        return sorted(groups.get(f"keyframes/{sub}", []))

    cams, corrected = pick("cameras"), pick("corrected_cameras")
    depth, conf, images = pick("depth"), pick("confidence"), pick("images")

    n = len(cams) or len(images)
    print(f"  frames captured:      {n}")
    print(f"  images:               {len(images)}")
    print(f"  depth maps:           {len(depth)}")
    print(f"  confidence maps:      {len(conf)}")
    print(f"  raw poses:            {len(cams)}")
    print(f"  optimised poses:      {len(corrected)}")

    if not corrected:
        print(f"\n  [!] corrected_cameras/ is EMPTY — no loop closure ran.")
        print(f"      Poses are raw ARKit and carry the full accumulated drift.")
    elif n > POSE_OPT_MAX:
        print(f"\n  [!] {n} frames is past the ~{POSE_OPT_MAX} ceiling for optimisation.")
    elif n > POSE_OPT_AUTO:
        print(f"\n  [!] {n} frames is over the ~{POSE_OPT_AUTO} auto threshold —")
        print(f"      optimisation must be forced from the custom processing panel.")
    else:
        print(f"\n  [ok] {n} frames is inside the ~{POSE_OPT_AUTO} auto-optimisation budget.")

    if depth and conf and len(depth) != len(conf):
        print(f"\n  [!] depth/confidence count mismatch — frames are not 1:1.")

    src_cams = corrected or cams
    if src_cams:
        which = "corrected_cameras" if corrected else "cameras"
        print(f"\n  SAMPLE POSE  ({which}/{Path(src_cams[0]).name})")
        try:
            cam = json.loads(src.read(src_cams[0]))
            for k in sorted(cam):
                v = cam[k]
                if isinstance(v, float):
                    v = round(v, 4)
                print(f"    {k:<22} {v}")
            missing = {"fx", "fy", "cx", "cy"} - set(cam)
            if missing:
                print(f"    [!] no intrinsics under {sorted(missing)} — check key names")
        except Exception as exc:
            print(f"    [!] could not parse: {exc}")

    if depth:
        print(f"\n  DEPTH  ({Path(depth[0]).name})")
        raw = src.read(depth[0])
        head = png_header(raw)
        if head:
            print(f"    {head['width']}×{head['height']}, "
                  f"{head['bit_depth']}-bit, color type {head['color_type']}")
        vals = png_gray_values(raw)
        if vals:
            nz = [v for v in vals if v > 0]
            if nz:
                lo, hi = min(nz), max(nz)
                med = statistics.median(nz)
                print(f"    non-zero samples: {len(nz)}/{len(vals)} "
                      f"({100 * len(nz) / len(vals):.0f}% valid)")
                print(f"    range {lo}–{hi}, median {med:.0f}")
                print(f"    → as millimetres: {lo / 1000:.2f}–{hi / 1000:.2f} m, "
                      f"median {med / 1000:.2f} m")
                if hi > 15000 or med < 100:
                    print(f"    [!] implausible for a room — units may not be mm")
                elif hi / 1000 > 5.0:
                    print(f"    [!] samples past 5 m are beyond reliable LiDAR range")

    if conf:
        print(f"\n  CONFIDENCE  ({Path(conf[0]).name})")
        vals = png_gray_values(src.read(conf[0]))
        if vals:
            hist = Counter(vals)
            names = {0: "low", 127: "medium", 255: "high"}
            for level in sorted(hist):
                pct = 100 * hist[level] / len(vals)
                print(f"    {level:>3} ({names.get(level, '?'):<6}) {pct:5.1f}%")
            low = 100 * hist.get(0, 0) / len(vals)
            if low > 30:
                print(f"    [!] {low:.0f}% low-confidence — glass, gloss, or too far out")


def report_photos(src: Source, groups: dict[str, list[str]]) -> None:
    print("=" * 74)
    print("PHOTO SET")
    print("=" * 74 + "\n")

    rooms = {d: [f for f in fs if Path(f).suffix.lower() in IMAGE_EXT]
             for d, fs in groups.items()}
    rooms = {d: fs for d, fs in rooms.items() if fs}

    print(f"  {len(rooms)} folder(s), {sum(len(f) for f in rooms.values())} images\n")
    for d in sorted(rooms):
        fs = rooms[d]
        flag = "" if 2 <= len(fs) <= 8 else "   [!] outside the 2–8 per room range"
        print(f"    {(d if d != '.' else '(root)'):<24} {len(fs):>3} images{flag}")

    heic = [f for fs in rooms.values() for f in fs
            if Path(f).suffix.lower() in {".heic", ".heif"}]
    if heic:
        print(f"\n  [!] {len(heic)} HEIC/HEIF files. Our contract says .jpeg —")
        print(f"      set Camera → Formats → Most Compatible, or convert on ingest.")

    sample = next((f for fs in rooms.values() for f in fs
                   if Path(f).suffix.lower() in {".jpg", ".jpeg"}), None)
    if not sample:
        return

    print(f"\n  EXIF  ({Path(sample).name})")
    exif = read_exif(src.read(sample))
    if not exif:
        print("    [!] no EXIF block — stripped in transfer. Set Settings → Photos →")
        print("        Transfer to Mac or PC → Keep Originals, and re-import.")
        print("        Without focal length the photo tier loses its intrinsics.")
        return
    for k in sorted(exif):
        print(f"    {k:<22} {exif[k]}")
    if "FocalLength" not in exif and "FocalLengthIn35mmFilm" not in exif:
        print("    [!] no focal length — cannot derive intrinsics from these files.")


def report_video(path: Path) -> None:
    print("=" * 74)
    print("VIDEO")
    print("=" * 74 + "\n")
    size = path.stat().st_size
    print(f"  {path.name}  ({human(size)})")
    print("\n  No pose or depth track — this tier is frames only, as expected.")
    print("  Resolution and frame rate need ffprobe; note them from the Photos app")
    print("  Info panel for now and record them in the bake-off doc.")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    target = Path(sys.argv[1]).expanduser()
    if not target.exists():
        print(f"error: {target} does not exist")
        return 1

    if target.is_file() and target.suffix.lower() in VIDEO_EXT:
        report_video(target)
        return 0

    src = Source(target)
    groups = print_tree(src)

    if any(d.startswith("keyframes") for d in groups):
        report_polycam(src, groups)
    elif any(Path(f).suffix.lower() in IMAGE_EXT for f in src.files()):
        report_photos(src, groups)
    else:
        print("Unrecognised layout — no keyframes/ and no images.")
        print("Paste the tree above into docs/capture-bakeoff.md anyway.")

    print("\n" + "=" * 74)
    print("Paste this whole output into docs/capture-bakeoff.md and commit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

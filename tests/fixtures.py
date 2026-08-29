"""Synthetic captures that stand in for real exports.

Lets us exercise the ingest path without a phone, and pin behaviour we would
otherwise only discover in the field. The PNG encoder here can emit every
filter type, because a real encoder picks filters per row and our decoder has
to survive all of them.
"""

from __future__ import annotations

import json
import random
import struct
import zipfile
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def encode_png_gray(width: int, height: int, bit_depth: int,
                    values: list[int], filter_type: int | str = 0) -> bytes:
    """Encode single-channel grayscale PNG.

    filter_type: 0-4 to force one filter on every row, or "cycle" to rotate
    through all five the way a real encoder's heuristic would.
    """
    bpp = bit_depth // 8
    stride = width * bpp
    pack = (lambda v: struct.pack(">H", v)) if bpp == 2 else (lambda v: bytes([v]))

    raw_rows = [b"".join(pack(values[y * width + x]) for x in range(width))
                for y in range(height)]

    out, prior = b"", bytes(stride)
    for y, row in enumerate(raw_rows):
        flt = (y % 5) if filter_type == "cycle" else int(filter_type)
        line = bytearray(stride)
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            b = prior[i]
            c = prior[i - bpp] if i >= bpp else 0
            if flt == 0:
                pred = 0
            elif flt == 1:
                pred = a
            elif flt == 2:
                pred = b
            elif flt == 3:
                pred = (a + b) // 2
            else:
                pred = _paeth(a, b, c)
            line[i] = (row[i] - pred) & 0xFF
        out += bytes([flt]) + bytes(line)
        prior = row

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, 0, 0, 0, 0)
    return (PNG_SIG + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(out)) + _chunk(b"IEND", b""))


def encode_jpeg_with_exif(focal_mm: float = 6.765, make: str = "Apple",
                          model: str = "iPhone 17 Pro",
                          px: int = 8064, py: int = 6048) -> bytes:
    """Minimal JPEG carrying the EXIF fields the photo tier depends on."""
    def entry(tag: int, typ: int, count: int, val: bytes) -> bytes:
        return struct.pack("<HHI", tag, typ, count) + val

    make_b, model_b = make.encode() + b"\x00", model.encode() + b"\x00"
    make_off = 50
    model_off = make_off + len(make_b)
    exif_off = model_off + len(model_b)
    focal_off = exif_off + 2 + 4 * 12 + 4

    ifd0 = struct.pack("<H", 3) + b"".join([
        entry(0x010F, 2, len(make_b), struct.pack("<I", make_off)),
        entry(0x0110, 2, len(model_b), struct.pack("<I", model_off)),
        entry(0x8769, 4, 1, struct.pack("<I", exif_off)),
    ]) + struct.pack("<I", 0)

    exif = struct.pack("<H", 4) + b"".join([
        entry(0x920A, 5, 1, struct.pack("<I", focal_off)),
        entry(0xA405, 3, 1, struct.pack("<H", 28) + b"\x00\x00"),
        entry(0xA002, 4, 1, struct.pack("<I", px)),
        entry(0xA003, 4, 1, struct.pack("<I", py)),
    ]) + struct.pack("<I", 0)

    num, den = round(focal_mm * 1000), 1000
    tiff = (b"II" + struct.pack("<HI", 0x2A, 8) + ifd0 + make_b + model_b
            + exif + struct.pack("<II", num, den))
    assert len(b"II" + struct.pack("<HI", 0x2A, 8) + ifd0) == make_off

    app1 = (b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(tiff))
            + b"Exif\x00\x00" + tiff)
    return b"\xff\xd8" + app1 + b"\xff\xda\x00\x02\x00" + b"\x00" * 64 + b"\xff\xd9"


def depth_values(width: int, height: int, seed: int = 7,
                 lo: int = 400, hi: int = 4200, invalid_rate: float = 0.1
                 ) -> list[int]:
    """Millimetre depths with a scatter of zeros where the sensor returned nothing."""
    rng = random.Random(seed)
    return [0 if rng.random() < invalid_rate else rng.randint(lo, hi)
            for _ in range(width * height)]


def confidence_values(width: int, height: int, seed: int = 11) -> list[int]:
    """Three ARKit levels. Observed byte values are 0/54/255 — the published
    notes say 0/127/255, and the export disagrees."""
    rng = random.Random(seed)
    return [rng.choice([0, 54, 255, 255]) for _ in range(width * height)]


def build_polycam_zip(dest: Path, frames: int = 40, corrected: bool = True,
                      width: int = 16, height: int = 12,
                      png_filter: int | str = "cycle",
                      wrapper: str | None = None) -> Path:
    """A raw export shaped like the real thing, at toy resolution.

    wrapper: name of a folder wrapping the whole archive, or None for the
    layout Polycam actually produces — files at the top level. Observed
    exports have no wrapper; the parameter exists so both shapes stay tested.
    """
    pre = f"{wrapper}/" if wrapper else ""
    d_vals = depth_values(width, height)
    c_vals = confidence_values(width, height)
    depth_png = encode_png_gray(width, height, 16, d_vals, png_filter)
    conf_png = encode_png_gray(width, height, 8, c_vals, png_filter)

    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr(f"{pre}mesh_info.json", json.dumps({"version": 1}))
        zf.writestr(f"{pre}raw.glb", b"\x00" * 1024)
        zf.writestr(f"{pre}polycam.mp4", b"\x00" * 1024)
        zf.writestr(f"{pre}thumbnail.jpg", b"\xff\xd8\xff\xd9")
        for i in range(frames):
            cam = {"t_00": 1.0, "t_01": 0.0, "t_02": 0.0, "t_03": 0.01 * i,
                   "t_10": 0.0, "t_11": 1.0, "t_12": 0.0, "t_13": 1.4,
                   "t_20": 0.0, "t_21": 0.0, "t_22": 1.0, "t_23": 0.02 * i,
                   "fx": 1592.4, "fy": 1592.4, "cx": 952.1, "cy": 714.3,
                   "width": 1920, "height": 1440, "blur_score": 0.12}
            zf.writestr(f"{pre}keyframes/cameras/{i:05d}.json", json.dumps(cam))
            zf.writestr(f"{pre}keyframes/images/{i:05d}.jpg", b"\xff\xd8\xff\xd9")
            zf.writestr(f"{pre}keyframes/depth/{i:05d}.png", depth_png)
            zf.writestr(f"{pre}keyframes/confidence/{i:05d}.png", conf_png)
            if corrected:
                zf.writestr(f"{pre}keyframes/corrected_cameras/{i:05d}.json",
                            json.dumps(cam))
    return dest


def build_photo_set(root: Path, rooms: dict[str, int] | None = None,
                    heic_room: str | None = None) -> Path:
    """Per-room photo folders, the shape the photo tier ingests."""
    rooms = rooms or {"kitchen": 5, "living_room": 3, "hallway": 6}
    jpeg = encode_jpeg_with_exif()
    for room, n in rooms.items():
        d = root / room
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / f"IMG_{i:04d}.jpg").write_bytes(jpeg)
    if heic_room:
        d = root / heic_room
        d.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            (d / f"IMG_9{i:03d}.HEIC").write_bytes(b"\x00" * 128)
    return root

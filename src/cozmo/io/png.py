"""Single-channel PNG decoding for depth and confidence rasters.

scripts/inspect_capture.py carries its own pure-Python copy of this on purpose:
that tool has to run on a clean machine in the field with nothing installed, so
it cannot import numpy. This version is the pipeline's, and is vectorised where
the format allows. tests/test_png_parity.py holds the two implementations to
identical output so the duplication cannot drift.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def header(data: bytes) -> dict | None:
    if data[:8] != PNG_SIG:
        return None
    w, h, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return {"width": w, "height": h, "bit_depth": bit_depth,
            "color_type": color_type}


def decode_gray(data: bytes) -> np.ndarray | None:
    """Decode 8- or 16-bit greyscale PNG to a 2-D array of raw sample values."""
    head = header(data)
    if not head or head["color_type"] != 0 or head["bit_depth"] not in (8, 16):
        return None

    idat = bytearray()
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        if ctype == b"IDAT":
            idat += data[pos + 8:pos + 8 + length]
        elif ctype == b"IEND":
            break
        pos += 12 + length

    raw = zlib.decompress(bytes(idat))
    w, h = head["width"], head["height"]
    bpp = head["bit_depth"] // 8
    stride = w * bpp

    # One filter byte per row, then the row's bytes.
    buf = np.frombuffer(raw, dtype=np.uint8).reshape(h, stride + 1)
    filters = buf[:, 0]
    rows = buf[:, 1:].astype(np.int16)
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int16)

    for y in range(h):
        f = filters[y]
        line = rows[y]
        if f == 0:
            cur = line
        elif f == 2:
            # Up depends only on the row above, so it vectorises whole.
            cur = (line + prev) & 0xFF
        else:
            # Sub, Average and Paeth each reference the pixel to the left,
            # which makes them inherently sequential along the row.
            cur = np.empty(stride, dtype=np.int16)
            if f == 1:
                for i in range(stride):
                    a = cur[i - bpp] if i >= bpp else 0
                    cur[i] = (line[i] + a) & 0xFF
            elif f == 3:
                for i in range(stride):
                    a = cur[i - bpp] if i >= bpp else 0
                    cur[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
            elif f == 4:
                for i in range(stride):
                    a = int(cur[i - bpp]) if i >= bpp else 0
                    b = int(prev[i])
                    c = int(prev[i - bpp]) if i >= bpp else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    cur[i] = (line[i] + pred) & 0xFF
            else:
                raise ValueError(f"unknown PNG filter {f}")
        out[y] = cur.astype(np.uint8)
        prev = cur.astype(np.int16)

    if bpp == 1:
        return out
    return out.reshape(h, w, 2).astype(np.uint16) @ np.array([256, 1], dtype=np.uint16)

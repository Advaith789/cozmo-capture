"""Fallback ingest: measure from a plain mesh export.

The LiDAR tier depends on Polycam's raw export, which only exists if Developer
Mode was switched on *before* the capture. It cannot be enabled afterwards. If
the operator misses that step there is no depth, no poses and no intrinsics,
and the whole tier scores nothing.

That is a single point of total failure sitting on one toggle in someone else's
app, so this exists to survive it. Every Polycam capture can export a mesh or a
point cloud without Developer Mode, and a mesh is a set of surface points, which
is what the wall and surface fitting downstream actually consumes. What is lost
is per-frame anything: no poses to resample, so no bootstrapped interval, and
no confidence map to filter by. The result is a measurement with an honest,
wider, clearly labelled interval rather than no measurement at all.

Formats: OBJ and PLY, both ASCII and binary little-endian. Parsed here rather
than pulled in as a dependency, because this is the path that runs when
something has already gone wrong and it should not need anything installed.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import numpy as np

from ..types import Capture, DepthSource, PosedFrame, PoseSource

MESH_EXT = {".obj", ".ply"}


def _read_obj(data: bytes, max_points: int) -> np.ndarray:
    """Vertices from an OBJ. Only `v` lines matter for measurement."""
    pts = []
    for line in data.splitlines():
        if line[:2] == b"v " or line[:2] == b"v\t":
            parts = line.split()
            if len(parts) >= 4:
                try:
                    pts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    continue
    return np.asarray(pts, dtype=np.float64)


def _read_ply(data: bytes, max_points: int) -> np.ndarray:
    """Vertices from a PLY, ascii or binary little-endian."""
    end = data.find(b"end_header")
    if end < 0:
        return np.empty((0, 3))
    header = data[:end].decode("ascii", "replace")
    body = data[data.find(b"\n", end) + 1:]

    fmt = "ascii" if "format ascii" in header else "binary"
    m = re.search(r"element vertex (\d+)", header)
    if not m:
        return np.empty((0, 3))
    n = int(m.group(1))

    # Properties of the vertex element, in order, up to the next element.
    vtx_block = header.split("element vertex")[1].split("element")[0]
    props = re.findall(r"property\s+(\w+)\s+(\w+)", vtx_block)

    if fmt == "ascii":
        names = [p[1] for p in props]
        try:
            ix, iy, iz = names.index("x"), names.index("y"), names.index("z")
        except ValueError:
            return np.empty((0, 3))
        pts = []
        for line in body.splitlines()[:n]:
            f = line.split()
            if len(f) > max(ix, iy, iz):
                try:
                    pts.append((float(f[ix]), float(f[iy]), float(f[iz])))
                except ValueError:
                    continue
        return np.asarray(pts, dtype=np.float64)

    sizes = {"char": 1, "uchar": 1, "int8": 1, "uint8": 1,
             "short": 2, "ushort": 2, "int16": 2, "uint16": 2,
             "int": 4, "uint": 4, "int32": 4, "uint32": 4, "float": 4,
             "float32": 4, "double": 8, "float64": 8}
    codes = {"char": "b", "uchar": "B", "int8": "b", "uint8": "B",
             "short": "h", "ushort": "H", "int16": "h", "uint16": "H",
             "int": "i", "uint": "I", "int32": "i", "uint32": "I",
             "float": "f", "float32": "f", "double": "d", "float64": "d"}
    stride = sum(sizes.get(t, 0) for t, _ in props)
    if stride == 0:
        return np.empty((0, 3))
    offsets, off = {}, 0
    for t, nm in props:
        offsets[nm] = (off, codes.get(t, "f"))
        off += sizes.get(t, 0)
    if not all(k in offsets for k in "xyz"):
        return np.empty((0, 3))

    step = max(1, n // max_points)
    pts = []
    for i in range(0, n, step):
        base = i * stride
        if base + stride > len(body):
            break
        try:
            pts.append(tuple(
                struct.unpack_from("<" + offsets[k][1], body, base + offsets[k][0])[0]
                for k in "xyz"))
        except struct.error:
            break
    return np.asarray(pts, dtype=np.float64)


def looks_like_mesh(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() in MESH_EXT
    return any(p.suffix.lower() in MESH_EXT for p in path.rglob("*"))


def load(path: str | Path, max_points: int = 900_000) -> Capture:
    """A mesh or point cloud export becomes a Capture the geometry can measure."""
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.suffix.lower() in MESH_EXT)
        if not files:
            raise ValueError(f"{path}: no .obj or .ply found")
        path = max(files, key=lambda p: p.stat().st_size)

    data = path.read_bytes()
    pts = (_read_ply(data, max_points) if path.suffix.lower() == ".ply"
           else _read_obj(data, max_points))
    if len(pts) < 5000:
        raise ValueError(f"{path}: only {len(pts)} vertices, too few to measure")

    if len(pts) > max_points:
        idx = np.random.default_rng(0).choice(len(pts), max_points, replace=False)
        pts = pts[idx]

    # Polycam meshes come out gravity aligned, but a mesh from anywhere else
    # may not, so the vertical is checked rather than assumed: in a room the
    # up axis is the one with the two dense flat extremes, which is also the
    # axis with the smallest spread.
    spans = pts.max(axis=0) - pts.min(axis=0)
    up_axis = int(np.argmin(spans))
    if up_axis != 1:
        order = [i for i in range(3) if i != up_axis]
        pts = pts[:, [order[0], up_axis, order[1]]]

    frame = PosedFrame(
        key="mesh", depth=None, confidence=None,
        K=np.eye(3), T_wc=np.eye(4),
        depth_source=DepthSource.MEASURED, pose_source=PoseSource.NONE,
        meta={})

    return Capture(
        frames=[frame], tier="C", source=str(path),
        meta={"loaded": 1, "total_keyframes": 1, "loop_closed": False,
              "tracking_segments": 1, "points": pts, "mesh_vertices": len(pts),
              "fallback": "mesh export, no per-frame data",
              "scale_source": "sensor", "scale_lo": 0.99, "scale_hi": 1.01,
              "views": 1, "sfm_points": len(pts), "sfm_mean_inliers": 0.0,
              "intrinsics_source": "not applicable"})

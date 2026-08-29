"""A room we know the exact dimensions of.

Every accuracy figure in this project is scored against a tape that has itself
proved good to only a few centimetres. That makes it impossible to tell how
much of an error is the pipeline and how much is the ruler.

So: build a room in software, put virtual cameras in it, ray-cast depth maps
from the walls, and hand the result to the same ingest the LiDAR tier uses. The
truth is then exact to floating point, and any error is entirely ours.

Noise is added deliberately and separately, so the two questions stay apart:
is the geometry right in principle, and how fast does it degrade when the
sensor and the poses stop being perfect.
"""

from __future__ import annotations

import numpy as np

from cozmo.types import Capture, DepthSource, PosedFrame, PoseSource


def _ray_box(origin, dirs, lo, hi):
    """Distance from `origin` along each direction to the inside of a box.

    A camera inside a room sees the box from within, so the hit is the nearest
    *exit* through one of the six planes. A ray exactly parallel to a plane
    never meets it, so those get an infinite distance rather than a divide by
    zero that would poison the minimum with NaN.
    """
    safe = np.where(np.abs(dirs) < 1e-12, 1e-12, dirs)
    t_lo = (lo - origin) / safe
    t_hi = (hi - origin) / safe
    # For each axis the exit is whichever bound lies ahead of the ray.
    t_exit = np.where(dirs > 0, t_hi, t_lo)
    t_exit = np.where(np.abs(dirs) < 1e-12, np.inf, t_exit)
    return np.min(t_exit, axis=1)


def room_capture(width: float = 3.00, depth: float = 4.00,
                 height: float = 2.50, n_views: int = 24,
                 img: tuple[int, int] = (192, 256), fx: float = 180.0,
                 depth_noise_cm: float = 0.0, pose_noise_cm: float = 0.0,
                 yaw_deg: float = 0.0, cam_height: float = 1.50,
                 seed: int = 0) -> tuple[Capture, dict]:
    """A box room seen from cameras walking its perimeter.

    Returns the capture and the exact truth it was built from. `width` runs
    along world X and `depth` along world Z before `yaw_deg` is applied, so a
    rotated room exercises the axis finder rather than letting it succeed by
    accident on an axis-aligned box.
    """
    rng = np.random.default_rng(seed)
    h, w = img
    cy_, cx_ = h / 2.0, w / 2.0

    lo = np.array([-width / 2, 0.0, -depth / 2])
    hi = np.array([+width / 2, height, +depth / 2])

    yaw = np.radians(yaw_deg)
    R_yaw = np.array([[np.cos(yaw), 0, -np.sin(yaw)],
                      [0, 1, 0],
                      [np.sin(yaw), 0, np.cos(yaw)]])

    # Pixel ray directions in the camera frame: +X right, +Y up, -Z forward.
    vs, us = np.mgrid[0:h, 0:w]
    rays = np.stack([(us - cx_) / fx, -(vs - cy_) / fx, -np.ones_like(us)], -1)
    rays /= np.linalg.norm(rays, axis=-1, keepdims=True)

    frames = []
    inset = 0.55                     # how far off the wall the operator walks
    for i in range(n_views):
        t = 2 * np.pi * i / n_views
        pos = np.array([(width / 2 - inset) * np.cos(t),
                        cam_height,
                        (depth / 2 - inset) * np.sin(t)])
        # Look at the room centre, with a little tilt so floor and ceiling are
        # both sampled, which is what the protocol asks a real operator for.
        # Face the room centre, pitching up and down along the walk so the
        # floor and ceiling both get sampled, which is what the protocol asks
        # a real operator to do at each corner.
        pitch = 0.30 * np.sin(3 * t)
        flat = np.array([-pos[0], 0.0, -pos[2]])
        flat /= np.linalg.norm(flat)
        fwd = flat + np.array([0.0, np.tan(pitch), 0.0])
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        R = np.stack([right, up, -fwd], axis=1)   # columns: camera axes in world

        world_dirs = (rays.reshape(-1, 3) @ R.T)
        dist = _ray_box(pos, world_dirs, lo, hi).reshape(h, w)
        # Ray length to perpendicular depth: the camera looks down -Z, so the
        # cosine to the optical axis is the ray's own -z component.
        d = dist * (-rays[..., 2])
        if depth_noise_cm:
            d = d + rng.normal(0, depth_noise_cm / 100.0, d.shape)

        T = np.eye(4)
        T[:3, :3] = R_yaw @ R
        T[:3, 3] = R_yaw @ pos
        if pose_noise_cm:
            T[:3, 3] += rng.normal(0, pose_noise_cm / 100.0, 3)

        frames.append(PosedFrame(
            key=f"{i:05d}", depth=d.astype(np.float32),
            confidence=np.full(d.shape, 2, np.uint8),
            K=np.array([[fx, 0, cx_], [0, fx, cy_], [0, 0, 1.0]]),
            T_wc=T, depth_source=DepthSource.MEASURED,
            pose_source=PoseSource.DEVICE_OPTIMISED, meta={}))

    truth = {"width": width, "depth": depth, "height": height,
             "area": width * depth, "yaw_deg": yaw_deg}
    return Capture(frames=frames, tier="C", source="synthetic",
                   meta={"loaded": len(frames), "total_keyframes": len(frames),
                         "loop_closed": True, "tracking_segments": 1}), truth


def measure(capture: Capture):
    """Run the shipped geometry over a capture and return what it found."""
    from cozmo.geometry import walls
    from cozmo.geometry.height import _modes, ceiling_height
    from cozmo.ingest import lidar
    from cozmo.geometry import room as room_mod

    pts = np.vstack([lidar.to_world_points(f) for f in capture.frames])
    fy, cy = _modes(pts[:, 1])
    axes = walls.detect(pts, fy, cy)
    h = ceiling_height(capture, bootstrap=0)
    rm = room_mod.build(axes, h, name="synthetic")
    if rm is None:
        return None
    spans = sorted([walls.span(axes.walls_a) or 0.0,
                    walls.span(axes.walls_b) or 0.0])
    return {"height": h.value, "spans": spans,
            "area": rm.floor_area.value if rm else None}

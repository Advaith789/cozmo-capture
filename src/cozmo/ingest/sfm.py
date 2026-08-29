"""Structure from motion for the camera-only tiers.

Tiers A and B get no depth and no poses. Everything has to come out of the
pixels, which means two problems the LiDAR tier never has:

**Poses.** Recovered incrementally: match features between views, solve the
essential matrix, chain the poses, triangulate. Standard, and it works here
because real rooms are not the blank boxes they look like. Measured on this
benchmark's video, adjacent frames give 559 to 934 RANSAC inliers, well past
the ~100 a stable pose needs. Furniture, posters, carpet and shadows carry it.

**Scale.** Monocular reconstruction is correct only up to an unknown factor, so
something has to supply metres. We use the one number the capture protocol
already fixes: the operator holds the phone at chest height, so the camera sits
a known distance above the floor. Find the floor plane in the sparse cloud,
measure the cameras above it, and scale so that distance equals the prior.

That prior is soft, roughly 1.40 to 1.60 m across people, about ±7%. Every
dimension inherits it, which is why the photo tier's interval is a percentage
rather than a fixed number of centimetres, and why the brief's photo gate is
±8% rather than the LiDAR tier's ±1.5 cm. The uncertainty is real and it is
reported rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:                                     # pragma: no cover
    cv2 = None

# Chest height for a standing adult holding a phone with both hands, which is
# what the capture protocol asks for. Range across people, not a guess at one.
CAMERA_HEIGHT_M = 1.50
CAMERA_HEIGHT_LO = 1.40
CAMERA_HEIGHT_HI = 1.60

MIN_INLIERS = 60


@dataclass
class SfmResult:
    poses: list[np.ndarray]          # 4x4 camera-to-world, metric after scaling
    points: np.ndarray               # (N, 3) sparse cloud, metric
    K: np.ndarray
    scale_source: str
    scale_lo: float                  # multiply points by these to get the
    scale_hi: float                  # low and high ends of the scale prior
    n_views: int
    mean_inliers: float
    views: list = None


def intrinsics_from_fov(width: int, height: int, equiv35: float = 26.0
                        ) -> np.ndarray:
    """Camera matrix from a 35mm-equivalent focal length.

    A 35mm frame is 36 mm wide, so f_pixels = (equiv / 36) * image_width. iPhone
    photo EXIF reports the equivalent directly; video does not carry EXIF at
    all, so it takes the default, which is the wide camera's nominal value.
    """
    f = (equiv35 / 36.0) * width
    return np.array([[f, 0.0, width / 2.0],
                     [0.0, f, height / 2.0],
                     [0.0, 0.0, 1.0]])


def _match(det, bf, a, b):
    ka, da = det.detectAndCompute(a, None)
    kb, db = det.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 20 or len(kb) < 20:
        return None
    matches = sorted(bf.match(da, db), key=lambda m: m.distance)
    if len(matches) < MIN_INLIERS:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in matches])
    dst = np.float32([kb[m.trainIdx].pt for m in matches])
    return src, dst


def reconstruct(images: list[np.ndarray], K: np.ndarray,
                apply_height_prior: bool = True) -> SfmResult | None:
    """Incremental reconstruction with relative scale resolved between views.

    Two-view pose recovery returns a translation of unit length, because the
    baseline between two images is genuinely unknowable from the images. So
    chaining raw two-view poses produces a trajectory where every step is one
    unit long no matter how far the camera moved, and the reconstruction comes
    out geometrically meaningless.

    Each new baseline is therefore rescaled against the previous one. Points
    seen in three consecutive views are triangulated in both pairs, and the
    ratio of their distances from the shared camera is the factor that puts the
    new step in the same units as the old. That is what makes the trajectory
    self-consistent; the absolute metre comes later, from the height prior.
    """
    if cv2 is None:
        return None

    det = cv2.ORB_create(6000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    feats = []
    for img in images:
        kp, desc = det.detectAndCompute(img, None)
        feats.append((kp, desc))

    poses = [np.eye(4)]
    cloud: list[np.ndarray] = []
    inlier_counts: list[int] = []
    views: list[dict] = []             # per view: pose, its points, their pixels
    prev_pair: dict | None = None      # matches and 3D of the previous step

    for i in range(len(images) - 1):
        (ka, da), (kb, db) = feats[i], feats[i + 1]
        if da is None or db is None:
            prev_pair = None
            continue
        matches = bf.match(da, db)
        if len(matches) < MIN_INLIERS:
            prev_pair = None
            continue
        qi = np.array([m.queryIdx for m in matches])
        ti = np.array([m.trainIdx for m in matches])
        src = np.float32([ka[j].pt for j in qi])
        dst = np.float32([kb[j].pt for j in ti])

        E, mask = cv2.findEssentialMat(src, dst, K, method=cv2.RANSAC,
                                       prob=0.999, threshold=1.5)
        if E is None or E.shape != (3, 3):
            prev_pair = None
            continue
        n_in, R, t, mask_pose = cv2.recoverPose(E, src, dst, K, mask=mask)
        if n_in < MIN_INLIERS:
            prev_pair = None
            continue
        inlier_counts.append(int(n_in))

        good = mask_pose.ravel() > 0
        T_prev = poses[-1]

        # Triangulate this pair with a unit baseline first, in the previous
        # camera's frame, so the two pairs can be compared like for like.
        rel = np.eye(4)
        rel[:3, :3] = R.T
        rel[:3, 3] = (-R.T @ t).ravel()
        P0 = K @ np.eye(4)[:3]
        P1 = K @ np.linalg.inv(rel)[:3]
        X = cv2.triangulatePoints(P0, P1, src[good].T, dst[good].T)
        X = (X[:3] / np.where(np.abs(X[3]) < 1e-9, 1e-9, X[3])).T
        ok = np.isfinite(X).all(axis=1) & (X[:, 2] > 0) & (np.linalg.norm(X, axis=1) < 200)
        X, qi_g, ti_g = X[ok], qi[good][ok], ti[good][ok]
        if len(X) < 12:
            prev_pair = None
            continue

        scale = 1.0
        if prev_pair is not None:
            # Features seen in view i-1, i and i+1. Their depth from camera i
            # is known in the old units and in the new unit-baseline units, and
            # the ratio is the factor that reconciles them.
            shared, ia, ib = np.intersect1d(prev_pair["train_idx"], qi_g,
                                            return_indices=True)
            if len(shared) >= 8:
                d_old = np.linalg.norm(prev_pair["points_in_cam"][ia], axis=1)
                d_new = np.linalg.norm(X[ib], axis=1)
                keep = (d_new > 1e-6) & np.isfinite(d_old) & np.isfinite(d_new)
                if keep.sum() >= 8:
                    ratios = d_old[keep] / d_new[keep]
                    scale = float(np.median(ratios))
                    if not np.isfinite(scale) or scale <= 1e-6 or scale > 1e3:
                        scale = 1.0

        rel_scaled = rel.copy()
        rel_scaled[:3, 3] *= scale
        T_new = T_prev @ rel_scaled
        poses.append(T_new)

        Xs = X * scale
        cloud.append((T_prev[:3, :3] @ Xs.T).T + T_prev[:3, 3])
        prev_pair = {"train_idx": ti_g, "points_in_cam": Xs}
        views.append({"index": i, "pose": T_prev,
                      "points_cam": Xs, "pixels": src[good][ok]})

    if len(poses) < 3 or not cloud:
        return None

    points = np.vstack(cloud)
    if apply_height_prior:
        scaled = _apply_scale(points, poses)
        if scaled is None:
            return None
        points, poses, _ = scaled

    return SfmResult(
        poses=poses, points=points, K=K, scale_source="camera_height_prior",
        scale_lo=CAMERA_HEIGHT_LO / CAMERA_HEIGHT_M,
        scale_hi=CAMERA_HEIGHT_HI / CAMERA_HEIGHT_M,
        n_views=len(poses),
        mean_inliers=float(np.mean(inlier_counts)) if inlier_counts else 0.0,
        views=views)


def _apply_scale(points: np.ndarray, poses: list[np.ndarray]):
    """Rotate gravity-up, then scale so the cameras sit at chest height.

    The reconstruction arrives in an arbitrary frame. The floor is the densest
    plane below the cameras, and its normal is 'up'; once the cloud is turned so
    that direction is +Y, the height of the cameras above it is a length we know
    in metres from the protocol, so the whole thing can be scaled.
    """
    cams = np.array([p[:3, 3] for p in poses])

    # Dominant plane by PCA: in a room the points spread mostly horizontally,
    # so the smallest-variance direction of the whole cloud approximates up.
    centred = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(centred[np.random.default_rng(0).integers(
        0, len(centred), min(len(centred), 20000))], full_matrices=False)
    up = vt[-1] / np.linalg.norm(vt[-1])

    # Point it away from the cameras' side, so "below" really is below.
    if float(np.median((cams - points.mean(axis=0)) @ up)) < 0:
        up = -up

    R = _basis_from_up(up)
    pts_r = points @ R.T
    cams_r = cams @ R.T

    floor = np.percentile(pts_r[:, 1], 2)
    cam_h = np.median(cams_r[:, 1]) - floor
    if not np.isfinite(cam_h) or cam_h <= 1e-6:
        return None

    s = CAMERA_HEIGHT_M / cam_h
    pts_out = pts_r * s
    poses_out = []
    for p in poses:
        q = np.eye(4)
        q[:3, :3] = R @ p[:3, :3]
        q[:3, 3] = (p[:3, 3] @ R.T) * s
        poses_out.append(q)
    return pts_out, poses_out, s


def _basis_from_up(up: np.ndarray) -> np.ndarray:
    """Rotation taking `up` to +Y."""
    y = up / np.linalg.norm(up)
    seed = np.array([1.0, 0.0, 0.0])
    if abs(y @ seed) > 0.9:
        seed = np.array([0.0, 0.0, 1.0])
    x = np.cross(y, seed)
    x /= np.linalg.norm(x)
    z = np.cross(x, y)
    return np.stack([x, y, z])

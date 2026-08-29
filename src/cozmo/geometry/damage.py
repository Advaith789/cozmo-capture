"""Damage regions: class, metric extent, and the rule that fired.

Two things about the brief shape this. It scores a phantom detection as harshly
as a miss, and it asks for "the rule that fired" alongside every flag. Both
point away from a learned classifier and toward explicit rules: a rule can be
read, argued with at a defense, and it fires the same way twice.

The observation the detector rests on is that a surface is locally uniform.
Paint, plaster and a door leaf all look like themselves over a few centimetres.
Damage does not: a gouge is darker than the wood around it, a stain or a
sticky note is a different colour from the wall it sits on. So a region is
flagged where it departs from the *local* appearance of its own surface, not
from any global notion of what a wall looks like.

Metric extent comes from the depth map. At distance d with focal length f in
pixels, one pixel spans d/f metres, so a region's size in centimetres falls out
of its size in pixels without any calibration of its own.

Two rules, matching the two damage classes staged in the benchmark:

  substrate_gouge    markedly darker than its surround, low saturation. A chip
                     or hole reads dark because it is a shadowed cavity.
  surface_marking    markedly more saturated, or brighter, than its surround. A
                     stain, a scuff, applied paper.

A detection has to survive being seen from several keyframes before it is
reported, because a single frame's specular highlight looks exactly like a
bright mark.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MIN_CM = 1.5             # smaller than this is sensor noise, not damage
MAX_CM = 40.0            # larger is a piece of furniture, not a defect
MIN_FRAMES = 5           # a mark few cameras saw is a highlight or a shadow
CLUSTER_M = 0.12         # two sightings this close in the room are one defect
DARK_DELTA = 38          # luminance units below the local surround
SAT_DELTA = 34           # saturation units above it


@dataclass(frozen=True)
class Damage:
    kind: str                 # substrate_gouge | surface_marking
    rule: str                 # the rule that fired, in words
    width_cm: float
    height_cm: float
    area_cm2: float
    depth_m: float            # how far the camera was from it
    world: tuple              # where in the room, metres
    seen_in: int              # keyframes it appeared in
    confidence: float


def _regions(bgr: np.ndarray, depth_m: np.ndarray, fx: float):
    """Anomalous blobs in one frame, with their metric size."""
    import cv2

    # Work at full colour resolution and lift depth to meet it, not the other
    # way round. At the depth raster's 256x192 a 7.6 cm mark is nine pixels
    # across, which is too few to tell a defect from wood grain; at 1024x768 it
    # is thirty six.
    H, W = bgr.shape[:2]
    depth_m = cv2.resize(depth_m, (W, H), interpolation=cv2.INTER_NEAREST)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lum, sat = hsv[:, :, 2].astype(np.int16), hsv[:, :, 1].astype(np.int16)

    # The local surround: a median over a patch several centimetres wide. Median
    # rather than mean so a mark does not drag its own reference toward itself.
    k = 41
    bg_lum = cv2.medianBlur(hsv[:, :, 2], k).astype(np.int16)
    bg_sat = cv2.medianBlur(hsv[:, :, 1], k).astype(np.int16)

    valid = np.isfinite(depth_m) & (depth_m > 0.3) & (depth_m < 5.0)

    dark = (bg_lum - lum > DARK_DELTA) & (sat < 90) & valid
    mark = (sat - bg_sat > SAT_DELTA) & valid

    out = []
    for mask, kind, rule in (
            (dark, "substrate_gouge",
             f"luminance {DARK_DELTA}+ below local median, low saturation"),
            (mark, "surface_marking",
             f"saturation {SAT_DELTA}+ above local median")):
        m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN,
                             np.ones((3, 3), np.uint8))
        n, labels, stats, cent = cv2.connectedComponentsWithStats(m, 8)
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            sel = labels == i
            d = float(np.median(depth_m[sel]))
            if not np.isfinite(d) or d <= 0:
                continue
            # depth raster is a quarter of the colour image, so scale focal too
            f_px = fx * depth_m.shape[1] / 1024.0   # fx given at 1024 wide
            cm = 100.0 * d / f_px
            wcm, hcm = w * cm, h * cm
            if not (MIN_CM <= max(wcm, hcm) <= MAX_CM):
                continue
            if area < 6:
                continue
            fill = area / max(w * h, 1)
            if fill < 0.35:                 # a scattered speckle, not a region
                continue
            out.append({"kind": kind, "rule": rule, "w": wcm, "h": hcm,
                        "area": area * cm * cm, "depth": d,
                        "centre": (float(cent[i][0]), float(cent[i][1])),
                        "fill": fill})
    return out


def _to_world(centre, depth, K, T_wc, shape):
    """Where in the room a detection actually is.

    Clustering detections by size alone merges every dark patch of a similar
    size anywhere in the room, which is how a room with no staged damage
    produced 38 findings. Two sightings are the same defect only if they are in
    the same place.
    """
    u, v = centre
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    p = np.array([(u - cx) * depth / fx, -(v - cy) * depth / fy, -depth])
    return T_wc[:3, :3] @ p + T_wc[:3, 3]


def detect(frames, max_frames: int = 40) -> list[Damage]:
    """Damage across a capture, keeping only what several frames agree on."""
    try:
        import cv2  # noqa: F401
    except ImportError:
        return []

    import cv2
    usable = [f for f in frames
              if f.depth is not None and f.meta.get("image_bytes")]
    if not usable:
        return []
    if len(usable) > max_frames:
        idx = np.linspace(0, len(usable) - 1, max_frames).round().astype(int)
        usable = [usable[i] for i in dict.fromkeys(idx)]

    found = []
    for f in usable:
        bgr = cv2.imdecode(np.frombuffer(f.meta["image_bytes"], np.uint8),
                           cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        for r in _regions(bgr, f.depth, float(f.K[0, 0]) * 4.0):
            r["world"] = _to_world(r["centre"], r["depth"], f.K, f.T_wc,
                                   f.depth.shape)
            found.append(r)

    # Cluster in the room, not in the abstract: same class, same place.
    clusters: list[dict] = []
    for r in found:
        for c in clusters:
            if (c["kind"] == r["kind"]
                    and np.linalg.norm(c["world"] - r["world"]) < CLUSTER_M):
                c["items"].append(r)
                c["world"] = np.mean([i["world"] for i in c["items"]], axis=0)
                break
        else:
            clusters.append({"kind": r["kind"], "rule": r["rule"],
                             "world": r["world"], "items": [r]})

    out = []
    for c in clusters:
        if len(c["items"]) < MIN_FRAMES:
            continue
        w = float(np.median([i["w"] for i in c["items"]]))
        h = float(np.median([i["h"] for i in c["items"]]))
        a = float(np.median([i["area"] for i in c["items"]]))
        d = float(np.median([i["depth"] for i in c["items"]]))
        out.append(Damage(kind=c["kind"], rule=c["rule"],
                          world=tuple(round(float(x), 3) for x in c["world"]),
                          width_cm=w, height_cm=h, area_cm2=a, depth_m=d,
                          seen_in=len(c["items"]),
                          confidence=min(1.0, len(c["items"]) / 6.0)))
    return sorted(out, key=lambda x: -x.seen_in)

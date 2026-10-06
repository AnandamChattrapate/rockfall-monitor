"""Risk score.

Paper formula: base = w1*C + w2*dA + w3*P + w4*(1 - Dnorm).
Extensions (see README "False-positive control"):
- dA is generalised to max(area growth, downward speed), because a rock falling across the
  view barely changes size.
- R = K * base, where K in [0, 1] is the fall-likeness of the track's trajectory. Swaying
  vegetation, birds, people and static rocks have K ~ 0, so they cannot reach High.
"""
from __future__ import annotations

import math

from .config import Settings

LOW, MODERATE, HIGH = "LOW", "MODERATE", "HIGH"


def _clip(v: float) -> float:
    return max(0.0, min(1.0, v))


def danger_zone(frame_shape, cfg: Settings) -> tuple:
    """Bottom band as (x1, y1, x2, y2)."""
    h, w = frame_shape[:2]
    return (0, int(round(h * (1.0 - cfg.danger_band))), w, h)


def normalized_distance(bbox, frame_shape, cfg: Settings) -> float:
    h, w = frame_shape[:2]
    cy = (bbox[1] + bbox[3]) / 2.0
    zy = danger_zone(frame_shape, cfg)[1]
    dist = max(0.0, zy - cy)  # 0 once the centre is inside the band
    return min(1.0, dist / math.hypot(w, h))


def fall_kinematics(track, frame_shape, cfg: Settings) -> tuple:
    """Return (K fall-likeness, V normalised downward speed), both in [0, 1].

    A rockfall moves down, mostly vertically, in a nearly straight line, and does not
    reverse. Oscillating branches fail straightness/monotonicity; birds and people moving
    sideways or upward fail verticality or drop. The whole track lifetime (up to
    cfg.fall_window updates) is judged: a rock is still until it detaches, so its track
    starts at the fall, while a bird that dives after flying around carries that history.
    """
    pts = list(getattr(track, "centers", ()))
    if len(pts) < cfg.fall_min_points:
        return 0.0, 0.0
    h = float(frame_shape[0])
    (s0, x0, y0), (s1, x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    if dy <= 0:
        return 0.0, 0.0
    net = math.hypot(dx, dy)
    path, mono, flips, last_sx = 0.0, 0, 0, 0
    tol = 0.005 * h
    for (_, xa, ya), (_, xb, yb) in zip(pts, pts[1:]):
        path += math.hypot(xb - xa, yb - ya)
        mono += (yb - ya) >= -tol
        sx = 0 if abs(xb - xa) <= tol else (1 if xb > xa else -1)
        if sx and last_sx and sx != last_sx:
            flips += 1  # sideways direction reversal: swaying or circling, not ballistic
        last_sx = sx or last_sx
    drop_s = _clip(dy / (cfg.fall_min_drop * h))
    vert_s = _clip((dy / net - 0.5) / 0.4)          # 1 within ~25 deg of vertical
    straight_s = _clip((net / path - 0.6) / 0.3) if path > 0 else 0.0
    mono_s = mono / (len(pts) - 1)
    flip_s = 1.0 / (1 + flips)
    # Gravity bends a falling path toward vertical (vy grows, vx stays). A path that bends
    # toward horizontal (a bird pulling out of a dive, a circling flight) is not a fall.
    mid = len(pts) // 2
    (_, xa, ya), (_, xm, ym), (_, xb, yb) = pts[0], pts[mid], pts[-1]
    a1 = math.degrees(math.atan2(abs(xm - xa), max(ym - ya, 1e-6)))
    a2 = math.degrees(math.atan2(abs(xb - xm), max(yb - ym, 1e-6)))
    curve_s = _clip(1.0 - (a2 - a1 - 5.0) / 15.0)
    k = drop_s * vert_s * straight_s * mono_s * flip_s * curve_s
    v = _clip((dy / max(1, s1 - s0)) / h / cfg.fall_speed_ref)
    return k, v


def base_score(track, frame_shape, cfg: Settings, speed: float = 0.0) -> float:
    d = normalized_distance(track.bbox, frame_shape, cfg)
    r = (cfg.w1 * track.conf + cfg.w2 * max(track.growth, speed)
         + cfg.w3 * track.persistence + cfg.w4 * (1.0 - d))
    return _clip(r)


def score(track, frame_shape, cfg: Settings) -> float:
    k, v = fall_kinematics(track, frame_shape, cfg)
    return _clip(k * base_score(track, frame_shape, cfg, v))


def classify(r: float, cfg: Settings | None = None) -> str:
    cfg = cfg or Settings()
    if r >= cfg.theta_high:
        return HIGH
    if r >= cfg.theta_mod:
        return MODERATE
    return LOW

"""Risk score R = w1*C + w2*dA + w3*P + w4*(1 - Dnorm), clipped to [0, 1]."""
from __future__ import annotations

import math

from .config import Settings

LOW, MODERATE, HIGH = "LOW", "MODERATE", "HIGH"


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


def score(track, frame_shape, cfg: Settings) -> float:
    d = normalized_distance(track.bbox, frame_shape, cfg)
    r = (cfg.w1 * track.conf + cfg.w2 * track.growth
         + cfg.w3 * track.persistence + cfg.w4 * (1.0 - d))
    return max(0.0, min(1.0, r))


def classify(r: float, cfg: Settings | None = None) -> str:
    cfg = cfg or Settings()
    if r >= cfg.theta_high:
        return HIGH
    if r >= cfg.theta_mod:
        return MODERATE
    return LOW

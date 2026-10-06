"""Synthetic rocky-slope video with rocks that detach and fall toward the bottom band."""
from __future__ import annotations

import cv2
import numpy as np


def _background(w: int, h: int, rng) -> np.ndarray:
    ys = np.linspace(150, 90, h, dtype=np.float32)[:, None]
    base = np.repeat(ys, w, axis=1)
    noise = cv2.GaussianBlur(rng.normal(0, 18, (h, w)).astype(np.float32), (0, 0), 3)
    g = np.clip(base + noise, 0, 255).astype(np.uint8)
    return cv2.merge([g * 0 + (g * 0.8).astype(np.uint8), (g * 0.85).astype(np.uint8), g])


def make_synthetic(path: str, frames: int = 150, w: int = 640, h: int = 360,
                   fps: int = 20, seed: int = 0, fall_start: int = 40, rocks: int = 3) -> dict:
    """Write an mp4. Returns metadata (fps, onset_s, impact_s)."""
    rng = np.random.default_rng(seed)
    bg = _background(w, h, rng)
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not out.isOpened():
        raise RuntimeError("cannot open VideoWriter for " + path)
    specs = []
    for i in range(rocks):
        specs.append(dict(x=w * (0.3 + 0.2 * i) + rng.uniform(-20, 20), y=h * 0.12,
                          r=14.0, vy=0.0, vx=rng.uniform(-1.0, 1.0), t0=fall_start + 6 * i))
    impact = None
    for f in range(frames):
        img = bg.copy()
        for s in specs:
            if f < s["t0"]:
                pos = (s["x"], s["y"], s["r"])
            else:
                s["vy"] += 0.9
                s["y"] += s["vy"]
                s["x"] += s["vx"]
                s["r"] = min(34.0, s["r"] * 1.05)
                pos = (s["x"], s["y"], s["r"])
            x, y, r = pos
            if y - r > h:
                impact = impact or f
                continue
            cv2.ellipse(img, (int(x), int(y)), (int(r * 1.15), int(r)), 20, 0, 360, (40, 45, 55), -1)
            cv2.ellipse(img, (int(x - r * 0.25), int(y - r * 0.25)), (int(r * 0.5), int(r * 0.4)),
                        20, 0, 360, (80, 85, 95), -1)
        out.write(img)
    out.release()
    return {"fps": fps, "onset_s": fall_start / fps,
            "impact_s": (impact if impact is not None else frames) / fps}

"""Frame-difference motion filter."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import Settings


@dataclass
class MotionResult:
    ratio: float
    mask: np.ndarray
    boxes: list = field(default_factory=list)       # (x1, y1, x2, y2)
    solidities: list = field(default_factory=list)  # contour area / hull area
    areas: list = field(default_factory=list)


class MotionFilter:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.prev: np.ndarray | None = None
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

    def reset(self) -> None:
        self.prev = None

    def process(self, frame: np.ndarray) -> MotionResult:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        gray = cv2.GaussianBlur(gray, (0, 0), self.cfg.sigma)
        if self.prev is None or self.prev.shape != gray.shape:
            self.prev = gray
            return MotionResult(0.0, np.zeros(gray.shape, np.uint8))
        diff = cv2.absdiff(gray, self.prev)
        self.prev = gray
        mask = (diff > self.cfg.tau).astype(np.uint8) * 255
        ratio = float(np.count_nonzero(mask)) / mask.size
        merged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)
        merged = cv2.dilate(merged, self._kernel)
        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        res = MotionResult(ratio, mask)
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.cfg.min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            hull = cv2.contourArea(cv2.convexHull(c))
            res.boxes.append((x, y, x + w, y + h))
            res.solidities.append(float(area / hull) if hull > 0 else 0.0)
            res.areas.append(float(area))
        return res

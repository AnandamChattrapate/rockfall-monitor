"""Rock detector: Ultralytics YOLO (custom weights) or motion-contour fallback."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import numpy as np

from .config import Settings
from .motion import MotionResult

log = logging.getLogger("rockfall.detector")


@dataclass
class Detection:
    bbox: tuple  # x1, y1, x2, y2
    conf: float
    cls: str = "rock"


class Detector:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.model = None
        self.mode = self._resolve_mode()

    def _resolve_mode(self) -> str:
        want = self.cfg.detector_mode
        if want == "motion":
            return "motion"
        have_weights = os.path.exists(self.cfg.rock_weights)
        if want == "auto" and not have_weights:
            return "motion"
        if want == "yolo" and not have_weights:
            log.warning("yolo mode requested but weights missing: %s; using motion", self.cfg.rock_weights)
            return "motion"
        try:
            from ultralytics import YOLO  # lazy import
            self.model = YOLO(self.cfg.rock_weights)
            return "yolo"
        except Exception as exc:  # ImportError or bad weights
            log.warning("cannot load YOLO (%s); using motion", exc)
            return "motion"

    def detect(self, frame: np.ndarray, motion: MotionResult) -> list:
        if self.mode == "yolo" and self.model is not None:
            return self._detect_yolo(frame)
        return self._detect_motion(motion)

    def _detect_motion(self, motion: MotionResult) -> list:
        out = []
        min_a = float(self.cfg.min_area)
        for box, sol, area in zip(motion.boxes, motion.solidities, motion.areas):
            size_factor = min(1.0, max(0.3, area / (2.0 * min_a)))
            out.append(Detection(tuple(box), float(np.clip(sol * size_factor, 0.0, 1.0))))
        return out

    def _detect_yolo(self, frame: np.ndarray) -> list:
        res = self.model.predict(frame, conf=self.cfg.yolo_conf, iou=self.cfg.yolo_iou, verbose=False)[0]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
            name = res.names.get(int(b.cls[0]), "rock") if hasattr(res, "names") else "rock"
            out.append(Detection((x1, y1, x2, y2), float(b.conf[0]), name))
        return out

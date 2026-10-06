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
        keep = {c.strip().lower() for c in self.cfg.rock_classes.split(",") if c.strip()}
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
            name = res.names.get(int(b.cls[0]), "rock") if hasattr(res, "names") else "rock"
            if keep and str(name).lower() not in keep:
                continue  # a person/vehicle class in the weights must never become a rock
            out.append(Detection((x1, y1, x2, y2), float(b.conf[0]), name))
        return out


# COCO classes that move in front of slopes but are never rockfall.
VETO_CLASSES = {"person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
                "boat", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear",
                "zebra", "giraffe", "kite", "frisbee", "sports ball", "umbrella"}


class Veto:
    """Removes detections that a COCO model labels as a bird, person, vehicle or animal.

    The model loads on first use, so building a Pipeline never blocks on a download.
    """

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.model = None
        self.state = "off" if not cfg.veto_model else "pending"

    def _load(self) -> None:
        try:
            from ultralytics import YOLO  # lazy import
            os.makedirs(os.path.dirname(self.cfg.veto_model) or ".", exist_ok=True)
            self.model = YOLO(self.cfg.veto_model)
            self.state = "on"
        except Exception as exc:
            log.warning("veto model unavailable (%s); birds/people are filtered by motion only", exc)
            self.state = "off"

    def filter(self, frame: np.ndarray, dets: list) -> list:
        if not dets or self.state == "off":
            return dets
        if self.state == "pending":
            self._load()
            if self.model is None:
                return dets
        res = self.model.predict(frame, conf=self.cfg.veto_conf, verbose=False)[0]
        boxes = [tuple(float(v) for v in b.xyxy[0].tolist()) for b in res.boxes
                 if res.names.get(int(b.cls[0]), "") in VETO_CLASSES]
        if not boxes:
            return dets
        return [d for d in dets if not any(_overlaps(d.bbox, v) for v in boxes)]


def _overlaps(a, b) -> bool:
    """True if the centre of a lies inside b, or b's centre inside a."""
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return (b[0] <= ax <= b[2] and b[1] <= ay <= b[3]) or (a[0] <= bx <= a[2] and a[1] <= by <= a[3])

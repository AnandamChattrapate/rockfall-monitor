"""Capture -> motion -> detect -> track -> risk -> alert, plus frame annotation."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

import cv2
import numpy as np

from .alerts import AlertManager, region_of
from .config import Settings
from .detector import Detector, Veto
from .motion import MotionFilter
from .risk import HIGH, LOW, MODERATE, classify, danger_zone, score
from .store import EventStore
from .tracker import IoUTracker

log = logging.getLogger("rockfall.pipeline")

LEVEL_COLOR = {LOW: (0, 200, 0), MODERATE: (0, 200, 255), HIGH: (0, 0, 255)}


class Pipeline:
    def __init__(self, cfg: Settings, source=0, store: EventStore | None = None,
                 alerts: AlertManager | None = None, clock=time.time):
        self.cfg = cfg
        self.source = source
        self.store = store
        self.clock = clock
        self.motion = MotionFilter(cfg)
        self.detector = Detector(cfg)
        self.veto = Veto(cfg)
        self.tracker = IoUTracker(cfg)
        self.alerts = alerts or AlertManager(cfg, clock=clock)
        self.level = LOW
        self.risk = 0.0
        self.fps = 0.0
        self._skip_counter = 0
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._seq = 0
        self.recent_events: deque = deque(maxlen=100)
        self.state = self._make_state(0.0, False, [], None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    # ---- core step -------------------------------------------------
    def _make_state(self, ratio, forwarded, tracks, event) -> dict:
        return {"ts": self.clock(), "fps": round(self.fps, 1), "motion_ratio": round(ratio, 5),
                "frame_forwarded": forwarded, "risk": round(self.risk, 3), "level": self.level,
                "detector_mode": self.detector.mode, "tracks": tracks, "event": event}

    def process_frame(self, frame: np.ndarray) -> dict:
        m = self.motion.process(frame)
        # Very high ratio = exposure change, cloud shadow or camera shake, not a rock.
        forwarded = self.cfg.theta <= m.ratio <= self.cfg.global_motion_max
        dets = self.veto.filter(frame, self.detector.detect(frame, m)) if forwarded else []
        active = self.tracker.update(dets)
        tracks, best, best_track = [], 0.0, None
        for t in active:
            r = score(t, frame.shape, self.cfg)
            tracks.append({"id": t.id, "bbox": [int(v) for v in t.bbox], "conf": round(t.conf, 3),
                           "persistence": round(t.persistence, 3), "growth": round(t.growth, 3),
                           "risk": round(r, 3)})
            if r > best:
                best, best_track = r, t
        self.risk = best
        self.level = classify(best, self.cfg)
        region = region_of(best_track.bbox, frame.shape, self.cfg.grid) if best_track else None
        event = self.alerts.update(self.level, best, region, best_track)
        if event is not None:
            event["id"] = self.store.add(event) if self.store else len(self.recent_events) + 1
            self.recent_events.append(event)
        self.state = self._make_state(m.ratio, forwarded, tracks, event)
        self.last_motion = m
        return self.state

    def feed(self, frame: np.ndarray) -> dict | None:
        """Apply frame skipping (2 normally, 1 at MODERATE+). Returns state if processed."""
        skip = 1 if self.level != LOW else max(1, self.cfg.frame_skip)
        self._skip_counter += 1
        if self._skip_counter < skip:
            return None
        self._skip_counter = 0
        return self.process_frame(frame)

    # ---- annotation ------------------------------------------------
    def annotate(self, frame: np.ndarray) -> np.ndarray:
        img = frame.copy()
        h, w = img.shape[:2]
        zx1, zy1, zx2, zy2 = danger_zone(img.shape, self.cfg)
        overlay = img.copy()
        cv2.rectangle(overlay, (zx1, zy1), (zx2, zy2), (0, 0, 255), -1)
        img = cv2.addWeighted(overlay, 0.18, img, 0.82, 0)
        cv2.line(img, (zx1, zy1), (zx2, zy1), (0, 0, 255), 1)
        for t in self.state["tracks"]:
            x1, y1, x2, y2 = t["bbox"]
            col = LEVEL_COLOR[classify(t["risk"], self.cfg)]
            cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
            cv2.putText(img, f"#{t['id']} {t['risk']:.2f}", (x1, max(12, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
        txt = f"RISK {self.risk:.2f} {self.level}"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img, (w - tw - 20, 6), (w - 6, th + 20), (0, 0, 0), -1)
        cv2.putText(img, txt, (w - tw - 13, th + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    LEVEL_COLOR[self.level], 2, cv2.LINE_AA)
        # motion ratio bar (full width = 2 x theta)
        ratio = self.state["motion_ratio"]
        full = max(1e-6, 2 * self.cfg.theta)
        bw = int(min(1.0, ratio / full) * w)
        cv2.rectangle(img, (0, h - 8), (w, h), (30, 30, 30), -1)
        cv2.rectangle(img, (0, h - 8), (bw, h), (255, 200, 0), -1)
        cv2.line(img, (w // 2, h - 8), (w // 2, h), (255, 255, 255), 1)
        return img

    def _publish(self, frame: np.ndarray) -> None:
        ok, buf = cv2.imencode(".jpg", self.annotate(frame), [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self._cond:
                self._jpeg = buf.tobytes()
                self._seq += 1
                self._cond.notify_all()

    def latest_jpeg(self) -> tuple:
        with self._cond:
            return self._seq, self._jpeg

    # ---- thread ----------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rf-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        src = self.source
        is_file = isinstance(src, str)
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            self.last_error = f"cannot open source {src!r}"
            log.error(self.last_error)
            return
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 0
        period = 1.0 / src_fps if is_file and src_fps > 1 else 0.0
        last = time.time()
        while not self._stop.is_set():
            t0 = time.time()
            ok, frame = cap.read()
            if not ok:
                if is_file and not str(src).lower().startswith(("rtsp://", "http")):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.motion.reset()
                    continue
                time.sleep(0.2)
                continue
            try:
                st = self.feed(frame)
                now = time.time()
                if st is not None:
                    inst = 1.0 / max(1e-6, now - last)
                    self.fps = inst if self.fps == 0 else 0.8 * self.fps + 0.2 * inst
                    last = now
                self._publish(frame)
            except Exception:
                log.exception("frame processing failed")
            if period:
                self._stop.wait(max(0.0, period - (time.time() - t0)))
        cap.release()


def run_offline(path: str, cfg: Settings, max_frames: int | None = None) -> list:
    """Run the pipeline synchronously on a video with video-time clock. Returns events."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    idx = {"n": 0}
    clock = lambda: idx["n"] / fps  # noqa: E731
    pipe = Pipeline(cfg, path, store=None, alerts=AlertManager(cfg, clock=clock), clock=clock)
    events = []
    while max_frames is None or idx["n"] < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        st = pipe.feed(frame)
        if st and st["event"]:
            events.append(st["event"])
        idx["n"] += 1
    cap.release()
    return events

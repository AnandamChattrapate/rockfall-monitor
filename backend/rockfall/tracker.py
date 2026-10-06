"""Greedy tracker: IoU or predicted-centroid matching (fast-falling rocks have zero IoU)."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .config import Settings


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def center(b) -> tuple:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


@dataclass
class Track:
    id: int
    bbox: tuple
    conf: float
    n: int = 10
    history: deque = field(default_factory=deque)   # recent bboxes
    hits: deque = field(default_factory=deque)      # recent match flags (last N frames)
    growth: float = 0.0
    misses: int = 0
    matched: bool = True
    centers: deque = field(default_factory=deque)   # (step, cx, cy), up to cfg.fall_window
    alerted: bool = False

    @property
    def persistence(self) -> float:
        """Fraction of the last N frames where the track matched."""
        return sum(self.hits) / float(self.n)

    def predicted_center(self, step: int) -> tuple:
        """Constant-velocity prediction from the last two matched centres."""
        if len(self.centers) < 2:
            return center(self.bbox)
        (s0, x0, y0), (s1, x1, y1) = self.centers[-2], self.centers[-1]
        ds = max(1, s1 - s0)
        k = (step - s1) / ds
        return (x1 + (x1 - x0) * k, y1 + (y1 - y0) * k)


class IoUTracker:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.tracks: list = []
        self._next_id = 1
        self.step = 0

    def _new(self, det) -> Track:
        n = self.cfg.history_n
        b = tuple(det.bbox)
        t = Track(self._next_id, b, det.conf, n, deque([b], maxlen=n), deque([True], maxlen=n),
                  centers=deque([(self.step, *center(b))], maxlen=self.cfg.fall_window))
        self._next_id += 1
        return t

    def _cost(self, t: Track, d) -> float | None:
        """Lower is better; None means the pair cannot match."""
        v = iou(t.bbox, d.bbox)
        if v >= self.cfg.iou_match:
            return 1.0 - v  # in [0, 0.7]
        px, py = t.predicted_center(self.step)
        cx, cy = center(d.bbox)
        size = math.hypot(t.bbox[2] - t.bbox[0], t.bbox[3] - t.bbox[1])
        gate = max(40.0, self.cfg.match_gate * size)
        dist = math.hypot(cx - px, cy - py)
        return 1.0 + dist / gate if dist <= gate else None

    def update(self, dets: list) -> list:
        self.step += 1
        pairs = []
        for ti, t in enumerate(self.tracks):
            for di, d in enumerate(dets):
                c = self._cost(t, d)
                if c is not None:
                    pairs.append((c, ti, di))
        pairs.sort()
        used_t, used_d = set(), set()
        for _, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            t, d = self.tracks[ti], dets[di]
            prev_a = area(t.bbox)
            cur_a = area(d.bbox)
            t.growth = min(1.0, max(0.0, (cur_a - prev_a) / prev_a)) if prev_a > 0 else 0.0
            t.bbox = tuple(d.bbox)
            t.conf = d.conf
            t.history.append(t.bbox)
            t.centers.append((self.step, *center(t.bbox)))
            t.hits.append(True)
            t.misses = 0
            t.matched = True
        survivors = []
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.hits.append(False)
                t.misses += 1
                t.matched = False
                t.growth = 0.0
                if t.misses > self.cfg.max_age:
                    continue
            survivors.append(t)
        for di, d in enumerate(dets):
            if di not in used_d:
                survivors.append(self._new(d))
        self.tracks = survivors
        return [t for t in self.tracks if t.matched]

import numpy as np
import pytest

from rockfall.alerts import AlertManager, region_of
from rockfall.config import Settings
from rockfall.detector import Detection
from rockfall.motion import MotionFilter
from rockfall.risk import classify, score
from rockfall.tracker import IoUTracker, Track, iou
from collections import deque


def test_settings_defaults_and_env(monkeypatch):
    monkeypatch.setenv("RF_THETA", "0.02")
    monkeypatch.setenv("RF_DEBOUNCE_K", "5")
    s = Settings.from_env()
    assert s.theta == 0.02 and s.debounce_k == 5 and s.tau == 25 and s.cooldown_s == 300


def test_motion_static_vs_moving():
    cfg = Settings()
    mf = MotionFilter(cfg)
    base = np.full((200, 300, 3), 100, np.uint8)
    assert mf.process(base).ratio == 0.0
    assert mf.process(base).ratio == 0.0
    moved = base.copy()
    moved[50:100, 50:100] = 255
    r = mf.process(moved)
    assert r.ratio > 0.015 and len(r.boxes) == 1
    x1, y1, x2, y2 = r.boxes[0]
    assert x1 <= 50 and y1 <= 50 and x2 >= 100 and y2 >= 100


def test_motion_ignores_small_noise_and_tiny_blobs():
    mf = MotionFilter(Settings())
    base = np.full((200, 300, 3), 100, np.uint8)
    mf.process(base)
    f = base.copy()
    f[10:14, 10:14] = 255  # tiny
    f += 5  # below tau
    r = mf.process(f)
    assert r.boxes == []


def test_tracker_matching_and_expiry():
    cfg = Settings()
    tr = IoUTracker(cfg)
    a = tr.update([Detection((10, 10, 50, 50), 0.8)])
    assert [t.id for t in a] == [1]
    b = tr.update([Detection((12, 12, 52, 52), 0.8), Detection((200, 200, 240, 240), 0.7)])
    assert sorted(t.id for t in b) == [1, 2]
    assert tr.tracks[0].persistence == pytest.approx(0.2)  # 2 hits / N=10
    for _ in range(cfg.max_age + 1):
        tr.update([])
    assert tr.tracks == []
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_tracker_growth():
    tr = IoUTracker(Settings())
    tr.update([Detection((0, 0, 100, 100), 0.5)])
    tr.update([Detection((0, 0, 110, 110), 0.5)])  # area 10000 -> 12100 = +21%
    assert tr.tracks[0].growth == pytest.approx(0.21)
    tr.update([Detection((0, 0, 200, 200), 0.5)])  # big jump clipped to 1
    assert tr.tracks[0].growth == 1.0


def mk_track(bbox, conf, growth, hits):
    return Track(1, bbox, conf, 10, deque([bbox]), deque(hits, maxlen=10), growth)


def test_risk_hand_computed():
    cfg = Settings()
    shape = (400, 300, 3)  # H=400 W=300 diag=500; zone y>=300
    # centre y=100 -> dist 200 -> Dnorm .4
    t = mk_track((100, 50, 140, 150), 0.8, 0.5, [True] * 6)  # P=.6
    # .35*.8 + .30*.5 + .25*.6 + .10*.6 = .28+.15+.15+.06 = .64
    assert score(t, shape, cfg) == pytest.approx(0.64)
    # inside the band: Dnorm 0 -> w4 term full
    t2 = mk_track((100, 330, 140, 390), 1.0, 1.0, [True] * 10)
    assert score(t2, shape, cfg) == pytest.approx(1.0)
    t3 = mk_track((100, 330, 140, 390), 0.0, 0.0, [])
    assert score(t3, shape, cfg) == pytest.approx(0.10)


def test_classify_thresholds():
    cfg = Settings()
    assert classify(0.0, cfg) == "LOW"
    assert classify(0.399, cfg) == "LOW"
    assert classify(0.40, cfg) == "MODERATE"
    assert classify(0.699, cfg) == "MODERATE"
    assert classify(0.70, cfg) == "HIGH"
    assert classify(1.0, cfg) == "HIGH"


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_debounce_k3_and_cooldown_per_region():
    clk = FakeClock()
    am = AlertManager(Settings(), clock=clk)
    ev = [am.update("HIGH", 0.8, "r2c1") for _ in range(2)]
    assert ev[0]["type"] == "LEVEL_CHANGE"
    assert ev[1] is None  # only 2 consecutive highs
    assert am.update("HIGH", 0.8, "r2c1")["type"] == "ALERT"  # 3rd
    # streak again within cooldown -> suppressed once
    for _ in range(2):
        assert am.update("HIGH", 0.8, "r2c1") is None
    assert am.update("HIGH", 0.8, "r2c1")["type"] == "SUPPRESSED"
    for _ in range(3):
        assert am.update("HIGH", 0.8, "r2c1") is None  # not repeated
    # other region is independent
    out = [am.update("HIGH", 0.8, "r1c0") for _ in range(3)]
    assert out[-1]["type"] == "ALERT"
    # after 300 s the first region can alert again
    clk.t += 300
    out = [am.update("HIGH", 0.8, "r2c1") for _ in range(3)]
    assert out[-1]["type"] == "ALERT"


def test_debounce_resets_on_dip():
    am = AlertManager(Settings(), clock=FakeClock())
    am.update("HIGH", 0.8, "r0c0")
    am.update("HIGH", 0.8, "r0c0")
    am.update("MODERATE", 0.5, "r0c0")
    assert am.update("HIGH", 0.8, "r0c0")["type"] == "LEVEL_CHANGE"
    assert am.update("HIGH", 0.8, "r0c0") is None


def test_alert_calls_notifier():
    got = []

    class N:
        def notify(self, e):
            got.append(e)

    am = AlertManager(Settings(), clock=FakeClock(), notifier=N())
    for _ in range(3):
        am.update("HIGH", 0.9, "r0c0")
    assert len(got) == 1 and got[0]["type"] == "ALERT"


def test_region_of():
    assert region_of((0, 0, 10, 10), (300, 300, 3), 3) == "r0c0"
    assert region_of((290, 290, 300, 300), (300, 300, 3), 3) == "r2c2"

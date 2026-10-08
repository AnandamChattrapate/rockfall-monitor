import pytest
from fastapi.testclient import TestClient

from rockfall.api import create_app
from rockfall.config import Settings
from rockfall.pipeline import Pipeline, run_offline
from rockfall.store import EventStore
from rockfall.synthetic import make_distractors, make_synthetic


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("v") / "syn.mp4")
    make_synthetic(p)
    return p


def test_health_and_events(tmp_path):
    cfg = Settings(db_path=str(tmp_path / "e.db"), detector_mode="motion")
    store = EventStore(cfg.db_path)
    store.add({"ts": 1.0, "type": "ALERT", "level": "HIGH", "risk": 0.9, "region": "r0c0", "message": "x"})
    c = TestClient(create_app(Pipeline(cfg, 0, store=store)))
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    ev = c.get("/api/events").json()
    assert len(ev) == 1 and ev[0]["type"] == "ALERT"
    assert c.get("/api/config").json()["theta_high"] == 0.7
    assert c.put("/api/config", json={"theta": 0.02}).json()["theta"] == 0.02
    assert c.put("/api/config", json={"port": 1}).status_code == 400


def test_ws_contract(tmp_path):
    cfg = Settings(db_path=str(tmp_path / "e.db"), detector_mode="motion")
    c = TestClient(create_app(Pipeline(cfg, 0, store=EventStore(cfg.db_path))))
    with c.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
    for k in ("ts", "fps", "motion_ratio", "frame_forwarded", "risk", "level",
              "detector_mode", "tracks", "event"):
        assert k in msg


def test_end_to_end_synthetic_alert(video):
    events = run_offline(video, Settings(detector_mode="motion", veto_model=""))
    types = {e["type"] for e in events}
    assert "ALERT" in types, events
    assert any(e["level"] == "HIGH" for e in events)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_distractors_never_reach_high(tmp_path, seed):
    """Swaying branches, birds, a walking person and an exposure jump must not alert."""
    p = str(tmp_path / "d.mp4")
    make_distractors(p, seed=seed)
    events = run_offline(p, Settings(detector_mode="motion", veto_model=""))
    assert not any(e["level"] == "HIGH" for e in events), events


def test_small_rock_alerts(tmp_path):
    """A rock ~16 px wide in a 640x360 frame moves far fewer than 1.5% of pixels."""
    p = str(tmp_path / "small.mp4")
    make_synthetic(p, rocks=1, radius=8.0, max_radius=8.0)
    events = run_offline(p, Settings(detector_mode="motion", veto_model=""))
    assert any(e["type"] == "ALERT" for e in events), events


def test_ws_delivers_every_event_in_order(tmp_path):
    cfg = Settings(db_path=str(tmp_path / "e.db"), detector_mode="motion")
    pipe = Pipeline(cfg, 0, store=EventStore(cfg.db_path))
    c = TestClient(create_app(pipe))
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        for i in range(4):  # burst faster than the 5 Hz tick
            pipe.push_event({"id": -i - 1, "ts": i, "type": "LEVEL_CHANGE", "level": "LOW",
                             "risk": 0, "region": None, "message": str(i)})
        got = []
        while len(got) < 4:
            got += ws.receive_json()["events"]
    assert [e["message"] for e in got] == ["0", "1", "2", "3"]


def test_test_alert_endpoint(tmp_path):
    got = []

    class N:
        def notify(self, e):
            got.append(e)

    from rockfall.alerts import AlertManager
    cfg = Settings(db_path=str(tmp_path / "e.db"), detector_mode="motion")
    pipe = Pipeline(cfg, 0, store=EventStore(cfg.db_path), alerts=AlertManager(cfg, notifier=N()))
    r = TestClient(create_app(pipe)).post("/api/test-alert").json()
    assert r["sent"] is True and got[0]["type"] == "TEST"
    assert pipe.store.list(1)[0]["type"] == "TEST"

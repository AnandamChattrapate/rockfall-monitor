import pytest
from fastapi.testclient import TestClient

from rockfall.api import create_app
from rockfall.config import Settings
from rockfall.pipeline import Pipeline, run_offline
from rockfall.store import EventStore
from rockfall.synthetic import make_synthetic


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
    events = run_offline(video, Settings(detector_mode="motion"))
    types = {e["type"] for e in events}
    assert "ALERT" in types, events
    assert any(e["level"] == "HIGH" for e in events)

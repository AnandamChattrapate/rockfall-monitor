"""FastAPI app: /video (MJPEG), /ws, /api/events, /api/config, /health."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .alerts import test_event
from .config import Settings
from .pipeline import Pipeline

MUTABLE = {"tau", "theta", "sigma", "min_area", "yolo_conf", "yolo_iou", "history_n", "w1", "w2",
           "w3", "w4", "theta_mod", "theta_high", "debounce_k", "cooldown_s", "frame_skip",
           "danger_band", "iou_match", "max_age", "site_location", "global_motion_max",
           "match_gate", "fall_min_points", "fall_min_drop", "fall_speed_ref", "veto_conf"}


def create_app(pipeline: Pipeline, cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or pipeline.cfg
    notifier = getattr(pipeline.alerts, "notifier", None)
    app = FastAPI(title="Rockfall Monitor")
    # Any local dashboard origin (localhost / 127.0.0.1 / [::1], any port) plus cfg.cors_origin.
    # The browser treats localhost:5173 and 127.0.0.1:5173 as different origins.
    app.add_middleware(CORSMiddleware, allow_origins=[cfg.cors_origin],
                       allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status": "ok", "detector_mode": pipeline.detector.mode,
                "running": bool(pipeline._thread and pipeline._thread.is_alive()),
                "error": pipeline.last_error}

    @app.get("/api/events")
    def events(limit: int = 100):
        return pipeline.store.list(limit) if pipeline.store else list(pipeline.recent_events)[-limit:]

    @app.get("/api/config")
    def get_config():
        return cfg.as_dict()

    @app.put("/api/config")
    def put_config(body: dict):
        bad = [k for k in body if k not in MUTABLE]
        if bad:
            raise HTTPException(400, f"not editable: {bad}")
        for k, v in body.items():
            cur = getattr(cfg, k)
            try:
                setattr(cfg, k, type(cur)(v))
            except (TypeError, ValueError):
                raise HTTPException(400, f"bad value for {k}")
        return cfg.as_dict()

    @app.post("/api/test-alert")
    def test_alert():
        """Fire the email + siren path and show a TEST event, to check alert delivery."""
        ev = test_event(cfg)
        if notifier is not None:
            notifier.notify(ev)
        ev["id"] = pipeline.store.add(ev) if pipeline.store else -1
        pipeline.push_event(ev)
        return {"sent": notifier is not None, "event": ev}

    @app.get("/video")
    async def video():
        async def gen():
            last = -1
            while True:
                seq, jpg = pipeline.latest_jpeg()
                if jpg is None or seq == last:
                    await asyncio.sleep(0.03)
                    continue
                last = seq
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        last_seq = pipeline.recent_events[-1]["seq"] if pipeline.recent_events else 0
        try:
            while True:
                state = dict(pipeline.state)
                # Send every event since the last tick, so an ALERT never queues behind others.
                new = [ev for ev in list(pipeline.recent_events) if ev["seq"] > last_seq]
                if new:
                    last_seq = new[-1]["seq"]
                state["events"] = new
                state["event"] = new[-1] if new else None
                await sock.send_json(state)
                await asyncio.sleep(0.2)
        except (WebSocketDisconnect, RuntimeError):
            pass

    return app

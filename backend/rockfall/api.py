"""FastAPI app: /video (MJPEG), /ws, /api/events, /api/config, /health."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import Settings
from .pipeline import Pipeline

MUTABLE = {"tau", "theta", "sigma", "min_area", "yolo_conf", "yolo_iou", "history_n", "w1", "w2",
           "w3", "w4", "theta_mod", "theta_high", "debounce_k", "cooldown_s", "frame_skip",
           "danger_band", "iou_match", "max_age", "site_location"}


def create_app(pipeline: Pipeline, cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or pipeline.cfg
    app = FastAPI(title="Rockfall Monitor")
    app.add_middleware(CORSMiddleware, allow_origins=[cfg.cors_origin], allow_methods=["*"],
                       allow_headers=["*"])

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
        last_id = pipeline.recent_events[-1]["id"] if pipeline.recent_events else 0
        try:
            while True:
                state = dict(pipeline.state)
                state["event"] = None
                for ev in list(pipeline.recent_events):
                    if ev["id"] > last_id:
                        state["event"] = ev
                        last_id = ev["id"]
                        break
                await sock.send_json(state)
                await asyncio.sleep(0.2)
        except (WebSocketDisconnect, RuntimeError):
            pass

    return app

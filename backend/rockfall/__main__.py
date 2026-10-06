"""python -m rockfall --source 0"""
from __future__ import annotations

import argparse
import logging

import uvicorn

from .alerts import AlertManager, Notifier
from .api import create_app
from .config import Settings
from .pipeline import Pipeline
from .store import EventStore


def parse_source(s: str):
    return int(s) if s.lstrip("-").isdigit() else s


def main() -> None:
    p = argparse.ArgumentParser(prog="rockfall")
    p.add_argument("--source", default="0", help="webcam index, video file, or RTSP URL")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = Settings.from_env()
    if a.host:
        cfg.host = a.host
    if a.port:
        cfg.port = a.port
    source = parse_source(a.source)
    if isinstance(source, int):
        # macOS only shows the camera permission prompt from the main thread.
        import cv2
        probe = cv2.VideoCapture(source)
        ok = probe.isOpened() and probe.read()[0]
        probe.release()
        if not ok:
            raise SystemExit(
                f"Camera {source} unavailable. Grant camera access to the app running this "
                "shell (System Settings > Privacy & Security > Camera), then restart it.")
    store = EventStore(cfg.db_path)
    pipe = Pipeline(cfg, source, store=store,
                    alerts=AlertManager(cfg, notifier=Notifier(cfg)))
    pipe.start()
    try:
        # /video and /ws stream forever; cap the wait so Ctrl+C does not hang on open dashboards.
        uvicorn.run(create_app(pipe, cfg), host=cfg.host, port=cfg.port, log_level="info",
                    timeout_graceful_shutdown=2)
    finally:
        pipe.stop()  # releases the camera


if __name__ == "__main__":
    main()

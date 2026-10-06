"""Settings (PLAN.md Table 2). Every field is overridable by env var RF_<FIELD>."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields, asdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # Motion filter
    tau: int = 25                 # motion pixel threshold
    theta: float = 0.015          # motion activity threshold
    sigma: float = 1.5            # Gaussian sigma
    min_area: int = 400           # min contour area (px)
    # Detector
    yolo_conf: float = 0.45
    yolo_iou: float = 0.50
    detector_mode: str = "auto"   # auto | yolo | motion
    rock_weights: str = str(BACKEND_DIR / "models" / "rock.pt")
    # Tracker / risk
    history_n: int = 10
    w1: float = 0.35              # confidence C
    w2: float = 0.30              # area growth dA
    w3: float = 0.25              # persistence P
    w4: float = 0.10              # proximity (1 - Dnorm)
    theta_mod: float = 0.40
    theta_high: float = 0.70
    iou_match: float = 0.3
    max_age: int = 5              # frames a track survives without a match
    danger_band: float = 0.25     # bottom fraction of frame that is the danger zone
    grid: int = 3                 # regions = grid x grid cells
    # Alerts
    debounce_k: int = 3
    cooldown_s: float = 300.0
    frame_skip: int = 2           # becomes 1 at MODERATE or above
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    alert_to: str = ""
    site_location: str = "Unknown site"
    siren_webhook: str = ""
    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origin: str = "http://localhost:5173"
    db_path: str = str(BACKEND_DIR / "data" / "events.db")

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        s = cls()
        for f in fields(cls):
            raw = os.environ.get("RF_" + f.name.upper())
            if raw is None or raw == "":
                continue
            default = getattr(s, f.name)
            try:
                setattr(s, f.name, type(default)(raw))
            except ValueError:
                pass
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    def as_dict(self) -> dict:
        d = asdict(self)
        d["smtp_pass"] = "***" if self.smtp_pass else ""
        return d

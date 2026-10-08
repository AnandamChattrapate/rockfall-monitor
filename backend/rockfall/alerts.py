"""Debounce + per-region cooldown, plus non-blocking email/siren notifier."""
from __future__ import annotations

import logging
import math
import os
import queue
import shutil
import smtplib
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
from email.message import EmailMessage

from .config import Settings
from .risk import HIGH

log = logging.getLogger("rockfall.alerts")

LEVEL_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2}


def region_of(bbox, frame_shape, grid: int) -> str:
    h, w = frame_shape[:2]
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    col = min(grid - 1, max(0, int(cx / w * grid)))
    row = min(grid - 1, max(0, int(cy / h * grid)))
    return f"r{row}c{col}"


class AlertManager:
    """update() returns at most one event dict per call (no id; the store assigns it)."""

    def __init__(self, cfg: Settings, clock=time.time, notifier=None):
        self.cfg = cfg
        self.clock = clock
        self.notifier = notifier
        self.level = "LOW"
        self._streak = 0
        self._streak_region = None
        self._last_alert: dict = {}
        self._suppress_noted: set = set()

    def update(self, level: str, risk: float, region: str | None, track=None) -> dict | None:
        """Debounce follows the track when one is given (a falling rock crosses grid cells);
        cooldown stays per region. A track alerts at most once."""
        now = self.clock()
        event = None
        if level != self.level:
            event = {"ts": now, "type": "LEVEL_CHANGE", "level": level, "risk": round(risk, 3),
                     "region": region, "message": f"Level {self.level} -> {level}"}
            self.level = level
        if level == HIGH and region is not None:
            key = ("track", track.id) if track is not None else ("region", region)
            if key != self._streak_region:
                self._streak_region = key
                self._streak = 0
            self._streak += 1
            if track is not None and getattr(track, "alerted", False):
                pass  # this rock already raised an alert
            elif self._streak >= self.cfg.debounce_k:
                self._streak = 0
                last = self._last_alert.get(region)
                if last is None or now - last >= self.cfg.cooldown_s:
                    self._last_alert[region] = now
                    if track is not None:
                        track.alerted = True
                    self._suppress_noted.discard(region)
                    event = {"ts": now, "type": "ALERT", "level": level, "risk": round(risk, 3),
                             "region": region,
                             "message": f"Rockfall alert in region {region} (risk {risk:.2f})"}
                    if self.notifier is not None:
                        self.notifier.notify(event)
                elif region not in self._suppress_noted:
                    self._suppress_noted.add(region)
                    event = {"ts": now, "type": "SUPPRESSED", "level": level, "risk": round(risk, 3),
                             "region": region, "message": f"Alert suppressed by cooldown in {region}"}
        else:
            self._streak = 0
            self._streak_region = None
        return event


def make_siren_wav(path: str, seconds: float = 2.0, rate: int = 22050) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        phase = 0.0
        for i in range(int(seconds * rate)):
            t = i / rate
            freq = 700 + 500 * (0.5 + 0.5 * math.sin(2 * math.pi * 1.5 * t))
            phase += 2 * math.pi * freq / rate
            frames += struct.pack("<h", int(12000 * math.sin(phase)))
        w.writeframes(bytes(frames))


class Notifier:
    """Runs email + siren on a worker thread so the pipeline never blocks."""

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._q: queue.Queue = queue.Queue()
        self._t = threading.Thread(target=self._run, name="rf-notifier", daemon=True)
        self._t.start()

    def notify(self, event: dict) -> None:
        self._q.put(event)

    def _run(self) -> None:
        while True:
            ev = self._q.get()
            for fn in (self._email, self._siren):
                try:
                    fn(ev)
                except Exception:
                    log.exception("notifier step %s failed", fn.__name__)

    def _email(self, ev: dict) -> None:
        c = self.cfg
        kind = "TEST" if ev.get("type") == "TEST" else "ALERT"
        subject = f"[Rockfall {kind}] {c.site_location}"
        body = (f"{ev['message']}\nSite: {c.site_location}\nRisk: {ev['risk']}\n"
                f"Region: {ev['region']}\nTime: {time.ctime(ev['ts'])}\n")
        if not (c.smtp_host and c.alert_to):
            log.warning("EMAIL not configured; would send: %s | %s", subject, body.replace("\n", " | "))
            return
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, c.smtp_user or "rockfall@localhost", c.alert_to
        msg.set_content(body)
        with smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=15) as s:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls()
                s.ehlo()
            elif c.smtp_user:
                raise RuntimeError("SMTP server has no STARTTLS; refusing to send credentials in clear text")
            if c.smtp_user:
                s.login(c.smtp_user, c.smtp_pass)
            s.send_message(msg)

    def _siren(self, ev: dict) -> None:
        c = self.cfg
        if c.siren_webhook:
            req = urllib.request.Request(c.siren_webhook, data=str(ev["message"]).encode(), method="POST")
            urllib.request.urlopen(req, timeout=10).close()
            return
        if sys.platform == "darwin" and shutil.which("afplay"):
            path = os.path.join(tempfile.gettempdir(), "rockfall_siren.wav")
            make_siren_wav(path)
            subprocess.run(["afplay", path], check=False, timeout=30)
        elif sys.platform == "win32":
            import winsound
            for _ in range(4):
                winsound.Beep(1200, 250)
                winsound.Beep(700, 250)
        else:
            log.warning("SIREN (no audio backend): %s", ev["message"])


def test_event(cfg: Settings) -> dict:
    return {"ts": time.time(), "type": "TEST", "level": "HIGH", "risk": 1.0, "region": None,
            "message": f"Test alert from {cfg.site_location}"}

# Rockfall Monitor — Implementation Plan

Source: `AI_Rockfall_Prediction_Paper.docx` (Chattrapate et al.). Goal: a working system that reads a real camera, detects and tracks moving rocks, scores risk, alerts, and shows a live dashboard.

## Pipeline (paper §3, Alg. 1)

```
camera (cv2.VideoCapture) → motion filter → detector → IoU tracker → risk score → classifier
                                                                     → debounce/cooldown → email + siren
                                                                     → FastAPI (MJPEG + WebSocket) → React dashboard
```

## Key design decision: detector

Stock YOLO (COCO) has no "rock" class. The detector therefore has two modes:

1. **`yolo`** — Ultralytics YOLO with custom rock weights (`ROCK_WEIGHTS` path). Train on a public rockfall dataset (for example Roboflow "rockfall" sets) with `scripts/train.py`.
2. **`motion`** (default fallback) — each motion contour above min area becomes a "rock candidate". Confidence = contour solidity × size factor. This works with a real camera on day one.

Mode `auto` uses `yolo` if the weights file exists, else `motion`.

## Parameters (paper Table 2) — `backend/rockfall/config.py`

| Param | Value |
|---|---|
| τ motion pixel threshold | 25 |
| θ motion activity | 0.015 |
| Gaussian σ | 1.5 |
| min contour area | 400 px |
| YOLO conf / IoU | 0.45 / 0.50 |
| history N | 10 frames |
| weights w1..w4 (C, ΔA, P, D) | 0.35, 0.30, 0.25, 0.10 |
| θ_mod / θ_high | 0.40 / 0.70 |
| debounce k | 3 |
| cooldown Tc | 300 s per region |

All values are overridable by env vars (`RF_*`).

## Risk score (§3.2)

`R = w1·C + w2·ΔA + w3·P + w4·(1 − Dnorm)`, clipped to [0,1].
- C: detection confidence.
- ΔA: area growth rate between frames, `clip((A_t − A_{t−1}) / A_{t−1}, 0, 1)`.
- P: fraction of last N frames where the track matched (IoU ≥ 0.3).
- Dnorm: distance of bbox centre from the danger-zone polygon/line, normalised by frame diagonal. Danger zone = bottom band of frame by default (configurable).

Moderate → lower frame-skip (2 → 1). High ×k consecutive → alert, then cooldown per 3×3 grid cell region.

## Modules (`backend/rockfall/`)

| File | Responsibility |
|---|---|
| `config.py` | dataclass `Settings`, env overrides |
| `motion.py` | `MotionFilter.process(frame) -> MotionResult(ratio, mask, boxes)` |
| `detector.py` | `Detector.detect(frame, motion) -> list[Detection(bbox, conf, cls)]` |
| `tracker.py` | `IoUTracker.update(dets) -> list[Track(id, bbox, history, persistence, growth)]` |
| `risk.py` | `score(track, frame_shape, cfg) -> float`, `classify(R) -> Level` |
| `alerts.py` | `AlertManager` (debounce, cooldown, SMTP email, siren via audio/GPIO/webhook) |
| `pipeline.py` | thread: capture → process → annotate; publishes frames + events |
| `store.py` | SQLite event log |
| `api.py` | FastAPI: `GET /video` (MJPEG), `WS /ws` (state ticks), `GET /api/events`, `GET/PUT /api/config`, `GET /health` |
| `__main__.py` | `python -m rockfall --source 0` |

## Frontend (`frontend/`, Vite + React)

Live feed (`<img src=/video>`), risk gauge, 10-minute trend chart with θ lines, active tracks table, event log, motion ratio telemetry, connection status.

## Subagent split

| Task | Model | Why |
|---|---|---|
| Backend CV pipeline + API + tests | Sonnet | core logic, real-time threading, correctness |
| React dashboard | Sonnet | moderate UI work, WS contract |
| README, `.env.example`, train script | Haiku | mechanical |
| Integration + verification | Opus (lead) | run tests, start server, check camera |

## WebSocket contract (`/ws`, ~5 Hz)

```json
{"ts": 1730000000.1, "fps": 14.8, "motion_ratio": 0.021, "frame_forwarded": true,
 "risk": 0.52, "level": "MODERATE", "detector_mode": "motion",
 "tracks": [{"id": 3, "bbox": [x1,y1,x2,y2], "conf": 0.8, "persistence": 0.6, "growth": 0.2, "risk": 0.52}],
 "event": null}
```
`event`, when present: `{"id", "ts", "type": "LEVEL_CHANGE|ALERT|SUPPRESSED", "level", "risk", "region", "message"}`.

## Verification

- Unit tests: motion filter on synthetic frames, tracker matching, risk formula against hand values, debounce/cooldown with injected clock (no sleeps).
- Integration: run with a synthetic video (falling-rock generator script) and with the real webcam (`--source 0`).
- Evaluation script: precision/recall/F1 + lead time on labelled clips (paper §5).

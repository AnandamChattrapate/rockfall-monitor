# Rockfall Monitor

A real-time rockfall detection and alerting system based on the paper *AI-Based Rockfall Prediction and Monitoring System Using Real-Time Computer Vision and Automated Alerting*. It reads a live camera, tracks moving rocks, scores the risk, and sends alerts by email and siren. A React dashboard shows the results.

## Overview

```
camera → motion filter → detector → IoU tracker → risk score → Low / Moderate / High
                                                        → debounce + cooldown → email + siren
                                                        → FastAPI (MJPEG + WebSocket) → React dashboard
```

- **Motion filter:** OpenCV frame differencing drops static frames.
- **Detector:** in `motion` mode (the default), each moving shape counts as a possible rock. In `yolo` mode, it uses trained rock weights. Stock YOLO has no rock class. See [Training Custom Weights](#training-custom-weights).
- **Risk:** `R = 0.35·C + 0.30·ΔA + 0.25·P + 0.10·(1 − D)`. The thresholds are 0.40 (Moderate) and 0.70 (High). An alert fires after 3 High readings in a row. The same region then stays quiet for 300 s.

## Project layout

```
backend/    Python package `rockfall` (pipeline, API, tests, scripts)
frontend/   Vite + React dashboard
PLAN.md     Implementation plan
```

## Run locally

**New to the project?** Follow [SETUP.md](SETUP.md). It has step-by-step setup for macOS and Windows and a one-command setup script for each (`scripts/setup.sh`, `scripts/setup.ps1`). The steps below are the manual version.

### 1. Prerequisites

- Python 3.10 or later (tested on 3.14)
- Node.js 18 or later (tested on 22)
- A webcam, or a video file

### 2. Install the backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` includes `ultralytics`, which pulls in PyTorch (about 1 GB). You only need it for YOLO mode.

### 3. Install the frontend

```bash
cd frontend
npm install
```

### 4. Check the install

```bash
cd backend
.venv/bin/python -m pytest -q
```

All tests should pass.

### 5. Start the backend

Use the webcam:

```bash
cd backend
.venv/bin/python -m rockfall --source 0
```

Or use a demo video if you do not have a camera:

```bash
cd backend
.venv/bin/python scripts/make_synthetic.py data/synthetic.mp4
.venv/bin/python -m rockfall --source data/synthetic.mp4
```

`--source` also accepts other camera indexes (`1`, `2`), and RTSP URLs. The API runs at http://127.0.0.1:8000. Check that it is up at http://127.0.0.1:8000/health.

**macOS camera permission:** run the backend from the Terminal app. On the first run, macOS asks for camera access. If it does not ask, open System Settings > Privacy & Security > Camera. Turn on Terminal, then restart Terminal. If camera access is missing, the backend stops with an error. It does not start with a blank feed.

### 6. Start the dashboard

Open a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173.

To use a backend on another host or port, set `VITE_API_URL` in `frontend/.env` (see `frontend/.env.example`).

### 7. Stop

Press Ctrl+C in each terminal. The backend releases the camera within about 2 seconds.

## False-positive control

Anything that moves creates motion blobs: swaying trees, birds, people, vehicles, and shadows. The system only raises risk for motion that behaves like a rockfall.

1. **Global-change gate.** A frame is skipped when more than 30% of its pixels change (`RF_GLOBAL_MOTION_MAX`). This covers auto-exposure jumps, cloud shadows and camera shake.
2. **Fall kinematics (K).** Each track's whole trajectory is scored from 0 to 1, and the risk is multiplied by K. A track scores high only when all of these hold:
   - it moves down by at least 5% of the frame height (`RF_FALL_MIN_DROP`);
   - it moves mostly vertically, within about 25° of vertical;
   - its path is nearly straight, with no up-down or left-right reversals;
   - it bends toward vertical, as gravity makes a fall do, never toward horizontal.

   This rejects swaying branches (they oscillate), birds and people moving sideways or upward, birds pulling out of a dive, and static rocks. A track needs 4 matched updates before it can score (`RF_FALL_MIN_POINTS`).
3. **COCO veto (optional).** A stock YOLOv8n model removes detections that it labels as a bird, person, vehicle or animal. On first use, it downloads `yolov8n.pt` to `backend/models/` (about 6 MB). If the model cannot load, the system logs a warning and uses rules 1 and 2 only. To turn it off, set `RF_VETO_MODEL=` (empty).
4. **Rock classes only in YOLO mode.** Only the classes in `RF_ROCK_CLASSES` count as rocks.

Risk score: `R = K × (0.35·C + 0.30·max(ΔA, V) + 0.25·P + 0.10·(1 − D))`, where `V` is the downward speed. A rock falling across the view barely changes size, so the paper's area-growth term ΔA alone under-scores it.

Known limit: rule 2 cannot separate a bird diving straight down from a falling rock. The COCO veto covers that case. For a site with frequent birds, keep the veto on, or train rock weights for YOLO mode.

## Configuration

Settings come from environment variables with the prefix `RF_`. To use a file:

```bash
cd backend
cp .env.example .env        # edit values
set -a; source .env; set +a
.venv/bin/python -m rockfall --source 0
```

Email alerts are logged, not sent, until `RF_SMTP_HOST` and `RF_ALERT_TO` are set.

### Key Parameters

| Env Var | Default | Description |
|---------|---------|-------------|
| `RF_DETECTOR_MODE` | `auto` | `auto`, `yolo`, or `motion` |
| `RF_ROCK_WEIGHTS` | `models/rock.pt` | Path to YOLO weights |
| `RF_THETA_MOD` | `0.40` | Moderate risk threshold |
| `RF_THETA_HIGH` | `0.70` | High risk threshold |
| `RF_DEBOUNCE_K` | `3` | Consecutive high-risk frames to trigger alert |
| `RF_COOLDOWN_S` | `300` | Seconds between alerts per region |
| `RF_FRAME_SKIP` | `2` | Process every N frames; becomes 1 at MODERATE+ |
| `RF_SMTP_HOST` | `` | Email server (leave empty to disable) |
| `RF_SMTP_PORT` | `587` | SMTP port |
| `RF_SMTP_USER` | `` | SMTP username |
| `RF_SMTP_PASS` | `` | SMTP password |
| `RF_ALERT_TO` | `` | Email recipient |
| `RF_SITE_LOCATION` | `Unknown site` | Site name in alerts |
| `RF_SIREN_WEBHOOK` | `` | HTTP endpoint for siren (POST) |

### Motion Filter Parameters

| Env Var | Default | Description |
|---------|---------|-------------|
| `RF_TAU` | `25` | Motion pixel threshold (0–255) |
| `RF_THETA` | `0.015` | Motion activity ratio threshold |
| `RF_SIGMA` | `1.5` | Gaussian blur sigma |
| `RF_MIN_AREA` | `400` | Minimum contour area (px²) |

### Detector Parameters

| Env Var | Default | Description |
|---------|---------|-------------|
| `RF_YOLO_CONF` | `0.45` | YOLO confidence threshold |
| `RF_YOLO_IOU` | `0.50` | YOLO IoU threshold (NMS) |

### Risk Scoring Weights

Risk `R = w1·C + w2·ΔA + w3·P + w4·(1 − D)`, clipped to [0,1].

| Env Var | Default | Component |
|---------|---------|-----------|
| `RF_W1` | `0.35` | Confidence C |
| `RF_W2` | `0.30` | Area growth rate ΔA |
| `RF_W3` | `0.25` | Persistence P |
| `RF_W4` | `0.10` | Proximity (1 − distance/diagonal) |

## Training Custom Weights

```bash
cd backend
# Prepare a dataset YAML (train/val image paths, nc: 1, names: [rock])
.venv/bin/python scripts/train.py --data rocks.yaml --epochs 100 --batch 16
# Weights saved to models/rock.pt
```

### Training Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--data` | `` | Dataset YAML (required) |
| `--base` | `yolov8n.pt` | Base YOLO model |
| `--epochs` | `50` | Training epochs |
| `--imgsz` | `640` | Image size |
| `--batch` | `16` | Batch size |
| `--device` | `None` | Device (auto, 0, 1, ...) |
| `--out` | `models/rock.pt` | Output weights path |

## Synthetic Data

Generate test videos:

```bash
cd backend
.venv/bin/python scripts/make_synthetic.py out.mp4 --frames 300 --rocks 5 --fall-start 80
```

| Flag | Default | Description |
|------|---------|-------------|
| `out` | `data/synthetic.mp4` | Output video path |
| `--frames` | `150` | Total frames |
| `--rocks` | `3` | Number of rocks |
| `--fall-start` | `40` | Frame when rocks detach |
| `--seed` | `0` | Random seed |

## Evaluation

Evaluate on a labelled CSV (columns: `clip`, `onset_s`, `impact_s`):

```bash
cd backend
.venv/bin/python scripts/evaluate.py clips.csv --tol 1.0
```

Output: precision, recall, F1, mean lead time (seconds).

| Flag | Default | Description |
|------|---------|-------------|
| `csv` | `` | Labelled clips CSV (required) |
| `--tol` | `1.0` | Tolerance for onset (s) |

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

Tests are deterministic (no sleeps); they inject a mock clock for debounce and cooldown logic.

## API

FastAPI serves:

- `GET /video` — MJPEG stream
- `WS /ws` — WebSocket: frame state (~5 Hz)
- `GET /api/events` — Event log (JSON)
- `GET /api/config` — Current settings (JSON)
- `PUT /api/config` — Update settings (JSON body)
- `GET /health` — Health check

## License

See paper: Chattrapate et al., AI_Rockfall_Prediction_Paper.docx

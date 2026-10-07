# Architecture and Data Flow

This document explains how the Rockfall Monitor works, from the camera to the alert. For setup steps, see [SETUP.md](SETUP.md).

## 1. The big picture

```
┌─────────────┐   frames    ┌──────────────────────── Python backend (one process) ───────────────────────┐
│ Camera      │────────────▶│ Capture thread                                                            │
│ webcam/RTSP │             │  motion filter → detector → veto → tracker → risk → classify → alert mgr  │
│ /video file │             │       │                                                       │      │     │
└─────────────┘             │       └──── annotated JPEG ──┐                  SQLite ◀──────┘      │     │
                            │                               ▼                 events.db            ▼     │
                            │  FastAPI server   /video (MJPEG)   /ws (JSON 5/s)   /api/*     Notifier    │
                            └──────────────────────┬─────────────────┬──────────────────────── │ ───────┘
                                                   │                 │                         │
                                                   ▼                 ▼                         ▼
                                          React dashboard (browser, localhost:5173)     Email (SMTP)
                                                                                         Siren (speaker/webhook)
```

There are two programs:

| Program | Language | Runs where | Job |
|---|---|---|---|
| Backend | Python (OpenCV, FastAPI, Ultralytics YOLO) | The computer with the camera | Analyse the video, decide the risk, send alerts, store events |
| Dashboard | React (JavaScript), built with Vite | The operator's browser | Show the live video, the risk and the event history |

The backend works on its own. Closing the dashboard does not stop the monitoring or the alerts.

## 2. Folder map

```
backend/rockfall/
  __main__.py   Starts everything: checks the camera, starts the capture thread and the web server
  config.py     All settings (paper Table 2 values + extensions), overridable by RF_* env vars
  pipeline.py   The capture thread and the per-frame processing loop
  motion.py     Stage 1: frame-difference motion filter (OpenCV)
  detector.py   Stage 2: rock detector (motion blobs or YOLO) + COCO veto (birds, people, vehicles)
  tracker.py    Stage 3: links detections across frames into tracks
  risk.py       Stage 4: fall-kinematics check + risk score + Low/Moderate/High
  alerts.py     Stage 5: debounce, cooldown, email and siren
  store.py      SQLite event log
  api.py        FastAPI endpoints for the dashboard
  synthetic.py  Generates test videos (falling rocks; distractors)
backend/scripts/  make_synthetic.py, train.py (YOLO training), evaluate.py (precision/recall/lead time)
backend/tests/    pytest suite
frontend/src/     App.jsx, useMonitor.js (WebSocket), api.js, components/Panels.jsx
```

## 3. Per-frame flow (the core)

The capture thread runs this loop for each camera frame (`pipeline.py`, `process_frame`):

### Step 0: Capture and frame skip

OpenCV reads a frame from the camera. At Low risk, only every 2nd frame is processed (`RF_FRAME_SKIP=2`), to save CPU. At Moderate or High, every frame is processed. This is the paper's "raise the sampling rate on Moderate" rule.

### Step 1: Motion filter (`motion.py`)

1. Convert the frame to grayscale and blur it (Gaussian, σ = 1.5) to remove sensor noise.
2. Subtract the previous frame. Pixels that changed by more than τ = 25 become "moving".
3. Compute the **motion ratio** m, the fraction of pixels that moved.
4. Group the moving pixels into blobs (contours). Drop blobs under 400 px.

The frame goes to the next stage only if 0.015 ≤ m ≤ 0.30:
- below 1.5%, nothing is happening;
- above 30%, the whole image changed. That is a lighting jump, a cloud shadow or camera shake, not a rock.

This stage is cheap, so the expensive stages run only when something moves.

### Step 2: Detector (`detector.py`)

The detector has two modes. `RF_DETECTOR_MODE=auto` picks YOLO if rock weights exist, else motion.

| Mode | How a "rock" is found | Confidence C |
|---|---|---|
| `motion` (default today) | Each motion blob is a rock candidate | Blob solidity × size factor |
| `yolo` | A YOLO model trained on rock images (`models/rock.pt`) | YOLO's score. Only classes in `RF_ROCK_CLASSES` are kept. |

**Veto:** a stock COCO YOLOv8n model then removes any candidate that it labels as a bird, person, vehicle or animal. It downloads `models/yolov8n.pt` (about 6 MB) on first use. If the model cannot load, the system logs a warning and continues without the veto.

### Step 3: Tracker (`tracker.py`)

The tracker links the detections in this frame to the objects seen in earlier frames. Each object becomes a **track** with an id, its box, and up to 40 past centre positions.

A detection matches a track in either case:
- its box overlaps the track's last box (IoU ≥ 0.3), or
- its centre is close to where the track was predicted to be. The prediction assumes constant velocity.

The prediction matters. A falling rock can move more than its own size between frames, so its boxes never overlap.

The tracker also computes two values per track:
- **Persistence P:** the fraction of the last 10 frames in which the track was seen.
- **Growth ΔA:** how fast the box area grows, for example as a rock comes toward the camera.

A track is deleted after it goes unseen for 5 processed frames.

### Step 4: Risk score (`risk.py`)

**4a. Fall-likeness K (0 to 1).** This step stops trees, birds and people from being flagged. It looks at the track's whole path. K is high only when all of these hold:

| Check | A rock… | Rejects |
|---|---|---|
| Drop | moves down at least 5% of the frame height | static rocks, small jitter |
| Vertical | moves within about 25° of vertical | birds and people moving sideways |
| Straight | moves in a nearly straight line | swaying branches |
| Monotonic | never moves back up | branches, circling birds |
| No sideways reversals | does not swing left then right | branches |
| Gravity curve | its path bends toward vertical over time | a bird pulling out of a dive |

A track needs at least 4 points before it can score.

**4b. Paper formula with one extension:**

```
R = K × ( 0.35·C  +  0.30·max(ΔA, V)  +  0.25·P  +  0.10·(1 − D) )
```

- **C:** detector confidence.
- **ΔA:** area growth. **V:** downward speed. A rock falling across the view barely changes size, so speed is used as an alternative.
- **P:** persistence.
- **D:** distance from the danger zone. The danger zone is the bottom 25% of the frame, drawn in red. D is 0 inside the zone, so closer objects score higher.

**4c. Classify:** R < 0.40 is **Low**. 0.40 to 0.70 is **Moderate**. R ≥ 0.70 is **High**.

The frame's risk is the highest R among its tracks.

### Step 5: Alert manager (`alerts.py`)

| Rule | Value | Why |
|---|---|---|
| Debounce | High must last 3 evaluations in a row for the same track | One noisy frame must not alert |
| One alert per rock | A track alerts once at most | No repeat alerts as the rock falls through the frame |
| Cooldown | 300 s per region (3×3 grid of the frame) | During a long event, there is no email or siren flood. A different region can still alert. |

When an alert fires, the **Notifier** sends the email and sounds the siren on a separate worker thread, so a slow mail server never stalls the video.

| Channel | Default | To make it reach people |
|---|---|---|
| Email | Written to the log only | Set `RF_SMTP_HOST`, `RF_SMTP_PORT`, `RF_SMTP_USER`, `RF_SMTP_PASS`, `RF_ALERT_TO` (comma-separated list). TLS is required. |
| Siren | macOS: a 2 s tone on the backend computer's speakers. Windows: written to the log only. | Set `RF_SIREN_WEBHOOK`. It receives an HTTP POST, for example to a siren relay controller. |
| Dashboard | Red ALERT row in the event log | Someone must watch the page |

### Step 6: Publish

The thread draws the overlay on the frame: boxes, track ids, the risk badge, the danger zone and the motion bar. It then encodes the frame as JPEG and saves the latest copy for the web server.

## 4. Database (`store.py`)

**Engine:** SQLite, a single file at `backend/data/events.db`. There is no database server to install. It is created on first run.

**Table `events`:**

| Column | Type | Meaning |
|---|---|---|
| `id` | INTEGER, auto | Event number |
| `ts` | REAL | Unix time in seconds |
| `type` | TEXT | `LEVEL_CHANGE`, `ALERT` or `SUPPRESSED` (an alert that cooldown blocked) |
| `level` | TEXT | `LOW`, `MODERATE` or `HIGH` |
| `risk` | REAL | Risk score R at that moment |
| `region` | TEXT | Grid cell, such as `r1c1` (row 1, column 1) |
| `message` | TEXT | Readable text |

**What is NOT stored:**
- video or images;
- per-frame detections or tracks (they are live only, over `/ws`);
- operator accounts.

**Read it:**
- Dashboard: event log panel.
- API: `GET http://127.0.0.1:8000/api/events?limit=100`.
- SQL: `sqlite3 backend/data/events.db "select * from events order by id desc limit 20;"`.

**Known limits:**
- **The log grows without limit.** Every Low↔Moderate change adds a row, and there is no cleanup.
- **It is local to one machine.** Each site has its own file, and there is no central database.

## 5. API (`api.py`)

| Endpoint | Type | Used by | Returns |
|---|---|---|---|
| `GET /video` | MJPEG stream (`multipart/x-mixed-replace`) | Dashboard `<img>` | Annotated live frames |
| `WS /ws` | WebSocket, about 5 messages per second | Dashboard | `{ts, fps, motion_ratio, frame_forwarded, risk, level, detector_mode, tracks[], event}` |
| `GET /api/events` | JSON | Dashboard on load | Last N events from SQLite |
| `GET /api/config` | JSON | Settings panel | Current settings. The SMTP password is masked. |
| `PUT /api/config` | JSON | Settings panel | Changes only allow-listed tunables, live, with no restart. Changes are not saved to disk. |
| `GET /health` | JSON | Monitoring | `status`, `detector_mode`, `running`, `error` |

**Security:** there is no login. The server listens on `127.0.0.1` only, so only the same computer can reach it. Do not expose it on a network without adding authentication.

## 6. Dashboard (`frontend/`)

**`useMonitor.js`:**
- opens the WebSocket and reconnects with backoff from 0.5 s to 10 s;
- keeps 10 minutes of risk history for the trend chart;
- merges stored events with live events.

**`Panels.jsx`:** live video, risk gauge, trend chart (with the 0.40 and 0.70 lines), active tracks table, event log, telemetry bar, and settings form.

**Node.js:** only builds and serves this React code during development (`npm run dev`). The backend never uses Node.

## 7. Threads and timing

| Thread | Does | Blocks on |
|---|---|---|
| Capture (`rf-capture`) | Steps 0–6 for each frame | Camera read |
| Notifier (`rf-notifier`) | Email and siren | Network, audio |
| Uvicorn event loop | HTTP, WebSocket, MJPEG | Clients |

**Latency:**
- A track needs about 4 processed frames before it can score, then 3 High evaluations to pass the debounce.
- In the synthetic tests, the alert fires about 1.0 s after the rock starts to fall.

**Shutdown:** Ctrl+C waits at most 2 s for open dashboard connections, then always releases the camera.

## 8. Configuration

Every setting in `config.py` can be overridden by an environment variable named `RF_` plus the setting name in capitals, for example `RF_THETA_HIGH=0.75`. See [README.md](README.md#configuration) for the full table. The values from the paper (Table 2) are the defaults.

## 9. Testing

`cd backend && .venv/bin/python -m pytest -q` runs 28 tests. They are deterministic: a fake clock replaces real time, and there are no sleeps.

**Unit tests:**
- motion filter;
- tracker, including a fast fall with no box overlap;
- the paper formula, against hand-computed values;
- fall kinematics: one accepted fall, plus six rejected cases (tree sway, bird sideways, bird climbing, bird pulling out of a dive, too-short track, static rock);
- debounce, cooldown and one-alert-per-rock;
- the global-motion gate;
- refusal to log in to SMTP without TLS.

**End-to-end tests:**
- a synthetic falling-rock video must raise an ALERT;
- synthetic distractor videos (branches, three birds, a walking person, an exposure jump; 3 seeds) must never reach High.

## 10. Known limitations

1. **A bird diving straight down moves like a falling rock.** The COCO veto or trained rock weights are needed for this case.
2. **Motion mode cannot tell a rock from other falling debris,** such as soil or a dropped tool. Train YOLO rock weights for real deployments (`scripts/train.py`).
3. **The danger zone is fixed** to the bottom 25% of the frame. Each camera needs it set for its own view.
4. **The camera must be fixed.** A moving or panning camera breaks frame differencing.
5. **Tested on synthetic video only.** Validate on real site footage with `scripts/evaluate.py`.
6. **No SMS or mobile push, and no alert sound in the dashboard.** The event log grows without limit.

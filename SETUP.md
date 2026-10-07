# Team Setup Guide (macOS and Windows)

This guide takes a new machine from nothing to a running system. Setup takes about 10 minutes, mostly for the PyTorch download (about 1 GB).

- [macOS](#macos)
- [Windows](#windows)
- [Daily use](#daily-use)
- [Troubleshooting](#troubleshooting)

## Requirements

| Tool | Version | Why |
|---|---|---|
| Git | any | Clone the repo |
| Python | 3.10 to 3.13 recommended (3.14 tested on macOS) | Backend |
| Node.js | 18 or later (LTS) | Dashboard |
| Webcam | built-in or USB | Live input. You can use the demo video without one. |
| Disk | about 3 GB free | Python packages |

---

## macOS

### 1. Install the tools

Install [Homebrew](https://brew.sh) if you do not have it. Then run:

```bash
brew install git python@3.12 node
```

Check the versions:

```bash
python3 --version
```

```bash
node --version
```

### 2. Clone the repo

```bash
git clone https://github.com/AnandamChattrapate/rockfall-monitor.git
```

```bash
cd rockfall-monitor
```

### 3. Run the setup script

```bash
./scripts/setup.sh
```

The script does these steps:
1. Creates `backend/.venv`.
2. Installs the Python packages.
3. Runs `npm install` in `frontend/`.
4. Runs the tests. The last line should say `passed`.

If you get `permission denied`, run `chmod +x scripts/setup.sh` first.

### 4. Allow camera access

Run the backend from the **Terminal** app (or iTerm), not from inside an editor's sandbox.

- **First run:** macOS asks for camera access. Click **Allow**.
- **No prompt, or you clicked Don't Allow:**
  1. Open System Settings > Privacy & Security > Camera.
  2. Turn on **Terminal**.
  3. Quit Terminal fully (Cmd+Q) and open it again.

### 5. Start the system

Terminal 1 (backend):

```bash
cd backend && .venv/bin/python -m rockfall --source 0
```

Terminal 2 (dashboard):

```bash
cd frontend && npm run dev
```

Open http://localhost:5173.

---

## Windows

Use **PowerShell** for all steps. Windows 10 and 11 are supported.

### 1. Install the tools

Use the installers:
- **Git:** https://git-scm.com/download/win
- **Python 3.12:** https://www.python.org/downloads/
  - On the first installer screen, tick **"Add python.exe to PATH"**.
- **Node.js LTS:** https://nodejs.org/

Or use winget:

```powershell
winget install Git.Git Python.Python.3.12 OpenJS.NodeJS.LTS
```

Close PowerShell and open it again so that the new PATH applies. Then check:

```powershell
py --version
```

```powershell
node --version
```

### 2. Clone the repo

```powershell
git clone https://github.com/AnandamChattrapate/rockfall-monitor.git
```

```powershell
cd rockfall-monitor
```

### 3. Run the setup script

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

The `-ExecutionPolicy Bypass` flag applies to this one run only. It does not change your system policy. The script does the same steps as on macOS. The last test line should say `passed`.

### 4. Allow camera access

1. Open Settings > Privacy & security > Camera.
2. Turn on **Camera access**.
3. Turn on **Let desktop apps access your camera**.
4. Close other apps that use the camera, such as Teams, Zoom or the Camera app. On Windows, only one app can use the camera at a time.

### 5. Start the system

PowerShell window 1 (backend):

```powershell
cd backend; .venv\Scripts\python.exe -m rockfall --source 0
```

PowerShell window 2 (dashboard):

```powershell
cd frontend; npm run dev
```

Open http://localhost:5173.

> On Windows, the siren is logged, not played. The built-in siren uses macOS `afplay`. To use a real siren, set `RF_SIREN_WEBHOOK` (see [README.md](README.md#configuration)).

---

## Daily use

| Task | macOS | Windows |
|---|---|---|
| Start backend (webcam) | `cd backend && .venv/bin/python -m rockfall --source 0` | `cd backend; .venv\Scripts\python.exe -m rockfall --source 0` |
| Use a second camera | `--source 1` | `--source 1` |
| Demo without a camera | `.venv/bin/python scripts/make_synthetic.py data/synthetic.mp4` then `--source data/synthetic.mp4` | `.venv\Scripts\python.exe scripts\make_synthetic.py data\synthetic.mp4` then `--source data\synthetic.mp4` |
| Start dashboard | `cd frontend && npm run dev` | `cd frontend; npm run dev` |
| Run tests | `cd backend && .venv/bin/python -m pytest -q` | `cd backend; .venv\Scripts\python.exe -m pytest -q` |
| Stop | Ctrl+C in each terminal. The camera turns off within about 2 s. | Same |
| Get latest code | `git pull`, then run setup again if `requirements.txt` or `package.json` changed | Same |

Check that the backend is up: http://127.0.0.1:8000/health should return `"status":"ok"`.

### Optional: email alerts

Email alerts are only logged until you configure SMTP. Copy `backend/.env.example` to `backend/.env` and fill in the `RF_SMTP_*` and `RF_ALERT_TO` values.

Load the file:
- **macOS:** `set -a; source .env; set +a`
- **Windows PowerShell:**
  ```powershell
  Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v }
  ```

Do not commit `.env`. It is in `.gitignore`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Camera 0 unavailable` | No camera permission, or another app is using the camera | Follow the camera step for your OS. Close Zoom, Teams or FaceTime. Try `--source 1`. |
| `address already in use` / port 8000 or 5173 busy | An old backend or dashboard is still running | macOS: `lsof -i :8000`, then `kill <PID>`. Windows: `netstat -ano \| findstr :8000`, then `taskkill /PID <PID> /F`. |
| Dashboard shows "offline" | The backend is not running, or it crashed | Check the backend terminal for errors. Open http://127.0.0.1:8000/health. |
| `py` / `python` not found (Windows) | Python is not on PATH | Run the Python installer again, choose Modify, and tick "Add to PATH". Then reopen PowerShell. |
| `running scripts is disabled on this system` | PowerShell execution policy | Use the `-ExecutionPolicy Bypass -File` command from step 3. |
| `pip install` fails on `torch` | Python version too new for your platform's PyTorch build | Install Python 3.12, delete `backend/.venv`, and run setup again. |
| `npm install` permission error on `~/.npm` (macOS) | Root-owned npm cache | `sudo chown -R $(id -u):$(id -g) ~/.npm` |
| Everything moving is flagged | You are on old code | Run `git pull`. The fix is in commit `ae9e886`. |
| First run pauses for a few seconds | It is downloading the bird and person filter model `yolov8n.pt` (about 6 MB) | Wait once. It is cached in `backend/models/`. |

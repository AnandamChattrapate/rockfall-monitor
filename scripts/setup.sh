#!/usr/bin/env bash
# One-time setup on macOS or Linux. Run from the repo root:  ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not found. $2" >&2; exit 1; }; }
need python3 "Install Python 3.10-3.13: brew install python@3.12"
need node "Install Node.js 18+: brew install node"
need npm "Install Node.js 18+: brew install node"

python3 - <<'EOF'
import sys
if sys.version_info < (3, 10):
    sys.exit(f"ERROR: Python {sys.version.split()[0]} is too old; need 3.10 or later")
EOF

echo "==> Backend: creating backend/.venv and installing packages (PyTorch is ~1 GB)"
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

echo "==> Frontend: installing npm packages"
(cd frontend && npm install)

echo "==> Running backend tests"
(cd backend && .venv/bin/python -m pytest -q)

echo
echo "Setup complete. Start the system with two terminals:"
echo "  1) cd backend  && .venv/bin/python -m rockfall --source 0"
echo "  2) cd frontend && npm run dev     then open http://localhost:5173"

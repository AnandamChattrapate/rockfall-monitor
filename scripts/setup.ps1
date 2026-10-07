# One-time setup on Windows. Run from the repo root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$cmd not found. $hint"
    }
}

# The Python launcher "py" ships with the python.org installer; fall back to "python".
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
Need $py "Install Python 3.10-3.13 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')."
Need node "Install Node.js 18+ LTS from https://nodejs.org/"
Need npm "Install Node.js 18+ LTS from https://nodejs.org/"

& $py -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Error "Python 3.10 or later is required." }

Write-Host "==> Backend: creating backend\.venv and installing packages (PyTorch is ~1 GB)"
& $py -m venv backend\.venv
if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed" }
$venvPy = "backend\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed" }

Write-Host "==> Frontend: installing npm packages"
Push-Location frontend
npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "npm install failed" }
Pop-Location

Write-Host "==> Running backend tests"
Push-Location backend
& .venv\Scripts\python.exe -m pytest -q
$testExit = $LASTEXITCODE
Pop-Location
if ($testExit -ne 0) { Write-Error "tests failed" }

Write-Host ""
Write-Host "Setup complete. Start the system with two terminals:"
Write-Host "  1) cd backend;  .venv\Scripts\python.exe -m rockfall --source 0"
Write-Host "  2) cd frontend; npm run dev     then open http://localhost:5173"

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from example. Add secrets manually."
    Copy-Item ".env.example" ".env"
}

if (-not (Test-Path "config\config.yaml")) {
    Write-Host "Creating config.yaml from example."
    Copy-Item "config\config.example.yaml" "config\config.yaml"
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
Write-Host "NOTE: Do not install multiple OpenCV variants (e.g. opencv-python-headless). Only use the pinned opencv-python."
Write-Host "Review requirements.txt package names before continuing."
$answer = Read-Host "Install reviewed Python requirements? (yes/no)"
if ($answer -eq "yes") {
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
} else {
    Write-Host "Skipped dependency installation."
}

New-Item -ItemType Directory -Force -Path data, logs, cache, artifacts, private_data, private_data\faces\references, private_data\faces\models | Out-Null
Write-Host "Setup complete. Edit .env and config\config.yaml."

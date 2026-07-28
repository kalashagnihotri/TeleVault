$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Warning "Live mode is a scaffold until the required phases in TASKS.md are complete."
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "Virtual environment missing. Please run scripts/setup.ps1"
}
& ".\.venv\Scripts\python.exe" -m src.main

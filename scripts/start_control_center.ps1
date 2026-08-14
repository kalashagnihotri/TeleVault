$ErrorActionPreference = "Stop"

# Resolve project root (one level up from scripts dir)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location -Path $ProjectRoot

# Check for virtual environment
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-Not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found at $PythonExe. Please run setup first."
    exit 1
}

# Set PYTHONPATH safely
$env:PYTHONPATH = "."

# Start Control Center
Write-Host "Starting Control Center backend..." -ForegroundColor Green
& $PythonExe -m src.control_center

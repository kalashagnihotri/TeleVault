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

# Free up port 8000 if occupied by a previous instance
$staleConn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($staleConn) {
    $stalePid = $staleConn.OwningProcess | Select-Object -Unique
    Write-Host "Releasing port 8000 (killing previous instance PID: $stalePid)..." -ForegroundColor Yellow
    Stop-Process -Id $stalePid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

# Set PYTHONPATH safely
$env:PYTHONPATH = "."

# Start Control Center
Write-Host "Starting Control Center backend on http://127.0.0.1:8000..." -ForegroundColor Green
& $PythonExe -m src.control_center

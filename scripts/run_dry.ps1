$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& ".\.venv\Scripts\python.exe" -m src.main --dry-run

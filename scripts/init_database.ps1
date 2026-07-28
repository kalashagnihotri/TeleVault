$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& ".\.venv\Scripts\python.exe" -c "from pathlib import Path; from src.database import ArchiveDatabase; db = ArchiveDatabase(Path('data/archive.sqlite3')); db.apply_migrations(Path('sql')); print('Database migrations completed:', db.path)"

# Windows Setup

## Required software

- Windows 10 or 11
- Python 3.11 or newer
- Git
- Google Drive for Desktop
- FFmpeg, including `ffmpeg.exe` and `ffprobe.exe`
- Antigravity IDE
- Optional: NVIDIA driver compatible with your RTX 3050
- Optional later: WSL2 or Docker Desktop for the local Telegram Bot API

> [!NOTE]
> This project requires OpenCV 4 (provided by `opencv-python` in `requirements.txt`). Do not install multiple OpenCV variants (like `opencv-contrib-python` or `opencv-python-headless`) simultaneously.

## Project setup

Open PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
cd C:\path\to\telegram_media_archive_antigravity
Copy-Item .env.example .env
Copy-Item config\config.example.yaml config\config.yaml
.\scripts\setup_windows.ps1
.\scripts\init_database.ps1
```

Edit `.env` and `config\config.yaml`.

Run tests:

```powershell
.\scripts\test.ps1
```

Dry run:

```powershell
.\scripts\run_dry.ps1
```

Live run only after reviewing dry-run output:

```powershell
.\scripts\run_live.ps1
```

## GPU use

Start with CPU mode. It is easier to verify.

After the basic pipeline works:
1. Install the model runtime chosen by the vision phase.
2. Confirm the runtime detects the RTX 3050.
3. Benchmark a test folder.
4. Keep CPU fallback enabled.

Do not block backups when GPU initialization fails.

## Task Scheduler

After live testing:

1. Open Task Scheduler.
2. Create Task, not Basic Task.
3. Trigger: at logon and optionally every hour.
4. Action:
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\full\path\scripts\run_live.ps1"`
   - Start in: project root
5. Enable “Run task as soon as possible after a scheduled start is missed.”
6. Do not allow multiple parallel instances.
7. Start only when network is available.

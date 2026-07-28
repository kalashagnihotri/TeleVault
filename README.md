# Telegram Media Archive

A local-first media backup and organization system for Android → temporary Google Drive → Windows laptop → Telegram.

## Core behavior

- Google Drive is a temporary queue, not the final archive.
- The Windows laptop performs all hashing, metadata extraction, face matching, scene labeling, video sampling, caption creation, and Telegram uploads.
- Every image is archived as:
  1. A Telegram photo preview with caption.
  2. The untouched original as a document reply.
- Every video is archived as:
  1. A generated thumbnail with caption.
  2. The untouched original as a document reply.
- Exact duplicates are blocked using SHA-256.
- Weak or uncertain face matches are labeled `Unknown Person`.
- Files without usable GPS go to `Misc`.
- Recognition failure never blocks backup.
- A file is deleted from the temporary Drive queue only after the original upload is confirmed and recorded.

## First setup order

1. Read `docs/01_ARCHITECTURE.md`.
2. Follow `docs/02_WINDOWS_SETUP.md`.
3. Create the Telegram group and bot using `docs/03_TELEGRAM_SETUP.md`.
4. Configure Google Drive using `docs/04_GOOGLE_DRIVE_SETUP.md`.
5. Copy `.env.example` to `.env`.
6. Copy `config/config.example.yaml` to `config/config.yaml`.
7. Run `scripts/setup_windows.ps1`.
8. Run `scripts/init_database.ps1`.
9. Enroll known faces using `docs/FACE_ENROLLMENT.md`.
10. Start in dry-run mode with `scripts/run_dry.ps1`.
11. Review output, then enable uploads with `scripts/run_live.ps1`.

## Antigravity

Open this whole folder as one Antigravity workspace. Antigravity recognizes:

- `.agents/agents.md`
- `.agents/skills/*.md`
- `.agents/workflows/*.md`

Suggested first command:

```text
/audit-project
```

Then:

```text
/build-phase-1
```

Do not ask an agent to build everything in one pass. Follow the phases in `TASKS.md`.

## Safety

Never commit:

- `.env`
- bot tokens
- Telegram API ID or API hash
- face reference photos
- generated face embeddings
- the production SQLite database
- private GPS locations

See `SECURITY.md` and `.gitignore`.

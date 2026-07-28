# Telegram Setup

## Create the bot

1. Open Telegram and message BotFather.
2. Create a new bot.
3. Copy the bot token into `.env`.
4. Never paste the token into code or Antigravity prompts.

## Create the archive group

1. Create a private Telegram group.
2. Convert or configure it as a forum with topics.
3. Add the bot.
4. Give the bot only the permissions it needs:
   - Send messages
   - Send media
   - Manage topics when topic creation is enabled
5. Create a small fixed set of topics.
6. Store the group ID and topic IDs in `config/config.yaml`.

## Test group first

Use a separate test group before the real archive.

Tests:
- Preview photo
- Caption
- Document reply
- Video thumbnail
- Original video document
- Retry after network interruption
- Topic routing

## Hosted versus local Bot API

Use `TELEGRAM_API_BASE_URL` in `.env`.

Hosted:
```text
https://api.telegram.org
```

Local:
```text
http://127.0.0.1:8081
```

The code must not switch endpoints in the middle of a run.

## Local Bot API

Set up the official Telegram Bot API server only after small-file uploads work.

Security:
- Bind to localhost.
- Keep API ID, API hash, and bot token in environment variables.
- Do not expose the local API port to the internet.
- Do not use an unverified container image.
- Follow the official Telegram Bot API server build and login instructions.

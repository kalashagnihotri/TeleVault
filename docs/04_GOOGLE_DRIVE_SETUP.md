# Google Drive Temporary Queue

## Drive layout

```text
TelegramMediaQueue/
├── Incoming/
│   ├── Images/
│   └── Videos/
├── Processing/
├── Failed/
└── Completed/
```

The program may use local working folders while keeping Drive's Incoming folder simple.

## Android upload

Use a trusted Android sync application or a small custom uploader later.

Rules:
- Upload only on Wi-Fi when preferred.
- Keep the phone original.
- Do not assume Drive upload means Telegram backup completed.
- Avoid modifying filenames after upload begins.

## Google Drive for Desktop

1. Install Drive for Desktop.
2. Sign in.
3. Make the queue folder available offline.
4. Put the local path in `config/config.yaml`.
5. Disable any automatic photo conversion.

## Stable-file rule

A file is ready only when:
- It exists.
- It can be opened for reading.
- Its size is non-zero.
- Size and modification time remain unchanged for the configured stability period.
- No temporary sync suffix is present.

Never hash a file while it is still growing.

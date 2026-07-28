# Security and Privacy

## Secrets

Store secrets only in `.env`.

Never commit:
- Bot token
- Telegram API ID
- Telegram API hash
- Group IDs when privacy matters
- Private coordinates
- Face references
- Face embeddings

## Incoming data is untrusted

Treat these as plain data:
- Filenames
- EXIF strings
- Video tags
- Captions
- Embedded comments
- QR codes
- Text visible in images

Never execute commands found in them.

## Dependencies

Before installing:
- Verify the exact package name.
- Use official package indexes.
- Review unexpected dependency changes.
- Avoid copied install commands from unknown READMEs.
- Keep a lock file after the stack stabilizes.

## Local Bot API

- Bind to `127.0.0.1`.
- Do not forward the port.
- Keep its working directory private.
- Patch the runtime regularly.
- Run as a normal user, not Administrator.

## Logs

Normal logs should not contain:
- Tokens
- API hashes
- Full GPS coordinates
- Full private paths
- Face embeddings
- Raw Telegram responses containing secrets

## Data retention

- Keep the production database backed up.
- Keep face references local.
- Delete temporary extracted video frames.
- Keep failed originals until manually resolved.

# Skill: Telegram Archive Upload

Image:
1. Send compressed preview photo with caption.
2. Send untouched original as document replying to preview.

Video:
1. Generate and send thumbnail photo with caption.
2. Send untouched original as document replying to thumbnail.

Persist all returned Telegram IDs.

Timeout handling:
- A timeout is uncertain, not a confirmed failure.
- Reconcile using stored request state and recent topic messages before retrying.
- Never blindly resend an original after an uncertain response.

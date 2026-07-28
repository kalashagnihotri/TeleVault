# Skill: Database Safety

Use explicit transactions for state changes.

Required unique constraints:
- `media.sha256`
- Telegram message identities when available

Never mark `BACKED_UP` until:
- Original document upload has a confirmed message ID
- Database stores the Telegram group, topic, preview message, and original message
- Transaction commits successfully

Never delete rows during normal retries.
Use migrations for schema changes.

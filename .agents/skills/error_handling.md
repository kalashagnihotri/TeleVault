# Skill: Error Handling

Every error must be classified:
- transient
- permanent media error
- configuration error
- dependency error
- uncertain remote result
- invariant violation

Transient errors use capped exponential backoff with jitter.
Permanent media errors still permit archive upload when possible.
Invariant violations stop destructive actions.

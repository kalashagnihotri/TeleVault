# Antigravity Prompts

## Begin safely

```text
Read AGENTS.md, .agents/agents.md, TASKS.md, DECISIONS.md, and SECURITY.md. Run /audit-project. Do not install anything or change code until you produce the audit artifact.
```

## Build one phase

```text
Run /build-next-phase. Implement only the first incomplete phase in TASKS.md. Preserve all non-negotiable invariants. Add tests and update the changelog.
```

## Review duplicate protection

```text
Act as @qa. Inspect hashing, reservation, upload retry, and cleanup logic for any path that can create duplicate Telegram messages or delete an unconfirmed source. Add failure-injection tests.
```

## Implement faces

```text
Act as @vision. Implement conservative face enrollment and matching according to docs/06_FACE_ENROLLMENT.md. Unknown is preferred over a weak identity. Do not add automatic self-training.
```

## Implement videos

```text
Act as @vision. Implement docs/07_VIDEO_LOGIC.md. Each pass must add frames and reuse previous results. Recognition failure must return Unknown and continue to archive.
```

## Prepare production

```text
Run /release-check. Do not mark ready until data-loss, duplicate, secret, and retry checks pass.
```

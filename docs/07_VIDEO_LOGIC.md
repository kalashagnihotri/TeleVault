# Three-Pass Video Logic

## Pass 1 — Fast

Use a small set of evenly spaced frames.

Suggested totals:
- Under 30 seconds: 4
- 30 seconds–2 minutes: 5
- 2–10 minutes: 7
- Over 10 minutes: 8

Stop when the combined result is confident.

## Pass 2 — Focused

Add frames:
- Near scene changes
- Around clear face detections
- Around previously uncertain matches
- From uncovered time ranges

Suggested cumulative totals:
- 8, 15, 20, or 25 depending on duration

Reuse all Pass 1 results.

## Pass 3 — Deep but bounded

Add more diverse frames:
- Avoid near-identical frames
- Prefer good lighting and larger faces
- Keep broad timeline coverage

Suggested cumulative totals:
- 15, 30, 45, or 60

After Pass 3:
- Confident → known labels
- Uncertain → Unknown
- Upload regardless

## Confidence aggregation

A person can be accepted when:
- One exceptionally strong, high-quality face passes the strict threshold, or
- Multiple independent frames support the same person.

One weak frame must not identify a person.

## Temporary files

Extracted frames belong in a local cache outside Drive.
Delete them after:
- Original archive upload succeeds, or
- The job is moved to a retained failure-debug folder according to policy.

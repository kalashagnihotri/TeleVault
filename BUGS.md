# Known and Anticipated Bugs

Use this format:

```text
ID:
Status:
Severity:
Environment:
Steps:
Expected:
Actual:
Data-loss risk:
Duplicate risk:
Workaround:
Fix:
Regression test:
```

## B-001 Telegram timeout ambiguity
A network timeout may occur after Telegram accepted an upload. Blind retry could create a duplicate.

Required fix: reconciliation before retry.

## B-002 Drive partial file
Drive for Desktop may expose a file before it is fully available.

Required fix: stable-size and readable-file checks.

## B-003 Cleanup coupled to upload
Deleting immediately after an HTTP response risks loss if the database commit fails.

Required fix: separate cleanup worker and safety delay.

## B-004 Weak nearest-person match
Choosing the nearest embedding without thresholds can misidentify a person.

Required fix: threshold, second-best margin, and unknown fallback.

## B-005 Duplicate workers
Two processes may discover the same file.

Required fix: database unique constraint and single-instance lock.

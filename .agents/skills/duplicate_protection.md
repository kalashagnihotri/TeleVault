# Skill: Duplicate Protection

## Exact duplicates
Use streaming SHA-256 over complete bytes.
Same hash means no second archive upload.

## Similar media
Perceptual hashes are advisory only.
Do not skip, delete, or merge based only on visual similarity.

## Race handling
Reserve new SHA-256 inside a database transaction.
A unique constraint must settle concurrent arrivals.

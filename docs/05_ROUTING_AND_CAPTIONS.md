# Routing and Captions

## Routing priority

1. Multiple known people → `Family & Groups`
2. One known person → `People`
3. Screenshot/document → `Screenshots & Documents`
4. Mountains, river, lake, or travel scene → `Travel & Nature`
5. Video with no stronger result → `Videos`
6. No confident result or no GPS → `Misc`
7. Otherwise → `Everyday`

No GPS always sets location to `Misc`, but other recognized labels may still appear in the caption.

## Caption template

```text
{date_taken_or_file_date}
Location: {location_or_Misc}
People: {known_people_and_unknowns}
#{labels}
Original: {safe_filename}
Archive ID: {short_hash}
```

## Caption safety

- Escape Telegram formatting.
- Remove control characters.
- Limit caption length.
- Never include exact private coordinates by default.
- Never include full local paths.
- Never expose internal face scores.

# Test Cases

## Duplicate protection
- Same bytes, same filename
- Same bytes, different filename
- Same bytes, different folder
- Concurrent discovery by two workers
- Edited image with similar perceptual hash
- Truncated file sharing a prefix

## Stable files
- File grows during scan
- File mtime changes
- Zero-byte placeholder
- Locked sync file
- Temporary extension

## Metadata
- Valid EXIF GPS
- No GPS
- Invalid GPS
- Rotated image
- Screenshot
- Video with and without creation time
- Unicode filename
- Very long filename

## Faces
- Known clear face
- Known side face
- Two known people
- Known plus unknown
- Similar-looking people
- Blurry face
- Tiny face
- No face

## Video
- Person appears only at beginning
- Person appears only near end
- Rapid cuts
- Long static clip
- Screen recording
- Corrupt middle section
- Variable frame rate
- More than one known person

## Telegram
- Preview success, original success
- Preview success, original failure
- Preview timeout with actual success
- Original timeout with actual success
- Rate limit
- Invalid topic
- Bot removed from group
- Local API offline
- File beyond configured size

## Cleanup
- Safety delay not reached
- Missing source file
- Read-only source
- Crash before deletion
- Database commit failure

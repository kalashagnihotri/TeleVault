# Decisions

## D-001 Processing device
Use the Acer Aspire 7 Windows laptop for all processing. The Android phone only uploads media to the temporary Drive queue.

## D-002 Temporary storage
Use Google Drive as a temporary queue. It is not the source of truth and not the final archive.

## D-003 Original preservation
Upload every original image and video as a Telegram document. A separate preview or thumbnail provides easy browsing.

## D-004 Duplicate identity
Full-file SHA-256 is the only automatic exact-duplicate key.

## D-005 Similarity
Perceptual similarity is review-only and cannot automatically block an upload.

## D-006 Missing GPS
Any file without usable GPS receives location `Misc`.

## D-007 Location lookup
Use custom offline places first. Avoid bulk calls to public OSM/Nominatim servers.

## D-008 Recognition
Use lightweight local models. Unknown is acceptable. False identification is not.

## D-009 Video analysis
Use three progressive passes. Each pass adds frames and reuses previous work.

## D-010 Cleanup
Never clean the Drive queue until the original document message is confirmed and committed in SQLite.

## D-011 Large files
Support a local Telegram Bot API endpoint for files above hosted Bot API limits. Configure one API base URL per running bot session.

## D-012 Topics
Use a small fixed topic set. Put people, places, and scene labels in captions and hashtags.

# Face Privacy Architecture

This document describes the privacy safeguards built into the local face recognition pipeline (Phase 5).

## Local-First Guarantee
The Telegram Media Archive processes face embeddings strictly on the local machine:
- No photos or reference images are uploaded to any third-party cloud face-recognition API.
- The `private_data/faces/references` directory must contain private photos manually curated by the user.
- Reference photos and their face embeddings are never sent to Telegram. They remain stored purely locally.

## Conservative Matching Strategy
To avoid misidentifying faces, the system is designed to favor an "Unknown Person" tag over a false positive:
1. **Explicit Thresholds**: Every match requires the computed cosine similarity to be at or above the explicit `accept_threshold`.
2. **Minimum Margin**: Even if a face matches a known person above the accept threshold, if another completely distinct person has a high similarity score such that the difference is smaller than `minimum_margin`, the system returns "Unknown Person". This guards against ambiguous or poor-quality captures.
3. **Graceful Degradation**: If the face matching models crash, OpenCV is not installed, or any processing errors occur, the system safely ignores the face recognition module and proceeds with archiving using an "Unknown Person" tag. It never blocks uploads due to computer vision errors.

## Uncoupled Capabilities
Users can configure the application to route media silently to private Telegram topics based on identified faces, without exposing those faces in public captions:
- Set `include_names_in_captions: false` to ensure names are excluded from the message text, even if a match is confident.
- Set `use_for_routing: true` to route files to an individual's private topic silently.

## Ephemeral Storage
Any debug crops generated during inference are temporary and solely used for local review. They are not uploaded to Telegram. All temporary files from FFmpeg and OpenCV processes are aggressively removed when no longer needed or if the program crashes.

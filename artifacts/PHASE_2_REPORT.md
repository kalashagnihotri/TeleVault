# Phase 2 Report

## Goal Accomplished
Implemented Phase 2: Metadata extraction and deterministic routing.
The system now safely extracts metadata from images using Pillow and videos using `ffprobe`. It maps GPS coordinates to offline custom places, selects the correct Telegram topic, and builds the appropriate captions, saving this rich state to the database without modifying the original media files.

## Components Implemented

### Metadata Extractors
- `src/metadata_image.py`: Utilizes `Pillow` to extract `DateTimeOriginal` and EXIF GPS tags. Safely handles missing/corrupt headers and correctly computes float degree coordinates from EXIF fraction tuples.
- `src/metadata_video.py`: Uses `subprocess.run` to call `ffprobe`, parsing the JSON output to extract creation times and GPS metadata via ISO 6709 location tags. Fails gracefully.

### Location and Routing
- `config/places.json` & `src/places.py`: A lightweight, completely offline bounding-box resolver that assigns custom labels like `"Home"` to coordinates, falling back to `"Misc"`.
- `src/routing.py`: Updated to deterministically default to `"everyday"` for media with GPS when no specific labels apply.
- `src/captions.py`: Generates the caption using date, location, mocked labels (for future phases), and the original file name/hash.

### System Pipeline
- `src/scanner.py`: Upon hash reservation, now seamlessly invokes the correct metadata extractor based on file type, routes the topic, builds the caption, and advances the database record to `READY_TO_UPLOAD`.
- `src/database.py`: Expanded with `update_metadata` to persist these attributes.

## Validation Results
- Testing covered standard images, videos, images without GPS, and completely corrupt binary blobs. 
- The corrupt file gracefully falls back to `"Misc"` and doesn't crash the queue scanner loop.
- All Phase 2 invariants have been satisfied.

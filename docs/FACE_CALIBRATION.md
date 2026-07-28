# Face Calibration

This document outlines the mechanics and troubleshooting of the local face calibration engine.

## Overview
Because reference photos can be added or removed, the engine needs to "calibrate" its embeddings against the latest dataset. To ensure stability and auditability, this process is heavily versioned and transactional.

## Calibration Database Table
Every time the system detects a change in the `private_data/faces/references` directory hash, it attempts calibration.

The `face_calibrations` table tracks:
- `model_identity`: The string identifier of the models used (e.g. `sface_2021dec_yunet_2023mar`).
- `reference_set_hash`: A SHA-256 hash identifying the exact contents of the reference directory.
- Threshold values (`accept_threshold`, `review_threshold`, `minimum_margin`).
- `active`: A flag representing whether this is the currently applied calibration.

## Transactional Activation
Calibration follows an all-or-nothing approach:
1. The new reference set is scanned and embeddings are generated.
2. If the process crashes or is missing OpenCV dependencies, the old calibration remains active.
3. If successful, a database transaction is opened. The new calibration is inserted as active, and the old calibration is set to inactive.
4. From then on, any new media scan will point to the new calibration ID in `face_analysis_attempts`.

## Troubleshooting Calibration Errors
- **OpenCV Missing**: If the engine logs `FaceEngineError: OpenCV is not installed or available`, verify your Python environment has `opencv-python` installed.
- **Detector Model Missing**: Download the required ONNX models and place them in `private_data/faces/models`. 
- **Insufficient References**: By default, each person requires 5 distinct images. If a folder has fewer, calibration may be rejected. Check logs for validation failures.
- **Stale Cache**: If you believe the references have changed but calibration hasn't triggered, check if you accidentally modified the `reference_set_hash` manually or try restarting the system.

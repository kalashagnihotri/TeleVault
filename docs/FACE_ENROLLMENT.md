# Face Enrollment Guide

This guide explains how to enroll reference faces for the local facial recognition engine.

## Directory Structure
To enroll a known person, create a folder for them in the `private_data/faces/references` directory. Place high-quality reference images of the person's face inside their respective folder. 

Example:
```
private_data/faces/references/
├── Alice_Smith/
│   ├── alice_front.jpg
│   ├── alice_profile.jpg
│   └── alice_smiling.png
└── Bob_Jones/
    ├── bob_1.jpg
    └── bob_2.jpg
```

## Enrollment Rules
1. **Clear Faces**: Reference images should contain only one clear, unoccluded face.
2. **Diversity**: Provide varying angles, lighting conditions, and expressions to improve recognition accuracy.
3. **Minimum References**: By default, the system requires at least `5` reference images per person to establish a reliable calibration set. Ensure each person folder meets this requirement.
4. **No Subfolders**: Do not use subfolders within a person's directory. All reference images should be directly inside the person's folder.

## Calibration Process
Once references are added or updated, the system detects the change by computing a hash over the directory contents. It will then transactionally generate a new `face_calibrations` record. If the reference set lacks enough images or is invalid, the calibration fails gracefully without overwriting the previously active calibration.

## Manual Updates
You can safely add, remove, or replace images in the `references/` directory while the archive is stopped. Upon restart, the engine will automatically re-calibrate against the new dataset.

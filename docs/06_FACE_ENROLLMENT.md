# Face Enrollment

## Folder structure

Keep this outside Google Drive:

```text
private_data/
└── face_references/
    ├── Person_A/
    ├── Person_B/
    └── Person_C/
```

Use real names only when you are comfortable storing them locally.

## Reference quality

Use 10–20 clear photos per person:
- Front
- Slight left and right
- Indoor and outdoor
- Different expressions
- Glasses when applicable
- Recent appearance
- Limited occlusion

Avoid:
- Very small faces
- Heavy blur
- Group photos for initial enrollment
- Strong filters

## Enrollment

The enrollment command must:
1. Detect one clear face.
2. Reject ambiguous images.
3. Align and normalize.
4. Generate an embedding.
5. Save it locally.
6. Record model version.

## Matching

A result is known only when:
- Face quality passes.
- Best score passes the minimum threshold.
- Best score is sufficiently better than second best.
- Optional repeated-frame evidence supports video matches.

Otherwise use `Unknown Person`.

Never learn automatically from unreviewed predictions.

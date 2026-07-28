# Skill: Three-Pass Video Processing

Pass 1:
- Few evenly distributed frames
- Stop only on confident classification

Pass 2:
- Add frames around scene changes and detected faces
- Reuse Pass 1 results

Pass 3:
- Add more diverse frames
- Avoid near-identical frames
- Reuse all earlier results
- If still uncertain, return Unknown

Recognition failure never blocks backup.
Keep extracted frames only until processing and upload are safely complete.

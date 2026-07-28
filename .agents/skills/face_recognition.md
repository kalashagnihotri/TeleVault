# Skill: Conservative Face Recognition

Reference enrollment:
- Multiple clear images per person
- Different angles and lighting
- Store embeddings locally
- Never upload references or embeddings

Matching:
- Detect and align face
- Reject low-quality faces
- Compare against all enrolled identities
- Require minimum similarity
- Require margin over second-best identity
- Otherwise return `Unknown Person`

Do not retrain automatically from unreviewed matches.

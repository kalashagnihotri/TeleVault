from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

def clean_text(value: str) -> str:
    return _CONTROL.sub("", value).strip()

def build_caption(
    *,
    date_text: str,
    location: str,
    people: list[str],
    unknown_face_decisions: list[str] = None,
    labels: list[str],
    filename: str,
    short_hash: str,
    max_length: int = 900,
    scene_state: str = "COMPLETED",
    scene_error_code: str | None = None,
    face_state: str = "COMPLETED",
    face_error_code: str | None = None,
) -> str:
    safe_labels = [
        "#" + re.sub(r"[^A-Za-z0-9_]", "", label.replace(" ", "_"))
        for label in labels
        if clean_text(label)
    ]
    unknown_face_decisions = unknown_face_decisions or []
    
    people_lines = []
    if people or unknown_face_decisions:
        if people:
            if len(people) == 1:
                people_lines.append(f"👤 {clean_text(people[0])}")
            else:
                people_lines.append(f"👥 {', '.join(map(clean_text, people))}")
                
        # Deduplicate identical unknown decision tags/statuses
        seen_decisions = set()
        for decision in unknown_face_decisions:
            if decision not in seen_decisions:
                seen_decisions.add(decision)
                people_lines.append("👤 Unknown Person")
                people_lines.append(f"Face status: {clean_text(decision)}")
    else:
        people_lines.append("People: None detected")

    lines = [
        clean_text(date_text),
        f"Location: {clean_text(location) or 'Misc'}",
    ]
    lines.extend(people_lines)
    lines.extend([
        " ".join(safe_labels),
        f"Original: {clean_text(filename)}",
        f"Archive ID: {clean_text(short_hash)}",
    ])
    
    # Build error block if applicable
    error_lines = []
    if scene_state == "FAILED" or face_state == "FAILED":
        error_lines.append("")
        error_lines.append("⚠️ Image Analysis")
        if scene_state == "FAILED":
            error_lines.append(f"Scene: unavailable ({clean_text(scene_error_code or 'UNKNOWN')})")
        else:
            error_lines.append("Scene: completed")
            
        if face_state == "FAILED":
            error_lines.append(f"Faces: unavailable ({clean_text(face_error_code or 'UNKNOWN')})")
        else:
            error_lines.append("Faces: completed")
            
    error_text = "\n".join(error_lines)
    
    # Calculate available length for the main caption
    available_length = max_length - len(error_text) - 1 # -1 for newline if needed
    
    caption = "\n".join(line for line in lines if line)
    
    if len(caption) > available_length:
        caption = caption[:available_length]
        
    if error_text:
        caption += "\n" + error_text.strip()
        
    return caption

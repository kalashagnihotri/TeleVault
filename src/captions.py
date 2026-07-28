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
    labels: list[str],
    filename: str,
    short_hash: str,
    max_length: int = 900,
) -> str:
    safe_labels = [
        "#" + re.sub(r"[^A-Za-z0-9_]", "", label.replace(" ", "_"))
        for label in labels
        if clean_text(label)
    ]
    lines = [
        clean_text(date_text),
        f"Location: {clean_text(location) or 'Misc'}",
        f"People: {', '.join(map(clean_text, people)) if people else 'None detected'}",
        " ".join(safe_labels),
        f"Original: {clean_text(filename)}",
        f"Archive ID: {clean_text(short_hash)}",
    ]
    caption = "\n".join(line for line in lines if line)
    return caption[:max_length]

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class RouteInput:
    media_type: str
    people: tuple[str, ...]
    labels: tuple[str, ...]
    has_gps: bool

def choose_topic(data: RouteInput) -> str:
    known_people = [p for p in data.people if p != "Unknown Person"]
    labels = {label.lower() for label in data.labels}

    if not data.has_gps:
        return "misc"
    if len(known_people) > 1:
        return "family_groups"
    if len(known_people) == 1:
        return "people"
    if labels & {"screenshot", "document"}:
        return "screenshots_documents"
    if labels & {"mountains", "river", "lake", "travel", "nature"}:
        return "travel_nature"
    if data.media_type == "video":
        return "videos"
    return "everyday"

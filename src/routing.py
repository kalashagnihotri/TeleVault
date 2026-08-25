from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

@dataclass(frozen=True, slots=True)
class RouteInput:
    media_type: str
    people: tuple[str, ...]
    labels: tuple[str, ...]
    has_gps: bool


@dataclass(frozen=True)
class RuleEvaluation:
    rule_name: str
    target_topic: str
    matched: bool
    reason: str
    superseded: bool = False


@dataclass(frozen=True)
class RoutingExplanation:
    assigned_topic: str
    winning_rule: str
    evaluations: Tuple[RuleEvaluation, ...]
    summary_reasons: Tuple[str, ...]


def choose_topic(data: RouteInput) -> str:
    known_people = [p for p in data.people if p != "Unknown Person"]
    labels = {label.lower() for label in data.labels}

    if len(known_people) > 1:
        return "family_groups"
    if len(known_people) == 1:
        return "people"
    if labels & {"screenshot", "document"}:
        return "screenshots_documents"
    if not data.has_gps:
        return "misc"
    if labels & {"mountains", "river", "lake", "travel", "nature"}:
        return "travel_nature"
    if data.media_type == "video":
        return "videos"
    return "everyday"


def explain_routing(data: RouteInput) -> RoutingExplanation:
    known_people = [p for p in data.people if p != "Unknown Person"]
    labels = {label.lower() for label in data.labels}

    evals: List[RuleEvaluation] = []
    winning_rule = ""
    assigned_topic = ""
    reasons: List[str] = []

    # Rule 1: Multiple known people -> family_groups
    m1 = len(known_people) > 1
    evals.append(RuleEvaluation(
        rule_name="Multiple Known People",
        target_topic="family_groups",
        matched=m1,
        reason=f"Found {len(known_people)} known people: {', '.join(known_people)}" if m1 else f"Only {len(known_people)} known person(s) found",
    ))
    if m1 and not assigned_topic:
        winning_rule = "Multiple Known People"
        assigned_topic = "family_groups"
        reasons.append(f"✓ Found {len(known_people)} known people ({', '.join(known_people)})")

    # Rule 2: Single known person -> people
    m2 = len(known_people) == 1
    evals.append(RuleEvaluation(
        rule_name="Single Known Person",
        target_topic="people",
        matched=m2,
        reason=f"Found 1 known person: {known_people[0]}" if m2 else f"Known people count is {len(known_people)} (expected exactly 1)",
        superseded=bool(assigned_topic)
    ))
    if m2 and not assigned_topic:
        winning_rule = "Single Known Person"
        assigned_topic = "people"
        reasons.append(f"✓ Face analysis matched known person: {known_people[0]}")

    # Rule 3: Screenshots or documents -> screenshots_documents
    doc_match = labels & {"screenshot", "document"}
    m3 = bool(doc_match)
    evals.append(RuleEvaluation(
        rule_name="Document / Screenshot Heuristic",
        target_topic="screenshots_documents",
        matched=m3,
        reason=f"Matched scene labels: {', '.join(doc_match)}" if m3 else "No screenshot or document label detected",
        superseded=bool(assigned_topic)
    ))
    if m3 and not assigned_topic:
        winning_rule = "Document / Screenshot Heuristic"
        assigned_topic = "screenshots_documents"
        reasons.append(f"✓ Matched document/screenshot labels: {', '.join(doc_match)}")

    # Rule 4: Missing GPS -> misc
    m4 = not data.has_gps
    evals.append(RuleEvaluation(
        rule_name="Missing GPS Location",
        target_topic="misc",
        matched=m4,
        reason="Media has no GPS coordinates" if m4 else "Media contains valid GPS coordinates",
        superseded=bool(assigned_topic)
    ))
    if m4 and not assigned_topic:
        winning_rule = "Missing GPS Location"
        assigned_topic = "misc"
        reasons.append("✓ No GPS coordinates found on media")

    # Rule 5: Nature / Travel -> travel_nature
    nature_match = labels & {"mountains", "river", "lake", "travel", "nature"}
    m5 = bool(nature_match)
    evals.append(RuleEvaluation(
        rule_name="Travel / Nature Heuristic",
        target_topic="travel_nature",
        matched=m5,
        reason=f"Matched travel/nature labels: {', '.join(nature_match)}" if m5 else "No travel or nature labels detected",
        superseded=bool(assigned_topic)
    ))
    if m5 and not assigned_topic:
        winning_rule = "Travel / Nature Heuristic"
        assigned_topic = "travel_nature"
        reasons.append(f"✓ Matched travel/nature labels: {', '.join(nature_match)} (GPS present)")

    # Rule 6: Video -> videos
    m6 = (data.media_type.lower() == "video")
    evals.append(RuleEvaluation(
        rule_name="Video Media Type",
        target_topic="videos",
        matched=m6,
        reason="Media is a video container" if m6 else "Media is an image",
        superseded=bool(assigned_topic)
    ))
    if m6 and not assigned_topic:
        winning_rule = "Video Media Type"
        assigned_topic = "videos"
        reasons.append("✓ Media is a video file")

    # Rule 7: Fallback -> everyday
    if not assigned_topic:
        winning_rule = "Everyday Default Fallback"
        assigned_topic = "everyday"
        reasons.append("✓ Default fallback topic (GPS present, no face/document/nature overrides)")

    evals.append(RuleEvaluation(
        rule_name="Everyday Default Fallback",
        target_topic="everyday",
        matched=True,
        reason="Default category when no specific heuristic overrides apply",
        superseded=(winning_rule != "Everyday Default Fallback")
    ))

    return RoutingExplanation(
        assigned_topic=assigned_topic,
        winning_rule=winning_rule,
        evaluations=tuple(evals),
        summary_reasons=tuple(reasons)
    )

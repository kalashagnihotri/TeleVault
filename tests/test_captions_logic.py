import pytest
from src.captions import build_caption

def test_caption_unknown_low_score():
    # screenshot + UNKNOWN_LOW_SCORE -> unknown_person tag, correct reason
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=[],
        unknown_face_decisions=["UNKNOWN_LOW_SCORE"],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345"
    )
    assert "👤 Unknown Person" in caption
    assert "Face status: UNKNOWN_LOW_SCORE" in caption

def test_caption_unknown_low_res():
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=[],
        unknown_face_decisions=["UNKNOWN_LOW_RES"],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345"
    )
    assert "Face status: UNKNOWN_LOW_RES" in caption

def test_caption_ignored_tiny():
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=[],
        unknown_face_decisions=["IGNORED_TINY"],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345"
    )
    assert "Face status: IGNORED_TINY" in caption

def test_caption_unknown_uncalibrated():
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=[],
        unknown_face_decisions=["UNKNOWN_UNCALIBRATED"],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345"
    )
    assert "Face status: UNKNOWN_UNCALIBRATED" in caption

def test_caption_no_face():
    # screenshot + NO_FACE -> no unknown_person tag
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=[],
        unknown_face_decisions=[],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345"
    )
    assert "People: None detected" in caption
    assert "Unknown Person" not in caption

def test_caption_technical_face_error():
    # technical face error -> sanitized analysis warning
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=[],
        unknown_face_decisions=[],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345",
        face_state="FAILED",
        face_error_code="SANITIZED_FACE_ERROR_CODE"
    )
    assert "⚠️ Image Analysis" in caption
    assert "Faces: unavailable (SANITIZED_FACE_ERROR_CODE)" in caption

def test_caption_mixed_faces():
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=["Person One"],
        unknown_face_decisions=["UNKNOWN_LOW_SCORE"],
        labels=["screenshot", "unknown_person"],
        filename="test.png",
        short_hash="12345"
    )
    assert "👤 Person One" in caption
    assert "👤 Unknown Person" in caption
    assert "Face status: UNKNOWN_LOW_SCORE" in caption
    assert "#unknown_person" in caption

def test_caption_multiple_known():
    caption = build_caption(
        date_text="2026-08-12",
        location="Misc",
        people=["Person One", "Person Two"],
        unknown_face_decisions=[],
        labels=["screenshot"],
        filename="test.png",
        short_hash="12345"
    )
    assert "👥 Person One, Person Two" in caption

from src.routing import RouteInput, choose_topic

def test_no_gps_always_misc() -> None:
    data = RouteInput(
        media_type="image",
        people=("Known Person",),
        labels=("Mountains",),
        has_gps=False,
    )
    assert choose_topic(data) == "misc"

def test_multiple_known_people() -> None:
    data = RouteInput(
        media_type="image",
        people=("A", "B", "Unknown Person"),
        labels=(),
        has_gps=True,
    )
    assert choose_topic(data) == "family_groups"

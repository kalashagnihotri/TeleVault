from src.video_sampling import frame_targets, evenly_spaced_timestamps

def test_progressive_targets() -> None:
    assert frame_targets(60, 1) == 5
    assert frame_targets(60, 2) == 15
    assert frame_targets(60, 3) == 30

def test_even_spacing() -> None:
    values = evenly_spaced_timestamps(100, 5)
    assert len(values) == 5
    assert values == sorted(values)

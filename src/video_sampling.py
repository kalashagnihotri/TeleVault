from __future__ import annotations

def frame_targets(duration_seconds: float, pass_number: int) -> int:
    if pass_number not in {1, 2, 3}:
        raise ValueError("pass_number must be 1, 2, or 3")

    if duration_seconds < 30:
        totals = (4, 8, 15)
    elif duration_seconds < 120:
        totals = (5, 15, 30)
    elif duration_seconds < 600:
        totals = (7, 20, 45)
    else:
        totals = (8, 25, 60)

    return totals[pass_number - 1]

def evenly_spaced_timestamps(duration_seconds: float, count: int) -> list[float]:
    if duration_seconds <= 0 or count <= 0:
        return []
    if count == 1:
        return [duration_seconds / 2]
    margin = min(0.5, duration_seconds * 0.02)
    start = margin
    end = max(start, duration_seconds - margin)
    step = (end - start) / (count - 1)
    return [round(start + step * i, 3) for i in range(count)]

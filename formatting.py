"""Display helpers."""

from __future__ import annotations


def format_duration(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} ч {minutes:02d} мин"
    if minutes:
        return f"{minutes} мин {secs:02d} с"
    return f"{secs} с"


def format_percent(ratio: float) -> str:
    return f"{ratio * 100:.0f}%"

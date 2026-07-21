"""Display helpers."""

from __future__ import annotations


def format_duration(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _secs = divmod(rem, 60)
    return f"{hours} ч {minutes:02d} мин"


def format_percent(ratio: float) -> str:
    return f"{ratio * 100:.0f}%"

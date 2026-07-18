"""SQLite persistence for daily time totals."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class DayStats:
    day: date
    total_seconds: int
    active_seconds: int

    @property
    def activity_ratio(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return self.active_seconds / self.total_seconds


@dataclass(frozen=True)
class PeriodStats:
    start: date
    end: date
    total_seconds: int
    active_seconds: int
    days: tuple[DayStats, ...]

    @property
    def activity_ratio(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return self.active_seconds / self.total_seconds


def default_db_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "TimeTrack"
    else:
        root = Path.home() / ".local" / "share" / "TimeTrack"
    return root / "timetrack.db"


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                active_seconds INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_seconds(self, day: date, total_delta: int, active_delta: int) -> None:
        if total_delta <= 0 and active_delta <= 0:
            return
        key = day.isoformat()
        self._conn.execute(
            """
            INSERT INTO daily_stats (date, total_seconds, active_seconds)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_seconds = total_seconds + excluded.total_seconds,
                active_seconds = active_seconds + excluded.active_seconds
            """,
            (key, max(0, total_delta), max(0, active_delta)),
        )
        self._conn.commit()

    def get_day(self, day: date) -> DayStats:
        row = self._conn.execute(
            "SELECT total_seconds, active_seconds FROM daily_stats WHERE date = ?",
            (day.isoformat(),),
        ).fetchone()
        if row is None:
            return DayStats(day=day, total_seconds=0, active_seconds=0)
        return DayStats(
            day=day,
            total_seconds=int(row["total_seconds"]),
            active_seconds=int(row["active_seconds"]),
        )

    def get_range(self, start: date, end: date) -> PeriodStats:
        if end < start:
            start, end = end, start
        rows = self._conn.execute(
            """
            SELECT date, total_seconds, active_seconds
            FROM daily_stats
            WHERE date >= ? AND date <= ?
            ORDER BY date
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        by_date = {
            date.fromisoformat(row["date"]): DayStats(
                day=date.fromisoformat(row["date"]),
                total_seconds=int(row["total_seconds"]),
                active_seconds=int(row["active_seconds"]),
            )
            for row in rows
        }
        days: list[DayStats] = []
        total = 0
        active = 0
        cursor = start
        while cursor <= end:
            stats = by_date.get(cursor, DayStats(day=cursor, total_seconds=0, active_seconds=0))
            days.append(stats)
            total += stats.total_seconds
            active += stats.active_seconds
            cursor += timedelta(days=1)
        return PeriodStats(
            start=start,
            end=end,
            total_seconds=total,
            active_seconds=active,
            days=tuple(days),
        )

    def get_week(self, day: date) -> PeriodStats:
        monday = day - timedelta(days=day.weekday())
        sunday = monday + timedelta(days=6)
        return self.get_range(monday, sunday)

    def get_month(self, day: date) -> PeriodStats:
        start = day.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(days=1)
        return self.get_range(start, end)

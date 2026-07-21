"""SQLite persistence for daily time totals and per-app sessions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from apps import TRACKED_APPS
from paths import default_db_path as _portable_db_path


@dataclass(frozen=True)
class DayStats:
    day: date
    tracked_total: int
    tracked_active: int
    manual_seconds: int
    start_time: str | None
    end_time: str | None
    app_totals: dict[str, int] = field(default_factory=dict)

    @property
    def total_seconds(self) -> int:
        return self.tracked_total + self.manual_seconds

    @property
    def active_seconds(self) -> int:
        return self.tracked_active + self.manual_seconds

    @property
    def activity_ratio(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return self.active_seconds / self.total_seconds

    @property
    def has_data(self) -> bool:
        return self.total_seconds > 0 or self.active_seconds > 0 or bool(self.app_totals)


@dataclass(frozen=True)
class PeriodStats:
    start: date
    end: date
    total_seconds: int
    active_seconds: int
    manual_seconds: int
    days: tuple[DayStats, ...]

    @property
    def activity_ratio(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return self.active_seconds / self.total_seconds


@dataclass(frozen=True)
class AppSessionRow:
    day: date
    start_time: str
    end_time: str
    app_key: str
    app_name: str
    total_seconds: int
    active_seconds: int


def default_db_path() -> Path:
    return _portable_db_path()


def _empty_day(day: date) -> DayStats:
    return DayStats(
        day=day,
        tracked_total=0,
        tracked_active=0,
        manual_seconds=0,
        start_time=None,
        end_time=None,
        app_totals={},
    )


def _row_to_day(row: sqlite3.Row, app_totals: dict[str, int] | None = None) -> DayStats:
    start = row["start_time"]
    end = row["end_time"]
    return DayStats(
        day=date.fromisoformat(row["date"]),
        tracked_total=int(row["total_seconds"] or 0),
        tracked_active=int(row["active_seconds"] or 0),
        manual_seconds=int(row["manual_seconds"] or 0),
        start_time=str(start) if start else None,
        end_time=str(end) if end else None,
        app_totals=dict(app_totals or {}),
    )


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
        self._ensure_column("manual_seconds", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("start_time", "TEXT")
        self._ensure_column("end_time", "TEXT")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_app_stats (
                date TEXT NOT NULL,
                app_key TEXT NOT NULL,
                app_name TEXT NOT NULL,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                active_seconds INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (date, app_key)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                app_key TEXT NOT NULL,
                app_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                active_seconds INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_sessions_date ON app_sessions(date)"
        )
        self._conn.commit()

    def _ensure_column(self, name: str, typedef: str) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(daily_stats)").fetchall()
        }
        if name not in columns:
            self._conn.execute(f"ALTER TABLE daily_stats ADD COLUMN {name} {typedef}")

    def close(self) -> None:
        self._conn.close()

    def add_seconds(self, day: date, total_delta: int, active_delta: int) -> None:
        if total_delta <= 0 and active_delta <= 0:
            return
        key = day.isoformat()
        now_hm = datetime.now().strftime("%H:%M")
        self._conn.execute(
            """
            INSERT INTO daily_stats (
                date, total_seconds, active_seconds, manual_seconds, start_time, end_time
            )
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_seconds = total_seconds + excluded.total_seconds,
                active_seconds = active_seconds + excluded.active_seconds,
                start_time = COALESCE(daily_stats.start_time, excluded.start_time),
                end_time = excluded.end_time
            """,
            (key, max(0, total_delta), max(0, active_delta), now_hm, now_hm),
        )
        self._conn.commit()

    def add_app_seconds(
        self,
        day: date,
        app_key: str,
        app_name: str,
        total_delta: int,
        active_delta: int,
    ) -> None:
        if total_delta <= 0 and active_delta <= 0:
            return
        self._conn.execute(
            """
            INSERT INTO daily_app_stats (
                date, app_key, app_name, total_seconds, active_seconds
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, app_key) DO UPDATE SET
                app_name = excluded.app_name,
                total_seconds = total_seconds + excluded.total_seconds,
                active_seconds = active_seconds + excluded.active_seconds
            """,
            (
                day.isoformat(),
                app_key,
                app_name,
                max(0, total_delta),
                max(0, active_delta),
            ),
        )
        self._conn.commit()

    def create_session(
        self,
        day: date,
        app_key: str,
        app_name: str,
        start_time: str,
        end_time: str,
        total_seconds: int,
        active_seconds: int,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO app_sessions (
                date, app_key, app_name, start_time, end_time, total_seconds, active_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day.isoformat(),
                app_key,
                app_name,
                start_time,
                end_time,
                max(0, total_seconds),
                max(0, active_seconds),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def update_session(
        self,
        session_id: int,
        end_time: str,
        total_seconds: int,
        active_seconds: int,
    ) -> None:
        self._conn.execute(
            """
            UPDATE app_sessions
            SET end_time = ?, total_seconds = ?, active_seconds = ?
            WHERE id = ?
            """,
            (end_time, max(0, total_seconds), max(0, active_seconds), session_id),
        )
        self._conn.commit()

    def delete_session(self, session_id: int) -> None:
        self._conn.execute("DELETE FROM app_sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    def add_manual_time(self, day: date, hours: int, minutes: int = 0) -> int:
        """Add manually entered work time (stored separately, counted in totals)."""
        seconds = max(0, int(hours)) * 3600 + max(0, int(minutes)) * 60
        if seconds <= 0:
            return 0
        key = day.isoformat()
        self._conn.execute(
            """
            INSERT INTO daily_stats (
                date, total_seconds, active_seconds, manual_seconds, start_time, end_time
            )
            VALUES (?, 0, 0, ?, NULL, NULL)
            ON CONFLICT(date) DO UPDATE SET
                manual_seconds = manual_seconds + excluded.manual_seconds
            """,
            (key, seconds),
        )
        self._conn.commit()
        return seconds

    def _app_totals_by_date(self, start: date, end: date) -> dict[date, dict[str, int]]:
        rows = self._conn.execute(
            """
            SELECT date, app_key, total_seconds
            FROM daily_app_stats
            WHERE date >= ? AND date <= ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        result: dict[date, dict[str, int]] = {}
        tracked_keys = {app.key for app in TRACKED_APPS}
        for row in rows:
            day = date.fromisoformat(row["date"])
            app_key = str(row["app_key"])
            if app_key not in tracked_keys:
                continue
            result.setdefault(day, {})[app_key] = int(row["total_seconds"] or 0)
        return result

    def get_day(self, day: date) -> DayStats:
        row = self._conn.execute(
            """
            SELECT date, total_seconds, active_seconds, manual_seconds, start_time, end_time
            FROM daily_stats
            WHERE date = ?
            """,
            (day.isoformat(),),
        ).fetchone()
        apps = self._app_totals_by_date(day, day).get(day, {})
        if row is None:
            empty = _empty_day(day)
            if not apps:
                return empty
            return DayStats(
                day=day,
                tracked_total=0,
                tracked_active=0,
                manual_seconds=0,
                start_time=None,
                end_time=None,
                app_totals=apps,
            )
        return _row_to_day(row, apps)

    def get_range(self, start: date, end: date) -> PeriodStats:
        if end < start:
            start, end = end, start
        rows = self._conn.execute(
            """
            SELECT date, total_seconds, active_seconds, manual_seconds, start_time, end_time
            FROM daily_stats
            WHERE date >= ? AND date <= ?
            ORDER BY date
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        apps_by_date = self._app_totals_by_date(start, end)
        by_date = {
            date.fromisoformat(row["date"]): _row_to_day(
                row, apps_by_date.get(date.fromisoformat(row["date"]), {})
            )
            for row in rows
        }
        days: list[DayStats] = []
        total = 0
        active = 0
        manual = 0
        cursor = start
        while cursor <= end:
            stats = by_date.get(cursor)
            if stats is None:
                apps = apps_by_date.get(cursor, {})
                stats = DayStats(
                    day=cursor,
                    tracked_total=0,
                    tracked_active=0,
                    manual_seconds=0,
                    start_time=None,
                    end_time=None,
                    app_totals=apps,
                )
            days.append(stats)
            total += stats.total_seconds
            active += stats.active_seconds
            manual += stats.manual_seconds
            cursor += timedelta(days=1)
        return PeriodStats(
            start=start,
            end=end,
            total_seconds=total,
            active_seconds=active,
            manual_seconds=manual,
            days=tuple(days),
        )

    def get_sessions(self, start: date, end: date) -> list[AppSessionRow]:
        if end < start:
            start, end = end, start
        rows = self._conn.execute(
            """
            SELECT date, start_time, end_time, app_key, app_name, total_seconds, active_seconds
            FROM app_sessions
            WHERE date >= ? AND date <= ?
            ORDER BY date, start_time, id
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            AppSessionRow(
                day=date.fromisoformat(row["date"]),
                start_time=str(row["start_time"]),
                end_time=str(row["end_time"]),
                app_key=str(row["app_key"]),
                app_name=str(row["app_name"]),
                total_seconds=int(row["total_seconds"] or 0),
                active_seconds=int(row["active_seconds"] or 0),
            )
            for row in rows
            if int(row["total_seconds"] or 0) > 0 or int(row["active_seconds"] or 0) > 0
        ]

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

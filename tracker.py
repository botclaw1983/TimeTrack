"""Background activity tracker using Win32 idle time and foreground app."""

from __future__ import annotations

import ctypes
import sys
import time
from datetime import date, datetime

from PySide6.QtCore import QObject, QTimer, Signal

from apps import ForegroundApp, get_foreground_app
from storage import Storage

TICK_MS = 5_000
IDLE_THRESHOLD_SECONDS = 60
SLEEP_GAP_SECONDS = 120


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


def get_idle_seconds() -> float:
    """Return seconds since last keyboard/mouse input."""
    if sys.platform != "win32":
        # Dev fallback outside Windows: treat as always active.
        return 0.0

    last_input = LASTINPUTINFO()
    last_input.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input)):
        return IDLE_THRESHOLD_SECONDS + 1

    tick_count = ctypes.windll.kernel32.GetTickCount()
    idle_ms = (tick_count - last_input.dwTime) & 0xFFFFFFFF
    return idle_ms / 1000.0


class _OpenSession:
    __slots__ = ("session_id", "day", "app", "start_clock", "total_seconds", "active_seconds")

    def __init__(self, session_id: int, day: date, app: ForegroundApp, start_clock: str) -> None:
        self.session_id = session_id
        self.day = day
        self.app = app
        self.start_clock = start_clock
        self.total_seconds = 0
        self.active_seconds = 0


class ActivityTracker(QObject):
    stats_updated = Signal(object, int, int)  # date, total_today, active_today
    paused_changed = Signal(bool)

    def __init__(self, storage: Storage, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._storage = storage
        self._paused = False
        self._last_tick_monotonic: float | None = None
        self._open_session: _OpenSession | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        self._last_tick_monotonic = time.monotonic()
        self._timer.start()
        self._emit_today()

    def stop(self) -> None:
        self._timer.stop()
        self._close_session()

    def set_paused(self, paused: bool) -> None:
        if self._paused == paused:
            return
        self._paused = paused
        self._last_tick_monotonic = time.monotonic()
        if paused:
            self._close_session()
        self.paused_changed.emit(paused)

    def toggle_pause(self) -> None:
        self.set_paused(not self._paused)

    def today_stats(self) -> tuple[int, int]:
        stats = self._storage.get_day(date.today())
        return stats.total_seconds, stats.active_seconds

    def _emit_today(self) -> None:
        total, active = self.today_stats()
        self.stats_updated.emit(date.today(), total, active)

    def _now_clock(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _close_session(self) -> None:
        session = self._open_session
        if session is None:
            return
        if session.total_seconds > 0 or session.active_seconds > 0:
            self._storage.update_session(
                session.session_id,
                self._now_clock(),
                session.total_seconds,
                session.active_seconds,
            )
        else:
            self._storage.delete_session(session.session_id)
        self._open_session = None

    def _ensure_session(self, day: date, app: ForegroundApp) -> _OpenSession:
        current = self._open_session
        if current is not None and current.day == day and current.app.key == app.key:
            return current

        self._close_session()
        start_clock = self._now_clock()
        session_id = self._storage.create_session(
            day=day,
            app_key=app.key,
            app_name=app.title,
            start_time=start_clock,
            end_time=start_clock,
            total_seconds=0,
            active_seconds=0,
        )
        opened = _OpenSession(session_id, day, app, start_clock)
        self._open_session = opened
        return opened

    def _on_tick(self) -> None:
        now_mono = time.monotonic()
        if self._last_tick_monotonic is None:
            self._last_tick_monotonic = now_mono
            return

        delta = now_mono - self._last_tick_monotonic
        self._last_tick_monotonic = now_mono

        if self._paused:
            return

        # Sleep/hibernate gap: do not credit wall-clock holes.
        if delta > SLEEP_GAP_SECONDS:
            self._close_session()
            return

        # Cap delta to a bit over the tick interval to avoid overcounting.
        delta = min(delta, TICK_MS / 1000.0 * 1.5)
        total_delta = int(round(delta))
        if total_delta <= 0:
            return

        idle = get_idle_seconds()
        active_delta = total_delta if idle < IDLE_THRESHOLD_SECONDS else 0
        today = date.today()
        app = get_foreground_app()

        self._storage.add_seconds(today, total_delta, active_delta)
        self._storage.add_app_seconds(today, app.key, app.title, total_delta, active_delta)

        session = self._ensure_session(today, app)
        session.total_seconds += total_delta
        session.active_seconds += active_delta
        self._storage.update_session(
            session.session_id,
            self._now_clock(),
            session.total_seconds,
            session.active_seconds,
        )

        self._emit_today()

"""Background activity tracker using Win32 idle time."""

from __future__ import annotations

import ctypes
import sys
import time
from datetime import date

from PySide6.QtCore import QObject, QTimer, Signal

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


class ActivityTracker(QObject):
    stats_updated = Signal(object, int, int)  # date, total_today, active_today
    paused_changed = Signal(bool)

    def __init__(self, storage: Storage, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._storage = storage
        self._paused = False
        self._last_tick_monotonic: float | None = None
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

    def set_paused(self, paused: bool) -> None:
        if self._paused == paused:
            return
        self._paused = paused
        self._last_tick_monotonic = time.monotonic()
        self.paused_changed.emit(paused)

    def toggle_pause(self) -> None:
        self.set_paused(not self._paused)

    def today_stats(self) -> tuple[int, int]:
        stats = self._storage.get_day(date.today())
        return stats.total_seconds, stats.active_seconds

    def _emit_today(self) -> None:
        total, active = self.today_stats()
        self.stats_updated.emit(date.today(), total, active)

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
            return

        # Cap delta to a bit over the tick interval to avoid overcounting.
        delta = min(delta, TICK_MS / 1000.0 * 1.5)
        total_delta = int(round(delta))
        if total_delta <= 0:
            return

        idle = get_idle_seconds()
        active_delta = total_delta if idle < IDLE_THRESHOLD_SECONDS else 0

        self._storage.add_seconds(date.today(), total_delta, active_delta)
        self._emit_today()

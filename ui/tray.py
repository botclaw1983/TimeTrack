"""System tray icon and menu."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from formatting import format_duration


class TrayController(QObject):
    open_stats_requested = Signal()
    quit_requested = Signal()
    pause_toggled = Signal()

    def __init__(self, icon_path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(QIcon(str(icon_path)), parent)
        self._tray.setToolTip("TimeTrack")
        self._pause_action = QAction("Пауза", self)
        self._pause_action.triggered.connect(self.pause_toggled.emit)

        menu = QMenu()
        stats_action = QAction("Статистика", self)
        stats_action.triggered.connect(self.open_stats_requested.emit)
        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(stats_action)
        menu.addAction(self._pause_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def update_tooltip(self, total_seconds: int, active_seconds: int, paused: bool) -> None:
        prefix = "⏸ " if paused else ""
        self._tray.setToolTip(
            f"{prefix}TimeTrack\n"
            f"Общее: {format_duration(total_seconds)}\n"
            f"Активное: {format_duration(active_seconds)}"
        )

    def set_paused(self, paused: bool) -> None:
        self._pause_action.setText("Продолжить" if paused else "Пауза")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_stats_requested.emit()

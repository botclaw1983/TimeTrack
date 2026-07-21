"""System tray icon and menu."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from formatting import format_duration


def _fallback_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#1c242b"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#f3f5f7"))
    painter.setBrush(QColor("#3d4a55"))
    painter.drawEllipse(8, 8, 48, 48)
    painter.setBrush(QColor("#f3f5f7"))
    painter.drawEllipse(28, 14, 8, 8)
    painter.drawRect(30, 28, 4, 16)
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    open_stats_requested = Signal()
    quit_requested = Signal()
    pause_toggled = Signal()

    def __init__(self, icon_path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        icon = QIcon(str(icon_path)) if icon_path.exists() else _fallback_icon()
        self._tray = QSystemTrayIcon(icon, parent)
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

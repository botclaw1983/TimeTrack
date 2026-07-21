"""TimeTrack — tray app for Windows work-time tracking."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from paths import is_portable, resource_path
from storage import Storage
from tracker import ActivityTracker
from ui.stats_window import StatsWindow
from ui.tray import TrayController

ICON_PATH = resource_path("resources", "icon.png")


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("TimeTrack")
    app.setOrganizationName("TimeTrack")

    if is_portable():
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "TimeTrack",
            "Системный трей недоступен. Приложение не может работать без иконки в трее.",
        )
        return 1

    storage = Storage()
    tracker = ActivityTracker(storage)
    stats_window = StatsWindow(storage)
    tray = TrayController(ICON_PATH)

    def open_stats() -> None:
        stats_window.refresh()
        stats_window.show()
        stats_window.raise_()
        stats_window.activateWindow()

    def on_stats_updated(_day, total: int, active: int) -> None:
        tray.update_tooltip(total, active, tracker.paused)
        if stats_window.isVisible():
            stats_window.refresh()

    def on_paused_changed(paused: bool) -> None:
        tray.set_paused(paused)
        total, active = tracker.today_stats()
        tray.update_tooltip(total, active, paused)

    def on_manual_time_added() -> None:
        total, active = tracker.today_stats()
        tray.update_tooltip(total, active, tracker.paused)

    def quit_app() -> None:
        tracker.stop()
        tray.hide()
        storage.close()
        app.quit()

    tray.open_stats_requested.connect(open_stats)
    tray.pause_toggled.connect(tracker.toggle_pause)
    tray.quit_requested.connect(quit_app)
    tracker.stats_updated.connect(on_stats_updated)
    tracker.paused_changed.connect(on_paused_changed)
    stats_window.manual_time_added.connect(on_manual_time_added)

    tray.show()
    tracker.start()
    total, active = tracker.today_stats()
    tray.update_tooltip(total, active, False)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

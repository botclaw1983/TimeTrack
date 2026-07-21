"""Resolve app / resource / data paths for source and portable builds."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Directory that contains the executable or project root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_root() -> Path:
    """Bundled resources root (PyInstaller extract dir or project root)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def is_portable() -> bool:
    """Portable mode: frozen build or portable.flag next to the app."""
    return is_frozen() or (app_dir() / "portable.flag").exists()


def data_dir() -> Path:
    """Writable data directory (DB, settings)."""
    if is_portable():
        path = app_dir() / "data"
    else:
        local_app_data = __import__("os").environ.get("LOCALAPPDATA")
        if local_app_data:
            path = Path(local_app_data) / "TimeTrack"
        else:
            path = Path.home() / ".local" / "share" / "TimeTrack"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    return data_dir() / "timetrack.db"


def settings_path() -> Path:
    return data_dir() / "settings.ini"


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)

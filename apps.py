"""Foreground app detection and known app mapping."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class TrackedApp:
    key: str
    title: str
    process_names: frozenset[str]


# Порядок колонок в сводке.
TRACKED_APPS: tuple[TrackedApp, ...] = (
    TrackedApp("excel", "Excel", frozenset({"excel.exe"})),
    TrackedApp("outlook", "Outlook", frozenset({"outlook.exe", "olk.exe"})),
    TrackedApp("obsidian", "Obsidian", frozenset({"obsidian.exe"})),
    TrackedApp("chrome", "Chrome", frozenset({"chrome.exe"})),
)

_PROCESS_TO_APP: dict[str, TrackedApp] = {
    name: app for app in TRACKED_APPS for name in app.process_names
}


@dataclass(frozen=True)
class ForegroundApp:
    key: str
    title: str
    process_name: str


def resolve_app(process_name: str) -> ForegroundApp:
    normalized = process_name.lower().strip()
    known = _PROCESS_TO_APP.get(normalized)
    if known is not None:
        return ForegroundApp(key=known.key, title=known.title, process_name=normalized)
    display = process_name[:-4] if normalized.endswith(".exe") else process_name
    display = display or "unknown"
    return ForegroundApp(key=f"other:{normalized}", title=display.capitalize(), process_name=normalized)


def get_foreground_process_name() -> str:
    """Return executable name of the foreground window process."""
    if sys.platform != "win32":
        return "unknown.exe"

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "unknown.exe"

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "unknown.exe"

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return "unknown.exe"

    try:
        size = wintypes.DWORD(260)
        buffer = ctypes.create_unicode_buffer(size.value)
        # QueryFullProcessImageNameW
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return "unknown.exe"
        path = buffer.value
        name = path.rsplit("\\", 1)[-1]
        return name or "unknown.exe"
    finally:
        kernel32.CloseHandle(handle)


def get_foreground_app() -> ForegroundApp:
    return resolve_app(get_foreground_process_name())

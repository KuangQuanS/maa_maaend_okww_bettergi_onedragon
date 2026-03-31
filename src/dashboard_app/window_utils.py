from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable


user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_CLOSE = 0x0010
SW_RESTORE = 9


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    pid: int
    rect: tuple[int, int, int, int]


EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def _window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def list_windows(visible_only: bool = True) -> list[WindowInfo]:
    windows: list[WindowInfo] = []

    @EnumWindowsProc
    def callback(hwnd: int, _: int) -> bool:
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        windows.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=_window_text(hwnd),
                class_name=_class_name(hwnd),
                pid=int(pid.value),
                rect=_rect(hwnd),
            )
        )
        return True

    user32.EnumWindows(callback, 0)
    return windows


def find_windows(
    *,
    title_contains: str = "",
    class_contains: str = "",
    title_regex: str = "",
    class_regex: str = "",
    pid: int | None = None,
    visible_only: bool = True,
) -> list[WindowInfo]:
    compiled_title = re.compile(title_regex, re.I) if title_regex else None
    compiled_class = re.compile(class_regex, re.I) if class_regex else None
    results: list[WindowInfo] = []
    for window in list_windows(visible_only=visible_only):
        if pid is not None and window.pid != pid:
            continue
        if title_contains and title_contains.lower() not in window.title.lower():
            continue
        if class_contains and class_contains.lower() not in window.class_name.lower():
            continue
        if compiled_title and not compiled_title.search(window.title):
            continue
        if compiled_class and not compiled_class.search(window.class_name):
            continue
        results.append(window)
    return results


def wait_for_window(*, timeout_sec: float, poll_interval: float = 0.5, predicate: Callable[[], list[WindowInfo]]) -> WindowInfo | None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        windows = predicate()
        if windows:
            return windows[0]
        time.sleep(poll_interval)
    return None


def close_windows(windows: list[WindowInfo]) -> None:
    for window in windows:
        user32.PostMessageW(window.hwnd, WM_CLOSE, 0, 0)


def close_matching_windows(
    *,
    title_contains: str = "",
    class_contains: str = "",
    title_regex: str = "",
    class_regex: str = "",
    pid: int | None = None,
) -> None:
    close_windows(
        find_windows(
            title_contains=title_contains,
            class_contains=class_contains,
            title_regex=title_regex,
            class_regex=class_regex,
            pid=pid,
            visible_only=False,
        )
    )


def restore_and_foreground(hwnd: int) -> bool:
    user32.ShowWindow(hwnd, SW_RESTORE)
    return bool(user32.SetForegroundWindow(hwnd))

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .window_utils import restore_and_foreground


user32 = ctypes.WinDLL("user32", use_last_error=True)

KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_KEYBOARD = 1


ULONG_PTR = wintypes.WPARAM


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTUNION),
    ]

VK_MAP = {
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "SHIFT": 0x10,
    "WIN": 0x5B,
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "TAB": 0x09,
}


def parse_hotkey(hotkey: str) -> list[int]:
    keys: list[int] = []
    for token in [item.strip().upper() for item in hotkey.split("+") if item.strip()]:
        if token in VK_MAP:
            keys.append(VK_MAP[token])
            continue
        if len(token) == 1:
            keys.append(ord(token))
            continue
        if token.startswith("F") and token[1:].isdigit():
            index = int(token[1:])
            if 1 <= index <= 24:
                keys.append(0x6F + index)
                continue
        raise ValueError(f"Unsupported hotkey token: {token}")
    return keys


def _send_keyboard(vk_code: int, flags: int = 0) -> None:
    packet = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0))
    sent = user32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def send_hotkey(hotkey: str, hwnd: int | None = None, settle_sec: float = 0.15, press_sec: float = 0.06) -> None:
    if not hotkey:
        return
    if hwnd:
        restore_and_foreground(hwnd)
        time.sleep(settle_sec)
    keys = parse_hotkey(hotkey)
    modifiers = keys[:-1]
    trigger = keys[-1]
    for code in modifiers:
        _send_keyboard(code, 0)
        time.sleep(0.02)
    _send_keyboard(trigger, 0)
    time.sleep(press_sec)
    _send_keyboard(trigger, KEYEVENTF_KEYUP)
    time.sleep(0.02)
    for code in reversed(modifiers):
        _send_keyboard(code, KEYEVENTF_KEYUP)
        time.sleep(0.02)


def click_screen(x: int, y: int, hwnd: int | None = None, settle_sec: float = 0.1) -> None:
    if hwnd:
        restore_and_foreground(hwnd)
        time.sleep(settle_sec)
    user32.SetCursorPos(x, y)
    time.sleep(0.02)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

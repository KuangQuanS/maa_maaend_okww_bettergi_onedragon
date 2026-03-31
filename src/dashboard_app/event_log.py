from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock


class EventLog:
    def __init__(self, path: Path, max_lines: int = 800):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._current_day = self._today_key()
        self._reset_if_new_day()
        self._load_existing(max_lines)

    def _today_key(self) -> str:
        return datetime.now().astimezone().date().isoformat()

    def _file_day(self) -> str | None:
        if not self.path.exists():
            return None
        stamp = datetime.fromtimestamp(self.path.stat().st_mtime).astimezone()
        return stamp.date().isoformat()

    def _reset_if_new_day(self) -> None:
        today = self._today_key()
        if self._file_day() == today:
            self._current_day = today
            return
        self._current_day = today
        self._lines.clear()
        self.path.write_text("", encoding="utf-8")

    def _load_existing(self, max_lines: int) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle.readlines()[-max_lines:]:
                self._lines.append(self._translate_line(line.rstrip()))

    def _translate_line(self, line: str) -> str:
        prefix, sep, message = line.partition("] ")
        if not sep:
            return line
        message = self._translate_message(message)
        return f"{prefix}] {message}"

    def _translate_message(self, message: str) -> str:
        app_names = {
            "maa": "MAA",
            "maaend": "MaaEnd",
            "bettergi": "BetterGI",
        }
        exact = {
            "Waiting for MAA to finish automatically.": "正在等待 MAA 自动完成。",
            "Watching MaaEnd logs and Endfield window state.": "正在监控 MaaEnd 日志和 Endfield 窗口状态。",
            "Parallel launch is disabled for BetterGI.": "BetterGI 未开启并行运行。",
            "BetterGI is already running.": "BetterGI 已在运行。",
            "Waiting 10s before sending BetterGI enable hotkey.": "发送 BetterGI 启动热键前等待 10 秒。",
            "Detected Genshin window after BetterGI enable hotkey.": "已在 BetterGI 启动热键后检测到原神窗口。",
            "Waiting 10s after detecting Genshin before sending daily task hotkey.": "检测到原神后再等待 10 秒，然后发送日常任务热键。",
            "Waiting 20s after detecting Genshin before sending daily task hotkey.": "检测到原神后再等待 20 秒，然后发送日常任务热键。",
        }
        if message in exact:
            return exact[message]

        patterns: list[tuple[str, callable]] = [
            (r"^Started app run for (\w+)\.$", lambda m: f"已启动程序任务：{app_names.get(m.group(1), m.group(1))}。"),
            (r"^Started workflow (.+)\.$", lambda m: f"已启动流程：{m.group(1)}。"),
            (r"^Stop requested for run ([0-9a-f]+)\.$", lambda m: f"已请求停止运行：{m.group(1)}。"),
            (r"^Closed stale app record for (\w+) after detached exit\.$", lambda m: f"{app_names.get(m.group(1), m.group(1))} 的脱机运行已结束，记录已同步。"),
            (r"^(MAA|MaaEnd|BetterGI) launched with PID (\d+)\.$", lambda m: f"{m.group(1)} 已启动，PID={m.group(2)}。"),
            (r"^Sent BetterGI enable hotkey: (.+)\.$", lambda m: f"已发送 BetterGI 启动热键：{m.group(1)}。"),
            (r"^Sent BetterGI daily task hotkey: (.+)\.$", lambda m: f"已发送 BetterGI 日常任务热键：{m.group(1)}。"),
            (r"^Sent MaaEnd fallback start hotkey: (.+)\.$", lambda m: f"已发送 MaaEnd 兜底启动热键：{m.group(1)}。"),
            (r"^Run for (\w+) failed: (.+)$", lambda m: f"{app_names.get(m.group(1), m.group(1))} 运行失败：{m.group(2)}"),
            (r"^Cleanup for (\w+) failed: (.+)$", lambda m: f"{app_names.get(m.group(1), m.group(1))} 收尾清理失败：{m.group(2)}"),
        ]
        for pattern, builder in patterns:
            matched = re.match(pattern, message)
            if matched:
                return builder(matched)
        return message

    def append(self, source: str, message: str, run_id: str = "", level: str = "INFO") -> None:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{stamp}][{level}][{source}]"
        if run_id:
            prefix = f"{prefix}[{run_id}]"
        line = f"{prefix} {message}"
        with self._lock:
            if self._current_day != self._today_key():
                self._reset_if_new_day()
            self._lines.append(line)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def lines(self, limit: int = 300) -> list[str]:
        with self._lock:
            return list(self._lines)[-limit:]

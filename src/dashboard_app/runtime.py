from __future__ import annotations

import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

from .event_log import EventLog
from .models import AppSpec, DashboardSettings, RunRecord, RunState
from .paths import AppPaths


@dataclass
class PollResult:
    terminal_state: RunState | None = None
    summary: str = ""
    result: str = ""


class FileTail:
    def __init__(self, path: Path, *, encodings: tuple[str, ...] = ("utf-8",)):
        self.path = path
        self.encodings = encodings or ("utf-8",)
        self.position = path.stat().st_size if path.exists() else 0

    def _decode(self, payload: bytes) -> str:
        for encoding in self.encodings:
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode(self.encodings[0], errors="ignore")

    def read_new(self) -> list[str]:
        if not self.path.exists():
            return []
        current_size = self.path.stat().st_size
        if current_size < self.position:
            self.position = 0
        with self.path.open("rb") as handle:
            handle.seek(self.position)
            payload = handle.read()
            self.position = handle.tell()
        return [line for line in self._decode(payload).splitlines() if line.strip()]


@dataclass
class ExecutionContext:
    record: RunRecord
    app_spec: AppSpec
    settings: DashboardSettings
    paths: AppPaths
    event_log: EventLog
    stop_event: Event
    process: subprocess.Popen[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_log_lines: deque[str] = field(default_factory=lambda: deque(maxlen=120))

    def log(self, message: str, level: str = "INFO") -> None:
        self.event_log.append(self.app_spec.id, message, self.record.run_id, level)

    def add_raw_lines(self, lines: list[str]) -> None:
        for line in lines:
            self.raw_log_lines.append(line)

    def raw_excerpt(self, limit: int = 40) -> str:
        return "\n".join(list(self.raw_log_lines)[-limit:])

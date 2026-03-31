from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from ..models import RunState
from ..process_utils import force_kill, popen_hidden, process_exists
from ..runtime import ExecutionContext, FileTail, PollResult
from ..window_utils import close_matching_windows, find_windows, wait_for_window
from .base import AdapterError, BaseAdapter


class BetterGIAdapter(BaseAdapter):
    CONFIG_PATH = Path(r"D:\BetterGI\User\config.json")
    LOG_DIR = Path(r"D:\BetterGI\log")
    TASK_PROGRESS_DIR = Path(r"D:\BetterGI\log\task_progress")
    EXECUTION_DIR = Path(r"D:\BetterGI\log\ExecutionRecords")
    CLI_START_ARG = "--startOneDragon"
    WINDOW_DETECT_TIMEOUT_SEC = 25
    COMPLETE_MARKERS = (
        "一条龙和配置组任务结束",
        "主窗体退出",
        "游戏已退出，BetterGI 自动停止截图器",
    )

    def _load_config(self) -> dict[str, Any]:
        if not self.CONFIG_PATH.exists():
            return {}
        with self.CONFIG_PATH.open("r", encoding="utf-8", errors="ignore") as handle:
            return json.load(handle)

    def _latest_file(self, folder: Path, pattern: str) -> Path | None:
        if not folder.exists():
            return None
        matches = sorted(folder.glob(pattern), key=lambda item: item.stat().st_mtime)
        return matches[-1] if matches else None

    def _tracked_windows(self) -> list:
        return find_windows(title_regex="BetterGI|更好的原神", visible_only=False)

    def _tracked_pids(self) -> set[int]:
        return {window.pid for window in self._tracked_windows()}

    def _pid_exists(self, pid: int) -> bool:
        return process_exists(pid)

    def validate(self, ctx: ExecutionContext) -> list[str]:
        warnings = super().validate(ctx)
        config = self._load_config()
        selected_flow = str(config.get("selectedOneDragonFlowConfigName", "")).strip() if isinstance(config, dict) else ""
        if not selected_flow:
            warnings.append("BetterGI 的 selectedOneDragonFlowConfigName 为空。")
        return warnings

    def launch(self, ctx: ExecutionContext) -> None:
        path = Path(ctx.app_spec.exe_path)
        if not path.exists():
            raise AdapterError(f"可执行文件不存在：{path}")

        existing_pids = self._tracked_pids()
        config = self._load_config()
        selected_flow = str(config.get("selectedOneDragonFlowConfigName", "")).strip() if isinstance(config, dict) else ""

        ctx.process = popen_hidden(
            [str(path), self.CLI_START_ARG],
            new_process_group=True,
            cwd=str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        ctx.metadata["launch_time"] = time.time()
        if selected_flow:
            ctx.metadata["selected_flow"] = selected_flow

        new_window = wait_for_window(
            timeout_sec=self.WINDOW_DETECT_TIMEOUT_SEC,
            predicate=lambda: [window for window in self._tracked_windows() if window.pid not in existing_pids],
        )
        if new_window is None:
            raise AdapterError(
                f"BetterGI 已启动，但在 {self.WINDOW_DETECT_TIMEOUT_SEC} 秒内没有检测到新的 BetterGI 窗口。"
            )

        ctx.metadata["main_window_hwnd"] = new_window.hwnd
        ctx.metadata["tracked_pid"] = new_window.pid
        latest_log = self._latest_file(self.LOG_DIR, "better-genshin-impact*.log")
        if latest_log is not None:
            ctx.metadata["main_log_tail"] = FileTail(latest_log, encodings=("utf-8", "gb18030"))
        ctx.log(
            f"BetterGI 已通过命令行 {self.CLI_START_ARG} 启动，启动器 PID={ctx.process.pid}，主窗口 PID={new_window.pid}。"
        )

    def start(self, ctx: ExecutionContext) -> None:
        ctx.metadata["command_started_at"] = time.time()
        ctx.log(f"BetterGI 已通过命令行 {self.CLI_START_ARG} 触发当前选中的一条龙配置。")

    def _progress_summary(self) -> str:
        latest = self._latest_file(self.TASK_PROGRESS_DIR, "*.json")
        if latest is None:
            return "BetterGI 正在运行。"
        try:
            with latest.open("r", encoding="utf-8", errors="ignore") as handle:
                payload = json.load(handle)
        except Exception:
            return "BetterGI 正在运行。"
        current = dict(payload.get("currentScriptGroupProjectInfo", {}))
        group = str(payload.get("currentScriptGroupName", ""))
        name = str(current.get("name", "")).strip()
        status = str(current.get("status", "")).strip()
        if group or name:
            return f"Group {group} | {name} | status={status or 'running'}"
        return "BetterGI 正在运行。"

    def _read_main_log(self, ctx: ExecutionContext) -> list[str]:
        tail = ctx.metadata.get("main_log_tail")
        if isinstance(tail, FileTail):
            lines = tail.read_new()
            if lines:
                ctx.add_raw_lines(lines[-20:])
            return lines
        return []

    def poll(self, ctx: ExecutionContext) -> PollResult:
        tracked_pid = int(ctx.metadata.get("tracked_pid", 0))
        if not tracked_pid:
            return PollResult(terminal_state=RunState.FAILED, summary="BetterGI 未找到可跟踪的主进程 PID。", result="launch_failed")

        lines = self._read_main_log(ctx)
        completion_seen = any(marker in line for line in lines for marker in self.COMPLETE_MARKERS)
        if completion_seen:
            return PollResult(
                terminal_state=RunState.DONE,
                summary="BetterGI 日志已确认一条龙完成并退出。",
                result="success",
            )
        summary = self._progress_summary()
        if lines:
            summary = lines[-1]

        if self._pid_exists(tracked_pid):
            return PollResult(summary=summary)

        started_at = float(ctx.metadata.get("command_started_at", 0.0) or 0.0)
        if started_at:
            elapsed = time.time() - started_at
            if elapsed < 15:
                return PollResult(
                    terminal_state=RunState.FAILED,
                    summary=f"BetterGI 在命令行启动后过早退出（{elapsed:.1f}s）。",
                    result="early_exit",
                )
            return PollResult(
                terminal_state=RunState.DONE,
                summary="BetterGI 已在任务结束后退出。",
                result="success",
            )

        return PollResult(
            terminal_state=RunState.FAILED,
            summary="BetterGI 在记录命令行启动前就已退出。",
            result="early_exit",
        )

    def stop(self, ctx: ExecutionContext) -> None:
        tracked_pid = int(ctx.metadata.get("tracked_pid", 0))
        if tracked_pid:
            close_matching_windows(pid=tracked_pid)
            time.sleep(2)
        if tracked_pid and self._pid_exists(tracked_pid):
            force_kill(tracked_pid)
        super().stop(ctx)

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from ..models import RunState
from ..process_utils import force_kill, image_exists, popen_hidden, process_exists
from ..runtime import ExecutionContext, FileTail, PollResult
from .base import AdapterError, BaseAdapter


class OkWWAdapter(BaseAdapter):
    CLI_ARGS = ["-t", "1", "-e"]
    ROOT_DIR = Path(r"D:\ok-ww")
    LAUNCHER_LOG_DIR = ROOT_DIR / "logs"
    SCRIPT_LOG_PATH = ROOT_DIR / "data" / "apps" / "ok-ww" / "working" / "logs" / "ok-script.log"
    GAME_IMAGE_NAME = "Client-Win64-Shipping.exe"
    CHILD_PID_PATTERN = re.compile(r"Command spawned pid=(\d+)")
    SCRIPT_PID_PATTERN = re.compile(r"pid=(\d+)")
    CHILD_DISCOVERY_TIMEOUT_SEC = 8.0
    CHILD_DISCOVERY_GRACE_SEC = 15.0
    SUCCESS_EXIT_GRACE_SEC = 20.0
    SUCCESS_MARKERS = (
        "Task completed",
        "Successfully Executed Task, Exiting Game and App!",
    )
    SHUTDOWN_MARKERS = (
        "TaskExecutor:Executor destroy",
        "MainWindow:Window closed exit_event.is not set False",
        "DeviceManager:stop_hwnd",
    )

    def _latest_file(self, folder: Path, pattern: str) -> Path | None:
        if not folder.exists():
            return None
        matches = sorted(folder.glob(pattern), key=lambda item: item.stat().st_mtime)
        return matches[-1] if matches else None

    def _setup_log_tails(self, ctx: ExecutionContext) -> None:
        launcher_log = self._latest_file(self.LAUNCHER_LOG_DIR, "app.*")
        if launcher_log is not None:
            launcher_tail = FileTail(launcher_log, encodings=("utf-8", "gb18030"))
            ctx.metadata["launcher_log_tail"] = launcher_tail
        script_tail = FileTail(self.SCRIPT_LOG_PATH, encodings=("utf-8", "gb18030"))
        ctx.metadata["script_log_tail"] = script_tail
        ctx.metadata["script_log_start_pos"] = script_tail.position

    def _read_tail(self, ctx: ExecutionContext, key: str) -> list[str]:
        tail = ctx.metadata.get(key)
        if not isinstance(tail, FileTail):
            return []
        lines = tail.read_new()
        if lines:
            ctx.add_raw_lines(lines[-20:])
        return lines

    def _extract_child_pid(self, ctx: ExecutionContext, lines: list[str], *, from_launcher: bool) -> int:
        existing = int(ctx.metadata.get("child_pid", 0) or 0)
        if existing:
            return existing

        pattern = self.CHILD_PID_PATTERN if from_launcher else self.SCRIPT_PID_PATTERN
        for line in lines:
            match = pattern.search(line)
            if not match:
                continue
            pid = int(match.group(1))
            if pid <= 0:
                continue
            ctx.metadata["child_pid"] = pid
            ctx.metadata["tracked_pid"] = pid
            ctx.log(f"OK-WW 实际任务进程已接管，PID={pid}。")
            return pid
        return 0

    def _read_text_since_start(self, ctx: ExecutionContext, path: Path, max_bytes: int = 65536) -> str:
        if not path.exists():
            return ""
        start_pos = int(ctx.metadata.get("script_log_start_pos", 0) or 0)
        try:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                seek_pos = max(start_pos, max(size - max_bytes, 0))
                handle.seek(seek_pos)
                payload = handle.read()
        except OSError:
            return ""
        for encoding in ("utf-8", "gb18030"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _mark_script_state(self, ctx: ExecutionContext, lines: list[str]) -> None:
        if not float(ctx.metadata.get("success_seen_at", 0.0) or 0.0):
            if any(marker in line for line in lines for marker in self.SUCCESS_MARKERS):
                ctx.metadata["success_seen_at"] = time.time()
        if not float(ctx.metadata.get("shutdown_seen_at", 0.0) or 0.0):
            if any(marker in line for line in lines for marker in self.SHUTDOWN_MARKERS):
                ctx.metadata["shutdown_seen_at"] = time.time()

    def _sync_script_state_from_file(self, ctx: ExecutionContext) -> None:
        excerpt = self._read_text_since_start(ctx, self.SCRIPT_LOG_PATH)
        if not excerpt:
            return
        if not float(ctx.metadata.get("success_seen_at", 0.0) or 0.0):
            if any(marker in excerpt for marker in self.SUCCESS_MARKERS):
                ctx.metadata["success_seen_at"] = time.time()
        if not float(ctx.metadata.get("shutdown_seen_at", 0.0) or 0.0):
            if any(marker in excerpt for marker in self.SHUTDOWN_MARKERS):
                ctx.metadata["shutdown_seen_at"] = time.time()

    def _refresh_logs(self, ctx: ExecutionContext) -> tuple[list[str], list[str]]:
        launcher_lines = self._read_tail(ctx, "launcher_log_tail")
        script_lines = self._read_tail(ctx, "script_log_tail")

        if launcher_lines:
            self._extract_child_pid(ctx, launcher_lines, from_launcher=True)
        if script_lines:
            self._extract_child_pid(ctx, script_lines, from_launcher=False)
            self._mark_script_state(ctx, script_lines)

        return launcher_lines, script_lines

    def _wait_for_child_pid(self, ctx: ExecutionContext) -> None:
        deadline = time.time() + self.CHILD_DISCOVERY_TIMEOUT_SEC
        while time.time() < deadline and not ctx.stop_event.is_set():
            self._refresh_logs(ctx)
            if int(ctx.metadata.get("child_pid", 0) or 0):
                return
            if ctx.process is not None and ctx.process.poll() is not None:
                break
            time.sleep(0.5)

    def _summarize(self, script_lines: list[str], launcher_lines: list[str], fallback: str) -> str:
        lines = script_lines or launcher_lines
        if not lines:
            return fallback
        last = lines[-1].strip()
        if any(marker in last for marker in self.SHUTDOWN_MARKERS):
            return "OK-WW 正在完成最后收尾。"
        if any(marker in last for marker in self.SUCCESS_MARKERS):
            return "OK-WW 已完成任务，正在退出游戏和程序。"
        if "waiting for game to start error" in last:
            return "OK-WW 正在等待鸣潮窗口接管。"
        if "TaskExecutor:start execute" in last:
            return "OK-WW 已进入自动化执行。"
        if "current task " in last:
            return last.split("current task ", 1)[-1].strip()
        return last[-120:]

    def _game_running(self) -> bool:
        return image_exists(self.GAME_IMAGE_NAME)

    def launch(self, ctx: ExecutionContext) -> None:
        path = Path(ctx.app_spec.exe_path)
        if not path.exists():
            raise AdapterError(f"可执行文件不存在：{path}")

        self._setup_log_tails(ctx)
        ctx.process = popen_hidden(
            [str(path), *self.CLI_ARGS],
            new_process_group=True,
            cwd=str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        ctx.metadata["launch_started_at"] = time.time()
        self._wait_for_child_pid(ctx)

        child_pid = int(ctx.metadata.get("child_pid", 0) or 0)
        if child_pid:
            ctx.log(
                f"OK-WW 已通过命令行 {' '.join(self.CLI_ARGS)} 启动，启动器 PID={ctx.process.pid}，任务 PID={child_pid}。"
            )
        else:
            ctx.log(f"OK-WW 已通过命令行 {' '.join(self.CLI_ARGS)} 启动，启动器 PID={ctx.process.pid}。")

    def start(self, ctx: ExecutionContext) -> None:
        ctx.metadata["command_started_at"] = time.time()
        ctx.log("OK-WW 已通过命令行触发任务。")

    def poll(self, ctx: ExecutionContext) -> PollResult:
        if ctx.process is None:
            return PollResult(
                terminal_state=RunState.FAILED,
                summary="OK-WW 未成功启动。",
                result="launch_failed",
            )

        launcher_lines, script_lines = self._refresh_logs(ctx)
        self._sync_script_state_from_file(ctx)

        launcher_pid = ctx.process.pid
        launcher_code = ctx.process.poll()
        child_pid = int(ctx.metadata.get("child_pid", 0) or 0)
        child_alive = bool(child_pid and process_exists(child_pid))
        launch_started_at = float(ctx.metadata.get("launch_started_at", 0.0) or 0.0)
        success_seen_at = float(ctx.metadata.get("success_seen_at", 0.0) or 0.0)
        shutdown_seen_at = float(ctx.metadata.get("shutdown_seen_at", 0.0) or 0.0)
        game_running = self._game_running()

        if shutdown_seen_at:
            return PollResult(
                terminal_state=RunState.DONE,
                summary="OK-WW 已完成任务并结束收尾。",
                result="success",
            )

        if success_seen_at and not child_alive and not game_running:
            return PollResult(
                terminal_state=RunState.DONE,
                summary="OK-WW 已完成任务并退出。",
                result="success",
            )

        if success_seen_at:
            if not game_running and (time.time() - success_seen_at) >= 2:
                return PollResult(
                    terminal_state=RunState.DONE,
                    summary="OK-WW 已完成任务，鸣潮已退出。",
                    result="success",
                )
            if not child_alive and (time.time() - success_seen_at) >= self.SUCCESS_EXIT_GRACE_SEC:
                return PollResult(
                    terminal_state=RunState.DONE,
                    summary="OK-WW 已完成任务并退出。",
                    result="success",
                )
            return PollResult(summary="OK-WW 已完成任务，等待游戏和程序收尾。")

        if child_alive:
            return PollResult(summary=self._summarize(script_lines, launcher_lines, "OK-WW 正在执行中。"))

        if child_pid:
            return PollResult(
                terminal_state=RunState.FAILED,
                summary="OK-WW 任务进程已退出，但未检测到完成标记。",
                result="exit_without_success",
            )

        if launcher_code is None or process_exists(launcher_pid):
            return PollResult(summary=self._summarize(script_lines, launcher_lines, "OK-WW 启动中，等待任务进程接管。"))

        if launch_started_at and (time.time() - launch_started_at) < self.CHILD_DISCOVERY_GRACE_SEC:
            return PollResult(summary="OK-WW 启动器已退出，等待实际任务进程接管。")

        return PollResult(
            terminal_state=RunState.FAILED,
            summary=f"OK-WW 启动器已退出，未检测到实际任务进程（退出码：{launcher_code}）。",
            result="launcher_exit",
        )

    def stop(self, ctx: ExecutionContext) -> None:
        child_pid = int(ctx.metadata.get("child_pid", 0) or 0)
        if child_pid and process_exists(child_pid):
            force_kill(child_pid)
        super().stop(ctx)

from __future__ import annotations

import ctypes
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from ..input_utils import send_hotkey
from ..models import RunState
from ..process_utils import image_exists, popen_hidden
from ..runtime import ExecutionContext, FileTail, PollResult
from ..window_utils import close_matching_windows, find_windows, wait_for_window
from .base import AdapterError, BaseAdapter


class MaaEndAdapter(BaseAdapter):
    DEFAULT_GAME_PATH = Path(r"D:\Hypergryph Launcher\games\Arknights Endfield\Endfield.exe")
    GAME_WAIT_TIMEOUT_SEC = 60
    GAME_POST_WINDOW_DELAY_SEC = 30
    HOTKEY_FALLBACK_DELAY_SEC = 30

    def _is_elevated(self) -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _root_dir(self, ctx: ExecutionContext) -> Path:
        return Path(ctx.app_spec.exe_path).parent

    def _config_path(self, ctx: ExecutionContext) -> Path:
        return self._root_dir(ctx) / "config" / "mxu-MaaEnd.json"

    def _debug_dir(self, ctx: ExecutionContext) -> Path:
        return self._root_dir(ctx) / "debug"

    def _load_config(self, ctx: ExecutionContext) -> dict[str, Any]:
        config_path = self._config_path(ctx)
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8", errors="ignore") as handle:
            return json.load(handle)

    def _find_nested(self, value: Any, key: str) -> Any | None:
        if isinstance(value, dict):
            if key in value:
                return value[key]
            for child in value.values():
                found = self._find_nested(child, key)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._find_nested(child, key)
                if found is not None:
                    return found
        return None

    def validate(self, ctx: ExecutionContext) -> list[str]:
        warnings = super().validate(ctx)
        config = self._load_config(ctx)
        game_path = self._game_path(ctx, config)
        if not game_path.exists():
            warnings.append(f"找不到终末地可执行文件：{game_path}")
        elif not self._is_elevated():
            warnings.append("启动终末地需要管理员权限，请以管理员身份运行面板。")
        if not config:
            warnings.append(f"找不到 MaaEnd 配置文件：{self._config_path(ctx)}")
            return warnings
        if not bool(self._find_nested(config, "autoRunOnLaunch")):
            warnings.append("MaaEnd 的 autoRunOnLaunch 未开启。")
        if not self._find_nested(config, "autoStartInstanceId"):
            warnings.append("MaaEnd 缺少 autoStartInstanceId。")
        return warnings

    def _game_path(self, ctx: ExecutionContext, config: dict[str, Any] | None = None) -> Path:
        config = config if config is not None else self._load_config(ctx)
        for key in ("connectedProgramPath", "program"):
            value = self._find_nested(config, key)
            if isinstance(value, str) and value.strip().lower().endswith("endfield.exe"):
                return Path(value)
        return self.DEFAULT_GAME_PATH

    def _latest_log(self, ctx: ExecutionContext, pattern: str) -> Path | None:
        matches = sorted(self._debug_dir(ctx).glob(pattern), key=lambda item: item.stat().st_mtime)
        return matches[-1] if matches else None

    def _target_windows(self) -> list:
        return find_windows(title_regex="Endfield", class_regex="UnityWndClass", visible_only=False)

    def _wait_after_window_detected(self, ctx: ExecutionContext) -> None:
        ctx.log(f"已检测到 Endfield 窗口，等待 {self.GAME_POST_WINDOW_DELAY_SEC} 秒后启动 MaaEnd。")
        deadline = time.time() + self.GAME_POST_WINDOW_DELAY_SEC
        while time.time() < deadline:
            if ctx.stop_event.is_set():
                raise AdapterError("任务在等待 Endfield 稳定时已取消。")
            time.sleep(0.5)

    def _game_process_running(self) -> bool:
        return image_exists("Endfield.exe")

    def _launch_game_and_wait(self, ctx: ExecutionContext) -> None:
        game_path = self._game_path(ctx)
        if self._target_windows():
            ctx.metadata["saw_target_window"] = True
            ctx.log("检测到终末地已在运行，跳过重复启动。")
            self._wait_after_window_detected(ctx)
            return
        if not game_path.exists():
            ctx.log(f"未找到终末地可执行文件：{game_path}，将直接启动 MaaEnd。", level="WARN")
            return

        if self._game_process_running():
            ctx.log("检测到 Endfield.exe 进程存在但没有窗口，仍尝试补发一次游戏启动。", level="WARN")

        try:
            game_process = popen_hidden(
                [str(game_path)],
                new_process_group=True,
                cwd=str(game_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            if getattr(exc, "winerror", None) == 740:
                raise AdapterError("启动终末地需要管理员权限，请以管理员身份运行面板。") from exc
            raise
        ctx.metadata["game_pid"] = game_process.pid
        ctx.log(
            f"终末地已触发启动，PID={game_process.pid}，等待窗口出现或 {self.GAME_WAIT_TIMEOUT_SEC} 秒超时。"
        )

        window = wait_for_window(
            timeout_sec=self.GAME_WAIT_TIMEOUT_SEC,
            predicate=self._target_windows,
        )
        if window is not None:
            ctx.metadata["saw_target_window"] = True
            self._wait_after_window_detected(ctx)
            return
        ctx.log(f"等待 Endfield 窗口超过 {self.GAME_WAIT_TIMEOUT_SEC} 秒，继续启动 MaaEnd。", level="WARN")

    def launch(self, ctx: ExecutionContext) -> None:
        self._launch_game_and_wait(ctx)
        ctx.process = self.launch_process(ctx)
        ctx.metadata["launch_time"] = time.time()
        ctx.metadata["last_log_update_at"] = time.time()
        ctx.metadata["task_activity_detected"] = False
        ctx.metadata["hotkey_sent"] = False
        ctx.metadata["monitor_invalid_seen"] = False
        ctx.metadata["getclientrect_errors"] = 0
        ctx.metadata["saw_target_window"] = bool(ctx.metadata.get("saw_target_window"))
        ctx.metadata["window_missing_since"] = None
        ctx.metadata["config"] = self._load_config(ctx)
        latest_web = self._latest_log(ctx, "mxu-web-*.log")
        latest_maa = self._latest_log(ctx, "maa.log")
        if latest_web:
            ctx.metadata["web_tail"] = FileTail(latest_web)
        if latest_maa:
            ctx.metadata["maa_tail"] = FileTail(latest_maa)
        ctx.log(f"MaaEnd 已启动，PID={ctx.process.pid}。")

    def start(self, ctx: ExecutionContext) -> None:
        ctx.log("正在监控 MaaEnd 日志和 Endfield 窗口状态。")

    def _read_logs(self, ctx: ExecutionContext) -> list[str]:
        collected: list[str] = []
        for key in ("web_tail", "maa_tail"):
            tail = ctx.metadata.get(key)
            if isinstance(tail, FileTail):
                lines = tail.read_new()
                if lines:
                    collected.extend(lines)
        if collected:
            ctx.metadata["last_log_update_at"] = time.time()
            ctx.add_raw_lines(collected[-20:])
        return collected

    def _maybe_send_start_hotkey(self, ctx: ExecutionContext) -> None:
        if ctx.metadata.get("hotkey_sent"):
            return
        if ctx.metadata.get("task_activity_detected"):
            return
        if time.time() - float(ctx.metadata.get("launch_time", time.time())) < self.HOTKEY_FALLBACK_DELAY_SEC:
            return
        hotkey = self._find_nested(ctx.metadata.get("config", {}), "startTasks")
        if not hotkey:
            return
        try:
            send_hotkey(str(hotkey))
        except Exception as exc:
            ctx.metadata["hotkey_sent"] = True
            ctx.log(f"MaaEnd 兜底启动热键发送失败：{hotkey}，已忽略本次兜底。错误：{exc}", level="WARN")
            return
        ctx.metadata["hotkey_sent"] = True
        ctx.log(f"已发送 MaaEnd 兜底启动热键：{hotkey}。")

    def poll(self, ctx: ExecutionContext) -> PollResult:
        if ctx.process is None:
            return PollResult(terminal_state=RunState.FAILED, summary="MaaEnd 未成功启动。", result="launch_failed")

        lines = self._read_logs(ctx)
        for line in lines:
            if "[Task]" in line or "调度器" in line or "[MAA]" in line:
                ctx.metadata["task_activity_detected"] = True
            if "Window no longer valid, stopping monitor" in line:
                ctx.metadata["monitor_invalid_seen"] = True
            if "GetClientRect failed" in line and "1400" in line:
                ctx.metadata["getclientrect_errors"] = int(ctx.metadata.get("getclientrect_errors", 0)) + 1

        self._maybe_send_start_hotkey(ctx)

        code = ctx.process.poll()
        if code is not None:
            return PollResult(terminal_state=RunState.DONE, summary=f"MaaEnd 已退出，退出码：{code}。", result="success")

        target_windows = find_windows(title_regex="Endfield", class_regex="UnityWndClass", visible_only=False)
        now = time.time()
        if target_windows:
            ctx.metadata["saw_target_window"] = True
            ctx.metadata["window_missing_since"] = None
        elif ctx.metadata.get("saw_target_window") and ctx.metadata.get("window_missing_since") is None:
            ctx.metadata["window_missing_since"] = now

        missing_since = ctx.metadata.get("window_missing_since")
        if missing_since:
            missing_for = now - float(missing_since)
            if missing_for >= 10 and (
                ctx.metadata.get("monitor_invalid_seen")
                or int(ctx.metadata.get("getclientrect_errors", 0)) >= 3
            ):
                return PollResult(
                    terminal_state=RunState.DONE,
                    summary="检测到 Endfield 窗口消失，且 MaaEnd 监控已失效，任务视为完成。",
                    result="success",
                )
            if now - float(ctx.metadata.get("last_log_update_at", now)) >= 20:
                return PollResult(
                    terminal_state=RunState.DONE,
                    summary="Endfield 窗口已关闭，且 MaaEnd 日志已静默，任务视为完成。",
                    result="success",
                )

        runtime = now - float(ctx.metadata.get("launch_time", now))
        if runtime >= ctx.app_spec.timeout_sec:
            return PollResult(terminal_state=RunState.FAILED, summary="MaaEnd 已超过最大运行时长。", result="timeout")

        if target_windows:
            return PollResult(summary="MaaEnd 正在运行，已附着 Endfield 窗口。")
        return PollResult(summary="MaaEnd 正在运行，等待 Endfield 窗口状态变化。")

    def cleanup(self, ctx: ExecutionContext) -> None:
        close_matching_windows(title_regex="Endfield", class_regex="UnityWndClass")
        time.sleep(5)
        if ctx.process is not None:
            close_matching_windows(pid=ctx.process.pid)
            try:
                ctx.process.wait(timeout=8)
            except Exception:
                self.stop(ctx)

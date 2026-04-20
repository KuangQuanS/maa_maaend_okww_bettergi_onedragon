from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import RunState
from ..process_utils import popen_hidden
from ..runtime import ExecutionContext, PollResult
from .base import AdapterError, BaseAdapter


class March7thAdapter(BaseAdapter):
    CLI_ARGS = ["main", "-e"]

    def launch(self, ctx: ExecutionContext) -> None:
        path = Path(ctx.app_spec.exe_path)
        if not path.exists():
            raise AdapterError(f"可执行文件不存在：{path}")

        ctx.process = popen_hidden(
            [str(path), *self.CLI_ARGS],
            new_process_group=True,
            cwd=str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        ctx.metadata["tracked_pid"] = ctx.process.pid
        ctx.log(
            f"March 7th Assistant 已通过命令行 {' '.join(self.CLI_ARGS)} 启动，PID={ctx.process.pid}。"
        )

    def start(self, ctx: ExecutionContext) -> None:
        ctx.log("March 7th Assistant 命令行任务已触发。")

    def poll(self, ctx: ExecutionContext) -> PollResult:
        if ctx.process is None:
            return PollResult(
                terminal_state=RunState.FAILED,
                summary="March 7th Assistant 未成功启动。",
                result="launch_failed",
            )

        code = ctx.process.poll()
        if code is None:
            return PollResult(summary="March 7th Assistant 正在运行。")

        if code == 0:
            return PollResult(
                terminal_state=RunState.DONE,
                summary="March 7th Assistant 已在任务结束后退出。",
                result="success",
            )

        return PollResult(
            terminal_state=RunState.FAILED,
            summary=f"March 7th Assistant 已退出，退出码：{code}。",
            result=f"exit_{code}",
        )

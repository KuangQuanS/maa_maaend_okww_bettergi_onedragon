from __future__ import annotations

from ..models import RunState
from ..runtime import ExecutionContext, PollResult
from .base import BaseAdapter


class MAAAdapter(BaseAdapter):
    def launch(self, ctx: ExecutionContext) -> None:
        ctx.process = self.launch_process(ctx)
        ctx.log(f"MAA 已启动，PID={ctx.process.pid}。")

    def start(self, ctx: ExecutionContext) -> None:
        ctx.log("MAA 属于长时任务，正在等待明日方舟自动化完成并随模拟器一起退出。")

    def poll(self, ctx: ExecutionContext) -> PollResult:
        if ctx.process is None:
            return PollResult(terminal_state=RunState.FAILED, summary="MAA 未成功启动。", result="launch_failed")
        code = ctx.process.poll()
        if code is None:
            return PollResult(summary="MAA 正在运行，等待明日方舟自动化和模拟器退出。")
        if code == 0:
            return PollResult(terminal_state=RunState.DONE, summary="MAA 已在自动化完成后正常退出。", result="success")
        return PollResult(
            terminal_state=RunState.FAILED,
            summary=f"MAA 已退出，退出码：{code}。",
            result="exit_nonzero",
        )

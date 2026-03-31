from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from ..process_utils import CREATE_NEW_PROCESS_GROUP, force_kill, popen_hidden
from ..runtime import ExecutionContext, PollResult


class AdapterError(RuntimeError):
    pass


class BaseAdapter(ABC):
    def validate(self, ctx: ExecutionContext) -> list[str]:
        warnings: list[str] = []
        path = Path(ctx.app_spec.exe_path)
        if not path.exists():
            warnings.append(f"找不到可执行文件：{path}")
        return warnings

    def launch_process(self, ctx: ExecutionContext) -> subprocess.Popen[str]:
        path = Path(ctx.app_spec.exe_path)
        if not path.exists():
            raise AdapterError(f"可执行文件不存在：{path}")
        return popen_hidden(
            [str(path)],
            new_process_group=True,
            cwd=str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    @abstractmethod
    def launch(self, ctx: ExecutionContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def start(self, ctx: ExecutionContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def poll(self, ctx: ExecutionContext) -> PollResult:
        raise NotImplementedError

    def stop(self, ctx: ExecutionContext) -> None:
        if ctx.process is None:
            return
        try:
            ctx.process.terminate()
            ctx.process.wait(timeout=5)
        except Exception:
            force_kill(ctx.process.pid)

    def cleanup(self, ctx: ExecutionContext) -> None:
        return

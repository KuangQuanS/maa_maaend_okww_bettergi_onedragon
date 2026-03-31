from __future__ import annotations

import subprocess
from typing import Any


CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def background_creationflags(*, new_process_group: bool = False, creationflags: int = 0) -> int:
    flags = creationflags | CREATE_NO_WINDOW
    if new_process_group:
        flags |= CREATE_NEW_PROCESS_GROUP
    return flags


def run_hidden(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("check", False)
    kwargs["creationflags"] = background_creationflags(creationflags=int(kwargs.get("creationflags", 0) or 0))
    return subprocess.run(args, **kwargs)


def popen_hidden(args: list[str], *, new_process_group: bool = False, **kwargs: Any) -> subprocess.Popen[str]:
    kwargs["creationflags"] = background_creationflags(
        new_process_group=new_process_group,
        creationflags=int(kwargs.get("creationflags", 0) or 0),
    )
    return subprocess.Popen(args, **kwargs)


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    result = run_hidden(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "").strip()
    return bool(output) and "No tasks are running" not in output and not output.startswith('"INFO:')


def image_exists(image_name: str) -> bool:
    if not image_name:
        return False
    result = run_hidden(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "").strip()
    return bool(output) and "No tasks are running" not in output and not output.startswith('"INFO:')


def force_kill(pid: int) -> None:
    if pid <= 0:
        return
    run_hidden(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

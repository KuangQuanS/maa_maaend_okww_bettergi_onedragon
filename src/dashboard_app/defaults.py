from __future__ import annotations

import re
from pathlib import Path

from .models import AppSpec, DashboardSettings, OCRActionSpec, RunState, WorkflowSpec


APP_PATHS = {
    "maa": Path(r"D:\maa\MAA.exe"),
    "maaend": Path(r"D:\maaend\MaaEnd.exe"),
    "bettergi": Path(r"D:\BetterGI\BetterGI.exe"),
    "okww": Path(r"D:\ok-ww\ok-ww.exe"),
}


def app_label(app_id: str) -> str:
    return {
        "maa": "MAA",
        "maaend": "MaaEnd",
        "bettergi": "BetterGI",
        "okww": "OK-WW",
    }.get(app_id, app_id)


def app_subtitle(app_id: str) -> str:
    return {
        "maa": "明日方舟自动化",
        "maaend": "MaaEnd 自动化",
        "bettergi": "BetterGI 一条龙",
        "okww": "OK-WW 命令行任务",
    }.get(app_id, app_id)


def state_label(state: str | RunState) -> str:
    value = state.value if isinstance(state, RunState) else str(state)
    return {
        RunState.IDLE.value: "空闲",
        RunState.VALIDATING.value: "校验中",
        RunState.LAUNCHING.value: "启动中",
        RunState.STARTING.value: "准备中",
        RunState.RUNNING.value: "运行中",
        RunState.CLEANUP.value: "收尾中",
        RunState.DONE.value: "已完成",
        RunState.FAILED.value: "失败",
        RunState.CANCELLED.value: "已取消",
    }.get(value, value)


def step_label(step: str) -> str:
    return {
        "validate": "校验",
        "launch": "启动程序",
        "start": "触发任务",
        "run": "运行任务",
        "stop": "停止任务",
        "cleanup": "收尾清理",
        "done": "完成",
        "workflow": "流程",
        "complete": "全部完成",
        "error": "异常",
        "resources": "资源检查",
    }.get(step, step)


def summary_label(summary: str) -> str:
    text = (summary or "").strip()
    if not text:
        return ""

    exact = {
        "Process exited while the dashboard was offline; exit code is unknown.": "进程已在面板离线期间退出，退出码未知。",
        "Detached process has exited; exit code is unknown.": "脱机运行的进程已经退出，退出码未知。",
        "Process is still running from a previous dashboard session; monitoring is detached.": "进程仍在运行，但上一次面板会话已经结束；当前状态为脱机监控。",
        "BetterGI is running.": "BetterGI 正在运行。",
        "Cleaning up BetterGI.": "正在清理 BetterGI。",
        "Cleaning up MAA.": "正在清理 MAA。",
        "Cleaning up MaaEnd.": "正在清理 MaaEnd。",
        "Validating executable and local config.": "正在校验可执行文件和本地配置。",
        "Dashboard shut down while this workflow was active; final state is unknown.": "面板关闭时该流程仍在运行，最终状态未知。",
        "Workflow cancelled.": "流程已取消。",
        "Run cancelled before launch.": "任务在启动前已取消。",
        "MAA did not launch.": "MAA 未成功启动。",
        "MAA exited normally after automation completed.": "MAA 已在自动化完成后正常退出。",
        "MAA is running. Waiting for Arknights automation and emulator shutdown.": "MAA 正在运行，等待明日方舟自动化和模拟器退出。",
        "MaaEnd did not launch.": "MaaEnd 未成功启动。",
        "MaaEnd exceeded max runtime.": "MaaEnd 已超过最大运行时长。",
        "MaaEnd is running with Endfield window attached.": "MaaEnd 正在运行，已附着 Endfield 窗口。",
        "MaaEnd is running and waiting for Endfield window state changes.": "MaaEnd 正在运行，等待 Endfield 窗口状态变化。",
        "Endfield window disappeared after MaaEnd monitor invalidation.": "检测到 Endfield 窗口消失，且 MaaEnd 监控已失效，任务视为完成。",
        "Endfield window is gone and MaaEnd logs are idle.": "Endfield 窗口已关闭，且 MaaEnd 日志已静默，任务视为完成。",
        "BetterGI has no tracked main PID.": "BetterGI 未找到可跟踪的主进程 PID。",
        "BetterGI main process exited after task run.": "BetterGI 已在任务结束后退出。",
        "BetterGI main process exited before command-line start was recorded.": "BetterGI 在记录命令行启动前就已退出。",
        "BetterGI 日志已确认一条龙完成并退出。": "BetterGI 日志已确认一条龙完成并退出。",
        "OK-WW 未成功启动。": "OK-WW 未成功启动。",
        "OK-WW 正在运行。": "OK-WW 正在运行。",
        "OK-WW 已在任务结束后退出。": "OK-WW 已在任务结束后退出。",
    }
    if text in exact:
        return exact[text]

    patterns: list[tuple[str, str]] = [
        (r"^Workflow step (\d+)/(\d+)$", r"流程步骤 \1/\2"),
        (r"^Running workflow (.+)\.$", r"正在执行流程 \1。"),
        (r"^Workflow (.+) finished\.$", r"流程 \1 已完成。"),
        (r"^Workflow references unknown app '(.+)'\.$", r"流程引用了未知程序“\1”。"),
        (r"^Workflow stopped at (.+)\.$", r"流程已停止在 \1。"),
        (r"^Running (.+) \((\d+)/(\d+)\)\.$", r"正在执行 \1（\2/\3）。"),
        (r"^Launching (.+)\.$", r"正在启动 \1。"),
        (r"^Starting (.+) automation\.$", r"正在准备 \1 自动化。"),
        (r"^(.+) was cancelled\.$", r"\1 已取消。"),
        (r"^Resource conflict: (.+)$", r"资源冲突：\1"),
        (r"^MAA exited with code (-?\d+)\.$", r"MAA 已退出，退出码：\1。"),
        (r"^MaaEnd exited with code (-?\d+)\.$", r"MaaEnd 已退出，退出码：\1。"),
        (r"^BetterGI main process exited too early after command-line start \((.+)\)\.$", r"BetterGI 在命令行启动后过早退出（\1）。"),
        (r"^OK-WW 已退出，退出码：(-?\d+)\。$", r"OK-WW 已退出，退出码：\1。"),
    ]
    for pattern, replacement in patterns:
        converted = re.sub(pattern, replacement, text)
        if converted != text:
            return converted

    replacements = (
        ("Launching ", "正在启动 "),
        ("Starting ", "正在准备 "),
        ("Running workflow ", "正在执行流程 "),
        ("Workflow ", "流程 "),
        (" is running.", " 正在运行。"),
        ("Workflow stopped at ", "流程已停止在 "),
    )
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
    return text


def default_app_specs() -> list[AppSpec]:
    return [
        AppSpec(
            id="maa",
            exe_path=str(APP_PATHS["maa"]) if APP_PATHS["maa"].exists() else "",
            start_strategy="launch_only",
            done_strategy="process_exit",
            timeout_sec=7200,
            start_resources=[],
            run_resources=["app:maa"],
            cleanup_template="none",
        ),
        AppSpec(
            id="maaend",
            exe_path=str(APP_PATHS["maaend"]) if APP_PATHS["maaend"].exists() else "",
            start_strategy="launch_only",
            done_strategy="log_and_window_idle",
            timeout_sec=10800,
            start_resources=[],
            run_resources=["foreground_automation", "window:endfield"],
            cleanup_template="close_game_then_app",
        ),
        AppSpec(
            id="bettergi",
            exe_path=str(APP_PATHS["bettergi"]) if APP_PATHS["bettergi"].exists() else "",
            start_strategy="command_line_start_one_dragon",
            done_strategy="process_exit",
            timeout_sec=10800,
            start_resources=[],
            run_resources=["foreground_automation", "window:bettergi"],
            cleanup_template="none",
        ),
        AppSpec(
            id="okww",
            exe_path=str(APP_PATHS["okww"]) if APP_PATHS["okww"].exists() else "",
            start_strategy="command_line_task_1",
            done_strategy="process_exit",
            timeout_sec=10800,
            start_resources=[],
            run_resources=["foreground_automation", "app:okww"],
            cleanup_template="none",
        ),
    ]


def default_workflows() -> list[WorkflowSpec]:
    return [
        WorkflowSpec(id="all_serial", name="四个一起执行", steps=["maa", "maaend", "bettergi", "okww"]),
        WorkflowSpec(id="maa_then_maaend", name="MAA -> MaaEnd", steps=["maa", "maaend"]),
        WorkflowSpec(id="maa_then_bettergi", name="MAA -> BetterGI", steps=["maa", "bettergi"]),
        WorkflowSpec(id="maa_then_okww", name="MAA -> OK-WW", steps=["maa", "okww"]),
    ]


def default_settings() -> DashboardSettings:
    return DashboardSettings(
        apps=default_app_specs(),
        parallel_overrides={"maa": True, "maaend": False, "bettergi": False, "okww": False},
        ocr_actions={"bettergi": OCRActionSpec(enabled=False)},
        sequence_order=["maa", "maaend", "bettergi", "okww"],
        sequence_enabled={"maa": True, "maaend": True, "bettergi": True, "okww": True},
    )

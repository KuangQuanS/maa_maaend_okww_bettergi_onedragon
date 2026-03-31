from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


def utcnow_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    LAUNCHING = "LAUNCHING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CLEANUP = "CLEANUP"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TargetType(str, Enum):
    APP = "app"
    WORKFLOW = "workflow"


@dataclass
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Rect":
        data = data or {}
        return cls(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class Offset:
    x: int = 0
    y: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Offset":
        data = data or {}
        return cls(x=int(data.get("x", 0)), y=int(data.get("y", 0)))

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass
class OCRActionSpec:
    action_type: str = "ocr_click_text"
    window_title: str = ""
    window_class: str = ""
    roi: Rect = field(default_factory=Rect)
    match_target: str = ""
    click_offset: Offset = field(default_factory=Offset)
    max_retry: int = 3
    template_path: str = ""
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OCRActionSpec":
        data = data or {}
        return cls(
            action_type=str(data.get("action_type", "ocr_click_text")),
            window_title=str(data.get("window_title", "")),
            window_class=str(data.get("window_class", "")),
            roi=Rect.from_dict(data.get("roi")),
            match_target=str(data.get("match_target", "")),
            click_offset=Offset.from_dict(data.get("click_offset")),
            max_retry=int(data.get("max_retry", 3)),
            template_path=str(data.get("template_path", "")),
            enabled=bool(data.get("enabled", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "window_title": self.window_title,
            "window_class": self.window_class,
            "roi": self.roi.to_dict(),
            "match_target": self.match_target,
            "click_offset": self.click_offset.to_dict(),
            "max_retry": self.max_retry,
            "template_path": self.template_path,
            "enabled": self.enabled,
        }


@dataclass
class AppSpec:
    id: str
    exe_path: str
    enabled: bool = True
    start_strategy: str = "launch_only"
    done_strategy: str = "process_exit"
    timeout_sec: int = 7200
    start_resources: list[str] = field(default_factory=list)
    run_resources: list[str] = field(default_factory=list)
    cleanup_template: str = "none"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSpec":
        return cls(
            id=str(data["id"]),
            exe_path=str(data.get("exe_path", "")),
            enabled=bool(data.get("enabled", True)),
            start_strategy=str(data.get("start_strategy", "launch_only")),
            done_strategy=str(data.get("done_strategy", "process_exit")),
            timeout_sec=int(data.get("timeout_sec", 7200)),
            start_resources=list(data.get("start_resources", [])),
            run_resources=list(data.get("run_resources", [])),
            cleanup_template=str(data.get("cleanup_template", "none")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "exe_path": self.exe_path,
            "enabled": self.enabled,
            "start_strategy": self.start_strategy,
            "done_strategy": self.done_strategy,
            "timeout_sec": self.timeout_sec,
            "start_resources": self.start_resources,
            "run_resources": self.run_resources,
            "cleanup_template": self.cleanup_template,
        }


@dataclass
class WorkflowSpec:
    id: str
    name: str
    steps: list[str] = field(default_factory=list)
    continue_on_failure: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowSpec":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            steps=[str(item) for item in data.get("steps", [])],
            continue_on_failure=bool(data.get("continue_on_failure", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "steps": self.steps,
            "continue_on_failure": self.continue_on_failure,
        }


@dataclass
class RunRecord:
    run_id: str
    target_type: TargetType
    target_id: str
    state: RunState
    step: str
    started_at: str
    ended_at: str = ""
    result: str = ""
    summary: str = ""

    @classmethod
    def create(cls, run_id: str, target_type: TargetType, target_id: str) -> "RunRecord":
        return cls(
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            state=RunState.IDLE,
            step="",
            started_at=utcnow_iso(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=str(data["run_id"]),
            target_type=TargetType(data["target_type"]),
            target_id=str(data.get("target_id", "")),
            state=RunState(data.get("state", RunState.IDLE.value)),
            step=str(data.get("step", "")),
            started_at=str(data.get("started_at", "")),
            ended_at=str(data.get("ended_at", "")),
            result=str(data.get("result", "")),
            summary=str(data.get("summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "state": self.state.value,
            "step": self.step,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result": self.result,
            "summary": self.summary,
        }


@dataclass
class DashboardSettings:
    version: int = 1
    apps: list[AppSpec] = field(default_factory=list)
    parallel_overrides: dict[str, bool] = field(default_factory=dict)
    ocr_actions: dict[str, OCRActionSpec] = field(default_factory=dict)
    sequence_order: list[str] = field(default_factory=list)
    sequence_enabled: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DashboardSettings":
        apps = [AppSpec.from_dict(item) for item in data.get("apps", [])]
        parallel_overrides = {str(key): bool(value) for key, value in dict(data.get("parallel_overrides", {})).items()}
        ocr_actions = {str(key): OCRActionSpec.from_dict(value) for key, value in dict(data.get("ocr_actions", {})).items()}
        sequence_order = [str(item) for item in data.get("sequence_order", [])]
        sequence_enabled = {str(key): bool(value) for key, value in dict(data.get("sequence_enabled", {})).items()}
        return cls(
            version=int(data.get("version", 1)),
            apps=apps,
            parallel_overrides=parallel_overrides,
            ocr_actions=ocr_actions,
            sequence_order=sequence_order,
            sequence_enabled=sequence_enabled,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "apps": [item.to_dict() for item in self.apps],
            "parallel_overrides": self.parallel_overrides,
            "ocr_actions": {key: value.to_dict() for key, value in self.ocr_actions.items()},
            "sequence_order": self.sequence_order,
            "sequence_enabled": self.sequence_enabled,
        }

    def get_app(self, app_id: str) -> AppSpec | None:
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

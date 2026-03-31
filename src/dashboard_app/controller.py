from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from dataclasses import dataclass
from threading import Event, RLock, Thread
from typing import Any

from .adapters import AdapterError, BetterGIAdapter, MAAAdapter, MaaEndAdapter, OkWWAdapter
from .defaults import app_label, default_app_specs, default_workflows, summary_label
from .event_log import EventLog
from .models import AppSpec, RunRecord, RunState, TargetType, WorkflowSpec, utcnow_iso
from .ocr_actions import OCRActionExecutor
from .paths import AppPaths
from .process_utils import image_exists, process_exists
from .runtime import ExecutionContext
from .storage import DashboardStorage


TRANSIENT_STATES = {
    RunState.VALIDATING,
    RunState.LAUNCHING,
    RunState.STARTING,
    RunState.RUNNING,
    RunState.CLEANUP,
}

TERMINAL_STATES = {
    RunState.DONE,
    RunState.FAILED,
    RunState.CANCELLED,
}


@dataclass
class ActiveRun:
    record: RunRecord
    thread: Thread
    stop_event: Event
    context: ExecutionContext | None = None


class ResourceManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._owners: dict[str, str] = {}

    def acquire(self, run_id: str, resources: list[str]) -> dict[str, str]:
        with self._lock:
            conflicts = {res: owner for res in resources if (owner := self._owners.get(res)) and owner != run_id}
            if conflicts:
                return conflicts
            for resource in resources:
                self._owners[resource] = run_id
            return {}

    def transition(self, run_id: str, resources: list[str]) -> dict[str, str]:
        with self._lock:
            owned = {res for res, owner in self._owners.items() if owner == run_id}
            conflicts = {res: owner for res in resources if (owner := self._owners.get(res)) and owner != run_id}
            if conflicts:
                return conflicts
            for resource in list(owned):
                self._owners.pop(resource, None)
            for resource in resources:
                self._owners[resource] = run_id
            return {}

    def release(self, run_id: str) -> None:
        with self._lock:
            for resource in [res for res, owner in self._owners.items() if owner == run_id]:
                self._owners.pop(resource, None)


class DashboardController:
    def __init__(self) -> None:
        self.paths = AppPaths.create()
        self.paths.ensure()
        self.storage = DashboardStorage(self.paths)
        self.settings = self.storage.load_settings()
        self._normalize_settings()
        self.workflows = self.storage.load_workflows()
        self._normalize_workflows()
        self.run_records = self.storage.load_run_records()
        self.event_log = EventLog(self.paths.event_log_file)
        self.ocr_executor = OCRActionExecutor()
        self.adapters = {
            "maa": MAAAdapter(),
            "maaend": MaaEndAdapter(),
            "bettergi": BetterGIAdapter(),
            "okww": OkWWAdapter(),
        }
        self.resource_manager = ResourceManager()
        self._lock = RLock()
        self._active_runs: dict[str, ActiveRun] = {}
        self._validation_warnings: dict[str, list[str]] = {}
        self._persisted_active_runs = self._load_persisted_active_runs()
        self._normalize_run_records()
        self._reconcile_orphaned_records()
        self.refresh_validations()

    def _normalize_settings(self) -> None:
        template_list = default_app_specs()
        templates = {app.id: app for app in template_list}
        changed = False
        existing_ids = {app.id for app in self.settings.apps}
        for template in template_list:
            if template.id not in existing_ids:
                self.settings.apps.append(copy.deepcopy(template))
                changed = True
        for app in self.settings.apps:
            template = templates.get(app.id)
            if template is None:
                continue
            if app.start_strategy != template.start_strategy:
                app.start_strategy = template.start_strategy
                changed = True
            if app.start_resources != template.start_resources:
                app.start_resources = list(template.start_resources)
                changed = True
            if app.run_resources != template.run_resources:
                app.run_resources = list(template.run_resources)
                changed = True
        expected_parallel = {"maa": True, "maaend": False, "bettergi": False, "okww": False}
        for app_id, enabled in expected_parallel.items():
            if self.settings.parallel_overrides.get(app_id) != enabled:
                self.settings.parallel_overrides[app_id] = enabled
                changed = True
        app_ids = [app.id for app in self.settings.apps]
        normalized_order: list[str] = []
        for app_id in self.settings.sequence_order:
            if app_id in app_ids and app_id not in normalized_order:
                normalized_order.append(app_id)
        for app_id in app_ids:
            if app_id not in normalized_order:
                normalized_order.append(app_id)
        if self.settings.sequence_order != normalized_order:
            self.settings.sequence_order = normalized_order
            changed = True
        normalized_enabled = {app_id: bool(self.settings.sequence_enabled.get(app_id, True)) for app_id in normalized_order}
        if self.settings.sequence_enabled != normalized_enabled:
            self.settings.sequence_enabled = normalized_enabled
            changed = True
        if changed:
            self.storage.save_settings(self.settings)

    def _normalize_workflows(self) -> None:
        template_list = default_workflows()
        templates = {workflow.id: workflow for workflow in template_list}
        obsolete_ids = {"maa_only", "maaend_only", "bettergi_only", "okww_only"}
        filtered_workflows = [workflow for workflow in self.workflows if workflow.id not in obsolete_ids]
        changed = len(filtered_workflows) != len(self.workflows)
        if changed:
            self.workflows = filtered_workflows
        existing_ids = {workflow.id for workflow in self.workflows}
        for workflow in self.workflows:
            template = templates.get(workflow.id)
            if template is None:
                continue
            if workflow.name != template.name:
                workflow.name = template.name
                changed = True
            if workflow.steps != template.steps:
                workflow.steps = list(template.steps)
                changed = True
            if workflow.continue_on_failure != template.continue_on_failure:
                workflow.continue_on_failure = template.continue_on_failure
                changed = True
        for template in templates.values():
            if template.id not in existing_ids:
                self.workflows.append(copy.deepcopy(template))
                changed = True
        order_map = {template.id: index for index, template in enumerate(template_list)}
        reordered = sorted(
            self.workflows,
            key=lambda workflow: (order_map.get(workflow.id, len(order_map)), workflow.name),
        )
        if [workflow.id for workflow in reordered] != [workflow.id for workflow in self.workflows]:
            self.workflows = reordered
            changed = True
        if changed:
            self.storage.save_workflows(self.workflows)

    def _normalize_run_records(self) -> None:
        changed = False
        for record in self.run_records:
            localized = summary_label(record.summary)
            if localized and localized != record.summary:
                record.summary = localized
                changed = True
        if changed:
            self.storage.save_run_records(self.run_records)

    def _load_persisted_active_runs(self) -> dict[str, dict[str, Any]]:
        if not self.paths.active_runs_file.exists():
            return {}
        try:
            with self.paths.active_runs_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {str(key): dict(value) for key, value in data.items()}
        except Exception:
            pass
        return {}

    def _save_persisted_active_runs(self) -> None:
        with self.paths.active_runs_file.open("w", encoding="utf-8") as handle:
            json.dump(self._persisted_active_runs, handle, ensure_ascii=False, indent=2)

    def _persist_active_run(self, record: RunRecord, *, pid: int | None = None) -> None:
        with self._lock:
            payload = self._persisted_active_runs.get(record.run_id, {})
            payload.update(
                {
                    "run_id": record.run_id,
                    "target_type": record.target_type.value,
                    "target_id": record.target_id,
                    "state": record.state.value,
                    "started_at": record.started_at,
                }
            )
            if pid is not None:
                payload["pid"] = pid
            self._persisted_active_runs[record.run_id] = payload
            self._save_persisted_active_runs()

    def _remove_persisted_run(self, run_id: str) -> None:
        with self._lock:
            if run_id in self._persisted_active_runs:
                self._persisted_active_runs.pop(run_id, None)
                self._save_persisted_active_runs()

    def _process_exists(self, pid: int) -> bool:
        return process_exists(pid)

    def _app_process_running(self, app_id: str) -> bool:
        app = self.settings.get_app(app_id)
        if app is None or not app.exe_path:
            return False
        image_name = app.exe_path.split("\\")[-1]
        return image_exists(image_name)

    def _reconcile_orphaned_app_record(self, record: RunRecord, payload: dict[str, Any] | None) -> bool:
        pid = int(payload.get("pid", 0)) if payload else 0
        is_running = self._process_exists(pid) if pid else self._app_process_running(record.target_id)
        if is_running:
            record.state = RunState.RUNNING
            record.step = "run"
            record.result = "detached"
            record.summary = "进程仍在运行，但上一次面板会话已经结束；当前状态为脱机监控。"
            record.ended_at = ""
            self.event_log.append("controller", f"已恢复 {record.target_id} 的脱机运行记录。", record.run_id, level="WARN")
            return True
        record.state = RunState.DONE
        record.step = "done"
        record.result = "detached_exit"
        record.summary = "进程已在面板离线期间退出，退出码未知。"
        record.ended_at = utcnow_iso()
        self.event_log.append("controller", f"{record.target_id} 的脱机运行记录已回填为退出完成。", record.run_id, level="WARN")
        return True

    def _reconcile_orphaned_records(self) -> None:
        changed = False
        for record in self.run_records:
            if record.state not in TRANSIENT_STATES:
                continue
            payload = self._persisted_active_runs.get(record.run_id)
            if record.target_type == TargetType.APP:
                changed = self._reconcile_orphaned_app_record(record, payload) or changed
            else:
                record.state = RunState.FAILED
                record.step = record.step or "workflow"
                record.result = "orphaned"
                record.summary = "面板关闭时该流程仍在运行，最终状态未知。"
                record.ended_at = utcnow_iso()
                self.event_log.append("controller", f"流程 {record.target_id} 在面板关闭后已完成脱机回填。", record.run_id, level="WARN")
                changed = True
        self._persisted_active_runs = {}
        self._save_persisted_active_runs()
        if changed:
            self._persist_records()

    def _refresh_detached_runs(self) -> None:
        changed = False
        active_run_ids = set(self._active_runs)
        for record in self.run_records:
            if record.target_type != TargetType.APP or record.state != RunState.RUNNING:
                continue
            if record.run_id in active_run_ids:
                continue
            if self._app_process_running(record.target_id):
                if record.result != "detached":
                    record.step = "run"
                    record.result = "detached"
                    record.summary = "进程仍在运行，但当前面板没有附着到这个运行实例；已切换为脱机监控。"
                    record.ended_at = ""
                    self.event_log.append("controller", f"{record.target_id} 仍在运行，已转为脱机监控状态。", record.run_id, level="WARN")
                    changed = True
                continue
            record.state = RunState.DONE
            record.step = "done"
            record.result = "detached_exit"
            record.summary = "进程已结束，退出发生在面板未附着期间，退出码未知。"
            record.ended_at = utcnow_iso()
            self.event_log.append("controller", f"{record.target_id} 的脱机运行已结束，记录已同步。", record.run_id, level="WARN")
            changed = True
        if changed:
            self._persist_records()

    def refresh_validations(self) -> None:
        warnings: dict[str, list[str]] = {}
        for app in self.settings.apps:
            dummy = RunRecord.create(f"validate-{app.id}", TargetType.APP, app.id)
            ctx = ExecutionContext(
                record=dummy,
                app_spec=app,
                settings=self.settings,
                paths=self.paths,
                event_log=self.event_log,
                stop_event=Event(),
            )
            ctx.metadata["ocr_executor"] = self.ocr_executor
            warnings[app.id] = self.adapters[app.id].validate(ctx)
        with self._lock:
            self._validation_warnings = warnings

    def set_app_path(self, app_id: str, path: str) -> None:
        with self._lock:
            app = self.settings.get_app(app_id)
            if app is None:
                return
            app.exe_path = path
            self.storage.save_settings(self.settings)
        self.refresh_validations()
        self.event_log.append("controller", f"已更新 {app_id} 的程序路径：{path}")

    def set_parallel_override(self, app_id: str, enabled: bool) -> None:
        with self._lock:
            self.settings.parallel_overrides[app_id] = enabled
            self.storage.save_settings(self.settings)
        self.event_log.append("controller", f"{app_id} 的并行开关已更新为：{enabled}。")

    def update_sequence(self, order: list[str], enabled: dict[str, bool]) -> None:
        valid_ids = [app.id for app in self.settings.apps]
        normalized_order: list[str] = []
        for app_id in order:
            if app_id in valid_ids and app_id not in normalized_order:
                normalized_order.append(app_id)
        for app_id in valid_ids:
            if app_id not in normalized_order:
                normalized_order.append(app_id)
        normalized_enabled = {
            app_id: bool(enabled.get(app_id, self.settings.sequence_enabled.get(app_id, True)))
            for app_id in normalized_order
        }
        with self._lock:
            if self.settings.sequence_order == normalized_order and self.settings.sequence_enabled == normalized_enabled:
                return
            self.settings.sequence_order = normalized_order
            self.settings.sequence_enabled = normalized_enabled
            self.storage.save_settings(self.settings)
        self.event_log.append("controller", "已更新顺序执行配置。")

    def set_ocr_action(self, app_id: str, action) -> None:
        with self._lock:
            self.settings.ocr_actions[app_id] = action
            self.storage.save_settings(self.settings)
        self.refresh_validations()
        self.event_log.append("controller", f"已更新 {app_id} 的 OCR 兜底配置。")

    def _find_workflow(self, workflow_id: str) -> WorkflowSpec | None:
        for workflow in self.workflows:
            if workflow.id == workflow_id:
                return workflow
        return None

    def _sequence_steps(self) -> list[str]:
        return [app_id for app_id in self.settings.sequence_order if self.settings.sequence_enabled.get(app_id, False)]

    def _sequence_name(self, steps: list[str] | None = None) -> str:
        sequence = steps if steps is not None else self._sequence_steps()
        if not sequence:
            return "当前顺序"
        return " -> ".join(app_label(app_id) for app_id in sequence)

    def _latest_sequence_record(self) -> RunRecord | None:
        for record in reversed(self.run_records):
            if record.target_type == TargetType.WORKFLOW and record.target_id == "custom_sequence":
                return record
        return None

    def _remember_record(self, record: RunRecord) -> None:
        with self._lock:
            self.run_records.append(record)
            self.run_records = self.run_records[-200:]
            self.storage.save_run_records(self.run_records)

    def _persist_records(self) -> None:
        with self._lock:
            self.storage.save_run_records(self.run_records)

    def _set_record_state(self, record: RunRecord, state: RunState, *, step: str | None = None, summary: str | None = None, result: str | None = None) -> None:
        with self._lock:
            record.state = state
            if step is not None:
                record.step = step
            if summary is not None:
                record.summary = summary
            if result is not None:
                record.result = result
            if state in {RunState.DONE, RunState.FAILED, RunState.CANCELLED}:
                record.ended_at = utcnow_iso()
            self.storage.save_run_records(self.run_records)

    def _register_active(self, handle: ActiveRun) -> None:
        with self._lock:
            self._active_runs[handle.record.run_id] = handle
        self._persist_active_run(handle.record)

    def _unregister_active(self, run_id: str) -> None:
        with self._lock:
            self._active_runs.pop(run_id, None)
        self._remove_persisted_run(run_id)

    def _latest_app_record(self, app_id: str) -> RunRecord | None:
        for record in reversed(self.run_records):
            if record.target_type == TargetType.APP and record.target_id == app_id:
                return record
        return None

    def _latest_workflow_record(self, workflow_id: str) -> RunRecord | None:
        for record in reversed(self.run_records):
            if record.target_type == TargetType.WORKFLOW and record.target_id == workflow_id:
                return record
        return None

    def _active_app_handle(self, app_id: str) -> ActiveRun | None:
        for handle in self._active_runs.values():
            if handle.record.target_type == TargetType.APP and handle.record.target_id == app_id:
                return handle
        return None

    def _any_workflow_active(self) -> bool:
        return any(handle.record.target_type == TargetType.WORKFLOW for handle in self._active_runs.values())

    def _allows_parallel_pair(self, app_id: str, other_app: str) -> bool:
        if app_id == other_app:
            return False
        if "maa" in {app_id, other_app}:
            return self.settings.parallel_overrides.get("maa", True)
        return False

    def _can_start_manual_app(self, app_id: str) -> str | None:
        if self._any_workflow_active():
            return "当前已有流程在运行。"
        if self._active_app_handle(app_id) is not None:
            return f"{app_label(app_id)} 已在运行。"
        active_apps = [handle.record.target_id for handle in self._active_runs.values() if handle.record.target_type == TargetType.APP]
        for other_app in active_apps:
            if not self._allows_parallel_pair(app_id, other_app):
                return f"{app_label(app_id)} 不能与 {app_label(other_app)} 同时运行。"
        return None

    def start_app(self, app_id: str) -> str | None:
        app = self.settings.get_app(app_id)
        if app is None:
            self.event_log.append("controller", f"未知程序：{app_id}", level="ERROR")
            return None
        block_reason = self._can_start_manual_app(app_id)
        if block_reason:
            self.event_log.append("controller", block_reason, level="WARN")
            return None
        record = RunRecord.create(uuid.uuid4().hex[:8], TargetType.APP, app_id)
        self._remember_record(record)
        stop_event = Event()
        thread = Thread(target=self._app_run_worker, args=(record, copy.deepcopy(app), stop_event), daemon=True)
        handle = ActiveRun(record=record, thread=thread, stop_event=stop_event)
        self._register_active(handle)
        thread.start()
        self.event_log.append("controller", f"已启动程序任务：{app_label(app_id)}。", record.run_id)
        return record.run_id

    def start_workflow(self, workflow_id: str) -> str | None:
        workflow = self._find_workflow(workflow_id)
        if workflow is None:
            self.event_log.append("controller", f"未知流程：{workflow_id}", level="ERROR")
            return None
        if self._active_runs:
            self.event_log.append("controller", "当前已有任务在运行，不能同时启动新流程。", level="WARN")
            return None
        record = RunRecord.create(uuid.uuid4().hex[:8], TargetType.WORKFLOW, workflow_id)
        self._remember_record(record)
        stop_event = Event()
        thread = Thread(target=self._workflow_run_worker, args=(record, workflow, stop_event), daemon=True)
        handle = ActiveRun(record=record, thread=thread, stop_event=stop_event)
        self._register_active(handle)
        thread.start()
        self.event_log.append("controller", f"已启动流程：{workflow.name}。", record.run_id)
        return record.run_id

    def start_sequence(self) -> str | None:
        if self._active_runs:
            self.event_log.append("controller", "当前已有任务在运行，不能同时启动新顺序。", level="WARN")
            return None
        steps = self._sequence_steps()
        if not steps:
            self.event_log.append("controller", "当前顺序没有勾选任何程序。", level="WARN")
            return None
        workflow = WorkflowSpec(id="custom_sequence", name=self._sequence_name(steps), steps=steps, continue_on_failure=False)
        record = RunRecord.create(uuid.uuid4().hex[:8], TargetType.WORKFLOW, workflow.id)
        self._remember_record(record)
        stop_event = Event()
        thread = Thread(target=self._workflow_run_worker, args=(record, workflow, stop_event), daemon=True)
        handle = ActiveRun(record=record, thread=thread, stop_event=stop_event)
        self._register_active(handle)
        thread.start()
        self.event_log.append("controller", f"已启动顺序：{workflow.name}。", record.run_id)
        return record.run_id

    def stop_run(self, run_id: str) -> None:
        handle = self._active_runs.get(run_id)
        if handle is None:
            return
        handle.stop_event.set()
        self.event_log.append("controller", f"已请求停止运行：{run_id}。")

    def stop_app(self, app_id: str) -> None:
        handle = self._active_app_handle(app_id)
        if handle is not None:
            self.stop_run(handle.record.run_id)

    def emergency_stop(self) -> None:
        for handle in list(self._active_runs.values()):
            handle.stop_event.set()
        self.event_log.append("controller", "已请求紧急停止所有运行中的任务。", level="WARN")

    def _workflow_step_can_overlap(self, workflow: WorkflowSpec, step_index: int, app_id: str) -> bool:
        if not self.settings.parallel_overrides.get(app_id, False):
            return False
        remaining_steps = workflow.steps[step_index + 1 :]
        if not remaining_steps:
            return False
        return all(self._allows_parallel_pair(app_id, other_app) for other_app in remaining_steps)

    def _start_workflow_child(self, app_spec: AppSpec, stop_event: Event, summary: str) -> ActiveRun:
        child_record = RunRecord.create(uuid.uuid4().hex[:8], TargetType.APP, app_spec.id)
        child_record.summary = summary
        self._remember_record(child_record)
        thread = Thread(target=self._app_run_worker, args=(child_record, copy.deepcopy(app_spec), stop_event), daemon=True)
        handle = ActiveRun(record=child_record, thread=thread, stop_event=stop_event)
        self._register_active(handle)
        thread.start()
        return handle

    def _wait_for_child_running(self, handle: ActiveRun, stop_event: Event) -> RunState:
        while True:
            state = handle.record.state
            if state in TERMINAL_STATES or state == RunState.RUNNING:
                return state
            if stop_event.is_set() and state == RunState.IDLE:
                return RunState.CANCELLED
            time.sleep(0.5)

    def _wait_for_parallel_children(self, handles: list[ActiveRun]) -> RunRecord | None:
        pending = list(handles)
        while pending:
            for handle in list(pending):
                state = handle.record.state
                if state not in TERMINAL_STATES:
                    continue
                pending.remove(handle)
                if state != RunState.DONE:
                    return handle.record
            if pending:
                time.sleep(1)
        return None

    def _parallel_children_failure(self, handles: list[ActiveRun]) -> RunRecord | None:
        remaining: list[ActiveRun] = []
        for handle in handles:
            state = handle.record.state
            if state == RunState.DONE:
                continue
            if state in {RunState.FAILED, RunState.CANCELLED}:
                return handle.record
            remaining.append(handle)
        handles[:] = remaining
        return None

    def _app_run_worker(self, record: RunRecord, app_spec: AppSpec, stop_event: Event) -> None:
        try:
            self._execute_app_run(record, app_spec, stop_event)
        finally:
            self._unregister_active(record.run_id)

    def _workflow_run_worker(self, record: RunRecord, workflow: WorkflowSpec, stop_event: Event) -> None:
        self._set_record_state(record, RunState.RUNNING, step="workflow", summary=f"正在执行流程 {workflow.name}。")
        parallel_children: list[ActiveRun] = []
        try:
            for step_index, app_id in enumerate(workflow.steps, start=1):
                if stop_event.is_set():
                    self._set_record_state(record, RunState.CANCELLED, step=app_id, summary="流程已取消。", result="cancelled")
                    return
                app_spec = self.settings.get_app(app_id)
                if app_spec is None:
                    self._set_record_state(record, RunState.FAILED, step=app_id, summary=f"流程引用了未知程序“{app_id}”。", result="invalid_workflow")
                    return
                step_summary = f"流程步骤 {step_index}/{len(workflow.steps)}"
                if self._workflow_step_can_overlap(workflow, step_index - 1, app_id):
                    self._set_record_state(
                        record,
                        RunState.RUNNING,
                        step=app_id,
                        summary=f"正在启动 {app_label(app_id)}（{step_index}/{len(workflow.steps)}），进入运行后自动继续下一步。",
                    )
                    child_handle = self._start_workflow_child(app_spec, stop_event, step_summary)
                    started_state = self._wait_for_child_running(child_handle, stop_event)
                    if started_state == RunState.RUNNING:
                        parallel_children.append(child_handle)
                        self._set_record_state(
                            record,
                            RunState.RUNNING,
                            step=app_id,
                            summary=f"{app_label(app_id)} 已进入运行，自动继续下一步。",
                        )
                        continue
                    child_record = child_handle.record
                else:
                    child_record = RunRecord.create(uuid.uuid4().hex[:8], TargetType.APP, app_id)
                    child_record.summary = step_summary
                    self._remember_record(child_record)
                    child_handle = ActiveRun(record=child_record, thread=threading.current_thread(), stop_event=stop_event)
                    self._register_active(child_handle)
                    try:
                        self._set_record_state(record, RunState.RUNNING, step=app_id, summary=f"正在执行 {app_label(app_id)}（{step_index}/{len(workflow.steps)}）。")
                        self._execute_app_run(child_record, copy.deepcopy(app_spec), stop_event)
                    finally:
                        self._unregister_active(child_record.run_id)
                if child_record.state != RunState.DONE:
                    stop_event.set()
                    workflow_state = RunState.CANCELLED if child_record.state == RunState.CANCELLED else RunState.FAILED
                    self._set_record_state(record, workflow_state, step=app_id, summary=f"流程已停止在 {app_label(app_id)}。", result=child_record.result or workflow_state.value.lower())
                    return
                failed_parallel = self._parallel_children_failure(parallel_children)
                if failed_parallel is not None:
                    stop_event.set()
                    workflow_state = RunState.CANCELLED if failed_parallel.state == RunState.CANCELLED else RunState.FAILED
                    self._set_record_state(
                        record,
                        workflow_state,
                        step=failed_parallel.target_id,
                        summary=f"流程已停止在 {app_label(failed_parallel.target_id)}。",
                        result=failed_parallel.result or workflow_state.value.lower(),
                    )
                    return
            failed_parallel = self._wait_for_parallel_children(parallel_children)
            if failed_parallel is not None:
                workflow_state = RunState.CANCELLED if failed_parallel.state == RunState.CANCELLED else RunState.FAILED
                self._set_record_state(
                    record,
                    workflow_state,
                    step=failed_parallel.target_id,
                    summary=f"流程已停止在 {app_label(failed_parallel.target_id)}。",
                    result=failed_parallel.result or workflow_state.value.lower(),
                )
                return
            self._set_record_state(record, RunState.DONE, step="complete", summary=f"流程 {workflow.name} 已完成。", result="success")
        except Exception as exc:
            self.event_log.append("controller", f"流程执行异常：{exc}", record.run_id, level="ERROR")
            self._set_record_state(record, RunState.FAILED, step=record.step, summary=str(exc), result="exception")
        finally:
            self._unregister_active(record.run_id)

    def _execute_app_run(self, record: RunRecord, app_spec: AppSpec, stop_event: Event) -> None:
        adapter = self.adapters[app_spec.id]
        ctx = ExecutionContext(
            record=record,
            app_spec=app_spec,
            settings=self.settings,
            paths=self.paths,
            event_log=self.event_log,
            stop_event=stop_event,
        )
        ctx.metadata["ocr_executor"] = self.ocr_executor
        active = self._active_runs.get(record.run_id)
        if active is not None:
            active.context = ctx

        warnings = adapter.validate(ctx)
        for warning in warnings:
            ctx.log(warning, level="WARN")
        self._set_record_state(record, RunState.VALIDATING, step="validate", summary="正在校验可执行文件和本地配置。")
        if stop_event.is_set():
            self._set_record_state(record, RunState.CANCELLED, step="validate", summary="任务在启动前已取消。", result="cancelled")
            return

        initial_resources = app_spec.start_resources or app_spec.run_resources
        conflicts = self.resource_manager.acquire(record.run_id, initial_resources)
        if conflicts:
            self._set_record_state(record, RunState.FAILED, step="resources", summary=f"资源冲突：{', '.join(sorted(conflicts))}", result="resource_conflict")
            return

        try:
            self._set_record_state(record, RunState.LAUNCHING, step="launch", summary=f"正在启动 {app_label(app_spec.id)}。")
            adapter.launch(ctx)
            tracked_pid = int(ctx.metadata.get("tracked_pid", 0) or 0)
            persisted_pid = 0
            if tracked_pid:
                self._persist_active_run(record, pid=tracked_pid)
                persisted_pid = tracked_pid
            elif ctx.process is not None:
                self._persist_active_run(record, pid=ctx.process.pid)
                persisted_pid = ctx.process.pid
            if stop_event.is_set():
                raise AdapterError("任务在启动阶段已取消。")
            self._set_record_state(record, RunState.STARTING, step="start", summary=f"正在准备 {app_label(app_spec.id)} 自动化。")
            adapter.start(ctx)
            conflicts = self.resource_manager.transition(record.run_id, app_spec.run_resources)
            if conflicts:
                raise AdapterError(f"进入运行阶段时发生资源冲突：{', '.join(sorted(conflicts))}")
            self._set_record_state(record, RunState.RUNNING, step="run", summary=f"{app_label(app_spec.id)} 正在运行。")
            while True:
                if stop_event.is_set():
                    adapter.stop(ctx)
                    self._set_record_state(record, RunState.CANCELLED, step="stop", summary=f"{app_label(app_spec.id)} 已取消。", result="cancelled")
                    break
                tracked_pid = int(ctx.metadata.get("tracked_pid", 0) or 0)
                if tracked_pid and tracked_pid != persisted_pid:
                    self._persist_active_run(record, pid=tracked_pid)
                    persisted_pid = tracked_pid
                poll = adapter.poll(ctx)
                if poll.summary:
                    record.summary = poll.summary
                if poll.terminal_state is not None:
                    self._set_record_state(record, poll.terminal_state, step="done", summary=poll.summary or record.summary, result=poll.result or poll.terminal_state.value.lower())
                    break
                time.sleep(1)
        except Exception as exc:
            self.event_log.append("controller", f"{app_spec.id} 运行失败：{exc}", record.run_id, level="ERROR")
            final_state = RunState.CANCELLED if stop_event.is_set() else RunState.FAILED
            final_result = "cancelled" if final_state == RunState.CANCELLED else "exception"
            self._set_record_state(record, final_state, step="error", summary=str(exc), result=final_result)
        finally:
            try:
                self._set_record_state(record, RunState.CLEANUP, step="cleanup", summary=f"正在清理 {app_label(app_spec.id)}。")
                adapter.cleanup(ctx)
            except Exception as exc:
                self.event_log.append("controller", f"{app_spec.id} 收尾清理失败：{exc}", record.run_id, level="ERROR")
            finally:
                self.resource_manager.release(record.run_id)
                if record.result == "cancelled":
                    record.state = RunState.CANCELLED
                elif record.result in {"success", "done", "detached_exit"}:
                    record.state = RunState.DONE
                elif record.result == "detached":
                    record.state = RunState.RUNNING
                elif record.result:
                    record.state = RunState.FAILED
                elif record.state == RunState.CLEANUP:
                    record.state = RunState.DONE
                    record.result = "success"
                if record.state in {RunState.DONE, RunState.FAILED, RunState.CANCELLED}:
                    record.ended_at = utcnow_iso()
                self._persist_records()

    def snapshot(self) -> dict[str, Any]:
        self._refresh_detached_runs()
        with self._lock:
            apps_snapshot = []
            for app in self.settings.apps:
                active = self._active_app_handle(app.id)
                latest = self._latest_app_record(app.id)
                state = active.record.state if active else (latest.state if latest else RunState.IDLE)
                summary = ""
                if active and active.context:
                    summary = active.context.record.summary or active.record.summary
                elif latest:
                    summary = latest.summary
                apps_snapshot.append(
                    {
                        "id": app.id,
                        "label": app_label(app.id),
                        "path": app.exe_path,
                        "enabled": app.enabled,
                        "allow_parallel": self.settings.parallel_overrides.get(app.id, False),
                        "state": state.value,
                        "summary": summary,
                        "warnings": self._validation_warnings.get(app.id, []),
                        "active_run_id": active.record.run_id if active else "",
                    }
                )

            active_sequence = next(
                (
                    handle
                    for handle in self._active_runs.values()
                    if handle.record.target_type == TargetType.WORKFLOW and handle.record.target_id == "custom_sequence"
                ),
                None,
            )
            latest_sequence = self._latest_sequence_record()
            sequence_state = active_sequence.record.state if active_sequence else (latest_sequence.state if latest_sequence else RunState.IDLE)
            sequence_summary = active_sequence.record.summary if active_sequence else (latest_sequence.summary if latest_sequence else "")
            sequence_snapshot = {
                "name": self._sequence_name(),
                "steps": self._sequence_steps(),
                "state": sequence_state.value,
                "summary": sequence_summary,
                "active_run_id": active_sequence.record.run_id if active_sequence else "",
                "items": [
                    {
                        "id": app_id,
                        "label": app_label(app_id),
                        "enabled": self.settings.sequence_enabled.get(app_id, False),
                    }
                    for app_id in self.settings.sequence_order
                ],
            }

            workflows_snapshot = []
            for workflow in self.workflows:
                active = next((handle for handle in self._active_runs.values() if handle.record.target_type == TargetType.WORKFLOW and handle.record.target_id == workflow.id), None)
                latest = self._latest_workflow_record(workflow.id)
                state = active.record.state if active else (latest.state if latest else RunState.IDLE)
                summary = active.record.summary if active else (latest.summary if latest else "")
                workflows_snapshot.append(
                    {
                        "id": workflow.id,
                        "name": workflow.name,
                        "steps": workflow.steps,
                        "state": state.value,
                        "summary": summary,
                        "active_run_id": active.record.run_id if active else "",
                    }
                )

            active_details = []
            for handle in self._active_runs.values():
                raw = handle.context.raw_excerpt() if handle.context else ""
                summary = handle.context.record.summary if handle.context else handle.record.summary
                active_details.append(
                    {
                        "run_id": handle.record.run_id,
                        "target_type": handle.record.target_type.value,
                        "target_id": handle.record.target_id,
                        "state": handle.record.state.value,
                        "step": handle.record.step,
                        "summary": summary,
                        "raw_log": raw,
                    }
                )

        return {
            "apps": apps_snapshot,
            "sequence": sequence_snapshot,
            "workflows": workflows_snapshot,
            "active_details": active_details,
            "event_log": self.event_log.lines(),
        }


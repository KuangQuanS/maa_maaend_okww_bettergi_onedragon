from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .defaults import default_settings, default_workflows
from .models import DashboardSettings, RunRecord, WorkflowSpec
from .paths import AppPaths


TRANSIENT_STATE_VALUES = {"VALIDATING", "LAUNCHING", "STARTING", "RUNNING", "CLEANUP"}


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


class DashboardStorage:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.paths.ensure()

    def _today_key(self) -> str:
        return datetime.now().astimezone().date().isoformat()

    def _file_day(self, path: Path) -> str | None:
        if not path.exists():
            return None
        stamp = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        return stamp.date().isoformat()

    def _prune_run_records_for_new_day(self) -> None:
        path = self.paths.run_records_file
        if not path.exists() or self._file_day(path) == self._today_key():
            return
        data = load_json(path, [])
        if not isinstance(data, list):
            save_json(path, [])
            return
        kept = [
            item
            for item in data
            if isinstance(item, dict) and str(item.get("state", "")) in TRANSIENT_STATE_VALUES
        ]
        save_json(path, kept)

    def load_settings(self) -> DashboardSettings:
        if not self.paths.settings_file.exists():
            settings = default_settings()
            self.save_settings(settings)
            return settings
        return DashboardSettings.from_dict(load_json(self.paths.settings_file, {}))

    def save_settings(self, settings: DashboardSettings) -> None:
        save_json(self.paths.settings_file, settings.to_dict())

    def load_workflows(self) -> list[WorkflowSpec]:
        if not self.paths.workflows_file.exists():
            workflows = default_workflows()
            self.save_workflows(workflows)
            return workflows
        data = load_json(self.paths.workflows_file, [])
        return [WorkflowSpec.from_dict(item) for item in data]

    def save_workflows(self, workflows: list[WorkflowSpec]) -> None:
        save_json(self.paths.workflows_file, [item.to_dict() for item in workflows])

    def load_run_records(self) -> list[RunRecord]:
        self._prune_run_records_for_new_day()
        data = load_json(self.paths.run_records_file, [])
        return [RunRecord.from_dict(item) for item in data]

    def save_run_records(self, records: list[RunRecord]) -> None:
        save_json(self.paths.run_records_file, [item.to_dict() for item in records])

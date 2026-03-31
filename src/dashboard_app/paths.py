from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def resolve_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    app_root: Path
    data_root: Path
    settings_file: Path
    workflows_file: Path
    runtime_dir: Path
    run_records_file: Path
    event_log_file: Path
    active_runs_file: Path

    @classmethod
    def create(cls) -> "AppPaths":
        app_root = resolve_app_root()
        data_root = app_root / "dashboard_data"
        runtime_dir = data_root / "runtime"
        return cls(
            app_root=app_root,
            data_root=data_root,
            settings_file=data_root / "settings.json",
            workflows_file=data_root / "workflows.json",
            runtime_dir=runtime_dir,
            run_records_file=runtime_dir / "run_records.json",
            event_log_file=runtime_dir / "events.log",
            active_runs_file=runtime_dir / "active_runs.json",
        )

    def ensure(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .defaults import APP_PATHS


def discover_existing_paths() -> dict[str, str]:
    discovered: dict[str, str] = {}
    for key, path in APP_PATHS.items():
        discovered[key] = str(path) if path.exists() else ""
    return discovered


def first_existing(paths: Iterable[Path]) -> str:
    for path in paths:
        if path.exists():
            return str(path)
    return ""

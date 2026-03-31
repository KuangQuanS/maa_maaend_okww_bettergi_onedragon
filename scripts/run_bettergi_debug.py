from __future__ import annotations

import json
import time
from pathlib import Path

from dashboard_app.controller import DashboardController


def load_new_events(path: Path, offset: int) -> tuple[list[str], int]:
    if not path.exists():
        return [], offset
    with path.open('r', encoding='utf-8', errors='ignore') as handle:
        handle.seek(offset)
        data = handle.read()
        offset = handle.tell()
    lines = [line.rstrip() for line in data.splitlines() if line.strip()]
    return lines, offset


def main() -> int:
    controller = DashboardController()
    run_id = controller.start_app('bettergi')
    if not run_id:
        print('FAILED: could not start bettergi run')
        return 1

    events_path = controller.paths.event_log_file
    events_offset = events_path.stat().st_size if events_path.exists() else 0
    started_at = time.time()
    print(f'RUN_ID={run_id}')

    while True:
        snapshot = controller.snapshot()
        detail = next((item for item in snapshot['active_details'] if item['run_id'] == run_id), None)
        app = next((item for item in snapshot['apps'] if item['id'] == 'bettergi'), None)
        state = detail['state'] if detail else (app['state'] if app else 'unknown')
        step = detail['step'] if detail else ''
        summary = detail['summary'] if detail else (app['summary'] if app else '')
        print(f"[{time.strftime('%H:%M:%S')}] state={state} step={step} summary={summary}")

        lines, events_offset = load_new_events(events_path, events_offset)
        for line in lines:
            if run_id in line:
                print(f'EVENT {line}')

        active = controller._active_runs.get(run_id)
        if active and active.context:
            tracked_pid = active.context.metadata.get('tracked_pid')
            launcher_pid = active.context.process.pid if active.context.process else None
            if tracked_pid or launcher_pid:
                print(f'PIDS launcher={launcher_pid} tracked={tracked_pid}')

        if state in {'DONE', 'FAILED', 'CANCELLED'}:
            break
        if time.time() - started_at >= 5400:
            print('INFO: debug wait reached 5400s; leaving BetterGI running if still active.')
            break
        time.sleep(2)

    records = controller.storage.load_run_records()
    record = next((item for item in reversed(records) if item.run_id == run_id), None)
    if record:
        print('FINAL_RECORD=' + json.dumps(record.to_dict(), ensure_ascii=False))

    latest_log = None
    log_dir = Path(r'D:\BetterGI\log')
    if log_dir.exists():
        logs = sorted(log_dir.glob('better-genshin-impact*.log'), key=lambda p: p.stat().st_mtime)
        if logs:
            latest_log = logs[-1]
    if latest_log:
        print(f'LOG_FILE={latest_log}')
        with latest_log.open('r', encoding='utf-8', errors='ignore') as handle:
            tail = handle.readlines()[-20:]
        for line in tail:
            print('LOG ' + line.rstrip())

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

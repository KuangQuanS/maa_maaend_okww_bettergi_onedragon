# Multi Run Dashboard

Windows dashboard for coordinating:

- `D:\maa\MAA.exe`
- `D:\maaend\MaaEnd.exe`
- `D:\BetterGI\BetterGI.exe`

## Development

```powershell
D:\python\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
run_dashboard_admin.bat
```

Smoke test:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe scripts\launch_dashboard.py --smoke-test
```

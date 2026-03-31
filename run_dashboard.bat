@echo off
setlocal
set "ROOT=%~dp0"
set "SCRIPT=%ROOT%scripts\launch_dashboard.py"
set "PYTHONW=%ROOT%.venv\Scripts\pythonw.exe"
if exist "%PYTHONW%" goto launch
set "PYTHONW=D:\python\pythonw.exe"
if exist "%PYTHONW%" goto launch
echo Pythonw not found.
pause
exit /b 1

:launch
start "" /D "%ROOT%" "%PYTHONW%" "%SCRIPT%" %*
exit /b 0

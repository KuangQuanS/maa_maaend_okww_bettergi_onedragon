@echo off
setlocal
set "ROOT=%~dp0"
if /I "%~1"=="__elevated__" (
    shift
    call "%ROOT%run_dashboard.bat" %*
    exit /b %errorlevel%
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -WorkingDirectory '%ROOT%' -FilePath '%ComSpec%' -ArgumentList '/c ""%~f0"" __elevated__ %*'"
exit /b %errorlevel%

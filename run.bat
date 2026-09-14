@echo off
REM Thunderbird-AI launcher (Windows). Used by Task Scheduler or run manually.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

REM Pass any args through, e.g.  run.bat --once   or   run.bat --check
"%PY%" -m thunderbird_ai.main %*

@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
uv run --no-project --python 3.13 python -m jarvis.server
pause

@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

set PYTHONPATH=%cd%
uvicorn backend.main:app --reload --port 8000
pause

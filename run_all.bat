@echo off
setlocal
cd /d "%~dp0"

start "Backend" cmd /k run_backend.bat
start "Frontend" cmd /k run_frontend.bat

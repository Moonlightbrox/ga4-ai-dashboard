@echo off
setlocal
cd /d "%~dp0\\frontend"

start "" http://localhost:3000
npm run dev
pause

@echo off
setlocal
cd /d "%~dp0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8765 .*LISTENING"') do taskkill /F /PID %%P >nul 2>&1
timeout /t 1 /nobreak >nul
py -3 dashboard.py

@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$dashboardProcesses = Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') -and $_.CommandLine -match 'dashboard\.py' }; $dashboardProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
py -3 dashboard.py

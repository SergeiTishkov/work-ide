@echo off
rem Removes Work IDE's background work: unregisters the task queue's two
rem workers from Windows Task Scheduler (tools\taskd.py uninstall, task 0056).
rem The queue and the schedules stay; without the workers a scheduled
rem collection runs only while the app has started a worker for a queued
rem task. WorkIDE-Background-Setup.cmd registers them again.
rem Double-click it; Windows asks for administrator rights once.
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  rem Not elevated: start an elevated copy.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" || pause
  exit /b
)
echo Work IDE background removal.
echo Workers running now are not stopped: they keep running until Windows
echo restarts or you sign out, and are not started again after that.
echo Press any key to remove them, or close this window.
pause >nul
".venv\Scripts\python.exe" tools\taskd.py uninstall
echo.
".venv\Scripts\python.exe" tools\taskd.py status
pause

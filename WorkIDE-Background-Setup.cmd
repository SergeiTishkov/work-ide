@echo off
rem Sets up Work IDE's background work: registers the task queue's two
rem workers with Windows Task Scheduler (tools\taskd.py install, task 0056).
rem The background one starts with Windows, the desktop one at sign-in; then
rem the scheduled collection and the queued tasks run without the app open.
rem Double-click it; Windows asks for administrator rights once. No password
rem is stored. To remove: .venv\Scripts\python tools\taskd.py uninstall
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  rem Not elevated: start an elevated copy and tell it whose workers they are.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%USERDOMAIN%\%USERNAME%' -Verb RunAs" || pause
  exit /b
)
set "OWNER=%*"
if "%OWNER%"=="" set "OWNER=%USERDOMAIN%\%USERNAME%"
echo Work IDE background setup, for %OWNER%.
echo The workers start right away: a scheduled collection that was missed
echo runs then, AI reads included.
echo Press any key to register them, or close this window.
pause >nul
".venv\Scripts\python.exe" tools\taskd.py install --user "%OWNER%"
echo.
".venv\Scripts\python.exe" tools\taskd.py status
pause

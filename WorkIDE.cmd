@echo off
rem Starts the Work IDE desktop app. Double-click it, or point a desktop
rem shortcut at it. The first start installs the app's dependencies.
setlocal
rem Inherited from an Electron-based editor, this would start Electron as plain Node.
set ELECTRON_RUN_AS_NODE=
cd /d "%~dp0app"
if not exist node_modules\electron\dist\electron.exe (
  echo Installing the app's dependencies, once...
  call npm install || (pause & exit /b 1)
)
start "" "%~dp0app\node_modules\electron\dist\electron.exe" "%~dp0app"

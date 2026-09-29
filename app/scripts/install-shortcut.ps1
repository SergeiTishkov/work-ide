# Creates a "Work IDE" shortcut on the desktop and in the Start menu, pointing
# straight at the app's Electron: no console window, and it can be pinned to
# the taskbar like any program. Run again after moving the repository.
#
#   powershell -ExecutionPolicy Bypass -File app\scripts\install-shortcut.ps1

$ErrorActionPreference = 'Stop'
$appDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$electron = Join-Path $appDir 'node_modules\electron\dist\electron.exe'

if (-not (Test-Path $electron)) {
    Write-Host "Installing the app's dependencies, once..."
    Push-Location $appDir
    try { npm install } finally { Pop-Location }
}

$shell = New-Object -ComObject WScript.Shell
$places = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) '')
)
foreach ($place in $places) {
    $link = $shell.CreateShortcut((Join-Path $place 'Work IDE.lnk'))
    $link.TargetPath = $electron
    $link.Arguments = "`"$appDir`""
    $link.WorkingDirectory = $appDir
    $link.IconLocation = "$electron,0"
    $link.Description = 'Work IDE: vacancy lists, feedback and agent runs'
    $link.Save()
    Write-Host "Shortcut: $($link.FullName)"
}

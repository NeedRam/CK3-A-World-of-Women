@echo off
setlocal
set "UFG_STEAM_ROOT=%ProgramFiles(x86)%\Steam\steamapps\common\Crusader Kings III\binaries"
if not exist "%UFG_STEAM_ROOT%" set "UFG_STEAM_ROOT=%ProgramFiles%\Steam\steamapps\common\Crusader Kings III\binaries"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Installer\install.ps1" -TargetRoot "%UFG_STEAM_ROOT%" -PackageRoot "%~dp0." -Interactive %*
set "UFG_EXIT=%ERRORLEVEL%"
endlocal & exit /b %UFG_EXIT%

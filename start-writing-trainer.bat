@echo off
setlocal

set "TRAINER_DIR=%~dp0..\en-sense-trainer"
if not exist "%TRAINER_DIR%\server.js" exit /b 0

%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8787/' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 exit /b 0

set "NODE_EXE="
node --version >nul 2>&1
if not errorlevel 1 set "NODE_EXE=node"
if not defined NODE_EXE if exist "%ProgramFiles%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles%\nodejs\node.exe"
if not defined NODE_EXE if exist "%ProgramFiles(x86)%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles(x86)%\nodejs\node.exe"
if not defined NODE_EXE if exist "%LocalAppData%\Programs\nodejs\node.exe" set "NODE_EXE=%LocalAppData%\Programs\nodejs\node.exe"

if not defined NODE_EXE (
    echo   [WARN] Node.js not found. Writing trainer will be unavailable.
    exit /b 0
)

echo   Starting writing trainer on http://localhost:8787 ...
start "" /MIN /D "%TRAINER_DIR%" "%NODE_EXE%" server.js
exit /b 0

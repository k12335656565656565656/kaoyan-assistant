@echo off
cd /d "%~dp0"
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"

if not exist "app.py" (
    echo [ERROR] app.py not found in %cd%
    pause
    exit /b 1
)

call :find_python
if not defined PYTHON_EXE (
    echo [ERROR] Python 3.10 or later was not found.
    echo         Install Python from https://www.python.org/downloads/ and try again.
    echo         During installation, enable "Add Python to PATH" if available.
    pause
    exit /b 1
)

echo   Using Python: %PYTHON_EXE% %PYTHON_ARGS%

echo.
echo   ============================================
echo      Kaoyan Study Assistant
echo      http://localhost:8505
echo   ============================================
echo.
echo   Starting server, please wait...
echo   Browser will open automatically once ready
echo   ============================================

if exist "%~dp0start-writing-trainer.bat" call "%~dp0start-writing-trainer.bat"

start "" /MIN /D "%~dp0" "%PYTHON_EXE%" %PYTHON_ARGS% -m streamlit run app.py --server.port 8505 --server.headless true --server.fileWatcherType none

set /a T=0
:wait
timeout /t 2 /nobreak >nul
set /a T+=2
netstat -ano 2>nul | find ":8505" | find "LISTENING" >nul
if %errorlevel%==0 goto open
if %T% lss 60 goto wait

echo   [WARN] Timeout after 60s. Check: http://localhost:8505
pause
exit /b 1

:open
echo   Server ready, opening browser...
start http://localhost:8505
echo.
echo   Browser opened. Press any key to close this window.
echo   (Server will keep running in background)
pause >nul
exit /b 0

:find_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

rem Prefer a project virtual environment when one exists.
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"

rem Do not use 'where': it may be unavailable when System32 is missing from PATH.
if not defined PYTHON_EXE (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
    )
)

rem Fall back to common per-user and machine-wide install locations.
if not defined PYTHON_EXE for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do if not defined PYTHON_EXE if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
if not defined PYTHON_EXE for /d %%D in ("%ProgramFiles%\Python*") do if not defined PYTHON_EXE if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
if not defined PYTHON_EXE for /d %%D in ("%ProgramFiles(x86)%\Python*") do if not defined PYTHON_EXE if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"

if defined PYTHON_EXE (
    "%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if errorlevel 1 (
        set "PYTHON_EXE="
        set "PYTHON_ARGS="
    )
)
exit /b 0

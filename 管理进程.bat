@echo off
cd /d "%~dp0"
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
set "PORT=8505"

:menu
cls
set "PID="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr "LISTENING" 2^>nul') do set "PID=%%a"

echo.
echo   ============================================
echo      Kaoyan Study Assistant - Process Manager
echo   ============================================
echo.
if defined PID (
    echo   [ON]   Running  PID:%PID%  Port:%PORT%
    echo          http://localhost:%PORT%
) else (
    echo   [OFF]  Stopped
)
echo.
echo   [1] Start    [2] Stop    [3] Browser
echo   [0] Exit
echo.

set "choice="
set /p "choice=   Select: "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto browser
if "%choice%"=="0" exit /b
goto menu

:start
if defined PID (
    echo   Already running (PID:%PID%)
    pause >nul
    goto menu
)
if not exist "app.py" (
    echo   app.py not found
    pause >nul
    goto menu
)
call :find_python
if not defined PYTHON_EXE (
    echo   Python 3.10 or later was not found.
    echo   Install Python from https://www.python.org/downloads/
    pause >nul
    goto menu
)
echo   Starting with %PYTHON_EXE% %PYTHON_ARGS% ...
if exist "%~dp0start-writing-trainer.bat" call "%~dp0start-writing-trainer.bat"
start "" /MIN /D "%~dp0" "%PYTHON_EXE%" %PYTHON_ARGS% -m streamlit run app.py --server.port %PORT% --server.headless true --server.fileWatcherType none

set /a N=0
:wait
timeout /t 2 /nobreak >nul
set /a N+=2
netstat -ano 2>nul | findstr ":%PORT%" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo   Ready, opening browser...
    start http://localhost:%PORT%
    pause >nul
    goto menu
)
if %N% lss 60 goto wait
echo   Timeout, check streamlit.log
pause >nul
goto menu

:stop
if not defined PID (
    echo   Not running
    pause >nul
    goto menu
)
echo   Stopping PID %PID% ...
taskkill /PID %PID% /F >nul 2>&1
if errorlevel 1 taskkill /F /IM python.exe >nul 2>&1
echo   Stopped
pause >nul
goto menu

:browser
start http://localhost:%PORT%
goto menu

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

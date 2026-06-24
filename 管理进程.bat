@echo off
cd /d "%~dp0"
setlocal
set "PORT=8505"

call :resolve_python
if errorlevel 1 (
    pause
    exit /b 1
)

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
echo   Starting...
call :start_streamlit

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
if errorlevel 1 (
    echo   Failed to stop PID %PID%. Please close it manually.
) else (
    echo   Stopped
)
pause >nul
goto menu

:browser
start http://localhost:%PORT%
goto menu

:resolve_python
set "PYTHON_CMD="
set "PYTHON_ARGS="

if defined PYTHON (
    if exist "%PYTHON%" (
        "%PYTHON%" -m streamlit --version >nul 2>&1 && (
            set "PYTHON_CMD=%PYTHON%"
            goto python_ready
        )
    )
)

python -m streamlit --version >nul 2>&1 && (
    set "PYTHON_CMD=python"
    goto python_ready
)

py -3 -m streamlit --version >nul 2>&1 && (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3"
    goto python_ready
)

echo   [ERROR] Streamlit is not available in the current Python environment.
echo           Try: python -m pip install -r requirements.txt
exit /b 1

:python_ready
exit /b 0

:start_streamlit
if defined PYTHON_ARGS (
    start "" /MIN /D "%~dp0" cmd /c ""%PYTHON_CMD%" %PYTHON_ARGS% -m streamlit run app.py --server.port %PORT% --server.headless true --server.fileWatcherType none"
) else (
    start "" /MIN /D "%~dp0" cmd /c ""%PYTHON_CMD%" -m streamlit run app.py --server.port %PORT% --server.headless true --server.fileWatcherType none"
)
exit /b 0

@echo off
cd /d "%~dp0"
setlocal

if not exist "app_kb.py" (
    echo [ERROR] app_kb.py not found in %cd%
    pause
    exit /b 1
)

call :resolve_python
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo   ============================================
echo      Kaoyan Knowledge Base
echo      http://localhost:8501
echo   ============================================
echo.
echo   Starting server, please wait...
echo   Browser will open automatically once ready
echo   ============================================

call :start_streamlit "app_kb.py" "8501"

set /a T=0
:wait
timeout /t 2 /nobreak >nul
set /a T+=2
netstat -ano 2>nul | find ":8501" | find "LISTENING" >nul
if %errorlevel%==0 goto open
if %T% lss 60 goto wait

echo   [WARN] Timeout after 60s. Check: http://localhost:8501
pause
exit /b 1

:open
echo   Server ready, opening browser...
start http://localhost:8501
echo.
echo   Browser opened. Press any key to close this window.
echo   (Server will keep running in background)
pause >nul
exit /b 0

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

echo [ERROR] Streamlit is not available in the current Python environment.
echo         Try: python -m pip install -r requirements_kb.txt
exit /b 1

:python_ready
exit /b 0

:start_streamlit
set "APP_FILE=%~1"
set "APP_PORT=%~2"

if defined PYTHON_ARGS (
    start "" /MIN /D "%~dp0" cmd /c ""%PYTHON_CMD%" %PYTHON_ARGS% -m streamlit run "%APP_FILE%" --server.port %APP_PORT% --server.headless true --server.fileWatcherType none"
) else (
    start "" /MIN /D "%~dp0" cmd /c ""%PYTHON_CMD%" -m streamlit run "%APP_FILE%" --server.port %APP_PORT% --server.headless true --server.fileWatcherType none"
)
exit /b 0

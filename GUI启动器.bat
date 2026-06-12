@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"

:: ============================================================
:: Step 1: detect Python 3.10+
:: ============================================================
echo [GUI] Detecting Python...

call :find_python
if "%PY_RESULT%"=="" goto :no_python

set "PYTHON_EXE=%PY_RESULT%"
echo [GUI] Python: %PYTHON_EXE%

:: ============================================================
:: Step 2: fix or create venv
:: ============================================================
set "VENV_DIR=%ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"

set "VENV_OK=0"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "print(1)" >nul 2>&1
    if not errorlevel 1 set "VENV_OK=1"
)

if "%VENV_OK%"=="1" goto :venv_ok

:: venv is broken or missing
if exist "%VENV_DIR%" (
    echo [GUI] Removing broken venv...
    rmdir /s /q "%VENV_DIR%"
)
echo [GUI] Creating fresh venv...
"%PYTHON_EXE%" -m venv "%VENV_DIR%"
if errorlevel 1 goto :venv_fail
echo [GUI] Venv created.

:venv_ok
:: ============================================================
:: Step 3: install deps if needed
:: ============================================================
echo [GUI] Checking launcher dependencies...
"%VENV_PY%" -c "import novel_world.launcher.gui, webview" >nul 2>&1
if not errorlevel 1 goto :deps_ok

echo [GUI] Installing launcher deps (may take a few minutes)...
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="

"%VENV_PY%" -m pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -e "%ROOT%[launcher]"
if errorlevel 1 "%VENV_PY%" -m pip install -q -e "%ROOT%[launcher]"
if errorlevel 1 if exist "%ROOT%\scripts\ensure_launcher_deps.py" "%VENV_PY%" "%ROOT%\scripts\ensure_launcher_deps.py" "%VENV_PY%"

:: re-check
"%VENV_PY%" -c "import novel_world.launcher.gui, webview" >nul 2>&1
if errorlevel 1 goto :deps_fail

:deps_ok
echo [GUI] Dependencies OK.

:: ============================================================
:: Step 4: launch
:: ============================================================
echo [GUI] Starting launcher...
if exist "%VENV_PYW%" (
    start "" /D "%ROOT%" "%VENV_PYW%" -m novel_world.launcher
) else (
    start "" /D "%ROOT%" "%VENV_PY%" -m novel_world.launcher
)
echo [GUI] Launcher should now be running.
echo       If not, you may need Edge WebView2:
echo       https://go.microsoft.com/fwlink/p/?LinkId=2124703
endlocal
exit /b 0

:: ============================================================
:: Error handlers
:: ============================================================
:no_python
echo.
echo ================================================================
echo  No Python 3.10+ found on this system.
echo.
echo  Please install Python 3.10 or later:
echo    https://www.python.org/downloads/
echo    Check "Add python.exe to PATH" during install.
echo ================================================================
echo.
pause
exit /b 1

:venv_fail
echo [Error] Failed to create venv.
echo        Make sure Python has the "venv" module.
pause
exit /b 1

:deps_fail
echo.
echo [Error] Could not install launcher dependencies.
echo   Possible causes: no internet, proxy/VPN, missing wheels.
echo   Try: %VENV_PY% -m pip install -e "%ROOT%[launcher]"
echo.
pause
exit /b 1

:: ============================================================
:: find_python
:: ============================================================
:find_python
set "PY_RESULT="

for %%V in (-3.14 -3.13 -3.12 -3.11 -3.10 -3) do (
    if "%PY_RESULT%"=="" (
        for /f "delims=" %%P in ('py %%V -c "import sys; print(sys.executable)" 2^>nul') do (
            if exist "%%P" (
                py %%V -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
                if not errorlevel 1 set "PY_RESULT=%%P"
            )
        )
    )
)

if "%PY_RESULT%"=="" (
    for %%C in (python python3) do (
        if "%PY_RESULT%"=="" (
            where %%C >nul 2>&1
            if not errorlevel 1 (
                for /f "delims=" %%P in ('%%C -c "import sys; print(sys.executable)" 2^>nul') do (
                    if exist "%%P" (
                        %%C -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
                        if not errorlevel 1 set "PY_RESULT=%%P"
                    )
                )
            )
        )
    )
)

if "%PY_RESULT%"=="" if exist "%LOCALAPPDATA%\Programs\Python\" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if "%PY_RESULT%"=="" if exist "%%D\python.exe" (
            "%%D\python.exe" -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
            if not errorlevel 1 set "PY_RESULT=%%D\python.exe"
        )
    )
)

if "%PY_RESULT%"=="" (
    for %%P in ("%ProgramFiles%\Python*\python.exe" "%ProgramFiles(x86)%\Python*\python.exe") do (
        if "%PY_RESULT%"=="" if exist "%%~P" (
            "%%~P" -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
            if not errorlevel 1 set "PY_RESULT=%%~P"
        )
    )
)

goto :eof
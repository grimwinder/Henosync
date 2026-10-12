@echo off
echo Setting up Henosync development environment...
echo.

:: Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found. Please install Node.js 20+ from https://nodejs.org
    exit /b 1
)
echo   Node.js found
for /f "tokens=*" %%v in ('node -v') do echo   Version: %%v

:: Check pnpm
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo   pnpm not found - installing...
    call npm install -g pnpm
)
echo   pnpm found

:: Check Python 3.11 or 3.12 via py launcher
:: vicon-dssdk (and several ROS2 packages) do not publish wheels for 3.13+.
set PYTHON_CMD=
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3.12
    goto :python_found
)
py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3.11
    goto :python_found
)
echo ERROR: Python 3.11 or 3.12 not found.
echo   Python 3.13+ is not yet supported (vicon-dssdk has no wheel for it).
echo   Install Python 3.12 from: https://python.org/downloads/release/python-3120/
echo   Make sure to tick "Add to PATH" and install the py launcher.
exit /b 1
:python_found
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version') do echo   %%v

:: Check Git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git not found. Please install from https://git-scm.com
    exit /b 1
)
echo   Git found
echo.

:: Install JavaScript dependencies
echo Installing JavaScript dependencies...
call pnpm install
echo   Done
echo.

:: Create Python virtual environment
echo Setting up Python virtual environment...
:: An existing .venv built with an unsupported Python (e.g. 3.13+) is recreated.
if exist apps\backend\.venv\Scripts\python.exe (
    apps\backend\.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"
    if errorlevel 1 (
        echo   Existing .venv uses an unsupported Python version - recreating it
        rmdir /s /q apps\backend\.venv
    )
)
if exist apps\backend\.venv (
    echo   .venv already exists - skipping creation
) else (
    %PYTHON_CMD% -m venv apps\backend\.venv
    echo   Created .venv
)

echo   Installing backend packages...
apps\backend\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
apps\backend\.venv\Scripts\python.exe -m pip install --quiet ^
    uvicorn ^
    fastapi ^
    aiosqlite ^
    "sqlalchemy[asyncio]" ^
    pydantic ^
    websockets ^
    aiofiles ^
    python-multipart ^
    roslibpy ^
    cflib
apps\backend\.venv\Scripts\python.exe -m pip install --quiet -e packages\plugin-sdk
echo   Done
echo.

:: VICON Python package (vicon_dssdk) is not on PyPI - it ships inside the
:: Vicon DataStream SDK installer. Install it from there if the SDK is present.
:: Set VICON_SDK_DIR to override the search location.
echo Installing VICON support...
if not defined VICON_SDK_DIR set "VICON_SDK_DIR=%ProgramFiles%\Vicon"
set VICON_PKG=
if exist "%VICON_SDK_DIR%" (
    for /d /r "%VICON_SDK_DIR%" %%d in (vicon_dssdk) do (
        if exist "%%d\setup.py" set "VICON_PKG=%%d"
        if exist "%%d\pyproject.toml" set "VICON_PKG=%%d"
    )
)
if defined VICON_PKG (
    echo   Found %VICON_PKG%
    :: Build from a writable copy - pip writes egg-info next to setup.py,
    :: which fails with "Access is denied" under Program Files.
    if exist "%TEMP%\vicon_dssdk_build" rmdir /s /q "%TEMP%\vicon_dssdk_build"
    xcopy /e /i /q "%VICON_PKG%" "%TEMP%\vicon_dssdk_build" >nul
    apps\backend\.venv\Scripts\python.exe -m pip install --quiet "%TEMP%\vicon_dssdk_build"
    rmdir /s /q "%TEMP%\vicon_dssdk_build"
)
apps\backend\.venv\Scripts\python.exe -c "import vicon_dssdk" >nul 2>&1
if errorlevel 1 (
    echo   WARNING: VICON support NOT installed - VICON positioning will not connect.
    echo   1. Download and install the Vicon DataStream SDK ^(Windows^):
    echo        https://www.vicon.com/software/datastream-sdk/
    echo   2. Re-run scripts\setup.bat - it will find and install it automatically.
    echo   Everything else in Henosync works without it.
) else (
    echo   VICON support installed
)
echo.

echo Henosync development environment is ready!
echo.
echo   Start the full app:  pnpm dev
echo.
pause
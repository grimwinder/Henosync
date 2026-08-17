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
if exist apps\backend\.venv (
    echo   .venv already exists - skipping creation
) else (
    %PYTHON_CMD% -m venv apps\backend\.venv
    echo   Created .venv
)

echo   Installing backend packages...
apps\backend\.venv\Scripts\pip install --quiet --upgrade pip
apps\backend\.venv\Scripts\pip install --quiet ^
    uvicorn ^
    fastapi ^
    aiosqlite ^
    "sqlalchemy[asyncio]" ^
    pydantic ^
    websockets ^
    aiofiles ^
    python-multipart ^
    roslibpy ^
    vicon-dssdk
apps\backend\.venv\Scripts\pip install --quiet -e packages\plugin-sdk
echo   Done
echo.

echo Henosync development environment is ready!
echo.
echo   Start the full app:  pnpm dev
echo.
pause
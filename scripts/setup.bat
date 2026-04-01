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

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python 3.11+ not found. Please install from https://python.org
    exit /b 1
)
echo   Python found
python --version

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
    python -m venv apps\backend\.venv
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
    python-multipart
echo   Done
echo.

echo Henosync development environment is ready!
echo.
echo   Start the full app:  pnpm dev
echo.
pause
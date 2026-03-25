@echo off
echo Setting up Henosync development environment...
echo.

:: Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found. Please install from https://nodejs.org
    exit /b 1
)
echo OK: Node.js found

:: Check pnpm
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pnpm...
    npm install -g pnpm
)
echo OK: pnpm found

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install from https://python.org
    exit /b 1
)
echo OK: Python found

:: Check Poetry
where poetry >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Poetry not found.
    echo Install from: https://install.python-poetry.org
    exit /b 1
)
echo OK: Poetry found

echo.

:: Install JS dependencies
echo Installing JavaScript dependencies...
call pnpm install
echo OK: JavaScript dependencies installed

:: Install Python dependencies
echo Installing Python dependencies...
cd apps\backend
call poetry install
cd ..\..
echo OK: Python dependencies installed

echo.
echo Henosync development environment is ready!
echo.
echo To start developing:
echo   Backend:  cd apps\backend and run: poetry run python main.py
echo   Frontend: pnpm dev
echo.
pause
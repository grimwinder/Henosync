#!/bin/bash

set -e  # Exit immediately if any command fails

echo "🚀 Setting up Henosync development environment..."
echo ""

# ── Check Prerequisites ─────────────────────────────────────────

echo "Checking prerequisites..."

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 20+ from https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 20 ]; then
    echo "❌ Node.js version must be 20 or higher. Current: $(node -v)"
    exit 1
fi
echo "✅ Node.js $(node -v)"

# Check pnpm
if ! command -v pnpm &> /dev/null; then
    echo "❌ pnpm not found. Installing..."
    npm install -g pnpm
fi
echo "✅ pnpm $(pnpm -v)"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3.11+ not found. Please install from https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_VERSION" -lt 11 ]; then
    echo "❌ Python version must be 3.11 or higher. Current: $(python3 --version)"
    exit 1
fi
echo "✅ Python $(python3 --version)"

# Check Poetry
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry not found. Installing..."
    curl -sSL https://install.python-poetry.org | python3 -
fi
echo "✅ Poetry $(poetry --version)"

# Check Git
if ! command -v git &> /dev/null; then
    echo "❌ Git not found. Please install from https://git-scm.com"
    exit 1
fi
echo "✅ Git $(git --version)"

echo ""

# ── Install JavaScript Dependencies ─────────────────────────────

echo "Installing JavaScript dependencies..."
pnpm install
echo "✅ JavaScript dependencies installed"
echo ""

# ── Install Python Dependencies ──────────────────────────────────

echo "Installing Python backend dependencies..."
cd apps/backend
poetry install
cd ../..
echo "✅ Python dependencies installed"
echo ""

# ── Set Up Git Hooks ─────────────────────────────────────────────

echo "Setting up Git hooks..."
pnpm exec husky init
echo "pnpm lint-staged" > .husky/pre-commit
chmod +x .husky/pre-commit
echo "✅ Git hooks configured"
echo ""

# ── Verify Backend Starts ────────────────────────────────────────

echo "Verifying backend starts correctly..."
cd apps/backend
timeout 10 poetry run python main.py &
BACKEND_PID=$!
sleep 4

if curl -s http://localhost:8765/health > /dev/null 2>&1; then
    echo "✅ Backend health check passed"
else
    echo "⚠️  Backend health check failed — check apps/backend manually"
fi

kill $BACKEND_PID 2>/dev/null
cd ../..
echo ""

# ── Done ─────────────────────────────────────────────────────────

echo "✅ Henosync development environment is ready!"
echo ""
echo "To start developing:"
echo "  Backend:  cd apps/backend && poetry run python main.py"
echo "  Frontend: pnpm dev"
echo ""
#!/bin/bash

set -e  # Exit immediately if any command fails

echo "Setting up Henosync development environment..."
echo ""

# ── Check Prerequisites ─────────────────────────────────────────

echo "Checking prerequisites..."

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found. Please install Node.js 20+ from https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 20 ]; then
    echo "ERROR: Node.js version must be 20 or higher. Current: $(node -v)"
    exit 1
fi
echo "  Node.js $(node -v)"

# Check pnpm
if ! command -v pnpm &> /dev/null; then
    echo "  pnpm not found — installing..."
    npm install -g pnpm
fi
echo "  pnpm $(pnpm -v)"

# Check Python 3.11 or 3.12 specifically.
# vicon-dssdk (and several ROS2 packages) do not publish wheels for 3.13+.
PYTHON=""
for candidate in python3.12 python3.11; do
    if command -v "$candidate" &> /dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11 or 3.12 not found."
    echo "  Python 3.13+ is not yet supported (vicon-dssdk has no wheel for it)."
    echo "  Install via Homebrew:  brew install python@3.12"
    echo "  Or download from:      https://python.org/downloads/release/python-3120/"
    exit 1
fi
echo "  $("$PYTHON" --version)"

# Check Git
if ! command -v git &> /dev/null; then
    echo "ERROR: Git not found. Install Xcode Command Line Tools: xcode-select --install"
    exit 1
fi
echo "  $(git --version)"

echo ""

# ── JavaScript Dependencies ──────────────────────────────────────

echo "Installing JavaScript dependencies..."
pnpm install
echo "  Done"
echo ""

# ── Python Virtual Environment ───────────────────────────────────

BACKEND_DIR="apps/backend"
VENV_DIR="$BACKEND_DIR/.venv"

echo "Setting up Python virtual environment..."

if [ -d "$VENV_DIR" ]; then
    echo "  .venv already exists — skipping creation"
else
    "$PYTHON" -m venv "$VENV_DIR"
    echo "  Created .venv with $("$PYTHON" --version)"
fi

echo "  Installing backend packages..."
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --quiet \
    uvicorn \
    fastapi \
    aiosqlite \
    "sqlalchemy[asyncio]" \
    pydantic \
    websockets \
    aiofiles \
    python-multipart \
    roslibpy \
    cflib
"$VENV_DIR/bin/python" -m pip install --quiet -e packages/plugin-sdk
echo ""
echo "  NOTE: VICON positioning requires the Vicon DataStream SDK, which ships"
echo "  with Vicon Tracker or Nexus. After installing Vicon software, run:"
echo "    $VENV_DIR/bin/python -m pip install '/path/to/Vicon/DataStream SDK/.../Python/vicon_dssdk'"
echo "  The backend works fine without it — only VICON-mode devices will be unavailable."
echo "  Done"
echo ""

# ── Verify Backend Starts ────────────────────────────────────────

echo "Verifying backend starts correctly..."
cd "$BACKEND_DIR"
".venv/bin/python" main.py &
BACKEND_PID=$!
sleep 4

if curl -s http://127.0.0.1:8765/health > /dev/null 2>&1; then
    echo "  Health check passed"
else
    echo "  WARNING: Backend health check failed — check apps/backend manually"
fi

kill $BACKEND_PID 2>/dev/null
wait $BACKEND_PID 2>/dev/null
cd ../..
echo ""

# ── Done ─────────────────────────────────────────────────────────

echo "Henosync development environment is ready!"
echo ""
echo "  Start the full app:  pnpm dev"
echo ""
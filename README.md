# Henosync

Open source robot fleet mission planner. Control and coordinate networks of drones, robots, and autonomous vehicles from a single desktop interface.

## Prerequisites

| Tool                          | Version | Notes                 |
| ----------------------------- | ------- | --------------------- |
| [Node.js](https://nodejs.org) | 20+     |                       |
| [pnpm](https://pnpm.io)       | 8+      | `npm install -g pnpm` |
| [Python](https://python.org/downloads/release/python-3120/) | **3.11 or 3.12** | 3.13+ is **not** supported — see below |
| [Git](https://git-scm.com)    | Any     |                       |
| [Vicon DataStream SDK](https://www.vicon.com/software/datastream-sdk/) | Any | Only needed for VICON positioning — see below |

> **Python version:** use 3.11 or 3.12. The Vicon Python package (`vicon_dssdk`) and several ROS2 packages have no builds for 3.13+. You can have other Python versions installed too — the Windows setup script picks 3.12/3.11 via the `py` launcher. On Windows, tick **"Add python.exe to PATH"** and keep the **py launcher** option when installing.

> **Note:** Poetry is not required. The setup scripts create a local Python virtual environment using the tools built into Python.

### VICON motion capture (optional)

Henosync talks to the VICON PC directly using Vicon's own Python package, `vicon_dssdk`. It is **not on PyPI** — it ships inside the Vicon DataStream SDK installer:

**Windows:**

1. Download the [Vicon DataStream SDK](https://www.vicon.com/software/datastream-sdk/) (e.g. `ViconDataStreamSDK_1.13.0+167154h.zip`) and extract it. The download contains Linux, Mac and Win64 zips — you only need the Windows installer:
   ```
   ViconDataStreamSDK_<version>\ViconDataStreamSDK_<version>_Win64\Win64\ViconDataStreamSDK_<version>_x64.msi
   ```
   (Extract `..._Win64.zip` first if it isn't already. Ignore the `.7z` source archives.)
2. The installer is unsigned, so Windows may block it ("Windows protected your PC"). Either click **More info → Run anyway**, or right-click the `.msi` → **Properties** → tick **Unblock** → **OK**.
3. Run the `.msi` and **keep the default install location** (`C:\Program Files\Vicon\DataStream SDK`) — setup only searches there unless you set `VICON_SDK_DIR`.
4. Run (or re-run) `scripts\setup.bat` from **cmd or PowerShell** (not Git Bash). It should print:
   ```
   Installing VICON support...
     Found C:\Program Files\Vicon\DataStream SDK\Win64\Python\vicon_dssdk
     VICON support installed
   ```
5. If Henosync was already running, **fully close and restart it** — the backend only loads the Vicon package at startup.

**Mac / Linux:** extract the SDK zip for your platform and run `VICON_SDK_DIR=/path/to/extracted/sdk ./scripts/setup.sh`.

**Connecting:** click the VICON dot in the title bar and enter the VICON PC's IP (port `801`). Your machine must be on the same network as the VICON PC, and Vicon Tracker/Nexus must be running live on it. If Windows Firewall prompts, allow access on **Private** networks.

Without the SDK, Henosync runs normally but the VICON indicator in the title bar never connects. If setup prints `WARNING: VICON support NOT installed`, check the SDK is installed under `C:\Program Files\Vicon` and re-run setup.

## Setup

Run the setup script once after cloning. It installs all JavaScript and Python dependencies automatically.

**Mac / Linux:**

```bash
git clone https://github.com/grimwinder/henosync.git
cd henosync
chmod +x scripts/setup.sh
./scripts/setup.sh
```

**Windows:**

```bat
git clone https://github.com/grimwinder/henosync.git
cd henosync
scripts\setup.bat
```

The setup script:

- Checks all prerequisites
- Runs `pnpm install` for JavaScript dependencies
- Creates `apps/backend/.venv` with Python 3.11/3.12 and installs Python packages via pip (an existing `.venv` built with the wrong Python version is recreated)
- Installs VICON support from the Vicon DataStream SDK if it is installed

Re-running setup is safe — do it after installing the Vicon SDK or if you get import errors.

## Running

After setup, a single command starts both the backend and the Electron desktop app:

```bash
pnpm dev
```

This starts Vite (renderer), compiles the Electron main process TypeScript, launches the backend Python server, and opens the desktop window.

## Project Structure

```
henosync/
├── apps/
│   ├── backend/               # Python FastAPI backend
│   │   ├── henosync/
│   │   │   ├── api/           # REST routes and WebSocket server
│   │   │   ├── core/          # Node registry, zone manager, failsafe
│   │   │   ├── plugin_system/ # Plugin loader and registry
│   │   │   ├── storage/       # SQLite database layer
│   │   │   └── transport/     # ROS2 and sim transport adapters
│   │   ├── main.py            # Uvicorn entry point
│   │   └── .venv/             # Python virtual environment (gitignored)
│   └── desktop/               # Electron + React + TypeScript frontend
│       └── src/
│           ├── main/          # Electron main process
│           ├── preload/       # Context bridge
│           └── renderer/      # React application
│               ├── components/
│               │   ├── fleet/ # Device panel, device detail
│               │   ├── map/   # MapLibre map, node markers
│               │   ├── nav/   # Navigation menu
│               │   └── zones/ # Zone list, detail panel, drawing tools
│               ├── hooks/     # React Query data hooks
│               ├── pages/     # HomePage, ZonesPage
│               ├── stores/    # Zustand state (nodes, zones, system)
│               └── types/     # Shared TypeScript types
├── plugins/                   # Device plugins (loaded at runtime)
│   └── sim-dummy/             # Simulated device plugin for development
└── scripts/
    ├── setup.sh               # Mac/Linux setup
    └── setup.bat              # Windows setup
```

## Features

- **Fleet management** — add, monitor, and remove robot devices
- **Live telemetry** — real-time position and status via WebSocket
- **Zones** — draw polygon and circle zones on the map (perimeter, no-go, safe return, coverage, alert, custom)
- **Zone detail** — click any zone to inspect vertex coordinates (A, B, C...)
- **Plugin system** — drop device plugins into `/plugins` for automatic loading
- **Offline maps** — OpenStreetMap tiles with dark rendering (no API key required)

## License

Apache 2.0 — see [LICENSE](LICENSE)

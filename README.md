# Henosync

Open source robot fleet mission planner. Control and coordinate networks of drones, robots, and autonomous vehicles from a single desktop interface.

## Prerequisites

| Tool                          | Version | Notes                 |
| ----------------------------- | ------- | --------------------- |
| [Node.js](https://nodejs.org) | 20+     |                       |
| [pnpm](https://pnpm.io)       | 8+      | `npm install -g pnpm` |
| [Python](https://python.org)  | 3.11+   |                       |
| [Git](https://git-scm.com)    | Any     |                       |

> **Note:** Poetry is not required. The setup scripts create a local Python virtual environment using the tools built into Python.

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
- Creates `apps/backend/.venv` and installs Python packages via pip

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

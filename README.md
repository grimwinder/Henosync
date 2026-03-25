# Henosync

Open source robot home base mission planner. Control and coordinate 
networks of drones, robots, and devices from a single intuitive desktop interface.

## Prerequisites

- [Node.js 20+](https://nodejs.org)
- [pnpm 8+](https://pnpm.io)
- [Python 3.11+](https://python.org)
- [Poetry](https://python-poetry.org)
- [Git](https://git-scm.com)

## Quick Start

**Mac/Linux:**
```bash
git clone https://github.com/YOUR_USERNAME/henosync.git
cd henosync
./scripts/setup.sh
```

**Windows:**
```bat
git clone https://github.com/YOUR_USERNAME/henosync.git
cd henosync
scripts\setup.bat
```

## Running in Development

Start the backend:
```bash
cd apps/backend
poetry run python main.py
```

Start the frontend (new terminal):
```bash
pnpm dev
```

## Project Structure
```
henosync/
├── apps/
│   ├── desktop/       # Electron + React frontend
│   └── backend/       # Python FastAPI backend
├── packages/
│   ├── plugin-sdk/    # SDK for plugin developers
│   ├── ui-components/ # Shared React components
│   └── mission-schema/# Shared mission JSON schema
├── plugins/
│   └── sim-dummy/     # Built-in simulation plugin
└── docs/              # Documentation
```

## License

Apache 2.0 — see [LICENSE](LICENSE)
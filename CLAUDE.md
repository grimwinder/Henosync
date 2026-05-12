# Henosync — Architecture Reference

Henosync is an open-source robot fleet mission planner built at Monash University.
4-person dev team. Apache 2.0. This file is the authoritative reference for Claude.

## Maintenance rule

**Claude must update this file at the end of every response that changes code.**
Update the relevant section if architecture/APIs/contracts changed.
Append a one-line entry to the Change log at the bottom with date and what changed.
Do not rewrite the whole file — only edit what is actually different.

---

## Engineering principles

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
- Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan before starting:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

---

## Repository layout

```
henosync/
├── apps/
│   ├── backend/                Python FastAPI backend (port 8765)
│   │   ├── main.py             Entry point — uvicorn on 127.0.0.1:8765
│   │   └── henosync/
│   │       ├── api/
│   │       │   ├── app.py      FastAPI app factory, startup/shutdown, /health, /api/plugins, /api/transports
│   │       │   ├── websocket_server.py  ConnectionManager, /ws/telemetry, /ws/events
│   │       │   └── routes/
│   │       │       ├── nodes.py       CRUD for nodes, reconnect
│   │       │       ├── commands.py    send_command, get stream URL
│   │       │       ├── missions.py    CRUD for missions
│   │       │       ├── execution.py   execute/pause/resume/abort, engine status
│   │       │       ├── operations.py  start/stop/list control plugin operations
│   │       │       ├── zones.py       CRUD for zones
│   │       │       ├── markers.py     CRUD for map markers
│   │       │       └── safety.py      emergency-stop
│   │       ├── core/
│   │       │   ├── node_registry.py    Source of truth for all nodes; manages connect/telemetry tasks
│   │       │   ├── operation_manager.py  Starts/stops control plugin operations; device matching
│   │       │   ├── mission_engine.py   Step-by-step mission state machine
│   │       │   ├── failsafe_manager.py Background heartbeat + battery monitor
│   │       │   ├── telemetry_bus.py    Pub/sub for TelemetryFrame and SystemEvent
│   │       │   ├── zone_manager.py     Zone CRUD + geometry (ray casting, haversine)
│   │       │   ├── marker_manager.py   Map marker CRUD
│   │       │   ├── fleet_context.py    Injected into control plugins; device access + messaging
│   │       │   ├── device_proxy.py     Wraps Node; universal movement, capability data, coord conversion
│   │       │   └── event_bus.py        Inter-control-plugin messaging (broadcast/point-to-point)
│   │       ├── models/
│   │       │   ├── node.py         Node, NodeCreate, NodeStatus, DeviceCategory, DeviceCapability,
│   │       │   │                   DeviceSpecs, CapabilitySpec, CapabilityRequirement, Position,
│   │       │   │                   LocalOrigin, GPSData, LidarScan, CameraFeed, BatteryData,
│   │       │   │                   NodeCapability, CommandResult
│   │       │   ├── mission.py      Mission, MissionCreate, MissionUpdate, MissionStep, StepType,
│   │       │   │                   StepStatus, FailsafeConfig, FailsafeAction, MissionStatus,
│   │       │   │                   Condition, ConditionOperator
│   │       │   └── telemetry.py    TelemetryFrame, SystemEvent, EventSeverity
│   │       ├── plugin_system/
│   │       │   ├── interfaces.py          NodePlugin ABC (5 abstract + 4 optional methods)
│   │       │   ├── control_interfaces.py  ControlPlugin ABC + OperationStatus + UIContribution
│   │       │   ├── loader.py              PluginLoader — scans plugins/ dir, loads manifest + plugin.py
│   │       │   └── registry.py            PluginRegistry — plugin_id→class, node_id→instance
│   │       ├── storage/
│   │       │   ├── database.py       DB_PATH = ~/.henosync/henosync.db; init_db() creates tables
│   │       │   └── mission_store.py  MissionStore — full SQLite CRUD for missions
│   │       └── transport/
│   │           ├── base.py      BaseTransport ABC
│   │           ├── ros2.py      ROS2Transport — wraps roslibpy (subscribe_topic, publish_to_topic, call_service)
│   │           └── registry.py  TransportRegistry — maps name → class; lists available transports
│   └── desktop/                Electron + React 18 + TypeScript + Vite (Electron wraps Vite dev/build)
│       └── src/
│           ├── main/
│           │   └── index.ts    Electron main process; spawns backend; window management; IPC handlers
│           ├── preload/
│           │   └── index.ts    contextBridge exposes window.henosync (backend, window, dialog)
│           └── renderer/
│               ├── App.tsx     Root — WebSocket lifecycle; title bar; page visibility switching
│               ├── pages/      HomePage, DevicesPage, MissionPage, PluginsPage, ZonesPage
│               ├── components/ fleet/, map/, zones/, nav/
│               ├── hooks/      React Query hooks (useNodes, useOperations, useMissions, …)
│               ├── stores/     Zustand stores (nodeStore, systemStore, operationStore, …)
│               ├── lib/
│               │   ├── api.ts          REST client; BACKEND_URL = http://127.0.0.1:8765
│               │   ├── websocket.ts    ManagedSocket with exponential backoff
│               │   └── queryClient.ts  React Query client configuration
│               └── types/      Shared TypeScript types
├── plugins/
│   ├── ue-sim/   Device plugin for UE AirSim SUV via rosbridge
│   └── template/ Starter template for new device plugins
└── packages/
    └── plugin-sdk/
        └── henosync_sdk/  Re-exports NodePlugin + models for out-of-tree plugins
```

---

## Backend architecture

### Entry point (`apps/backend/main.py`)

`uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="info")`. The app object is created by `create_app()` in `api/app.py`.

### Startup sequence (`henosync/api/app.py`)

`PLUGINS_DIR` is resolved as `Path(__file__).parent.parent.parent.parent.parent / "plugins"` (5 levels up from app.py → repo root/plugins).

1. `PluginLoader(PLUGINS_DIR).load_all()` — scans plugins/, loads device plugins into `plugin_registry`, control plugins into `operation_manager`
2. `mission_store.initialize()` — creates `missions` table if not exists
3. `node_registry.initialize()` — calls `init_db()`, loads all saved nodes from SQLite, triggers async `_connect_node()` for each
4. `zone_manager.initialize()` — loads active zones from SQLite
5. `marker_manager.initialize()` — loads markers from SQLite
6. `failsafe_manager.start()` — starts background heartbeat loop

On shutdown: `failsafe_manager.stop()` → `node_registry.shutdown()` (disconnects all nodes).

### Core singletons (all in `henosync/core/`)

Module-level instances — never instantiate, always import the singleton.

| Singleton            | File                      | Responsibility                                                                                                                                                                                                                                                 |
| -------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `node_registry`      | node_registry.py          | Source of truth for all nodes. Persists to SQLite. Manages plugin connect/disconnect/telemetry tasks. In-memory cache: `_nodes: dict[str, Node]`.                                                                                                              |
| `operation_manager`  | operation_manager.py      | Starts/stops control plugin operations. Matches devices to plugins by capability. Handles device priority conflicts. Tracks `_operations: dict[str, ActiveOperation]` and `_device_assignments: dict[str, str]`.                                               |
| `mission_engine`     | mission_engine.py         | Step-by-step mission execution state machine. One active mission at a time.                                                                                                                                                                                    |
| `failsafe_manager`   | failsafe_manager.py       | HEARTBEAT_TIMEOUT=5s, POLL_INTERVAL=1s. Monitors ONLINE/DEGRADED nodes. Triggers safe state + pauses mission on heartbeat loss. Battery threshold check per active mission failsafe config. Tracks `_triggered: dict[str, bool]` to avoid repeated triggering. |
| `telemetry_bus`      | telemetry_bus.py          | Per-node asyncio queues (maxsize=50). Event queue (maxsize=100). Non-blocking puts; drops oldest frame when full. Direct callback subscribers for WS server.                                                                                                   |
| `zone_manager`       | zone_manager.py           | Geographic zone CRUD + point-in-polygon (ray casting for polygon, haversine for circle). ZoneType: PERIMETER, NO_GO, SAFE_RETURN, COVERAGE, ALERT, CUSTOM. Persists to SQLite.                                                                                 |
| `marker_manager`     | marker_manager.py         | Map marker CRUD. Persists to SQLite.                                                                                                                                                                                                                           |
| `plugin_registry`    | plugin_system/registry.py | Maps `plugin_id → class`, `plugin_id → manifest`, `node_id → instance`.                                                                                                                                                                                        |
| `event_bus`          | event_bus.py              | Inter-control-plugin messaging (broadcast / point-to-point).                                                                                                                                                                                                   |
| `mission_store`      | storage/mission_store.py  | Full SQLite CRUD for missions. Missions ARE persisted — `missions` table in henosync.db.                                                                                                                                                                       |
| `connection_manager` | api/websocket_server.py   | Manages WebSocket connection lists; broadcasts telemetry and event messages.                                                                                                                                                                                   |

### Database (`~/.henosync/henosync.db`)

SQLite, accessed via `aiosqlite`. Path: `DB_PATH = Path.home() / ".henosync" / "henosync.db"`.

Tables:

- `nodes` — id, name, plugin_id, config (JSON), home_lat/lon/alt, created_at
- `zones` — id, name, zone_type, shape, points (JSON), center_lat/lon, radius_m, created_by, active, color
- `map_markers` — id, name, marker_type, lat, lon, color
- `missions` — id, name, status, steps (JSON), failsafe (JSON), metadata (JSON), created_at, updated_at

### Plugin system — two separate types

**Device plugins** (`NodePlugin` ABC in `plugin_system/interfaces.py`)

- 5 abstract methods: `connect`, `disconnect`, `send_command`, `telemetry_stream`, `get_safe_state`
- 4 optional methods: `get_video_stream_url`, `validate_config`, `on_mission_start`, `on_mission_end`
- One class per hardware type; one instance per connected node (node_id → instance in `plugin_registry`)
- `connect()` must return False (not raise) on failure
- `send_command()` should return success as soon as robot ACCEPTS command (not when complete)
- `telemetry_stream()` is an AsyncGenerator — yield TelemetryFrame at 1Hz
- Loaded from `plugins/<name>/plugin.py` — PluginLoader finds any `NodePlugin` subclass

**Control plugins** (`ControlPlugin` ABC in `plugin_system/control_interfaces.py`)

- 4 abstract methods: `start(context)`, `stop()`, `get_status()`, `get_ui_contribution()`
- 4 optional event handlers: `on_device_joined`, `on_device_left`, `on_message`, `on_operator_input`
- Class attributes: `PLUGIN_ID`, `PLUGIN_NAME`, `PLUGIN_VERSION`, `PLUGIN_AUTHOR`, `OPERATION_NAME`, `OPERATION_DESCRIPTION`, `REQUIRED_CAPABILITIES`, `SUPPORTED_CATEGORIES`, `PRIORITY` (int, higher = wins device conflicts)
- `start()` runs as background asyncio.Task until `stop()` is called; check `self._stop_requested`
- `stop()` must complete within 3 seconds
- `get_status()` must be non-blocking (no awaits) — returns `OperationStatus`
- `get_ui_contribution()` returns `UIContribution` with `config_schema` (drives Mission Planner step config form)
- Config passed via `plugin._config = config` (set by operation_manager before `start()`)

**Plugin loading** (`plugin_system/loader.py`)
Required manifest fields: `id`, `name`, `version`, `author`, `description`, `sdk_version`, `node_types`, `capabilities`.
Loader uses `importlib.util` to load `plugin.py`, then inspects module attrs for `NodePlugin` or `ControlPlugin` subclass.

### Device → Control plugin interaction path

```
Control plugin
  └── FleetContext (injected by operation_manager at start)
        └── DeviceProxy (wraps Node object)
              └── plugin_registry.get_instance(node_id) → NodePlugin instance
                    └── NodePlugin.send_command(node, capability, params)
```

Control plugins NEVER call NodePlugin directly. Always go through DeviceProxy.

### DeviceProxy (`core/device_proxy.py`)

Universal device interface for control plugins. Key features:

- `move_to(lat, lon, alt)` — checks no-go zones, converts GPS→local frame if device uses odometry, dispatches `send_command("move_to", ...)`
- `stop()`, `return_home()` — dispatch named commands
- `get_gps_data()`, `get_lidar_scan()`, `get_camera_feed()`, `get_battery_data()` — standard-format data from telemetry dict
- `has_capability(DeviceCapability)`, `meets_requirement(CapabilityRequirement)` — capability negotiation
- Coordinate conversion: `_gps_to_local()` (equirectangular, accurate <1km), `local_to_gps()` — uses `node.local_origin`
- `category` comes from `node.specs.category` (returns `UNKNOWN` if specs not set)

### FleetContext (`core/fleet_context.py`)

Injected into control plugins. Provides:

- `context.devices` — list of `DeviceProxy` objects matched at operation start
- `context.recruit_device(device_id)` — dynamically add device (checks priority, updates `_device_assignments`)
- `context.release_device(device_id)` — return device to pool
- `context.get_available_devices(capabilities, categories)` — query unassigned devices
- `context.zone_manager` — direct access to zone_manager singleton
- `context.broadcast(message)`, `context.send_to_plugin(id, message)` — inter-plugin messaging via event_bus
- `context.send_alert(title, message, severity)` — operator notification via telemetry_bus
- `context.request_operator_input(prompt, options)` — TODO Phase 5, currently returns first option

### Data flow: robot telemetry to GUI

```
NodePlugin.telemetry_stream() yields TelemetryFrame
  → node_registry._run_telemetry_stream() updates:
      node.last_seen, node.telemetry (full dict),
      node.battery_percent (if key present),
      node.signal_strength (if key present),
      node.position (Position from lat+lon+alt keys)
  → telemetry_bus.publish_telemetry(frame)
      → direct callbacks → connection_manager.broadcast_telemetry()
      → WS /ws/telemetry → frontend websocket.ts
      → nodeStore.updateTelemetry() → Zustand → React re-render
```

If telemetry stream raises an exception, node is set to `DEGRADED`.

### REST API surface

All route files are in `henosync/api/routes/`. All prefixed `/api/` except `/health`.

| Route file    | Endpoints                                                                                                                                                                |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| nodes.py      | `GET /api/nodes`, `POST /api/nodes`, `GET /api/nodes/{id}`, `DELETE /api/nodes/{id}`, `POST /api/nodes/{id}/reconnect`                                                   |
| commands.py   | `POST /api/nodes/{id}/command`, `GET /api/nodes/{id}/stream_url`                                                                                                         |
| missions.py   | `GET /api/missions`, `POST /api/missions`, `GET /api/missions/{id}`, `PUT /api/missions/{id}`, `DELETE /api/missions/{id}`                                               |
| execution.py  | `POST /api/missions/{id}/execute`, `POST /api/missions/{id}/pause`, `POST /api/missions/{id}/resume`, `POST /api/missions/{id}/abort`, `GET /api/missions/engine/status` |
| operations.py | `GET /api/operations`, `POST /api/operations/start`, `POST /api/operations/{plugin_id}/stop`, `GET /api/control-plugins`                                                 |
| zones.py      | `GET /api/zones`, `POST /api/zones`, `DELETE /api/zones/{id}`                                                                                                            |
| markers.py    | `GET /api/markers`, `POST /api/markers`, `DELETE /api/markers/{id}`                                                                                                      |
| safety.py     | `POST /api/safety/emergency-stop`                                                                                                                                        |
| app.py inline | `GET /health`, `GET /api/plugins` (device manifests), `GET /api/transports`                                                                                              |

### WebSocket endpoints

- `ws://127.0.0.1:8765/ws/telemetry` — streams `{"type":"telemetry", "node_id", "timestamp", "sequence", "values"}` and `{"type":"ping"}` every 1s
- `ws://127.0.0.1:8765/ws/events` — streams `{"type":"event", "id", "severity", "title", "message", "node_id", "timestamp", "acknowledged"}` and `{"type":"ping"}` every 1s
- Frontend filters out "ping" type messages. Reconnects with exponential backoff (base=1s, max=30s, factor=1.5×).

### Transport system (`henosync/transport/`)

`BaseTransport` ABC + `ROS2Transport` (wraps roslibpy: `subscribe_topic()`, `publish_to_topic()`, `call_service()`, `client` property). `TransportRegistry` maps name → class and lists available transports.
**The transport system is NOT currently used by either the Jackal or ue-sim plugins** — both call roslibpy directly. The transport system exists as infrastructure for future standardisation.

### Mission engine (`core/mission_engine.py`)

Step types: `MOVE`, `ACTION`, `WAIT`, `CONDITION`, `PARALLEL`, `LOOP`, `WAIT_FOR`.

- LOOP: executes `loop_step_ids` in sequence for `loop_count` iterations; MAX_ITERATIONS=1000 safety cap
- WAIT_FOR: polls condition every 500ms up to `wait_for_timeout_seconds` (default 30s)
- CONDITION: evaluates `gt`/`lt`/`eq`/`neq` operators against telemetry value; branches to `then_step_id` or `else_step_id`
- Validates all target nodes are ONLINE before starting
- Calls `on_mission_start` / `on_mission_end` on all involved NodePlugin instances
- `pause()` / `resume()` from exact step index
- `mission_engine` (step executor) and `operation_manager` (control plugin runner) are parallel execution paths. UI currently uses operation_manager only.

### Failsafe manager (`core/failsafe_manager.py`)

- `HEARTBEAT_TIMEOUT = 5.0s`, `POLL_INTERVAL = 1.0s`
- Monitors all ONLINE/DEGRADED nodes; skips OFFLINE/ERROR/CONNECTING
- On node lost: notifies `operation_manager.on_node_lost()`, calls `get_safe_state()`, sets status=ERROR, pauses active mission, emits CRITICAL event
- On node recovered: emits WARNING event (does NOT auto-resume mission)
- Battery check: only triggers if active mission is EXECUTING and battery ≤ failsafe threshold
- Battery failsafe actions: `RETURN_HOME` (calls `send_command("return_home",{})`), `ABORT` (aborts mission), `PAUSE` (pauses mission)
- `_triggered` dict prevents repeated firing for same dropout; uses `f"{node_id}_battery"` key for battery events
- `emergency_stop_all()`: stops all operations → aborts mission → concurrent safe state all ONLINE nodes via `asyncio.gather`

---

## Models

### Node model (`models/node.py`)

Key types:

- `NodeStatus`: CONNECTING, ONLINE, DEGRADED, OFFLINE, ERROR
- `DeviceCategory`: DRONE, PLANE, AGV, BOAT, ROV, ARM, UNKNOWN
- `DeviceCapability`: MOVE_2D, MOVE_3D, GPS, LIDAR, CAMERA, SONAR, IMU, THERMAL, HORN, LIGHTS, PAYLOAD, ARM_TOOL, BATTERY, CHARGING
- `DeviceSpecs`: category, capabilities (list[CapabilitySpec]), physical/operational specs, coordinate_frame ("gps" or "local")
- `Position`: lat, lon, alt, heading, accuracy — ALL positions in system are WGS84
- `Node`: id (UUID), name, plugin_id, status, position, battery_percent, signal_strength, capabilities (list[NodeCapability]), telemetry (dict), last_seen, home_position, local_origin, config, specs
- `NodeCapability`: id, label, params (list[str]), destructive (bool) — declared by plugin, drives GUI action buttons

### Mission model (`models/mission.py`)

- `MissionStep`: id, step_type, label, target_node_id, parameters, status, condition, then/else_step_id, parallel_step_ids, loop_step_ids, loop_count, loop_condition, wait_for_condition, wait_for_timeout_seconds
- `FailsafeConfig`: on_node_lost (default PAUSE), on_low_battery (default RETURN_HOME), low_battery_threshold (default 20.0%)
- `FailsafeAction`: ABORT, PAUSE, CONTINUE, RETURN_HOME
- `MissionStatus`: DRAFT, READY, EXECUTING, PAUSED, COMPLETED, ABORTED, FAILED

### Telemetry model (`models/telemetry.py`)

- `TelemetryFrame`: node_id, timestamp, sequence_number, values (dict[str, Any])
- `SystemEvent`: id, severity, title, message, node_id (optional), timestamp, acknowledged
- `EventSeverity`: INFO, WARNING, CRITICAL

---

## Frontend architecture

### Electron main process (`desktop/src/main/index.ts`)

- Spawns backend: Windows uses `.venv/Scripts/python.exe main.py`, other platforms use `.venv/bin/python main.py`
- Health check: 20 retries × 500ms = 10s max wait before showing window
- Window: 1440×900, minWidth=1280, minHeight=720, `frame=false` (custom title bar), CSP header set
- Window state (position/size) persisted to `userData/window-state.json`
- IPC handlers: `window:minimize`, `window:maximize`, `window:close`, `window:isMaximized`, `backend:url`, `backend:port`, `dialog:openFile`, `dialog:saveFile`

### Preload (`desktop/src/preload/index.ts`)

`contextBridge` exposes `window.henosync` with three namespaces:

- `window.henosync.backend` — `getUrl()`, `getPort()`
- `window.henosync.window` — `minimize()`, `maximize()`, `close()`, `isMaximized()`
- `window.henosync.dialog` — `openFile(options)`, `saveFile(options)`

Security: `nodeIntegration=false`, `contextIsolation=true`, `sandbox=true`.

### App root (`renderer/App.tsx`)

- Starts `wsManager` (telemetry + events WebSockets) on mount, stops on unmount
- Custom title bar: HENOSYNC logo, backend-connected indicator dot, online node count, window controls
- Page routing: all pages rendered simultaneously; visibility toggled via `display: page === "x" ? "flex" : "none"` — no React Router, single `useState` page selector

### State management — two layers

**Zustand stores** (`renderer/stores/`) — in-memory, updated by WebSocket messages and React Query side effects:

- `nodeStore` — `nodes: Record<string, Node>`. `setNodes()` (bulk from poll), `upsertNode()`, `removeNode()`, `updateTelemetry(frame)` (merges values dict, extracts battery_percent/signal_strength/position from lat+lon keys)
- `systemStore` — `events: SystemEvent[]` (newest-first, max 100), `unreadCount`, `backendConnected`. `setHealth()`, `setBackendConnected()`
- `operationStore` — running operations list
- `missionStore` — `engineStatus`. `setEngineStatus()`
- `zoneStore` — zones dict. `setZones()`, `upsertZone()`, `removeZone()`
- `markerStore` — markers dict
- `pluginStore` — device plugin manifests
- `uiStore` — UI state (selected node, active panels, etc.)

**React Query** (`renderer/hooks/`) — server state for REST calls. Mutations call `api.ts` directly (not React Query mutations for side effects).

Poll intervals:
| Hook | Interval |
|---|---|
| `useNodes()` | 5000ms |
| `useOperations()` | 2000ms |
| `useMissionEngineStatus()` | 2000ms |
| `useHealth()` | 5000ms |
| `useZones()` | 10000ms |
| `useDevicePlugins()` | staleTime 30000ms (no active poll) |
| `useControlPlugins()` | staleTime 30000ms |
| `useMissions()` | no poll (on-demand) |

`useNodes()` side effect: calls `setNodes()` to sync Zustand store on every poll.
`useZones()` side effect: calls `setZones()` on every poll.
`useMissionEngineStatus()` side effect: calls `setEngineStatus()`.
`useHealth()` side effect: calls `setHealth()` or `setBackendConnected(false)` on error.

### WebSocket client (`renderer/lib/websocket.ts`)

`ManagedSocket`: `RECONNECT_BASE_MS=1000`, `RECONNECT_MAX_MS=30000`, `RECONNECT_BACKOFF=1.5`. Ignores messages with `type === "ping"`. Events socket status change used as proxy for overall backend connectivity in `systemStore`.

### API client (`renderer/lib/api.ts`)

`BACKEND_URL = "http://127.0.0.1:8765"`. Named exports only — never `api.xxx` namespace pattern. `apiFetch` base function handles errors. Full coverage: nodes, missions, control-plugins, operations, zones, markers, safety, health, device-plugins, transports, stream URL.

### useMapLayouts (`renderer/hooks/useMapLayouts.ts`)

Saves zone+marker snapshots to `localStorage` under key `"henosync_map_layouts"`.
`load(layout)` does full delete+recreate via REST API (calls `deleteZone`/`deleteMarker` for all existing, then `createZone`/`createMarker` from snapshot) — then pushes result to Zustand stores directly.

### Pages

- **HomePage** — map + device panel + mission status panel + camera feed panel
- **DevicesPage** — device list, Add Device modal (uses `config_schema` from plugin manifest), device detail panel
- **MissionPage** — map + mission step builder (right panel) + step config (bottom panel) + run controls. Steps stored as `MissionBlock[]` in local state (not persisted to backend missions). Run Mission: iterates blocks, calls `startOperation(block.pluginId, block.params)`, polls `getOperations()` every 500ms until state is `"completed"`, `"failed"`, or `"idle"`. `stopRequestedRef` allows clean cancellation.
- **PluginsPage** — lists control plugins; starts operations
- **ZonesPage** — map with draw tools for zones and markers

---

## Plugin development rules

### Device plugin checklist

- Inherit `NodePlugin` from `henosync.plugin_system.interfaces`
- Implement all 5 abstract methods
- Set `node.specs = DeviceSpecs(category=..., capabilities=[...])` in `connect()` for capability matching
- Populate standard telemetry keys: `battery_percent`, `lat`, `lon`, `alt`, `speed`, `heading`, `status_text`, `signal_strength`
- `connect()` returns `False` (never raise) on failure
- `telemetry_stream()` is AsyncGenerator — yield TelemetryFrame at ~1Hz
- Plugin class must define `PLUGIN_ID` (must match manifest `id`)

### Control plugin checklist

- Inherit `ControlPlugin` from `henosync.plugin_system.control_interfaces`
- Declare `REQUIRED_CAPABILITIES` and `SUPPORTED_CATEGORIES`
- `start()` runs as background task; check `self._stop_requested` in main loop
- `stop()` must complete within 3 seconds
- `get_status()` must be non-blocking; read from internal state set by `start()`
- Read operator config via `self._config` (set by operation_manager before `start()`)
- Call `context.send_alert()` for operator notifications
- NEVER call NodePlugin or plugin_registry directly — always use DeviceProxy through FleetContext

### Manifest structure (`plugins/<name>/manifest.json`)

Required fields: `id`, `name`, `version`, `author`, `description`, `sdk_version`, `node_types` (array), `capabilities` (array of `{id, label, params, destructive}` objects).

`config_schema` field types: `"string"`, `"number"`, `"boolean"`, `"select"`.
For `"select"`: include `"options": [{"label": "...", "value": "..."}]`.
Optional per field: `required`, `default`, `min`, `max`, `placeholder`, `description`.

---

## Plugins in detail

### UE Sim plugin (`plugins/ue-sim/`)

Incremental test plugin for Unreal Engine ROS2 simulation via rosbridge. Uses roslibpy directly. Connection to rosbridge on host:port (default 9090). No ROS2 install required on the Henosync machine — only roslibpy.

Vehicle: AirSim SUV1 (ground vehicle — AGV category). Topic namespace: `/airsim_node/SUV1/`.

Current milestone: **Milestone 2** — GPS position on map, speed in telemetry panel.

- Subscribes to `global_gps` (`sensor_msgs/NavSatFix`) → `lat`, `lon`, `alt`
- Subscribes to `car_state` (`airsim_ros_pkgs/CarState`) → `speed`
- `gps_received` flag guards against emitting `lat=0,lon=0` before first GPS message (would place vehicle at null island)
- Topic names are constants `GPS_TOPIC`, `STATE_TOPIC` at top of plugin.py — update if AirSim namespace differs
- `_NodeState._topics` list tracks subscribed topics for clean unsubscribe on disconnect

Milestone 1 ✓: connect to rosbridge, heartbeat telemetry, device goes Online.
Milestone 2 ✓: GPS position on map, speed in telemetry panel.
Milestone 2b ✓: camera feed via web_video_server — `get_video_stream_url()` returns `http://<host>:8080/stream?topic=/airsim_node/SUV1/StereoCamera0_Scene/image`. Requires `web_video_server` running on the Linux sim machine (`ros2 run web_video_server web_video_server`).
Milestone 3 (next): IMU heading.

Connect uses `asyncio.get_running_loop().run_in_executor(None, ros.run)` + `asyncio.wait` with 10s timeout on `connected_event` / `failed_event`. `_NodeState` holds `ros` (roslibpy.Ros instance), `connected` flag, topic data fields, and `_topics` list.

### Template plugin (`plugins/template/`)

Starter template. Shows manifest `capabilities` array format with `{id, label, params, destructive}` objects.

---

## Design system

**Colours (CSS vars in globals.css):**

- Background layers: `#0D0F12` (base) → `#141619` → `#1C1F24` → `#252A31`
- Border: `#2A2F38` | Accent: `#4A9EFF` | Success: `#3DD68C`
- Warning: `#F5A623` | Danger: `#F05252` | Muted: `#8B95A3` | Text: `#E8EAED`
- In-component dark shades (inline styles): `#0D0D0D`, `#141414`, `#1C1C1C`, `#2D2D2D`

**Typography:** Inter 13px base.
**Radii:** 4px (sm), 6px (md), 8px (lg). **Transition:** 150ms ease.
**Header rows:** always 36px tall, `#0D0D0D` background, `1px solid #2D2D2D` border-bottom.
**Panel labels:** `font-size: 10px`, `font-weight: 700`, `letter-spacing: ~1px`, `color: #666666`.
Tailwind is available but rarely used — most styling is inline CSS objects.

---

## Key constraints and conventions

- All positions system-wide are WGS84 GPS (lat/lon/alt). DeviceProxy handles conversion for local-frame (odometry) devices.
- Rosbridge connection: Henosync connects via roslibpy WebSocket (default port 9090). No ROS2 install or ROS_DOMAIN_ID needed on the Henosync machine. Works with Unreal Engine sim via rclUE bridge.
- `mission_engine` and `operation_manager` are parallel execution paths. MissionPage UI uses operation_manager only. Mission engine is wired to REST API but not yet used in UI.
- Failsafe manager runs independently and cannot be bypassed by plugins.
- Emergency stop: `POST /api/safety/emergency-stop` → stops all operations → aborts mission → concurrent safe state all nodes.
- No simulation transports exist. `transport/` contains only `ROS2Transport`. UE sim connects via same rosbridge path as real hardware.
- Setup: `scripts/setup.bat` / `scripts/setup.sh` create `.venv` and install packages with pip directly. Poetry (`pyproject.toml`) is for documentation only — not used for actual installs.
- Plugin loader identifies plugin type by inspecting module for `NodePlugin` or `ControlPlugin` subclass — first match wins.

---

## Change log

| Date       | Change                                                                                                                                                                                                                                 |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-05-04 | Initial CLAUDE.md created from full codebase audit                                                                                                                                                                                     |
| 2026-05-04 | Removed `plugins/sim-dummy/`, `plugins/test-movements/` — simulation cleanup                                                                                                                                                           |
| 2026-05-04 | Removed `transport/simulation.py`; cleaned `transport/registry.py` to ros2 only                                                                                                                                                        |
| 2026-05-04 | Jackal plugin: removed `internal_sim` transport mode; always uses ros2_bridge                                                                                                                                                          |
| 2026-05-04 | Jackal manifest: removed `transport` select + `home_lat`/`home_lon` fields; `host` now required                                                                                                                                        |
| 2026-05-04 | Fixed `mission_engine._execute_loop` name collision — LOOP step handler renamed to `_execute_loop_step`                                                                                                                                |
| 2026-05-04 | Fixed `failsafe_manager.emergency_stop_all` — removed duplicated abort+safe-state block                                                                                                                                                |
| 2026-05-04 | Fixed `datetime.utcnow()` → `datetime.now(timezone.utc)` in models/mission.py, node.py, telemetry.py                                                                                                                                   |
| 2026-05-04 | Fixed `HomePage.tsx` — added missing `getStreamUrl` import; removed undefined `api` namespace reference                                                                                                                                |
| 2026-05-04 | MissionPage Run Mission wired to real backend: sequential `startOperation` + poll `getOperations` loop                                                                                                                                 |
| 2026-05-04 | Added maintenance rule to CLAUDE.md requiring updates after every code change                                                                                                                                                          |
| 2026-05-04 | Removed `plugins/area-patrol/` — control plugins deferred; focus is device plugins                                                                                                                                                     |
| 2026-05-11 | Added `plugins/ue-sim/` — incremental test plugin for UE ROS2 sim via rosbridge                                                                                                                                                        |
| 2026-05-11 | Added roslibpy to setup.bat, setup.sh, pyproject.toml                                                                                                                                                                                  |
| 2026-05-12 | Full codebase audit — comprehensive CLAUDE.md rewrite; corrected: missions persist to SQLite (not in-memory), useNodes polls at 5s (not 3s), useOperations polls at 2s (not 1s), transport system exists but unused by current plugins |
| 2026-05-12 | Added Engineering Principles section (think before coding, simplicity first, surgical changes, goal-driven execution)                                                                                                                  |
| 2026-05-12 | ue-sim Milestone 2: subscribed to global_gps (NavSatFix) and car_state (CarState); position on map, speed in telemetry                                                                                                                 |
| 2026-05-12 | ue-sim Milestone 2b: implemented get_video_stream_url() for web_video_server camera feed                                                                                                                                               |
| 2026-05-12 | Removed plugins/jackal/ entirely                                                                                                                                                                                                       |
| 2026-05-12 | Fixed all ruff linting violations in backend (I001 import order, W292 missing newlines, W291 trailing whitespace, F401 unused import, N806 uppercase locals in mission_engine and zone_manager)                                        |

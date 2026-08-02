# Henosync — Architecture Reference

Henosync is an open-source robot fleet mission planner built at Monash University.
4-person dev team. Apache 2.0. This file is the authoritative reference for Claude.

## Maintenance rule

**Claude must update this file at the end of every response that changes code.**
Update the relevant section if architecture/APIs/contracts changed.
Append a one-line entry to the Change log at the bottom with date and what changed.
Do not rewrite the whole file — only edit what is actually different.

## Git rule

**Never run `git commit` or `git push` unless the user explicitly asks.**
Stage files and show a summary if needed, but do not commit or push on your own initiative.

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
│   ├── device/           Installed device plugins (one subfolder per plugin)
│   │   └── ue-sim/       Device plugin for UE AirSim SUV via rosbridge
│   ├── control/          Installed control plugins (one subfolder per plugin)
│   │   └── auto-navigate/ Autonomous navigation — move to marker/zone, area coverage, perimeter patrol
│   └── templates/        Plugin templates — not loaded by the backend
│       ├── device-template/  Starter device plugin template
│       └── control-template/ Starter control plugin template
└── packages/
    └── plugin-sdk/
        └── henosync_sdk/  Canonical SDK — NodePlugin, ControlPlugin, all shared models
                           Installed into backend venv via: pip install -e packages/plugin-sdk
                           Backend imports from here. Plugins import from henosync_sdk directly.
```

---

## Backend architecture

### Entry point (`apps/backend/main.py`)

`uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="info")`. The app object is created by `create_app()` in `api/app.py`.

### Startup sequence (`henosync/api/app.py`)

`DEVICE_PLUGINS_DIR` = `plugins/device/`, `CONTROL_PLUGINS_DIR` = `plugins/control/` (both resolved from repo root). Templates in `plugins/templates/` are never scanned.

1. `PluginLoader(DEVICE_PLUGINS_DIR).load_all()` + `PluginLoader(CONTROL_PLUGINS_DIR).load_all()` — scans device and control dirs separately; device plugins → `plugin_registry`, control plugins → `operation_manager`
2. `mission_store.initialize()` — creates `missions` table if not exists
3. `node_registry.initialize()` — calls `init_db()`, loads all saved nodes from SQLite, triggers async `_connect_node()` for each
4. `zone_manager.initialize()` — loads active zones from SQLite
5. `marker_manager.initialize()` — loads markers from SQLite
6. `failsafe_manager.start()` — starts background heartbeat loop

On shutdown: `failsafe_manager.stop()` → `node_registry.shutdown()` (disconnects all nodes).

### Core singletons (all in `henosync/core/`)

Module-level instances — never instantiate, always import the singleton.

| Singleton            | File                      | Responsibility                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| -------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `node_registry`      | node_registry.py          | Source of truth for all nodes. Persists to SQLite. Manages plugin connect/disconnect/telemetry tasks. Tracks `_telemetry_tasks` and `_liveness_tasks` per node; cancels both on disconnect. Liveness monitor polls `plugin.is_connected()` every 2 s (LIVENESS_CHECK_INTERVAL). Per-frame timeout of 15 s (FRAME_TIMEOUT) catches frozen generators. Status is always set here — never by plugins. In-memory cache: `_nodes: dict[str, Node]`. |
| `operation_manager`  | operation_manager.py      | Starts/stops control plugin operations. Matches devices to plugins by capability. Handles device priority conflicts. Tracks `_operations: dict[str, ActiveOperation]` and `_device_assignments: dict[str, str]`.                                                                                                                                                                                                                               |
| `mission_engine`     | mission_engine.py         | Step-by-step mission execution state machine. One active mission at a time.                                                                                                                                                                                                                                                                                                                                                                    |
| `failsafe_manager`   | failsafe_manager.py       | HEARTBEAT_TIMEOUT=5s, POLL_INTERVAL=1s. Monitors ONLINE/DEGRADED nodes. Triggers safe state + pauses mission on heartbeat loss. Battery threshold check per active mission failsafe config. Tracks `_triggered: dict[str, bool]` to avoid repeated triggering.                                                                                                                                                                                 |
| `telemetry_bus`      | telemetry_bus.py          | Per-node asyncio queues (maxsize=50). Event queue (maxsize=100). Non-blocking puts; drops oldest frame when full. Direct callback subscribers for WS server.                                                                                                                                                                                                                                                                                   |
| `zone_manager`       | zone_manager.py           | Geographic zone CRUD + point-in-polygon (ray casting for polygon, haversine for circle). ZoneType: PERIMETER, NO_GO, SAFE_RETURN, COVERAGE, ALERT, CUSTOM. Persists to SQLite.                                                                                                                                                                                                                                                                 |
| `marker_manager`     | marker_manager.py         | Map marker CRUD. Persists to SQLite.                                                                                                                                                                                                                                                                                                                                                                                                           |
| `plugin_registry`    | plugin_system/registry.py | Maps `plugin_id → class`, `plugin_id → manifest`, `node_id → instance`.                                                                                                                                                                                                                                                                                                                                                                        |
| `event_bus`          | event_bus.py              | Inter-control-plugin messaging (broadcast / point-to-point).                                                                                                                                                                                                                                                                                                                                                                                   |
| `mission_store`      | storage/mission_store.py  | Full SQLite CRUD for missions. Missions ARE persisted — `missions` table in henosync.db.                                                                                                                                                                                                                                                                                                                                                       |
| `connection_manager` | api/websocket_server.py   | Manages WebSocket connection lists; broadcasts telemetry and event messages.                                                                                                                                                                                                                                                                                                                                                                   |

### Database (`~/.henosync/henosync.db`)

SQLite, accessed via `aiosqlite`. Path: `DB_PATH = Path.home() / ".henosync" / "henosync.db"`.

Tables:

- `nodes` — id, name, plugin_id, config (JSON), home_lat/lon/alt, created_at
- `zones` — id, name, zone_type, shape, points (JSON), center_lat/lon, radius_m, created_by, active, color
- `map_markers` — id, name, marker_type, lat, lon, color
- `missions` — id, name, status, steps (JSON), failsafe (JSON), metadata (JSON), created_at, updated_at

### Plugin system — two separate types

**Device plugins** (`NodePlugin` ABC in `henosync_sdk/interfaces.py`)

- 4 abstract methods: `connect`, `disconnect`, `telemetry_stream`, `get_safe_state`
- Standard command methods (optional overrides): `cmd_move_to`, `cmd_stop`, `cmd_return_home`, `cmd_take_photo`, `handle_custom_command`
- 6 optional hooks: `on_reconnect`, `get_video_stream_url`, `validate_config`, `on_mission_start`, `on_mission_end`, `is_connected`
- One class per hardware type; one instance per connected node (node_id → instance in `plugin_registry`)
- `connect(node, config, context: NodePluginContext)` — store `self._context = context`; set `node.specs`; return `(True, "")` or `(False, "reason")`
- `on_reconnect(node, config, context)` called instead of `connect()` on manual reconnect; default delegates to `connect()`
- `send_command(node, envelope: CommandEnvelope)` is non-abstract — dispatches standard commands to `cmd_*` methods, custom commands to `handle_custom_command()`
- `telemetry_stream()` yields `TelemetryFrame` with typed fields (`position`, `battery`, `imu`, `speed`, `signal_strength`, `status_text`, `custom`). Never use a flat `values` dict.
- `TelemetryFrame.to_values_dict()` flattens typed fields to dict for WebSocket broadcast and `node.telemetry` (backward compat with frontend REST polling)
- `TELEMETRY_RATE_HZ: float = 1.0` class attribute — sleep `1.0 / self.TELEMETRY_RATE_HZ`
- `telemetry_stream()` loop must be `while node.id in self._nodes:` — no connection checks; node_registry cancels the task via `is_connected()` and explicit task cancellation on disconnect
- `is_connected(node) -> bool` optional hook — return `False` when the transport is dead; node_registry polls every 2 s and sets DEGRADED if False. Default returns `True` (failsafe heartbeat is the fallback)
- `NodePluginContext`: injected by `node_registry` at connect time. `context.emit_event(title, message, severity)` → operator events panel. `context.command_completed(command_id, success, message)` → async completion signal.
- `CommandEnvelope`: `command_id` (UUID), `command_type` (use `CommandType` enum or any string), `params` dict
- `CommandType` enum: `MOVE_TO`, `STOP`, `RETURN_HOME`, `TAKE_PHOTO`, `ACTIVATE`, `DEACTIVATE`
- Loader validates at load time: if manifest declares `move_to`, plugin must override `cmd_move_to` (WARNING logged if not)
- Loaded from `plugins/<name>/plugin.py` — PluginLoader finds any `NodePlugin` subclass

**Control plugins** (`ControlPlugin` ABC in `plugin_system/control_interfaces.py`)

- 4 abstract methods: `start(context)`, `stop()`, `get_status()`, `get_ui_contribution()`
- 4 optional event handlers: `on_device_joined`, `on_device_left`, `on_message`, `on_operator_input`
- Class attributes: `PLUGIN_ID`, `PLUGIN_NAME`, `PLUGIN_VERSION`, `PLUGIN_AUTHOR`, `OPERATION_NAME`, `OPERATION_DESCRIPTION`, `REQUIRED_CAPABILITIES`, `SUPPORTED_CATEGORIES`, `PRIORITY` (int, higher = wins device conflicts)
- `start()` runs as background asyncio.Task until `stop()` is called; check `self._stop_requested`
- `stop()` must complete within 3 seconds
- `get_status()` must be non-blocking (no awaits) — returns `OperationStatus`
- `get_ui_contribution()` returns `UIContribution` with `config_schema` (drives Mission Planner step config form)
- `_stop_requested`, `_config`, `_context` declared on base class `__init__` — visible to IDEs, no manual declaration needed in subclasses
- Config read via `self._config` (injected by operation_manager before `start()`)

**Plugin loading** (`plugin_system/loader.py`)
Required manifest fields: `id`, `name`, `version`, `author`, `description`, `sdk_version`, `node_types`, `capabilities`.
Loader uses `importlib.util` to load `plugin.py`, then inspects module attrs for `NodePlugin` or `ControlPlugin` subclass.
After finding the class, `_validate_plugin_commands()` cross-checks manifest capability IDs against `cmd_*` method overrides — emits WARNING if mismatch.

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
- `DeviceCategory`: DRONE, PLANE, AGV, BOAT, ROV, ARM, LEGGED, VTOL, TRACKED, STATIC, UNKNOWN
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

- `TelemetryFrame`: node_id, timestamp, sequence_number, typed fields (position, battery, imu, gps, lidar, camera, speed, heading, signal_strength, status_text), custom (dict escape hatch). `to_values_dict()` flattens to dict for WS/REST backward compat.
- `CommandEnvelope`: command_id (UUID), command_type (str or CommandType), params (dict)
- `CommandType` enum: MOVE_TO, STOP, RETURN_HOME, TAKE_PHOTO, ACTIVATE, DEACTIVATE
- `NodePluginContext`: emit_event(title, message, severity), command_completed(command_id, success, message)
- `IMUData`: roll, pitch, yaw, angular_velocity_x/y/z
- `SystemEvent`: id, severity, title, message, node_id (optional), timestamp, acknowledged
- `EventSeverity`: INFO, WARNING, CRITICAL — now in SDK (imported by backend from henosync_sdk)

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

## Plugin maintenance rule

**When editing any device plugin, check whether `plugins/template/plugin.py` needs to be updated to stay consistent.**

Specifically check:

- Does `_NodeState` in the template reflect the same fields and patterns used in the edited plugin?
- Does `disconnect()` show the same cleanup pattern (unsubscribe, close transport)?
- Does `is_connected()` stub reflect the current interface contract?
- Does `telemetry_stream()` use the correct loop condition and typed `TelemetryFrame` fields?

If any of these have drifted, update the template in the same response — do not leave it stale.
Also check other device plugins in `plugins/device/` for the same drift and flag any to the user.

---

## Plugin development rules

### Device plugin checklist

- Inherit `NodePlugin` from `henosync_sdk` (install via `pip install -e packages/plugin-sdk`)
- Call `super().__init__()` in `__init__`; store `self._context = context` in `connect()`
- Implement 4 abstract methods: `connect`, `disconnect`, `telemetry_stream`, `get_safe_state`
- Override `cmd_move_to`, `cmd_stop`, `cmd_return_home` for the capabilities you declare in the manifest
- Override `handle_custom_command` for device-specific commands not in `CommandType`
- Set `node.specs = DeviceSpecs(category=..., capabilities=[...])` in `connect()` for capability matching
- `connect(node, config, context)` returns `(True, "")` on success, `(False, "reason")` on failure — never raise
- `telemetry_stream()` yields `TelemetryFrame` with typed fields (`position`, `battery`, `imu`, etc.) — not `values` dict
- Use `custom={}` on `TelemetryFrame` only for plugin-specific data not covered by typed fields
- `TELEMETRY_RATE_HZ` class attribute controls sleep: `await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)`
- `telemetry_stream()` loop condition must be `while node.id in self._nodes:` only — no connection checks in the loop; node_registry handles status and cancellation
- Override `is_connected(node) -> bool` for faster dead-connection detection (default: `True`). node_registry polls this every 2 s; returning `False` cancels the telemetry stream and sets DEGRADED. Do NOT set node status directly.
- Plugin class must define `PLUGIN_ID` (must match manifest `id`)
- Loader validates at load time: if manifest declares `move_to`, plugin must override `cmd_move_to`

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

`fixed_capabilities` (optional array of `DeviceCapability` strings) — capabilities always present on the device; shown as locked chips in the Add Device modal.
`optional_capabilities` (optional array of `DeviceCapability` strings) — capabilities the user can toggle in the Add Device modal (e.g. attachments). Selected set is stored in `config.selected_capabilities`.
Both are passed through to the frontend as-is from the manifest. Backend `list_plugins()` returns the full manifest dict.

`config_schema` field types: `"string"`, `"number"`, `"boolean"`, `"select"`.
For `"select"`: include `"options": [{"label": "...", "value": "..."}]`.
Optional per field: `required`, `default`, `min`, `max`, `placeholder`, `description`.

---

## Plugins in detail

### UE Sim plugin (`plugins/device/ue-sim/`)

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

### Jackal UGV plugin (`plugins/jackal/`)

Plugin for Clearpath Jackal UGV via ROS2 rosbridge (roslibpy). Connects over WiFi — no ROS2 install required on the Henosync machine. AGV category. All 5 milestones implemented.

Current milestone: **Milestone 5** — all features complete.

Topics subscribed (standard Clearpath Jackal ROS2 Jazzy defaults — update module-level constants in plugin.py if your Jackal namespace differs):

| Constant | Topic | Type | Data |
|---|---|---|---|
| `GPS_TOPIC` | `/navsat/fix` | `sensor_msgs/NavSatFix` | lat, lon, alt |
| `IMU_TOPIC` | `/imu/data` | `sensor_msgs/Imu` | orientation quaternion → yaw heading |
| `BATTERY_TOPIC` | `/battery_state` | `sensor_msgs/BatteryState` | percentage (×100 → battery_percent) |
| `ODOM_TOPIC` | `/odometry/filtered` | `nav_msgs/Odometry` | twist.linear.x/y → speed (magnitude) |

Topics published:

| Constant | Topic | Type | Used by |
|---|---|---|---|
| `CMDVEL_TOPIC` | `/cmd_vel` | `geometry_msgs/Twist` | `cmd_stop`, `get_safe_state` |
| `GOAL_TOPIC` | `/goal_pose` | `geometry_msgs/PoseStamped` | `cmd_move_to` (requires Nav2) |

Key notes:
- `gps_received` guard prevents null-island placement before first GPS fix
- `origin_lat`/`origin_lon` captured on first GPS fix; used by `cmd_move_to` for equirectangular GPS→local projection (accurate <1 km)
- `cmd_move_to` requires Nav2 running on the Jackal with GPS-fused EKF (`/odom`→`/map` transform)
- `get_safe_state` and `cmd_stop` both publish zero-velocity Twist to `/cmd_vel`
- Camera: `get_video_stream_url()` returns `http://<host>:<camera_port>/stream?topic=<camera_topic>` — requires `web_video_server` running on the Jackal (`ros2 run web_video_server web_video_server`)
- Config fields: `host` (required), `port` (default 9090), `camera_port` (default 8080), `camera_topic` (default `/front_camera/image_raw`)

Milestone 1 ✓: connect to rosbridge, heartbeat telemetry, device goes Online.
Milestone 2 ✓: GPS on map, IMU heading, battery, speed.
Milestone 3 ✓: stop and emergency stop via `/cmd_vel` zero-velocity Twist.
Milestone 4 ✓: move-to GPS waypoint via Nav2 `/goal_pose` (requires Nav2 running on Jackal).
Milestone 5 ✓: camera feed via `web_video_server` with configurable port and topic.

### Control template plugin (`plugins/control-template/`)

Starter control plugin template. Shows `_stop_requested` loop pattern, `self._config` access, `context.devices` iteration, and optional `on_device_joined`/`on_device_left` handlers.

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

| Date       | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-05-04 | Initial CLAUDE.md created from full codebase audit                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-04 | Removed `plugins/sim-dummy/`, `plugins/test-movements/` — simulation cleanup                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-04 | Removed `transport/simulation.py`; cleaned `transport/registry.py` to ros2 only                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-05-04 | Jackal plugin: removed `internal_sim` transport mode; always uses ros2_bridge                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-05-04 | Jackal manifest: removed `transport` select + `home_lat`/`home_lon` fields; `host` now required                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-05-04 | Fixed `mission_engine._execute_loop` name collision — LOOP step handler renamed to `_execute_loop_step`                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-04 | Fixed `failsafe_manager.emergency_stop_all` — removed duplicated abort+safe-state block                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-04 | Fixed `datetime.utcnow()` → `datetime.now(timezone.utc)` in models/mission.py, node.py, telemetry.py                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-04 | Fixed `HomePage.tsx` — added missing `getStreamUrl` import; removed undefined `api` namespace reference                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-04 | MissionPage Run Mission wired to real backend: sequential `startOperation` + poll `getOperations` loop                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 2026-05-04 | Added maintenance rule to CLAUDE.md requiring updates after every code change                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-05-04 | Removed `plugins/area-patrol/` — control plugins deferred; focus is device plugins                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-11 | Added `plugins/ue-sim/` — incremental test plugin for UE ROS2 sim via rosbridge                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-05-11 | Added roslibpy to setup.bat, setup.sh, pyproject.toml                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 2026-05-12 | Full codebase audit — comprehensive CLAUDE.md rewrite; corrected: missions persist to SQLite (not in-memory), useNodes polls at 5s (not 3s), useOperations polls at 2s (not 1s), transport system exists but unused by current plugins                                                                                                                                                                                                                                                                                        |
| 2026-05-12 | Added Engineering Principles section (think before coding, simplicity first, surgical changes, goal-driven execution)                                                                                                                                                                                                                                                                                                                                                                                                         |
| 2026-05-12 | ue-sim Milestone 2: subscribed to global_gps (NavSatFix) and car_state (CarState); position on map, speed in telemetry                                                                                                                                                                                                                                                                                                                                                                                                        |
| 2026-05-12 | ue-sim Milestone 2b: implemented get_video_stream_url() for web_video_server camera feed                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 2026-05-12 | Removed plugins/jackal/ entirely                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 2026-05-12 | Fixed all ruff linting violations in backend (I001 import order, W292 missing newlines, W291 trailing whitespace, F401 unused import, N806 uppercase locals in mission_engine and zone_manager)                                                                                                                                                                                                                                                                                                                               |
| 2026-05-15 | Rewrote plugins/template/plugin.py — per-node \_NodeState, node.specs in connect(), gps_received guard, get_safe_state() no longer kills telemetry, params validated in send_command()                                                                                                                                                                                                                                                                                                                                        |
| 2026-05-15 | Fixed plugins/template/manifest.json — valid node_types category, removed unused transport field                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 2026-05-15 | Added **init** to ControlPlugin base class declaring \_stop_requested, \_config, \_context as typed attributes                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-05-15 | Added plugins/control-template/ — starter control plugin template with stop loop pattern, config access, device iteration, and event handlers                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-05-15 | connect() return type changed from bool to tuple[bool, str] — reason surfaced to operator on failure via event; on_reconnect() optional hook added to NodePlugin                                                                                                                                                                                                                                                                                                                                                              |
| 2026-05-15 | failsafe_manager: get_safe_state() result.success now checked; emits CRITICAL event if safe state fails rather than silently logging                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-15 | Added TELEMETRY_RATE_HZ class attribute to NodePlugin; plugins use 1.0/TELEMETRY_RATE_HZ in sleep instead of hardcoded 1.0                                                                                                                                                                                                                                                                                                                                                                                                    |
| 2026-05-15 | SDK overhaul: henosync_sdk is now canonical for all plugin-facing types; backend imports from SDK; plugins import from henosync_sdk directly (no sys.path hacks); SDK installed via pip install -e packages/plugin-sdk                                                                                                                                                                                                                                                                                                        |
| 2026-05-15 | SDK now contains interfaces.py (NodePlugin), control_interfaces.py (ControlPlugin), models.py (all shared types); backend node.py and telemetry.py re-export SDK types and add backend-only types (NodeCreate, SystemEvent, etc.)                                                                                                                                                                                                                                                                                             |
| 2026-05-15 | Updated setup.bat, setup.sh, and CI workflow to install SDK into backend venv                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-05-15 | Typed TelemetryFrame: replaced values dict with structured fields (position, battery, imu, gps, lidar, speed, signal_strength, status_text, custom); added to_values_dict() for WS/REST backward compat                                                                                                                                                                                                                                                                                                                       |
| 2026-05-15 | Added CommandType enum and CommandEnvelope model; all send_command calls now typed; DeviceProxy creates envelopes, plugins receive them                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-15 | NodePluginContext injected at connect() — plugins call context.emit_event() and context.command_completed(); stored as self.\_context; node_registry creates per-node context with telemetry_bus callbacks                                                                                                                                                                                                                                                                                                                    |
| 2026-05-15 | NodePlugin send_command now non-abstract with standard dispatch; cmd_move_to/cmd_stop/cmd_return_home/cmd_take_photo/handle_custom_command are optional overrides; abstract methods reduced to 4                                                                                                                                                                                                                                                                                                                              |
| 2026-05-15 | Loader manifest validation: _validate_plugin_commands() warns at load time if manifest declares move_to/stop/etc but plugin doesn't override the matching cmd_\* method                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-15 | Added IMUData model; added DeviceCategory: LEGGED, VTOL, TRACKED, STATIC; EventSeverity moved to SDK                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-15 | DeviceProxy get_gps_data/get_battery_data/get_lidar_scan now read from typed TelemetryFrame via node_registry.get_last_frame(); node_registry.\_last_frames stores latest frame per node                                                                                                                                                                                                                                                                                                                                      |
| 2026-05-27 | Centralised device status detection: node_registry tracks telemetry/liveness tasks per node and cancels both on disconnect; per-frame timeout (15 s) catches frozen generators; liveness monitor polls plugin.is_connected() every 2 s and sets DEGRADED if False; added is_connected() optional hook to NodePlugin (default True); telemetry loops in all plugins simplified to `while node.id in self._nodes:` only; ue-sim overrides is_connected() with ros.is_connected + last_message_time check (MESSAGE_TIMEOUT=10 s) |
| 2026-05-27 | node_registry liveness monitor wraps is_connected() in asyncio.wait_for(timeout=5.0) — hanging plugin implementations can no longer block the monitor; ue-sim MESSAGE_TIMEOUT moved from module constant to class attribute so subclasses can override it                                                                                                                                                                                                                                                                     |
| 2026-05-27 | Removed plugins/template/ — superseded by ue-sim as the reference implementation                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 2026-05-27 | Added fixed_capabilities and optional_capabilities arrays to manifest format; Add Device modal chips are now driven entirely by these fields — no frontend code needed per plugin; ue-sim declares gps+camera fixed; template declares gps+battery fixed, camera+lidar optional                                                                                                                                                                                                                                               |
| 2026-06-01 | Added plugins/jackal/ — Clearpath Jackal UGV plugin (all 5 milestones: connect, GPS/IMU/battery/speed, stop, move-to via Nav2, camera feed)                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-07-27 | Reorganised plugins/ into device/, control/, templates/; app.py now runs PluginLoader separately for each; templates/ is never scanned; updated CLAUDE.md plugin maintenance rule to reference new paths                                                                                                                                                                                                                                                                                                                      |
| 2026-07-27 | Added plugins/control/auto-navigate/ — placeholder control plugin with StepType enum (MOVE*TO_MARKER, MOVE_TO_ZONE, AREA_COVERAGE, PERIMETER_PATROL), NavigationStep dataclass, step dispatch, and stubbed \_execute*\* methods                                                                                                                                                                                                                                                                                               |
| 2026-08-02 | Merged upstream/develop into develop — moved plugins/jackal/ to plugins/device/jackal/ to match the new device/control/templates layout                                                                                                                                                                                                                                                                                                                                                                                     |

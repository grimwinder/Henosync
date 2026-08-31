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
│   │   ├── ue-sim/       Device plugin for UE AirSim SUV via rosbridge
│   │   └── turtlebot3/   TurtleBot3 Burger via rosbridge — VICON or GPS positioning
│   ├── control/          Installed control plugins (one subfolder per plugin)
│   │   ├── auto-navigate/ Autonomous navigation — move to marker/zone, area coverage, perimeter patrol
│   │   └── teleop/        Manual arrow-key driving for a single ground vehicle
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
- `on_operator_input(input_key, value)` is now wired end-to-end: `POST /api/operations/{plugin_id}/input` → `operation_manager.send_operator_input()` → the running plugin instance's `on_operator_input()`. 400s if the operation isn't running. Frontend has no generic UI for this — each control plugin's panel opts in explicitly (see `PluginsPage.tsx` teleop handling below).

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

- `move_to(lat, lon, alt)` — always dispatches `CommandType.MOVE_TO` with `lat`/`lon`/`alt` in params. **Additionally**, for local-frame devices (`coordinate_frame="local"` with `node.local_origin` set — e.g. VICON-tracked `turtlebot3`), also sends the equivalent local `x`/`y`/`z` metres (`_gps_to_local()`), matching `cmd_move_to(node, lat, lon, alt, x=None, y=None, z=None)`'s contract in `interfaces.py` — a device can use whichever representation it needs (`turtlebot3.cmd_move_to()` converts `x`/`y` back to lat/lon itself when present, then runs identical distance/bearing logic either way). **Does NOT check no-go zones** — despite `zone_manager.py`'s docstring claiming it does, the actual implementation never called it; callers needing that check must do it themselves (see `auto-navigate._go_to_waypoint()`).
  - History here matters: this used to send x/y/z **instead of** lat/lon for local-frame devices, but `send_command()`'s `MOVE_TO` dispatch at the time only read `lat`/`lon` from params — so local-frame devices silently got `cmd_move_to(lat=0.0, lon=0.0)` (bug, found 2026-08-23). Two independent fixes for this landed in parallel on different branches: this repo's fix made `move_to()` always send lat/lon and dropped the x/y/z branch entirely (removing `_gps_to_local()`); `develop`'s fix instead extended the dispatcher to forward `x`/`y`/`z` through as additional kwargs and taught `turtlebot3.cmd_move_to()` to accept and convert them. Reconciled 2026-08-24 by keeping develop's dispatcher/turtlebot3 design and restoring `_gps_to_local()` — `move_to()` now sends **both** representations always, so lat/lon is never lost (the original bug) and local-frame devices that want metres still get them (develop's design intent, which a lat/lon-only fix would have silently made permanently dead code without being incorrect for turtlebot3 specifically, since VICON positions are already expressed in the same coordinate convention as real markers).
- `stop()`, `return_home()` — dispatch named commands
- `get_gps_data()`, `get_lidar_scan()`, `get_camera_feed()`, `get_battery_data()` — standard-format data from telemetry dict
- `has_capability(DeviceCapability)`, `meets_requirement(CapabilityRequirement)` — capability negotiation
- Coordinate conversion: `_gps_to_local()` (equirectangular, accurate <1km) — used by `move_to()` above. `local_to_gps()` (the reverse) has no caller anywhere in the codebase — `vicon_manager.py` and `henosync_sdk/positioning.py` each have their own independent, separate implementation of the same conversion.
- `category` comes from `node.specs.category` (returns `UNKNOWN` if specs not set)

### FleetContext (`core/fleet_context.py`)

Injected into control plugins. Provides:

- `context.devices` — list of `DeviceProxy` objects matched at operation start
- `context.recruit_device(device_id)` — dynamically add device (checks priority, updates `_device_assignments`). **Doesn't check capabilities/category** — only priority and availability. `operation_manager.recruit_device_into_operation()` (below) validates against the plugin's `REQUIRED_CAPABILITIES`/`SUPPORTED_CATEGORIES` before calling this, so use that from the REST layer rather than calling `context.recruit_device()` directly if capability safety matters.
- `context.release_device(device_id)` — return device to pool
- `context.get_available_devices(capabilities, categories)` — query unassigned devices
- `context.zone_manager` — direct access to zone_manager singleton
- `context.marker_manager` — direct access to marker_manager singleton (mirrors `context.zone_manager` exactly); needed for `auto-navigate`'s `MOVE_TO_MARKER` to resolve marker IDs
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
| operations.py | `GET /api/operations`, `POST /api/operations/start`, `POST /api/operations/{plugin_id}/stop`, `POST /api/operations/{plugin_id}/input`, `GET /api/operations/{plugin_id}/recruitable`, `POST /api/operations/{plugin_id}/recruit`, `GET /api/control-plugins` |
| zones.py      | `GET /api/zones`, `POST /api/zones`, `DELETE /api/zones/{id}`                                                                                                            |
| markers.py    | `GET /api/markers`, `POST /api/markers`, `DELETE /api/markers/{id}`                                                                                                      |
| vicon.py      | `GET /api/vicon/connection`, `POST /api/vicon/connection`, `DELETE /api/vicon/connection`, `GET /api/vicon/objects`, `POST /api/vicon/origin`                           |
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
| `useRecruitableDevices(pluginId, enabled)` | 3000ms, only while `enabled` (an operation is running) |

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

**Movement (added for teleop):** declares `MOVE_2D` (fixed capability) and a custom `cmd_vel` capability — no `move_to`/`cmd_move_to`, since AirSim's car has no autopilot and must be driven by continuous throttle/steering, not GPS waypoints. `handle_custom_command()` handles `cmd_vel` (`params: linear, angular`, both -1..1), maps it to `airsim_ros_pkgs/CarControls` and publishes on `CAR_CMD_TOPIC = /airsim_node/SUV1/car_cmd` via a `roslibpy.Topic` publisher created in `connect()` (`state.car_cmd_topic`). `linear < 0` sets `is_manual_gear=True, manual_gear=-1` for reverse; `linear`/`angular` both zero sets `brake=1.0`. `get_safe_state()` now publishes a full-brake `CarControls` message (previously a no-op, since there was no movement to make safe).

### Teleop plugin (`plugins/control/teleop/`)

Manual arrow-key driving for a single ground vehicle. `REQUIRED_CAPABILITIES=[MOVE_2D]`, `SUPPORTED_CATEGORIES=[AGV]`, binds the first matched device in `context.devices`. `PRIORITY=10` so manual control preempts autonomous operations (e.g. `auto-navigate`) on device conflicts.

- `on_operator_input(input_key, value)` — `input_key` is `"up"|"down"|"left"|"right"`, `value` is `True`/`False` (keydown/keyup). Updates an internal pressed-key set only; no device I/O here.
- `start()` loop resends `device.send_command("cmd_vel", {"linear", "angular"})` at `SEND_RATE_HZ=5.0` computed fresh each tick from the pressed-key set — up/down drive linear, left/right drive angular, both in [-1, 1].
- `stop()` clears all pressed keys and sends one final `cmd_vel(0, 0)` — the operation can never be stopped mid-drive.
- Frontend: `useArrowKeyDrive()` (`renderer/hooks/useArrowKeyDrive.ts`) is mounted once at the top of `PluginsPage` (not conditionally inside `ControlPluginPanel` — it's driven by whether the `teleop` operation is running, from `useOperations()`, so it stays live even if you navigate away from the Plugins page while teleop is running). Binds `window` keydown/keyup listeners, supports both arrow keys and WASD, dedupes OS key-repeat, and — critically — releases all held keys via `sendOperatorInput()` on cleanup so the vehicle never keeps driving after the operation stops. `ControlPluginPanel` still shows the live drive-status chip when `plugin.id === "teleop"`.
- Wired against `ue-sim` and `turtlebot3` — any `AGV` device plugin implementing a `cmd_vel` custom command works automatically, since the control plugin has no device-specific code.

### Auto Navigate plugin (`plugins/control/auto-navigate/`)

`MOVE_TO_MARKER`, `MOVE_TO_ZONE`, and `AREA_COVERAGE` are implemented; `PERIMETER_PATROL` is still an unimplemented stub (deferred). `REQUIRED_CAPABILITIES=[GPS, MOVE_2D]`.

- `_resolve_target()` resolves the target via `context.marker_manager.get_marker()` / `context.zone_manager.get_zone()` (zone centroid = circle center, or average of polygon points) — **once per step, not once per device** (see multi-device below).
- `_go_to_waypoint()` checks the target against `context.zone_manager.is_in_no_go_zone()` once (rejects with an alert; does NOT check the path, only the destination), then **prefers the device's own `cmd_move_to()` via `device.move_to()`** — e.g. `turtlebot3`, which drives with real heading from `/odom` and needs no heading estimation. Detects whether a real `cmd_move_to` exists by checking for `"not implemented"` in the returned `CommandResult.message` (the exact string every unimplemented `cmd_*` stub in the SDK returns — not a guess). Falls back to `_navigate_to()` (generic `cmd_vel` + GPS course-over-ground heading estimate, same mechanism `teleop` uses) only for devices without a real `cmd_move_to`, e.g. `ue-sim`.
- `_navigate_to()`'s heading estimate is exponential-smoothed (`heading + 0.5 * angle_diff(new_estimate, heading)`) to avoid turn-direction oscillation near the 180°-antipodal case, and the controller never fully stops to turn in place (`MIN_ALIGNMENT_FRACTION` keeps a minimum forward crawl) — a stationary robot produces no new GPS fix, so a hard turn-in-place would freeze the heading estimate. `MIN_MOVE_FOR_HEADING_M`/`MAX_ANGULAR`/`MIN_ALIGNMENT_FRACTION` are physically coupled — the minimum turning-circle diameter must stay larger than `MIN_MOVE_FOR_HEADING_M` or the heading estimate can never refresh mid-turn. All three issues were only found via simulation (a unicycle-model physics harness driving the real controller code), not obvious from reading the code.
- **Obstacle reaction (not detection) lives in the `_navigate_to()` fallback path only** — checks `send_command`'s `CommandResult` and reacts to `data["reason"] == "obstacle"` — alerts once, waits up to `OBSTACLE_BLOCKED_TIMEOUT_S=15s` for the path to clear, aborts if it doesn't. `start()` warns once if an assigned device has no LiDAR (`DeviceCapability.LIDAR`). **Currently dead code in practice** — built against a since-removed generic `ros2-diffdrive` plugin that set `data["reason"]="obstacle"` on a blocked `cmd_vel`; no currently-loaded device plugin (`ue-sim`, `turtlebot3`) does this. The preferred `move_to()`/`turtlebot3` path has no obstacle detection of any kind, dead code or otherwise.
- `step.speed_ms` (from `NavigationStep`) is unused by `_navigate_to()` — no generic way to convert an absolute m/s target into the normalized `cmd_vel` contract without knowing each device's calibration.

**Multi-device (2026-08-23):** for `MOVE_TO_MARKER`/`MOVE_TO_ZONE`, `_execute_step()` resolves the target **once** and every device in `context.devices` navigates there **concurrently** (`_run_on_devices()` → `asyncio.gather`) — a shared target, all robots start together, not a per-device queue and not sequential (it was sequential — `for device in context.devices: await ...` — until this change; that meant device 2 didn't move until device 1 finished the whole step). Per-device state that used to be singular is now keyed, since multiple devices are in flight at once:
- `self._current_devices: dict[device_id, DeviceProxy]` (was `self._current_device`, singular) — every device currently navigating. `stop()` now calls `device.stop()` on all of them concurrently (needed for the same reason as before: `turtlebot3.cmd_move_to()` blocks on its own internal stop flag, not ours).
- `self._device_status: dict[device_name, str]` (was one shared `self._status_text`) — `_go_to_waypoint()`/`_navigate_to()` write here now instead, since concurrent devices would otherwise race to overwrite one string. `get_status()` joins these into `status_text` (e.g. `"RobotA: 4.2 m to target; RobotB: Arrived"`) and also exposes the raw dict via `OperationStatus.data["devices"]`.

**Adding a device to a running operation** — manual only, no automatic join:
- `operation_manager.recruit_device_into_operation(plugin_id, device_id)` validates the device against the plugin's `REQUIRED_CAPABILITIES`/`SUPPORTED_CATEGORIES` (unlike `FleetContext.recruit_device()`, which only checks priority/availability — see FleetContext section), then calls `context.recruit_device()` and the plugin's `on_device_joined(proxy)`.
- `operation_manager.get_recruitable_devices(plugin_id)` — devices online, matching requirements, not already assigned anywhere; backs the "Available devices" list in `PluginsPage`.
- `AutoNavigatePlugin.on_device_joined(device)` — if a `MOVE_TO_MARKER`/`MOVE_TO_ZONE` target is currently active (`self._current_target`, set by `_execute_step()`), fires the new device toward it as a background task (`asyncio.create_task`), concurrently with whatever's already in flight. Needs `self._context` — stashed in `start()`, since the `ControlPlugin` base class declares `self._context` but `operation_manager` never actually populates it, and `on_device_joined()`'s signature (part of the `ControlPlugin` ABC, shared by all control plugins) doesn't receive `context` as a parameter.
- Frontend: `PluginsPage.tsx`'s `ControlPluginPanel` polls `GET /api/operations/{plugin_id}/recruitable` (3s, only while running) and shows an "Add" button per candidate device.

Tested via simulation: `_navigate_to()` convergence across a full sweep of starting headings/targets, no-go zone rejection, obstacle block/recover/timeout reaction, concurrent multi-device dispatch (proved via artificial per-device delays and checking start-time overlap), mid-operation join sending the new device to the active target, and `stop()` interrupting every concurrently-navigating device — all with fake devices. Also verified end-to-end through the real REST layer (recruit/recruitable routes) with injected fake online nodes. Not yet tested against real devices, `turtlebot3`, or `ue-sim` live.

**AREA_COVERAGE (2026-08-31):** `_execute_area_coverage(step, context)` — a step-level method like `MOVE_TO_MARKER`/`MOVE_TO_ZONE`, not per-device — resolves the target zone, splits it into `len(context.devices)` parallel strips via `_generate_coverage_paths()`, captures each device's current GPS fix as its individual return-to-start position, then runs every device on its own strip concurrently via `_run_coverage_path()` (`asyncio.gather`). The split happens once, using however many devices are assigned when the step starts — a device recruited later via `on_device_joined()` mid-sweep is not folded in (static partitioning, matches point-to-point's existing no-re-split behaviour for a mid-operation join).

- `_generate_coverage_paths(zone, num_robots, spacing_m, angle_deg)` (module-level, pure geometry) — converts the zone to a local-XY polygon (`_zone_polygon_and_origin`; circle zones approximated as a `CIRCLE_APPROXIMATION_SIDES`-gon), rotates it so `angle_deg` (0=east, 90=north, matching the field's existing doc) aligns with +x (`_rotate`/`_unrotate`), slices the rotated bounding box into `num_robots` bands of **equal area** via `_equal_area_band_bounds()` (not equal height — see below), and generates a boustrophedon (alternating left-right/right-left) sweep within each band at `spacing_m` line spacing. Per-line extent is found by **sampling** (`_inside_extent` + `_point_in_polygon_xy`, ray-casting) rather than exact polygon-edge intersection — a scan line's covered extent is the outer span of inside samples, not a per-gap breakdown, so a sharply concave zone can get a slightly optimistic or stair-stepped sweep near inward corners. Sample count is capped (`MAX_COVERAGE_SAMPLES=20000`, coarsened rather than failed if exceeded — same spirit as `mission_engine`'s `MAX_ITERATIONS`). Raises `ValueError` (caught by `_execute_area_coverage`, surfaced via `context.send_alert`) for zero robots, non-positive spacing, a zone too small to have any extent, or unusable zone geometry.
- `_equal_area_band_bounds(polygon, num_robots, x_min, x_max, y_min, y_max)` — the original version split `[y_min, y_max]` into `num_robots` equal-**height** bands, which badly unbalances coverage time on any non-rectangular zone (a short/wide band and a tall/narrow band can hold very different amounts of actual zone area — caught by the user testing the feature via the Coverage Planner artifact below, on an L-shaped zone). Fixed (2026-08-31) to split by equal **area** instead: samples `_width_at_y()` at `AREA_PROFILE_Y_SAMPLES=150` heights to build a cumulative area-vs-y profile (trapezoidal integration), then finds the y at each `1/num_robots` fraction of total area by interpolating on that profile. `_width_at_y()` (`AREA_PROFILE_X_SAMPLES=80` samples) estimates width as the *fraction* of samples inside the polygon scaled by the full x-extent — deliberately different from `_inside_extent()`'s outer-span notion, since area-balancing must discount a concave zone's real gaps rather than credit them as covered. This is a fixed one-time cost per step start (150×80 = 12,000 point-in-polygon checks), independent of zone size/spacing, so it isn't subject to `MAX_COVERAGE_SAMPLES` coarsening. A pointed region (e.g. a triangular corner) can still end up as a tall, narrow band to make up its equal share of area, which can produce a very short or empty sweep path for whichever robot gets it — inherent to a 1D horizontal-band split, not a bug; `_run_coverage_path()` already handles an empty path gracefully.
- `_run_coverage_path(device, waypoints, start_position, context)` — registers the device in `_current_devices` once for the whole path (not per-waypoint, so `stop()`/the collision guard treat a mid-sweep device the same as one mid-single-waypoint nav), walks `waypoints` in order via the new `_navigate_one_waypoint()` helper, then navigates to `start_position` if one was captured. `_device_status` reports sweep progress (`"Sweeping — waypoint 3/8"`) and the final outcome.
- Extracted `_navigate_one_waypoint(device, lat, lon, context)` out of what was `_go_to_waypoint_tracked()` — the actual "drive to one point, honoring collision-guard pause/retry" logic, reusable per-waypoint-in-a-loop by `_run_coverage_path()` and as a single call by `_go_to_waypoint_tracked()` (which now only adds the `_current_devices` registration + final status). It also records `self._device_target[device.id] = (lat, lon)` on every call.
- `_collision_guard()` previously judged yield priority by comparing both devices' distance to the one shared `self._current_target` — meaningless for `AREA_COVERAGE`, where each device has its own distinct waypoint at any given moment and `self._current_target` stays `None` throughout. It now reads `self._device_target.get(device.id, self._current_target)` per device (falling back to the shared target for `MOVE_TO_MARKER`/`MOVE_TO_ZONE`, unchanged behaviour there), and the `len(self._current_devices) < 2` gate no longer also requires `self._current_target is not None` — so the guard is live during coverage sweeps too, not just point-to-point moves. `self._device_target` is popped in the same `finally` blocks that already clean up `_current_devices`/`_collision_paused`.
- `coverage_angle_deg` (already existed on `NavigationStep`, defaulting to 0.0) was previously dead — not read by `_parse_steps()` and not exposed in `get_ui_contribution()`'s `config_schema`. Both fixed; it's now an operator-configurable "Sweep Angle (°)" number field, needed for the feature to be usable on non-square zones.

Verified via simulation (`test_area_coverage.py`, `test_area_coverage_exec.py` — not committed, scratch scripts): geometry — rotate/unrotate round-trips, point-in-polygon edge cases, a 3-way split of a square zone stays within its bounding box, circle-zone approximation, `num_robots=1` degenerate case, `ValueError` on zero robots/non-positive spacing, and — added with the equal-area fix — a 4-way split of an L-shaped (concave) zone where each band's actual area is independently re-measured on a 400×400 grid and confirmed within 0.3% of an equal share, versus 29.4% max deviation for a naive equal-height split of the same zone (confirms both that the fix works and that it was worth doing). Execution — two fake devices given genuinely different sweep paths (not one shared target), each returns to its own captured start position, per-device status reflects sweep progress and completion, `_current_devices`/`_device_target` are cleared after completion, a device with `_stop_requested` already set issues zero `move_to()` calls and reports "Stopped", and the collision guard still detects and pauses the farther-from-its-own-target device when two devices' fake positions are placed within `MIN_SEPARATION_M` during a coverage run. Not yet tested against real devices, `turtlebot3`, or `ue-sim` live.

A companion visualization (not part of the repo — an interactive artifact built for manual testing) runs this exact geometry in-browser: draw or pick a zone shape, set robot count/spacing/angle, and see the equal-area bands and each robot's generated sweep path directly, including live area-balance diagnostics. This is what surfaced the original equal-height bug.

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

- All positions system-wide are WGS84 GPS (lat/lon/alt). DeviceProxy handles conversion for local-frame (odometry) devices. This includes zones/markers drawn in VICON map mode: the frontend still passes raw arena metres (VICONMap.tsx's `lon=x_m, lat=y_m` convention), but `zones.py`/`markers.py`'s POST routes convert them to real WGS84 at creation time via `vicon_manager.origin` (an arena-wide anchor, separate from any single robot's `home_lat`/`home_lon`) before storing — so `auto-navigate` and everything else can keep assuming real WGS84 unconditionally. `VICONMap.tsx` reverse-converts back to local metres for its own SVG rendering. Set the arena origin via the VICON panel (title bar) before drawing VICON-mode zones/markers — both routes 400 if it isn't set yet.
- Rosbridge connection: Henosync connects via roslibpy WebSocket (default port 9090). No ROS2 install or ROS_DOMAIN_ID needed on the Henosync machine. Works with Unreal Engine sim via rclUE bridge.
- `mission_engine` and `operation_manager` are parallel execution paths. MissionPage UI uses operation_manager only. Mission engine is wired to REST API but not yet used in UI.
- Failsafe manager runs independently and cannot be bypassed by plugins.
- Emergency stop: `POST /api/safety/emergency-stop` → stops all operations → aborts mission → concurrent safe state all nodes.
- No simulation transports exist. `transport/` contains only `ROS2Transport`. UE sim connects via same rosbridge path as real hardware.
- Setup: `scripts/setup.bat` / `scripts/setup.sh` create `.venv` and install packages with pip directly. Poetry (`pyproject.toml`) is for documentation only — not used for actual installs.
- **Python version: 3.11 or 3.12 required.** 3.13+ is not supported — `vicon-dssdk` and several ROS2 packages have no wheels for it yet. `setup.bat` uses the Windows py launcher (`py -3.12` / `py -3.11`); `setup.sh` searches for `python3.12` / `python3.11` explicitly. Both fail fast with a clear message if neither is found.
- Plugin loader identifies plugin type by inspecting module for `NodePlugin` or `ControlPlugin` subclass — first match wins.

---

## Change log

| Date       | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-05-04 | Initial CLAUDE.md created from full codebase audit                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-04 | Removed `plugins/sim-dummy/`, `plugins/test-movements/` — simulation cleanup                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 2026-05-04 | Removed `transport/simulation.py`; cleaned `transport/registry.py` to ros2 only                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-04 | Jackal plugin: removed `internal_sim` transport mode; always uses ros2_bridge                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-04 | Jackal manifest: removed `transport` select + `home_lat`/`home_lon` fields; `host` now required                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-04 | Fixed `mission_engine._execute_loop` name collision — LOOP step handler renamed to `_execute_loop_step`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-04 | Fixed `failsafe_manager.emergency_stop_all` — removed duplicated abort+safe-state block                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-04 | Fixed `datetime.utcnow()` → `datetime.now(timezone.utc)` in models/mission.py, node.py, telemetry.py                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-05-04 | Fixed `HomePage.tsx` — added missing `getStreamUrl` import; removed undefined `api` namespace reference                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-04 | MissionPage Run Mission wired to real backend: sequential `startOperation` + poll `getOperations` loop                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 2026-05-04 | Added maintenance rule to CLAUDE.md requiring updates after every code change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-04 | Removed `plugins/area-patrol/` — control plugins deferred; focus is device plugins                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-05-11 | Added `plugins/ue-sim/` — incremental test plugin for UE ROS2 sim via rosbridge                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-11 | Added roslibpy to setup.bat, setup.sh, pyproject.toml                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 2026-05-12 | Full codebase audit — comprehensive CLAUDE.md rewrite; corrected: missions persist to SQLite (not in-memory), useNodes polls at 5s (not 3s), useOperations polls at 2s (not 1s), transport system exists but unused by current plugins                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 2026-05-12 | Added Engineering Principles section (think before coding, simplicity first, surgical changes, goal-driven execution)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 2026-05-12 | ue-sim Milestone 2: subscribed to global_gps (NavSatFix) and car_state (CarState); position on map, speed in telemetry                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 2026-05-12 | ue-sim Milestone 2b: implemented get_video_stream_url() for web_video_server camera feed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-05-12 | Removed plugins/jackal/ entirely                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 2026-05-12 | Fixed all ruff linting violations in backend (I001 import order, W292 missing newlines, W291 trailing whitespace, F401 unused import, N806 uppercase locals in mission_engine and zone_manager)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-05-15 | Rewrote plugins/template/plugin.py — per-node \_NodeState, node.specs in connect(), gps_received guard, get_safe_state() no longer kills telemetry, params validated in send_command()                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 2026-05-15 | Fixed plugins/template/manifest.json — valid node_types category, removed unused transport field                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 2026-05-15 | Added **init** to ControlPlugin base class declaring \_stop_requested, \_config, \_context as typed attributes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| 2026-05-15 | Added plugins/control-template/ — starter control plugin template with stop loop pattern, config access, device iteration, and event handlers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-15 | connect() return type changed from bool to tuple[bool, str] — reason surfaced to operator on failure via event; on_reconnect() optional hook added to NodePlugin                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 2026-05-15 | failsafe_manager: get_safe_state() result.success now checked; emits CRITICAL event if safe state fails rather than silently logging                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-05-15 | Added TELEMETRY_RATE_HZ class attribute to NodePlugin; plugins use 1.0/TELEMETRY_RATE_HZ in sleep instead of hardcoded 1.0                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-05-15 | SDK overhaul: henosync_sdk is now canonical for all plugin-facing types; backend imports from SDK; plugins import from henosync_sdk directly (no sys.path hacks); SDK installed via pip install -e packages/plugin-sdk                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 2026-05-15 | SDK now contains interfaces.py (NodePlugin), control_interfaces.py (ControlPlugin), models.py (all shared types); backend node.py and telemetry.py re-export SDK types and add backend-only types (NodeCreate, SystemEvent, etc.)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 2026-05-15 | Updated setup.bat, setup.sh, and CI workflow to install SDK into backend venv                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-15 | Typed TelemetryFrame: replaced values dict with structured fields (position, battery, imu, gps, lidar, speed, signal_strength, status_text, custom); added to_values_dict() for WS/REST backward compat                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-15 | Added CommandType enum and CommandEnvelope model; all send_command calls now typed; DeviceProxy creates envelopes, plugins receive them                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-15 | NodePluginContext injected at connect() — plugins call context.emit_event() and context.command_completed(); stored as self.\_context; node_registry creates per-node context with telemetry_bus callbacks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-05-15 | NodePlugin send_command now non-abstract with standard dispatch; cmd_move_to/cmd_stop/cmd_return_home/cmd_take_photo/handle_custom_command are optional overrides; abstract methods reduced to 4                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 2026-05-15 | Loader manifest validation: _validate_plugin_commands() warns at load time if manifest declares move_to/stop/etc but plugin doesn't override the matching cmd_\* method                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-05-15 | Added IMUData model; added DeviceCategory: LEGGED, VTOL, TRACKED, STATIC; EventSeverity moved to SDK                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-05-15 | DeviceProxy get_gps_data/get_battery_data/get_lidar_scan now read from typed TelemetryFrame via node_registry.get_last_frame(); node_registry.\_last_frames stores latest frame per node                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-05-27 | Centralised device status detection: node_registry tracks telemetry/liveness tasks per node and cancels both on disconnect; per-frame timeout (15 s) catches frozen generators; liveness monitor polls plugin.is_connected() every 2 s and sets DEGRADED if False; added is_connected() optional hook to NodePlugin (default True); telemetry loops in all plugins simplified to `while node.id in self._nodes:` only; ue-sim overrides is_connected() with ros.is_connected + last_message_time check (MESSAGE_TIMEOUT=10 s)                                                                                                                                                                                                                                                                                                                                                            |
| 2026-05-27 | node_registry liveness monitor wraps is_connected() in asyncio.wait_for(timeout=5.0) — hanging plugin implementations can no longer block the monitor; ue-sim MESSAGE_TIMEOUT moved from module constant to class attribute so subclasses can override it                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-05-27 | Added fixed_capabilities and optional_capabilities arrays to manifest format; Add Device modal chips are now driven entirely by these fields — no frontend code needed per plugin; ue-sim declares gps+camera fixed; template declares gps+battery fixed, camera+lidar optional                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-07-27 | Reorganised plugins/ into device/, control/, templates/; app.py now runs PluginLoader separately for each; templates/ is never scanned; updated CLAUDE.md plugin maintenance rule to reference new paths                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-07-27 | Added plugins/control/auto-navigate/ — placeholder control plugin with StepType enum (MOVE*TO_MARKER, MOVE_TO_ZONE, AREA_COVERAGE, PERIMETER_PATROL), NavigationStep dataclass, step dispatch, and stubbed \_execute*\* methods                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-08-03 | Wired on_operator_input end-to-end: added operation_manager.send_operator_input(); added POST /api/operations/{plugin_id}/input route; added frontend sendOperatorInput() in api.ts                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 2026-08-03 | Added plugins/control/teleop/ — manual arrow-key driving control plugin; MOVE_2D required, AGV-only, PRIORITY=10 to preempt autonomous ops; resends cmd_vel at 5 Hz from pressed-key state; stop() always sends a final zero-velocity command                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-08-03 | ue-sim: added movement support — MOVE_2D fixed capability, custom cmd_vel command (handle_custom_command) mapped to airsim_ros_pkgs/CarControls, published via new car_cmd_topic publisher created in connect(); get_safe_state() now publishes full brake instead of no-op                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 2026-08-03 | Added apps/desktop renderer/hooks/useArrowKeyDrive.ts; PluginsPage.tsx ControlPluginPanel gained a Start/Stop Operation control and, for plugin.id==="teleop", a live drive-status indicator                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 2026-08-03 | Added henosync_sdk/positioning.py — PositioningMixin with \_local_to_gps(x_m, y_m, home_lat, home_lon) equirectangular conversion; exported as PositioningMixin from henosync_sdk; device template updated to inherit it and show GPS/VICON conditional subscription pattern; manifest config_schema extended with position_source select, vicon_object_name, home_lat, home_lon fields                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-08-03 | Device template: added POSITION_FIX_TIMEOUT (10s) and POSITION_STALE_TIMEOUT (3s) class attributes; telemetry_stream emits WARNING event if no initial position arrives and suppresses stale position from map; \_no_fix_warned/\_stale_warned flags prevent event spam; \_stale_warned resets on recovery; both \_on_gps and \_on_vicon update last_position_time                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-08-03 | ue-sim: added POSITION_FIX_TIMEOUT (10s) no-fix warning — emits WARNING event if global_gps topic never publishes after connect; stale detection unchanged (handled by is_connected() + MESSAGE_TIMEOUT)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-08-03 | Added henosync_sdk/rosbridge.py — shared ensure_reactor() utility; Twisted reactor is now a process-wide singleton managed by the SDK; ue-sim updated to import from SDK (removed local \_ensure_reactor); fixes crash when multiple rosbridge plugins run in the same process                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| 2026-08-03 | Added plugins/device/turtlebot3/ — TurtleBot3 Burger plugin; VICON (default) or GPS positioning; /odom for speed+heading; /battery_state for battery; proportional goto controller in cmd_move_to() publishes Twist to /cmd_vel; full position health checks; cmd_return_home uses node.home_position                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 2026-08-03 | Fixed teleop→turtlebot3: added handle_custom_command for cmd_vel (was silently dropped); scales normalised [-1,1] to hardware limits; negates angular to match ROS angular.z convention (right=CCW); sets stop_requested to interrupt any running goto loop; fixed ue-sim car_cmd_topic missing advertise() call; fixed all roslibpy publish() calls to use reactor.callFromThread() — Twisted WebSocket send is not thread-safe from asyncio thread                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-08-03 | useArrowKeyDrive: added WASD to KEY_MAP alongside arrow keys; moved hook from ControlPluginPanel (conditional render) to top-level PluginsPage (always in tree) so keys fire from any page when teleop is running                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 2026-08-03 | turtlebot3: fixed /cmd_vel message type — TurtleBot3 Burger on ROS2 Jazzy+ uses geometry_msgs/TwistStamped (not Twist); updated topic type and message format (header + twist nesting); removed debug warning logs                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-08-03 | Fixed NodePlugin.send_command()/cmd_move_to() dispatch bug: DeviceProxy.move_to() sends {x,y,z} params for coordinate_frame="local" devices, but the dispatcher only ever forwarded lat/lon/alt — local-frame move_to calls always silently landed on (0,0,0). cmd_move_to base signature now takes optional x/y/z alongside lat/lon/alt (backward compatible); dispatcher forwards both sets. device-template's cmd_move_to stub updated to show the branch. turtlebot3's cmd_move_to updated to convert an incoming local x/y target back to lat/lon via node.local_origin instead of re-deriving distance from stale lat/lon fields                                                                                                                                                                                                                                                   |
| 2026-08-03 | Added plugins/device/jackal/ — Clearpath Jackal (ROS2) device plugin via rosbridge/henosync_sdk.rosbridge.ensure_reactor. VICON (default) or GPS positioning (fixed gps+battery+imu capabilities; optional camera+lidar, topics overridable in config since Jackal is a modular platform). cmd_move_to publishes a Nav2 goal_pose (PoseStamped) topic rather than calling the NavigateToPose action, since roslibpy's ROS2 action support is unreliable over rosbridge — goal_pose is a plain topic subscribed to by bt_navigator. ASSUMPTION: VICON home origin is assumed aligned with the Jackal's Nav2 map frame — unverified, needs on-robot calibration check. KNOWN LIMITATION: cmd_stop/get_safe_state publish zero Twist to platform/cmd_vel_unstamped directly; this does not cancel an in-flight Nav2 goal, so Nav2's controller may resume commanding velocity moments later |
| 2026-08-03 | teleop: removed spurious self.\_stop_requested = True in no-device early exit from start()                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-08-05 | Moved rosbridge/Twisted reactor utility from henosync_sdk/rosbridge.py to henosync_sdk/protocols/ros2.py — SDK core is now protocol-agnostic; rosbridge.py kept as compatibility shim                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 2026-08-05 | Added henosync_sdk/protocols/ros2.py — ROS2Plugin base class (connect/disconnect/is_connected/telemetry_stream/subscribe/advertise/publish all implemented); ensure_reactor moved here from rosbridge.py shim                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-08-05 | Added henosync_sdk/protocols/mavlink.py — MAVLinkPlugin base class for PX4/ArduPilot devices; handles UDP connection, heartbeat, background recv loop, message dispatch, helpers: send_command_long, send_set_position_target, send_vision_position, request_message_interval                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-08-05 | Refactored turtlebot3 and ue-sim to subclass ROS2Plugin; plugins now only implement create_state/setup_node/build_telemetry/callbacks/command handlers; all connection boilerplate removed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

| 2026-08-05 | Updated plugins/templates/device-template/plugin.py — replaces old NodePlugin boilerplate with ROS2Plugin (Option A, active) and MAVLinkPlugin (Option B, commented out) starters; includes GPS/VICON branching, position health checks, no-fix warnings, and cmd\*vel publisher pattern |
| 2026-08-12 | Fixed ros2.py close event lambda — roslibpy passes one argument to close callbacks; changed `lambda:` to `lambda \**:` to accept and discard it |
| 2026-08-12 | turtlebot3: fixed namespace topic construction — compute prefix = f"/{ns}" once and use for all topics; strip() (not rstrip) so leading slashes in user input don't produce double-slash topics; manifest namespace placeholder updated to "tb2" (no slashes) |
| 2026-08-12 | turtlebot3: removed diagnostic battery logging; battery reading confirmed working via namespace field (set "tb2" for /tb2/battery_state etc.) |
| 2026-08-05 | Added henosync_sdk/protocols/vicon.py — VICONMixin with \_start_vicon()/\_stop_vicon(); connects directly to VICON DataStream SDK over TCP (port 801), no intermediate ROS2 bridge PC required; polls GetFrame() in executor, calls on_position(x_m,y_m,z_m,yaw_rad,occluded) from asyncio thread; exported as VICONMixin from henosync_sdk |
| 2026-08-05 | turtlebot3: replaced ROS2 topic VICON subscription with VICONMixin.\_start_vicon(); added disconnect() override to stop VICON before rosbridge cleanup; manifest.json gains vicon_host field (default "localhost") |
| 2026-08-17 | setup.bat and setup.sh: removed vicon-dssdk from pip install — it is not on PyPI; ships with Vicon DataStream SDK installer; must be pip-installed from local path after SDK install; added note to setup output explaining this |
| 2026-08-17 | vicon_manager: fixed SDK API — correct import is ViconDataStream (not DataStream); GetFrame() returns True/False; GetSegmentGlobalTranslation/EulerXYZ return ((x,y,z), occluded) tuples and raise DataStreamException on error; SetStreamMode uses Client.StreamMode.EClientPull |
| 2026-08-17 | setup.bat and setup.sh: switched from pip to python -m pip for upgrade/install to avoid Windows permission error on pip self-upgrade |
| 2026-08-17 | template plugin.py: fixed rstrip("/") → strip("/") in namespace handling to match turtlebot3 fix |
| 2026-08-05 | device-template: updated VICON branch to use VICONMixin.\_start_vicon(); added disconnect() override; \_on_vicon now receives DataStream SDK args (x_m,y_m,z_m,yaw_rad,occluded) not a ROS2 message; added heading field to \_NodeState |
| 2026-08-05 | Added henosync_sdk/protocols/positioning.py — PositioningState (base state class with lat/lon/alt/heading/position_received) and StandardPositioningMixin (\_setup_positioning, \_teardown_positioning, \_check_position_health, \_position_for_frame, \_status_text); handles VICON/GPS automatically; exported from henosync_sdk |
| 2026-08-05 | turtlebot3: refactored to use StandardPositioningMixin — removed all positioning/no-fix/stale logic from plugin; \_NodeState now inherits PositioningState; setup_node calls \_setup_positioning(); on_telemetry_tick calls \_check_position_health(); disconnect calls \_teardown_positioning() |
| 2026-08-05 | device-template: updated to StandardPositioningMixin pattern; manifest.json gains vicon_host and gps_topic fields; template plugin.py is now minimal — positioning needs zero per-plugin code |
| 2026-08-05 | Implemented vicon_manager as core singleton (henosync/core/vicon_manager.py) — one TCP DataStream SDK connection per VICON PC; scans ONLINE/DEGRADED nodes with position_source=vicon; publishes position-only TelemetryFrame via telemetry_bus; updates node.position directly; emits WARNING if no position after 10s; 5s retry backoff on failed connections; wired into app.py startup/shutdown |
| 2026-08-05 | Removed VICONMixin, StandardPositioningMixin, PositioningState from henosync_sdk — deleted protocols/vicon.py and protocols/positioning.py; PositioningMixin (\_local_to_gps helper) retained |
| 2026-08-05 | turtlebot3: stripped StandardPositioningMixin; VICON mode is now zero plugin code (just sets node.local_origin); GPS mode subscribes to /gps/fix directly; cmd_move_to reads node.position regardless of source |
| 2026-08-05 | device-template: updated to plain ROS2Plugin; VICON = set local_origin + done; GPS = subscribe /gps/fix; MAVLink Option B updated to match same pattern |
| 2026-08-05 | Added show_when to PluginConfigField type; AddNodeModal filters config fields by show_when condition; turtlebot3 and device-template manifests: vicon_host/vicon_object_name/home_lat/home_lon hidden when GPS selected, gps_topic hidden when VICON selected |

| 2026-08-12 | Fixed plugin loader: \_find\*plugin_class now skips abstract classes (ROS2Plugin, MAVLinkPlugin imported into plugin modules were being picked up before the concrete subclass) |
| 2026-08-17 | Removed plugins/device/ros2-diffdrive/ entirely |
| 2026-08-17 | setup.bat/setup.sh: pin Python to 3.11 or 3.12 — vicon-dssdk has no wheels for 3.13+; setup.bat uses py launcher, setup.sh searches python3.12/python3.11 explicitly; both fail fast with clear message |
| 2026-08-17 | Added VICON status indicator to title bar (left of backend Connected dot): shows green/red VICON dot when any node has position_source=vicon; hidden when no VICON nodes configured; /health now returns vicon_configured and vicon_connected fields |
| 2026-08-17 | Refactored VICON from per-device config to independent connection: vicon_connections SQLite table; vicon_manager loads saved connection on startup and exposes connect()/disconnect()/get_subject_names(); new /api/vicon/connection (GET/POST/DELETE) and /api/vicon/objects routes; VICON dot in title bar is now clickable — opens a panel to connect/disconnect and shows live object count; vicon_host removed from turtlebot3 and device-template manifests |
| 2026-08-17 | jackal: migrated VICON positioning to core vicon_manager, matching turtlebot3/device-template — removed the plugin's own `/vicon/{object_name}/{object_name}` rosbridge topic subscription and `_on_vicon` callback (and the now-unused PositioningMixin base); connect() now only sets node.local_origin for VICON mode, vicon_manager's direct VICON DataStream SDK connection populates node.position; telemetry_stream() branches on position_source — GPS mode keeps its own fix/stale warnings and Position field, VICON mode reads node.position and omits its own warnings (vicon_manager emits its own no-fix event); manifest.json gained show_when on vicon_object_name/home_lat/home_lon (vicon only) and gps_topic (gps only), matching turtlebot3's manifest |
| 2026-08-18 | jackal: fixed ros.on("close", lambda \*\*: ...) — roslibpy passes one arg to close callbacks; lambda: caused TypeError in Twisted thread; fixed asyncio.get_event_loop()→get_running_loop(), ensure_future→create_task; anchored last_message_time at connect time so wrong namespace causes DEGRADED within MESSAGE_TIMEOUT seconds |
| 2026-08-17 | turtlebot3: initialise last_message_time = time.monotonic() at end of setup_node() — wrong namespace (topics never publish) now causes DEGRADED within MESSAGE_TIMEOUT seconds instead of staying ONLINE forever |
| 2026-08-17 | MissionPage: added device_select ConfigField branch (DeviceSelectField component) — renders live node dropdown from Zustand store; teleop step now shows Robot picker so operator can choose which AGV to drive |
| 2026-08-17 | Fixed Electron preload path: \_\_dirname inside out/main/main/index.js is out/main/main/ so preload must be ../preload/index.js not preload/index.js |
| 2026-08-17 | Fixed Electron CSP: onHeadersReceived hook now only applies in production — dev mode CSP blocked Vite HMR inline scripts causing blank screen and React preamble error |
| 2026-08-17 | Added PUT /api/nodes/{id} route and node_registry.update_node() — updates name/config in SQLite and triggers reconnect; NodeUpdate model was already defined |
| 2026-08-17 | DevicesPage: moved Remove button to top-right of hero as icon button; added Edit icon button above it; clicking Edit opens EditNodeModal (inline component) with name + config_schema fields pre-filled; confirm delete dialog appears as absolute-positioned popover anchored to hero; removed Danger Zone section from scrollable body |
| 2026-08-18 | turtlebot3: added missing Optional import — plugin failed to load entirely (name 'Optional' is not defined at startup) |
| 2026-08-18 | desktop: renamed postcss.config.js → postcss.config.mjs — eliminates Node ESM/CJS ambiguity warning on startup |
| 2026-08-24 | VICON map mode: GPS/VICON toggle pill on HomePage; VICONSetupModal (shape + dimensions, localStorage); VICONMap SVG component (boundary rect/circle, robot dots by raw x/y); vicon_manager emits vicon_x/vicon_y in TelemetryFrame.custom for frontend positioning |
| 2026-08-24 | Fixed GPS→VICON blue-screen crash: GPS MissionMap now always mounted in both HomePage and ZonesPage; VICON overlay at zIndex:2 with solid #0D0D0D background covers it — avoids maplibre WebGL lifecycle teardown that caused the crash; ZonesPage updated to same always-mounted pattern |
| 2026-08-24 | Separate zone+marker sets per map mode: added map_mode column (TEXT DEFAULT 'gps') to zones and map_markers tables via safe ALTER TABLE migration; Zone/MapMarker models, create/list methods, and REST routes all accept map_mode; GET /api/zones?mode= and GET /api/markers?mode= filter by mode; useZones/useMarkers hooks include mode in query key and auto-refetch on mode switch; useCreateZone/useCreateMarker inject current mapMode from uiStore so callers need no changes |
| 2026-08-24 | ZonesPage: added always-visible GPS/VICON toggle pill at zIndex:20 (top-right); MapToolbar always rendered in both modes |
| 2026-08-24 | VICONMap: full drawing support — SVG click/mousemove/dblclick events convert to VICON x_m/y_m (via viewBox coordinate inversion accounting for preserveAspectRatio letterboxing); polygon (dblclick to finish), circle (2-click), marker placement; draft shapes rendered as SVG; existing VICON zones and markers rendered from store (coordinate convention: lon=x_m, lat=y_m); ZonesPage wires drawMode and onFinish\* callbacks so CreateZoneModal/PlaceMarkerModal work unchanged; removed mapMode==="gps" guard from modal renders so they appear in both modes |
| 2026-08-23 | Reconciled a stash of local work (built pre-pull, against a now-deleted plugins/device/ros2-diffdrive/) against 9 incoming commits (turtlebot3, VICON, shared ROS2Plugin base). Reapplied unaffected: context.marker_manager on FleetContext (+ operation_manager wiring, marker_manager.get_marker()), auto-navigate's MOVE_TO_MARKER/MOVE_TO_ZONE go-to-waypoint controller. Dropped: ros2-diffdrive's GPS/LiDAR additions (plugin no longer exists — see Auto Navigate section for what's now dead code as a result). Manually reconciled apps/desktop/.../AddNodeModal.tsx and PluginsPage.tsx against upstream's show_when field filtering and the (better) top-level useArrowKeyDrive placement — also fixed a dangling isTeleop reference in PluginsPage.tsx left over from that upstream refactor. Extracted ConfigField/fieldStyle/initConfig into new shared renderer/components/common/ConfigField.tsx (still novel vs upstream); PluginsPage's ControlPluginPanel now renders a config form from plugin.ui.config_schema before Start, keyed by plugin.id so switching plugins resets it |
| 2026-08-23 | Fixed DeviceProxy.move_to(): removed the coordinate_frame=="local" branch that converted to local x/y and sent {"x","y","z"} — send_command()'s MOVE_TO dispatch only ever reads "lat"/"lon" from params, so that branch silently produced cmd_move_to(lat=0.0, lon=0.0) for every local-frame device (never caught before since no plugin combined coordinate_frame="local" with a working cmd_move_to until turtlebot3). move_to() now always sends {lat, lon, alt}; local-frame plugins convert internally using node.local_origin. Removed _gps_to_local() (no other caller) |
| 2026-08-23 | auto-navigate: added _go_to_waypoint() — prefers device.move_to() (detects a real cmd_move_to via the "not implemented" string every unimplemented SDK cmd_* stub returns) over the generic _navigate_to() cmd_vel controller, since turtlebot3.cmd_move_to() uses real /odom heading instead of GPS course-over-ground estimation. _execute_move_to_marker/_zone now call _go_to_waypoint() instead of _navigate_to() directly. Added self._current_device tracking + stop() now calls device.stop() to interrupt a blocking move_to() (turtlebot3's cmd_move_to loops until arrival, checking its own internal stop flag, not ours) |
| 2026-08-23 | auto-navigate: multi-device support — MOVE_TO_MARKER/MOVE_TO_ZONE now resolve the target once per step and dispatch every assigned device concurrently (asyncio.gather) instead of sequentially (previously device 2 didn't move until device 1 finished the whole step). self._current_device (singular) -> self._current_devices dict; self._status_text -> self._device_status dict keyed by device name (concurrent devices would otherwise race to overwrite one shared string); get_status() joins per-device text and exposes the raw dict via OperationStatus.data. stop() now interrupts every currently-navigating device concurrently, not just one. get_status()'s progress kwarg fixed to progress_percent (OperationStatus's actual field name — previously silently dropped by pydantic's default extra="ignore", not a crash, just a no-op) |
| 2026-08-23 | Added manual mid-operation device recruitment: operation_manager.recruit_device_into_operation() (validates capabilities/category, unlike FleetContext.recruit_device() which only checks priority/availability) and get_recruitable_devices(); new routes GET/POST /api/operations/{plugin_id}/recruitable and /recruit. AutoNavigatePlugin.on_device_joined() now actually does something — sends the newly-recruited device toward self._current_target if a MOVE_TO_MARKER/MOVE_TO_ZONE step is active; stashes self._context in start() since operation_manager never populates the ControlPlugin base class's _context attribute and on_device_joined()'s signature has no context param. Manual only — no automatic join when a new device connects. Frontend: PluginsPage.tsx shows an "Available devices" list with per-device Add buttons while an operation is running (useRecruitableDevices, 3s poll) |
| 2026-08-23 | auto-navigate: added _collision_guard() — background task for the whole operation (not per-step, so a dynamically-joined device is covered too) checking pairwise distance between every currently-navigating device every SEPARATION_CHECK_PERIOD_S=0.5s; if closer than MIN_SEPARATION_M=2.0m, whichever is farther from its own target yields via device.stop() (same interruption mechanism as the operator Stop button), self._collision_paused tracks who's waiting, _go_to_waypoint_tracked() retries automatically once clear. Fixed a livelock found via simulation: when fewer than 2 devices remain navigating, pause flags weren't being cleared, so a paused device could wait forever with nothing left to conflict with. Also found via simulation and NOT fixed (structural, not a bug): since every robot in a multi-device operation shares one destination, the guard can't fully prevent close proximity during final approach to that shared point — the non-yielding robot completes its approach unimpeded, and measured worst case was 0.58m against a configured 2.0m minimum. Ported ConfigField.tsx forward to handle the new device_select field type (DeviceSelectField, mirroring MissionPage's own component) added on develop alongside teleop's robot-picker — without this, teleop's node_id field would have silently failed to render in the new PluginsPage config form |
| 2026-08-24 | Ported the entire 2026-08-23 multi-robot/collision-guard auto-navigate work from feature/teleop-control-plugin onto develop (stayed on develop per explicit direction — it has independent progress: jackal plugin, teleop device-select, DevicesPage edit). Applied via git stash apply; only CLAUDE.md and PluginsPage.tsx needed manual conflict resolution (both trivial — develop had no competing content at those exact points). All backend core files (fleet_context, marker_manager, operation_manager, device_proxy, operations routes) were byte-identical between the two branches pre-merge, so those applied cleanly with no reconciliation needed |
| 2026-08-24 | Reconciled DeviceProxy.move_to() with develop's own independent fix for the same local-frame bug (see DeviceProxy section) — restored _gps_to_local() and now sends both lat/lon and x/y/z always, rather than this session's earlier lat/lon-only fix, which worked for turtlebot3 but would have silently made develop's x/y/z dispatcher support (interfaces.py, cmd_move_to's x/y/z params) permanently dead code |
| 2026-08-24 | Fixed unrelated pre-existing bug (not from this session's work) blocking plugins/device/turtlebot3/plugin.py from loading at all: cmd_move_to()'s x/y/z params are typed Optional[float] but only `Any` was imported from typing — added Optional to the import |
| 2026-08-31 | Implemented AREA_COVERAGE in auto-navigate: zone is split into per-device parallel strips (_generate_coverage_paths, strip decomposition + sampling-based boustrophedon sweep) sized to however many devices are assigned when the step starts; each device sweeps its own strip and returns to its own captured start position (_run_coverage_path). Extracted _navigate_one_waypoint() (single-waypoint drive + collision-guard pause/retry) out of _go_to_waypoint_tracked() so both point-to-point and coverage paths share it. _collision_guard() now judges yield priority per-device (self._device_target) instead of against one shared self._current_target, so inter-robot separation checking now also applies during coverage sweeps, not just MOVE_TO_MARKER/MOVE_TO_ZONE. Wired the previously-dead coverage_angle_deg field into _parse_steps() and the config_schema as a Sweep Angle (°) number field. Verified via new geometry + async-simulation scratch scripts, ruff, and tsc — not yet tested against real devices or a concave zone |
| 2026-08-31 | Fixed AREA_COVERAGE band splitting: equal-height strips (previous entry) badly unbalance coverage time on any non-rectangular zone — found by the user testing an L-shaped zone in a companion visualization built for manual testing of this feature. Added _equal_area_band_bounds() + _width_at_y(): builds a cumulative area-vs-y profile via sampling (AREA_PROFILE_Y_SAMPLES=150 × AREA_PROFILE_X_SAMPLES=80, a fixed one-time cost per step start) and splits by equal area instead of equal height. _generate_coverage_paths() now computes per-band line count individually since band heights vary. Verified: independent 400×400-grid re-measurement of each band's true area on an L-shaped test zone came out within 0.3% of equal share (vs. 29.4% for the old equal-height split on the same zone) |
| 2026-08-31 | Recovered this session's uncommitted work after it was reverted to HEAD on disk (git stash apply on stash@{0} — the working tree had gone clean, meaning everything from 2026-08-23 onward existed only in that stash, never committed). Applied cleanly except CLAUDE.md, which had a pure append conflict against two teammate commits (turtlebot3 Optional-import fix — byte-identical to this session's own independent fix; VICON map mode) that landed on develop after the stash was created — resolved by keeping both sets of changelog rows |
| 2026-08-31 | Fixed VICON-mode zones/markers so auto-navigate (MOVE_TO_ZONE/AREA_COVERAGE) works against them: VICONMap.tsx's drawing tools were storing raw arena metres directly in Zone/MapMarker lat/lon fields (`lon=x_m, lat=y_m`, no conversion), violating the system-wide "everything is WGS84" invariant and producing nonsense-scale geometry if auto-navigate ever read one. Added a shared VICON arena origin (`vicon_origin` SQLite table, `vicon_manager.origin`/`set_origin()`, separate from any per-robot `home_lat`/`home_lon` since it isn't tied to one device) settable via a new "Arena Origin" section in the VICON panel (title bar) and `POST /api/vicon/origin`. `zones.py`/`markers.py`'s POST routes now convert incoming coordinates through `vicon_manager.local_to_gps()` (renamed from `_local_to_gps`, same equirectangular projection already used for node.position) when `map_mode == "vicon"`, before storing — 400s with a clear message if no origin is set yet. Frontend zone/marker *creation* code (VICONMap.tsx, CreateZoneModal.tsx, ZonesPage.tsx) needed no changes, since it already just sends raw metres in those fields — only *rendering* needed updating: VICONMap.tsx gained `homeLat`/`homeLon` props (wired from `useViconConnection()` in ZonesPage.tsx/HomePage.tsx) and a `gpsToLocal()` inverse-projection helper, applied to zones/markers before projecting to SVG; zones/markers are hidden (not drawn at a wrong position) until an origin is set. GPS-mode zones/markers are completely unaffected. Verified via a TestClient smoke test against the real dev DB (with origin save/restore around it): 400 with no origin, exact match against `vicon_manager`'s own conversion once one is set, GPS-mode passthrough unchanged. **Known gap**: any VICON-mode zones/markers created before this fix still hold raw-metres values and were not migrated — delete and redraw them |
| 2026-08-31 | MissionPage: added VICON map mode — GPS/VICON toggle pill (top-left, zIndex:20); GPS MissionMap always mounted; VICON overlay at zIndex:2 with solid #0D0D0D background; shows VICONMap when viconSpace is configured, placeholder text when not; MapStylePicker hidden in VICON mode |
| 2026-08-31 | VICONMap: added pan support — drag to pan SVG viewBox; panOffset state shifts viewBox minX/minY; eventToVicon accounts for pan; threshold-based click/pan disambiguation (3px); grab/grabbing cursor; drawing mode disables pan |

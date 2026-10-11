# Results tooling

Scripts for collecting the data behind the paper's Results section (Section V).
None of them change how Henosync behaves. They read its live WebSocket and
REST API while you run experiments in the app.

Run every script with the backend's Python, from the repo root:

```
apps/backend/.venv/Scripts/python.exe tools/results/<script>.py ...   # Windows
apps/backend/.venv/bin/python tools/results/<script>.py ...           # macOS / Linux
```

`resource_monitor.py` also needs `python -m pip install psutil`.

## The scripts

| Script | What it gives you |
|---|---|
| `ws_logger.py` | Records a **run directory**: every telemetry frame and event, plus node status changes and operation state changes. All the `analyze_*` scripts read this. |
| `analyze_telemetry.py` | Update rate, jitter, dropped frames and backend-to-UI delay, per robot, split into the robot's own stream and VICON. |
| `analyze_waypoints.py` | Final position error, time, path efficiency and success rate for every move-to-marker trial in a run. |
| `analyze_coverage.py` | Lawnmower coverage %, deviation from the planned path, completion time, and minimum distance between robots. |
| `reconnection_trial.py` | Guided dropout trials: time to DEGRADED and ERROR, whether the robot recovered on its own, and manual reconnect time. Writes a CSV. |
| `resource_monitor.py` | CPU and memory of the backend and desktop app, for each OS and scenario. |
| `plugin_loc.py` | Lines of code per plugin, and which files outside the plugin changed when it was added (Table III). |

Backend tests that support the same claims are in `apps/backend/tests/`:
`test_coverage_paths.py`, `test_operation_manager.py`,
`test_connection_liveness.py`, `test_failsafe_vicon.py`. Run them with
`python -m pytest tests` from `apps/backend`.

## Before every robot session

1. Add every robot in Henosync **before** starting the logger. Robot names are
   read once at start.
2. Draw the VICON zones and markers you'll use, with simple names (e.g. `Target A`, `Arena`).
3. Start the logger in its own terminal and leave it running for the whole session:
   `python tools/results/ws_logger.py --out runs/<session-name>`
4. Screen-record Henosync and film the robot as planned. The logger gives the numbers.
5. Stop the logger with Ctrl+C at the end.

## Use case 1: single Jackal, waypoints

Run auto-navigate (or an area-navigate "Move to Marker" step) to one marker
about 10 times. Reset the robot to a similar start position between trials.

```
python tools/results/analyze_telemetry.py runs/jackal_waypoints --csv runs/jackal_telemetry.csv
python tools/results/analyze_waypoints.py runs/jackal_waypoints --node Jackal --marker "Target A" \
    --tolerance 0.3 --csv runs/jackal_waypoints.csv
```

Use `--plugin area-navigate` if the trials were area-navigate steps.
Backend-to-UI delay assumes the logger and backend run on the same laptop.

## Use case 2: single-robot lawnmower

Run one area-navigate "Area Coverage" step. Note the Coverage Spacing and
Sweep Angle you set.

```
python tools/results/analyze_coverage.py runs/jackal_lawnmower --zone Arena \
    --spacing 0.5 --angle 0 --nodes Jackal
```

Path deviation includes the drive to the first lane and the return to the
start position, so its max will be high. Use the mean and p95 for tracking accuracy.

The planner fits `floor(strip height / spacing)` lanes into each strip, so
the real gap between lanes can be up to twice the requested spacing.
`test_coverage_paths.py` documents this. Report coverage % with the actual
lane gap, or pick a zone height that is a whole multiple of the spacing.

## Use case 3: two missions at the same time

In the Mission page:

1. Step 1: area-navigate "Area Coverage" or "Perimeter Patrol", with **Robots**
   set to the Jackal.
2. Step 2: auto-navigate with **Robot** set to the TurtleBot3, and
   **Run with step 1** ticked.
3. Run the mission. Both steps start together, and the mission finishes when both are done.

```
python tools/results/analyze_coverage.py runs/multi --zone Arena --spacing 0.5 --nodes Jackal
python tools/results/analyze_waypoints.py runs/multi --node TurtleBot3 --marker "Target B"
```

For a shared coverage step (both robots in one area-navigate step), pass both
names to `--nodes` to get per-robot coverage and the minimum separation.

## Use case 5: device types

```
python tools/results/plugin_loc.py
```

Also take one screenshot with every device type online at once.

## Use case 6: dropout and reconnection

Run 20 trials for each way of cutting the link. Use a robot that is idle, or
one running a mission, whichever matches the claim you want to make.

```
# Hands-free laptop WiFi drop (Windows, no admin needed):
python tools/results/reconnection_trial.py --node Jackal --trials 20 --method wifi \
    --cut-cmd "netsh wlan disconnect" --restore-cmd "netsh wlan connect name=<SSID>" \
    --outage 15 --out runs/reconnect_wifi.csv

# Manual (press Enter at the moment you cut the link):
python tools/results/reconnection_trial.py --node Jackal --trials 20 --method rosbridge-kill \
    --out runs/reconnect_rosbridge.csv
```

What to expect: Henosync does not reconnect on its own (a deliberate design
choice), so `auto_recovered` should be `False`. The useful numbers are
`to_degraded_s`, `to_error_s` and `reconnect_to_online_s`.

If the laptop reaches the VICON PC over WiFi, turning WiFi off also cuts
VICON. Record which setup you used.

## Install and platforms

On each OS: time a fresh install by following the setup steps and count the steps.
Then, with Henosync running:

```
python tools/results/resource_monitor.py --duration 60 --label "idle, 0 robots" --csv runs/resources.csv
python tools/results/resource_monitor.py --duration 60 --label "1 robot" --csv runs/resources.csv
python tools/results/resource_monitor.py --duration 60 --label "mission running" --csv runs/resources.csv
```

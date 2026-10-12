# Results tooling

How to collect the data behind the paper's Results section (Section V).

## Mission runs are recorded automatically

Every press of **Run Mission** is recorded by Henosync to its own folder:

```
~/.henosync/runs/<YYYY-MM-DD_HH-MM-SS>_<mission name>/
```

The mission name is the saved plan's name ("Untitled mission" if the plan
was never saved). Nothing needs to be started by hand. The mission log
shows "Recording run · <run id>" at the start and "Run saved" at the end.

Open the **Runs** list with the clock icon at the top of the Mission page's
step list. For each run you can:

- **expand** it to see per-step results
- **Export CSV**: one row per step per robot (available once the run finishes)
- **View report**: opens the run's `report.html` in your browser
- **Open folder**: the raw recording
- **Delete** (click twice to confirm)

Every finished run also gets a human-readable `report.html` in its folder,
built automatically by `henosync_report.py` (also reachable from the
**View Report** button that appears on the Mission page after a run). To build
one combined report across many runs, run the script by hand:

```
python tools/results/henosync_report.py ~/.henosync/runs -o henosync_report.html --open
```

CSV columns: `run_id, mission, step, step_name, step_type, robot, target,
started_at, ended_at, duration_s, outcome, final_x_m, final_y_m, target_x_m,
target_y_m, final_error_m, coverage_pct, status_text`.

- `final_error_m` is filled for move-to-marker steps with a VICON marker.
- `coverage_pct` is filled for Area Coverage steps in a VICON zone. It uses
  the step's Coverage Spacing as the swath width.
- `outcome` is `completed`, `failed`, `stopped` or `not run`.
- **Pick robots explicitly in each step** (Robot / Robots fields). Final
  position and error are tied to the robots the step was given.

## The scripts

Run them from the repo root with the backend's Python:

```
apps/backend/.venv/Scripts/python.exe tools/results/<script>.py ...   # Windows
apps/backend/.venv/bin/python tools/results/<script>.py ...           # macOS / Linux
```

Every `analyze_*` script takes either a run folder path or just the run id
shown in the Runs list (looked up in `~/.henosync/runs`).

| Script                  | What it gives you                                                                                                                                                                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `analyze_waypoints.py`  | Final error, time, path efficiency and success rate across one or more runs (pass multiple run IDs to aggregate).                                                                                                   |
| `analyze_coverage.py`   | Coverage %, deviation from the planned path, time, and minimum robot separation for a coverage step.                                                                                                                |
| `analyze_telemetry.py`  | Update rate, jitter and dropped frames per robot, split into robot stream and VICON. Add `--dropout` to cross-reference DEGRADED/ERROR windows with VICON position — proves the robot kept moving during a dropout. |
| `analyze_timing.py`     | Per-step timeline from a parallel mission: serial estimate, actual wall time, and speedup ratio.                                                                                                                    |
| `ws_logger.py`          | Records a run folder for things that **aren't** missions (use case 5, and backend-to-UI delay). Start it, Ctrl+C to stop.                                                                                           |
| `reconnection_trial.py` | Guided dropout trials. Writes its own CSV.                                                                                                                                                                          |
| `resource_monitor.py`   | CPU and memory per OS and scenario. Writes its own CSV. Needs `python -m pip install psutil`.                                                                                                                       |
| `plugin_loc.py`         | Lines of code per plugin and files changed outside it (Table III).                                                                                                                                                  |

Backend tests for the same claims are in `apps/backend/tests/`
(`python -m pytest tests -v` from `apps/backend`).

## Use case 1: single Jackal, waypoints

Build one mission with 10 steps that alternate between two markers, e.g.
auto-navigate to `Target A`, then `Target B`, then `Target A`, and so on,
each with **Robot** set to the Jackal. Save the plan as e.g.
"Jackal waypoints", then Run Mission.

- Table II: Export CSV from the Runs list, or for aggregated statistics across all repetitions:
  `python tools/results/analyze_waypoints.py "<run1>" "<run2>" ... --tolerance 0.3`
- Telemetry rates: `python tools/results/analyze_telemetry.py "<run id>"`
- Backend-to-UI delay: run `ws_logger.py --out runs/telemetry_check` for a
  few minutes and analyse that folder instead. The in-app recording only
  measures inside the backend.

## Use case 2: single-robot lawnmower

One Area Coverage step with **Robots** set to the Jackal. Run it 3 times.
`coverage_pct` is in the CSV. For path deviation:

```
python tools/results/analyze_coverage.py "<run id>"
```

Path deviation includes the drive to the first lane and back to the start.
Report the mean and p95.

**Known planner limitation:** each strip gets `floor(strip height / spacing)`
lanes, so lanes can be up to twice as far apart as requested. With 2 or more
robots, the equal-area split can make a strip slightly shorter than a whole
multiple and lose a lane. For example, a 2 m tall zone at 0.5 m spacing gets
4 lanes with 1 robot but only 3 with 2 robots, so coverage is at most about
75% even with perfect driving. Check the lane count before quoting coverage
figures.

## Use case 3: two missions at the same time

Step 1: area-navigate Area Coverage or Perimeter Patrol, **Robots** = Jackal.
Step 2: auto-navigate, **Robot** = TurtleBot3, **Run with step 1** ticked.
The CSV's `started_at`/`ended_at` show the overlap. It has `coverage_pct` for
the Jackal row and `final_error_m` for the TurtleBot3 row. For both robots in
one shared coverage step, `analyze_coverage.py` also gives the minimum separation.

For the parallel speedup figure:
`python tools/results/analyze_timing.py "<run id>"`
This prints the per-step timeline, which steps overlapped, the serial estimate
(sum of step durations), the actual wall time, and the speedup ratio.

## Use case 5: device types

Not a mission. Run `python tools/results/plugin_loc.py`, and with every type
online, `ws_logger.py --out runs/all_devices` for 2 minutes, then
`analyze_telemetry.py runs/all_devices`.

## Use case 6: dropout and reconnection

Not a mission. 20 trials per method:

```
# Hands-free laptop WiFi drop (Windows, no admin needed):
python tools/results/reconnection_trial.py --node Jackal --trials 20 --method wifi \
    --cut-cmd "netsh wlan disconnect" --restore-cmd "netsh wlan connect name=<SSID>" \
    --outage 15 --out runs/reconnect_wifi.csv

# Manual (press Enter at the moment you cut the link):
python tools/results/reconnection_trial.py --node Jackal --trials 20 --method rosbridge-kill \
    --out runs/reconnect_rosbridge.csv
```

Reconnection is operator-initiated by design, so `auto_recovered` should be
`False`. If the laptop reaches the VICON PC over WiFi, turning WiFi off also
cuts VICON. Record which setup you used.

## Install and platforms

On each OS: time a fresh install by following the setup steps and count the steps.
Then, with Henosync running:

```
python tools/results/resource_monitor.py --duration 60 --label "idle, 0 robots" --csv runs/resources.csv
python tools/results/resource_monitor.py --duration 60 --label "mission running" --csv runs/resources.csv
```

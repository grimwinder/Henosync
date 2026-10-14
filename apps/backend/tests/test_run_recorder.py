"""
Per-mission run recording: one folder per Run Mission, per-step results
(final error for waypoint steps, coverage % for coverage steps) and CSV export.
"""

import asyncio
import csv
import sys

import pytest
from henosync_sdk import Node, TelemetryFrame

from henosync.core.marker_manager import MapMarker, MarkerType, marker_manager
from henosync.core.node_registry import node_registry
from henosync.core.run_recorder import CSV_COLUMNS, run_recorder
from henosync.core.telemetry_bus import telemetry_bus
from henosync.core.zone_manager import GeoPoint, Zone, ZoneType, zone_manager

recorder_module = sys.modules["henosync.core.run_recorder"]


@pytest.fixture
def arena(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module, "RUNS_DIR", tmp_path / "runs")

    jackal = Node(name="Jackal", plugin_id="jackal")
    marker = MapMarker(
        name="Target A", marker_type=MarkerType.WAYPOINT, lat=1.0, lon=2.0, map_mode="vicon"
    )
    zone = Zone(
        name="Arena", zone_type=ZoneType.COVERAGE, map_mode="vicon",
        points=[GeoPoint(lat=y, lon=x) for x, y in [(0, 0), (2, 0), (2, 1.5), (0, 1.5)]],
    )
    node_registry._nodes[jackal.id] = jackal
    marker_manager._markers[marker.id] = marker
    zone_manager._zones[zone.id] = zone

    yield jackal, marker, zone

    node_registry._nodes.pop(jackal.id, None)
    marker_manager._markers.pop(marker.id, None)
    zone_manager._zones.pop(zone.id, None)


async def _vicon(node_id: str, points: list[tuple[float, float]]) -> None:
    for seq, (x, y) in enumerate(points):
        await telemetry_bus.publish_telemetry(TelemetryFrame(
            node_id=node_id, sequence_number=seq,
            custom={"vicon_x": x, "vicon_y": y},
        ))
    await asyncio.sleep(0.02)


def _line(a: tuple[float, float], b: tuple[float, float], n: int = 40):
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


@pytest.mark.asyncio
async def test_run_records_results_and_exports_csv(arena, tmp_path):
    jackal, marker, zone = arena
    steps = [
        {"index": 0, "name": "Go to A", "plugin_id": "auto-navigate",
         "params": {"node_id": jackal.id, "marker_id": marker.id}},
        {"index": 1, "name": "Sweep", "plugin_id": "area-navigate",
         "params": {"step_type": "area_coverage", "zone_id": zone.id,
                    "node_ids": [jackal.id], "coverage_spacing_m": 0.5}},
        {"index": 2, "name": "Never reached", "plugin_id": "auto-navigate",
         "params": {"node_id": jackal.id, "marker_id": marker.id}},
    ]
    started = await run_recorder.start_run("Lab test", steps)
    run_id = started["run_id"]
    assert run_recorder.get_run(run_id)["outcome"] == "running"

    # Step 1: drive to (1.95, 1.0); target is (2.0, 1.0) -> 0.05 m error
    run_recorder.record_step(run_id, 0, "start")
    await asyncio.sleep(0.02)
    await _vicon(jackal.id, _line((0.0, 0.0), (1.95, 1.0)))
    run_recorder.record_step(run_id, 0, "end", "completed")
    await asyncio.sleep(0.02)

    # Step 2: three full-width lanes 0.5 m apart cover the 2 x 1.5 m zone
    run_recorder.record_step(run_id, 1, "start")
    await asyncio.sleep(0.02)
    lanes = (
        _line((0, 0.25), (2, 0.25)) + _line((2, 0.75), (0, 0.75)) + _line((0, 1.25), (2, 1.25))
    )
    await _vicon(jackal.id, lanes)
    run_recorder.record_step(run_id, 1, "end", "completed")

    run = await run_recorder.stop_run(run_id, "completed")

    assert run["outcome"] == "completed"
    assert run["robots"] == ["Jackal"]
    waypoint, sweep, skipped = run["results"]
    assert waypoint["step_type"] == "move_to_marker"
    assert waypoint["target"] == "Target A"
    assert waypoint["final_error_m"] == pytest.approx(0.05, abs=1e-3)
    assert sweep["step_type"] == "area_coverage"
    assert sweep["coverage_pct"] > 95
    assert skipped["outcome"] == "not run"

    dest = tmp_path / "export.csv"
    run_recorder.export_csv(run_id, str(dest))
    with dest.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_COLUMNS
        rows = list(reader)
    assert len(rows) == 3
    assert rows[0]["mission"] == "Lab test"

    report = await run_recorder.report(run_id)  # waits for the auto-built report
    assert report.endswith("report.html")
    with open(report, encoding="utf-8") as f:
        assert "Lab test" in f.read()

    assert [r["id"] for r in run_recorder.list_runs()] == [run_id]
    run_recorder.delete_run(run_id)
    assert run_recorder.list_runs() == []


@pytest.mark.asyncio
async def test_unfinished_steps_are_marked_stopped(arena):
    jackal, marker, _ = arena
    steps = [{"index": 0, "name": "Go to A", "plugin_id": "auto-navigate",
              "params": {"node_id": jackal.id, "marker_id": marker.id}}]
    run_id = (await run_recorder.start_run("Stopped test", steps))["run_id"]
    run_recorder.record_step(run_id, 0, "start")

    run = await run_recorder.stop_run(run_id, "stopped")

    assert run["outcome"] == "stopped"
    assert run["results"][0]["outcome"] == "stopped"
    with pytest.raises(ValueError):
        run_recorder.record_step(run_id, 0, "end", "completed")  # run no longer active
    await run_recorder.report(run_id)


@pytest.mark.asyncio
async def test_dropout_run_report_uses_robot_log(arena, monkeypatch):
    """
    Test 2 end to end on the recording side: a coverage step, an operator
    dropout mid-step, the robot's own log (part of it delivered only after the
    run stopped), and the report's account of the dropout.
    """
    import importlib.util
    import json
    import re
    import shutil
    import subprocess
    import time
    from pathlib import Path

    from henosync_sdk import NodeStatus

    from henosync.models import EventSeverity

    monkeypatch.setattr(recorder_module, "REPORT_REBUILD_DELAY_S", 0.05)
    jackal, _marker, zone = arena
    steps = [{"index": 0, "name": "Sweep", "plugin_id": "area-navigate",
              "params": {"step_type": "area_coverage", "zone_id": zone.id,
                         "node_ids": [jackal.id], "coverage_spacing_m": 0.5}}]
    run_id = (await run_recorder.start_run("Test 2", steps))["run_id"]
    seq = iter(range(1, 1000))

    def rob(kind, **kw):
        return {"seq": next(seq), "t": time.time(), "kind": kind, "path_id": "p1",
                "run_id": run_id, **kw}

    def deliver(records):
        now = time.time()
        return [{**r, "recv": now, "sent": now} for r in records]

    def status(s):
        jackal.status = s
        node_registry._notify_listeners(jackal)

    status(NodeStatus.ONLINE)
    run_recorder.record_step(run_id, 0, "start")
    run_recorder.record_robot_log(run_id, jackal.id, deliver([rob("link_up"), rob("path_start", total=6)]))
    lane1 = _line((0, 0.25), (2, 0.25))
    await _vicon(jackal.id, lane1)

    # Operator drops the link: Henosync goes DEGRADED, VICON keeps arriving.
    await telemetry_bus.publish_event(
        "Link Dropout Simulated", "Operator cut the connection", EventSeverity.WARNING, jackal.id)
    status(NodeStatus.DEGRADED)
    await asyncio.sleep(0.05)
    offline = [rob("link_lost", last_heartbeat_t=time.time() - 0.01)]
    lane2 = _line((2, 0.75), (0, 0.75))
    for i, (x, y) in enumerate(lane2):
        await _vicon(jackal.id, [(x, y)])
        if i % 8 == 0:
            offline.append(rob("sample", x=x, y=y, theta=3.14, v=0.3, w=0.0, wp=2, link=False, pose_ok=True))
    offline.append(rob("waypoint", index=3, x=0.0, y=0.75, dist=0.05, link=False))
    await asyncio.sleep(0.05)

    # Link restored; robot sends its link_restored + the rest of the path live.
    status(NodeStatus.ONLINE)
    restored = [rob("link_restored", down_s=0.5, backlog=len(offline))]
    await _vicon(jackal.id, _line((0, 1.25), (2, 1.25)))
    restored.append(rob("path_done", total=6, link=True))
    run_recorder.record_step(run_id, 0, "end", "completed")
    await run_recorder.stop_run(run_id, "completed")

    # The offline backlog only lands after the run stopped -> report rebuilt.
    run_recorder.record_robot_log(run_id, jackal.id, deliver(offline + restored))
    await asyncio.sleep(0.2)
    report_path = Path(await run_recorder.report(run_id))
    run_dir = report_path.parent
    lines = (run_dir / "robot.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 + len(offline) + len(restored)
    assert all(json.loads(line)["node_id"] == jackal.id for line in lines)

    spec = importlib.util.spec_from_file_location("henosync_report", recorder_module.REPORT_SCRIPT)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    result = report.analyse_run(run_dir)
    (w,) = result["offline"]
    assert w["simulated"] and w["restored"]
    assert w["vicon_m"] > 1.5 and w["vicon_n"] > 10, "Henosync's VICON kept tracking"
    assert w["cmd_samples"] >= 3 and w["robot_m"] > 1.0
    assert w["wps"] == [3] and w["robot_down"] is not None
    assert w["synced"] is not None and w["synced"] > w["end"]
    titles = [f["title"] for f in result["findings"]]
    assert any("kept executing its mission on the onboard controller" in t for t in titles)
    series = result["series"]
    assert result["zones"] and series["offline"][jackal.id] and series["robot"][jackal.id]
    assert any(t["label"] == "Disconnected" for t in result["tiles"])

    # The page script must still parse after the template changes.
    node_bin = shutil.which("node")
    if node_bin:
        html = report_path.read_text(encoding="utf-8")
        script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
        js = run_dir / "report_check.js"
        js.write_text(script, encoding="utf-8")
        check = subprocess.run([node_bin, "--check", str(js)], capture_output=True, text=True)
        assert check.returncode == 0, check.stderr

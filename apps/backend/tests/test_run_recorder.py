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

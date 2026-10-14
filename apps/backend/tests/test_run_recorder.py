"""
Run recorder: verifies that start_run creates a CSV in DOWNLOADS_DIR,
record_step updates step context, stop_run finalises, and delete_run
removes both the folder and the CSV.
"""

import asyncio
import csv
import sys
from pathlib import Path

import pytest

recorder_module = sys.modules.get("henosync.core.run_recorder")


@pytest.fixture(autouse=True)
def patch_dirs(tmp_path, monkeypatch):
    # Re-import to get fresh module-level constants after monkeypatching
    import henosync.core.run_recorder as rm
    monkeypatch.setattr(rm, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(rm, "DOWNLOADS_DIR", tmp_path / "downloads")


@pytest.mark.asyncio
async def test_run_lifecycle(tmp_path):
    import henosync.core.run_recorder as rm

    steps = [
        {"index": 0, "display_name": "Go to A", "plugin_id": "area-navigate",
         "params": {"step_type": "move_to_marker"}},
        {"index": 1, "display_name": "Sweep", "plugin_id": "area-navigate",
         "params": {"step_type": "area_coverage"}},
    ]

    result = await rm.run_recorder.start_run("Lab test", steps)
    run_id = result["run_id"]
    csv_path = Path(result["csv_path"])

    # CSV file is created immediately
    assert csv_path.exists()

    # Record step events
    rm.run_recorder.record_step(run_id, 0, "start")
    rm.run_recorder.record_step(run_id, 0, "end", "completed")
    rm.run_recorder.record_step(run_id, 1, "start")

    # stop_run closes the file and returns run metadata
    run = await rm.run_recorder.stop_run(run_id, "completed")
    assert run["outcome"] == "completed"
    assert run["csv_path"] == str(csv_path)
    assert csv_path.exists()

    # CSV has a header row and at least the rows written during the poll loop
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "timestamp" in (reader.fieldnames or [])
        assert "mission_name" in (reader.fieldnames or [])
        rows = list(reader)
    assert len(rows) > 0
    assert rows[0]["mission_name"] == "Lab test"


@pytest.mark.asyncio
async def test_delete_removes_csv(tmp_path):
    import henosync.core.run_recorder as rm

    result = await rm.run_recorder.start_run("Delete test", [])
    run_id = result["run_id"]
    csv_path = Path(result["csv_path"])

    await rm.run_recorder.stop_run(run_id, "completed")
    assert csv_path.exists()

    rm.run_recorder.delete_run(run_id)

    assert not csv_path.exists()
    assert rm.run_recorder.list_runs() == []


@pytest.mark.asyncio
async def test_record_step_after_stop_raises():
    import henosync.core.run_recorder as rm

    result = await rm.run_recorder.start_run("Stop test", [])
    run_id = result["run_id"]
    await rm.run_recorder.stop_run(run_id, "stopped")

    with pytest.raises(ValueError):
        rm.run_recorder.record_step(run_id, 0, "start")

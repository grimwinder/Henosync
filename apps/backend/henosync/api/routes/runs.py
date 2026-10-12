from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.run_recorder import run_recorder

router = APIRouter(prefix="/api/runs", tags=["runs"])


class StartRunRequest(BaseModel):
    mission: str
    steps: list[dict[str, Any]] = []


class StepEventRequest(BaseModel):
    index: int
    event: str  # "start" | "end"
    outcome: Optional[str] = None
    status_text: str = ""


class StopRunRequest(BaseModel):
    outcome: str  # "completed" | "stopped" | "failed"


class ExportRunRequest(BaseModel):
    path: str


@router.get("")
async def list_runs():
    return {"runs": run_recorder.list_runs()}


@router.post("/start")
async def start_run(request: StartRunRequest):
    return await run_recorder.start_run(request.mission, request.steps)


@router.get("/{run_id}")
async def get_run(run_id: str):
    try:
        return run_recorder.get_run(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@router.post("/{run_id}/step")
async def record_step(run_id: str, request: StepEventRequest):
    try:
        run_recorder.record_step(
            run_id, request.index, request.event, request.outcome, request.status_text
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request: StopRunRequest):
    try:
        return await run_recorder.stop_run(run_id, request.outcome)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/export")
async def export_run(run_id: str, request: ExportRunRequest):
    try:
        return {"path": run_recorder.export_csv(run_id, request.path)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/report")
async def run_report(run_id: str):
    try:
        return {"path": await run_recorder.report(run_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@router.delete("/{run_id}")
async def delete_run(run_id: str):
    try:
        run_recorder.delete_run(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}

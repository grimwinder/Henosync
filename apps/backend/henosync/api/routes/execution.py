from fastapi import APIRouter, HTTPException
from ...core.mission_engine import mission_engine

router = APIRouter(prefix="/api/missions", tags=["execution"])


@router.post("/{mission_id}/execute")
async def execute_mission(mission_id: str):
    """Start executing a mission."""
    success = await mission_engine.execute(mission_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to start mission. Check nodes are online "
                   "and no other mission is running."
        )
    return {"success": True, "status": mission_engine.get_status()}


@router.post("/{mission_id}/pause")
async def pause_mission(mission_id: str):
    """Pause the active mission."""
    success = await mission_engine.pause()
    if not success:
        raise HTTPException(
            status_code=400,
            detail="No active mission to pause"
        )
    return {"success": True, "status": mission_engine.get_status()}


@router.post("/{mission_id}/resume")
async def resume_mission(mission_id: str):
    """Resume a paused mission from exact step."""
    success = await mission_engine.resume()
    if not success:
        raise HTTPException(
            status_code=400,
            detail="No paused mission to resume"
        )
    return {"success": True, "status": mission_engine.get_status()}


@router.post("/{mission_id}/abort")
async def abort_mission(mission_id: str):
    """Abort the active mission immediately."""
    success = await mission_engine.abort()
    if not success:
        raise HTTPException(
            status_code=400,
            detail="No active mission to abort"
        )
    return {"success": True, "status": mission_engine.get_status()}


@router.get("/engine/status")
async def engine_status():
    """Get current mission engine status."""
    return mission_engine.get_status()
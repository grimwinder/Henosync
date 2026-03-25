from fastapi import APIRouter, HTTPException
from ...models import MissionCreate, MissionUpdate, Mission
from ...storage.mission_store import mission_store

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get("/")
async def list_missions():
    """Get all saved missions."""
    missions = await mission_store.get_all()
    return {"missions": [m.model_dump() for m in missions]}


@router.post("/")
async def create_mission(mission_create: MissionCreate):
    """Create a new mission."""
    mission = await mission_store.create(mission_create)
    return mission.model_dump()


@router.get("/{mission_id}")
async def get_mission(mission_id: str):
    """Get a specific mission."""
    mission = await mission_store.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission.model_dump()


@router.put("/{mission_id}")
async def update_mission(mission_id: str, update: MissionUpdate):
    """Update a mission."""
    mission = await mission_store.update(mission_id, update)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission.model_dump()


@router.delete("/{mission_id}")
async def delete_mission(mission_id: str):
    """Delete a mission."""
    success = await mission_store.delete(mission_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"success": True}
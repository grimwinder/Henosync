from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...core.zone_manager import zone_manager, ZoneType, GeoPoint

router = APIRouter(prefix="/api/zones", tags=["zones"])


class ZoneCreateRequest(BaseModel):
    name: str
    zone_type: str
    points: list[dict] = []
    center: Optional[dict] = None
    radius_m: Optional[float] = None
    color: str = "#4A9EFF"


@router.get("")
async def list_zones():
    zones = zone_manager.get_all_zones()
    return {"zones": [z.model_dump() for z in zones]}


@router.post("")
async def create_zone(body: ZoneCreateRequest):
    try:
        zone_type = ZoneType(body.zone_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid zone_type: {body.zone_type}")
    points = [GeoPoint(**p) for p in body.points]
    center = GeoPoint(**body.center) if body.center else None
    zone = await zone_manager.create_zone(
        name=body.name,
        zone_type=zone_type,
        points=points,
        center=center,
        radius_m=body.radius_m,
        color=body.color,
    )
    return zone.model_dump()


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    success = await zone_manager.delete_zone(zone_id)
    if not success:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"success": True}

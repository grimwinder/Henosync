from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...core.vicon_manager import local_to_gps, vicon_manager
from ...core.zone_manager import GeoPoint, ZoneType, zone_manager

router = APIRouter(prefix="/api/zones", tags=["zones"])


class ZoneCreateRequest(BaseModel):
    name: str
    zone_type: str
    points: list[dict] = []
    center: Optional[dict] = None
    radius_m: Optional[float] = None
    color: str = "#4A9EFF"
    map_mode: str = "gps"


@router.get("")
async def list_zones(mode: str = Query(default="gps")):
    zones = zone_manager.get_all_zones(map_mode=mode)
    return {"zones": [z.model_dump() for z in zones]}


def _vicon_point_to_gps(raw: dict, home_lat: float, home_lon: float) -> dict:
    """
    A point from VICONMap.tsx's drawing tools carries raw arena metres in
    its lat/lon fields (convention: lon=x_m, lat=y_m — see VICONMap.tsx),
    not real coordinates. Convert to real WGS84 here, once, at creation
    time, so every consumer downstream (auto-navigate's geometry, no-go
    zone checks, etc.) can keep assuming all positions are real WGS84 —
    matching the rest of the system.
    """
    lat, lon = local_to_gps(raw["lon"], raw["lat"], home_lat, home_lon)
    return {"lat": lat, "lon": lon}


@router.post("")
async def create_zone(body: ZoneCreateRequest):
    try:
        zone_type = ZoneType(body.zone_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid zone_type: {body.zone_type}")

    points_raw = body.points
    center_raw = body.center
    if body.map_mode == "vicon":
        origin = vicon_manager.origin
        if origin is None:
            raise HTTPException(
                status_code=400,
                detail="Set a VICON arena origin before drawing VICON zones — "
                       "open the VICON panel in the title bar.",
            )
        home_lat, home_lon = origin
        points_raw = [_vicon_point_to_gps(p, home_lat, home_lon) for p in points_raw]
        center_raw = _vicon_point_to_gps(center_raw, home_lat, home_lon) if center_raw else None

    points = [GeoPoint(**p) for p in points_raw]
    center = GeoPoint(**center_raw) if center_raw else None
    zone = await zone_manager.create_zone(
        name=body.name,
        zone_type=zone_type,
        points=points,
        center=center,
        radius_m=body.radius_m,
        color=body.color,
        map_mode=body.map_mode,
    )
    return zone.model_dump()


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    success = await zone_manager.delete_zone(zone_id)
    if not success:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"success": True}

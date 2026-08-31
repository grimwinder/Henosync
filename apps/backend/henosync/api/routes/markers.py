from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...core.marker_manager import MarkerType, marker_manager
from ...core.vicon_manager import local_to_gps, vicon_manager

router = APIRouter(prefix="/api/markers", tags=["markers"])


class MarkerCreateRequest(BaseModel):
    name: str
    marker_type: str
    lat: float
    lon: float
    color: str = "#4A9EFF"
    map_mode: str = "gps"


@router.get("")
async def list_markers(mode: str = Query(default="gps")):
    markers = marker_manager.get_all_markers(map_mode=mode)
    return {"markers": [m.model_dump() for m in markers]}


@router.post("")
async def create_marker(body: MarkerCreateRequest):
    try:
        marker_type = MarkerType(body.marker_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid marker_type: {body.marker_type}")

    lat, lon = body.lat, body.lon
    if body.map_mode == "vicon":
        origin = vicon_manager.origin
        if origin is None:
            raise HTTPException(
                status_code=400,
                detail="Set a VICON arena origin before placing VICON markers — "
                       "open the VICON panel in the title bar.",
            )
        # VICONMap.tsx's marker placement passes raw arena metres in lat/lon
        # (convention: lon=x_m, lat=y_m) — convert to real WGS84 once, here,
        # so downstream consumers can keep assuming real coordinates.
        home_lat, home_lon = origin
        lat, lon = local_to_gps(lon, lat, home_lat, home_lon)

    marker = await marker_manager.create_marker(
        name=body.name,
        marker_type=marker_type,
        lat=lat,
        lon=lon,
        color=body.color,
        map_mode=body.map_mode,
    )
    return marker.model_dump()


@router.delete("/{marker_id}")
async def delete_marker(marker_id: str):
    success = await marker_manager.delete_marker(marker_id)
    if not success:
        raise HTTPException(status_code=404, detail="Marker not found")
    return {"success": True}

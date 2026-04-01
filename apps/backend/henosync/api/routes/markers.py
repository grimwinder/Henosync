from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ...core.marker_manager import marker_manager, MarkerType

router = APIRouter(prefix="/api/markers", tags=["markers"])


class MarkerCreateRequest(BaseModel):
    name: str
    marker_type: str
    lat: float
    lon: float
    color: str = "#4A9EFF"


@router.get("")
async def list_markers():
    markers = marker_manager.get_all_markers()
    return {"markers": [m.model_dump() for m in markers]}


@router.post("")
async def create_marker(body: MarkerCreateRequest):
    try:
        marker_type = MarkerType(body.marker_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid marker_type: {body.marker_type}")
    marker = await marker_manager.create_marker(
        name=body.name,
        marker_type=marker_type,
        lat=body.lat,
        lon=body.lon,
        color=body.color,
    )
    return marker.model_dump()


@router.delete("/{marker_id}")
async def delete_marker(marker_id: str):
    success = await marker_manager.delete_marker(marker_id)
    if not success:
        raise HTTPException(status_code=404, detail="Marker not found")
    return {"success": True}
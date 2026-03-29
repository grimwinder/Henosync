from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from ...core.operation_manager import operation_manager
from ...core.zone_manager import zone_manager, ZoneType, GeoPoint

router = APIRouter(tags=["operations"])


# ── Control Plugins ────────────────────────────────────────────

@router.get("/api/control-plugins")
async def list_control_plugins():
    """List all loaded control plugins."""
    return {"plugins": operation_manager.get_registered_plugins()}


class StartOperationRequest(BaseModel):
    plugin_id: str
    config: dict[str, Any] = {}


@router.post("/api/operations/start")
async def start_operation(request: StartOperationRequest):
    """Start a control plugin operation."""
    success, message = await operation_manager.start_operation(
        request.plugin_id, request.config
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/api/operations/{plugin_id}/stop")
async def stop_operation(plugin_id: str):
    """Stop a running operation."""
    success, message = await operation_manager.stop_operation(plugin_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.get("/api/operations")
async def list_operations():
    """Get status of all running operations."""
    return {"operations": operation_manager.get_all_operation_statuses()}


# ── Zones ──────────────────────────────────────────────────────

class CreateZoneRequest(BaseModel):
    name: str
    zone_type: ZoneType
    points: list[GeoPoint] = []
    center: GeoPoint | None = None
    radius_m: float | None = None
    color: str = "#F05252"


@router.get("/api/zones")
async def list_zones():
    """Get all active zones."""
    return {"zones": [z.model_dump() for z in zone_manager.get_all_zones()]}


@router.post("/api/zones")
async def create_zone(request: CreateZoneRequest):
    """Create a new zone."""
    zone = zone_manager.create_zone(
        name=request.name,
        zone_type=request.zone_type,
        points=request.points,
        center=request.center,
        radius_m=request.radius_m,
        color=request.color
    )
    return zone.model_dump()


@router.delete("/api/zones/{zone_id}")
async def delete_zone(zone_id: str):
    """Delete a zone."""
    success = zone_manager.delete_zone(zone_id)
    if not success:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"success": True}
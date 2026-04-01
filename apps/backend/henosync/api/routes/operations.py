from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from ...core.operation_manager import operation_manager

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

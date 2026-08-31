from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


class OperatorInputRequest(BaseModel):
    input_key: str
    value: Any = None


@router.post("/api/operations/{plugin_id}/input")
async def send_operator_input(plugin_id: str, request: OperatorInputRequest):
    """Forward operator input (e.g. keyboard) to a running operation."""
    success, message = await operation_manager.send_operator_input(
        plugin_id, request.input_key, request.value
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.get("/api/operations/{plugin_id}/recruitable")
async def list_recruitable_devices(plugin_id: str):
    """Devices that could be manually added to this running operation."""
    devices = await operation_manager.get_recruitable_devices(plugin_id)
    return {"devices": devices}


class RecruitDeviceRequest(BaseModel):
    device_id: str


@router.post("/api/operations/{plugin_id}/recruit")
async def recruit_device(plugin_id: str, request: RecruitDeviceRequest):
    """Manually add an online device to a running operation."""
    success, message = await operation_manager.recruit_device_into_operation(
        plugin_id, request.device_id
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}

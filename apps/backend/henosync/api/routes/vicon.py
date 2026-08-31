from fastapi import APIRouter
from pydantic import BaseModel

from ...core.vicon_manager import vicon_manager

router = APIRouter(prefix="/api/vicon", tags=["vicon"])


class VICONConnectRequest(BaseModel):
    host: str
    port: int = 801


class VICONOriginRequest(BaseModel):
    home_lat: float
    home_lon: float


@router.get("/connection")
async def get_connection():
    saved = vicon_manager.saved_connection
    origin = vicon_manager.origin
    return {
        "host": saved[0] if saved else None,
        "port": saved[1] if saved else 801,
        "connected": vicon_manager.is_connected,
        "home_lat": origin[0] if origin else None,
        "home_lon": origin[1] if origin else None,
    }


@router.post("/origin")
async def set_origin(body: VICONOriginRequest):
    await vicon_manager.set_origin(body.home_lat, body.home_lon)
    return {"success": True}


@router.post("/connection")
async def connect(body: VICONConnectRequest):
    await vicon_manager.connect(body.host, body.port)
    return {"success": True}


@router.delete("/connection")
async def disconnect():
    await vicon_manager.disconnect()
    return {"success": True}


@router.get("/objects")
async def get_objects():
    names = await vicon_manager.get_subject_names()
    return {"objects": names}

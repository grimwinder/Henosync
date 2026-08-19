from fastapi import APIRouter
from pydantic import BaseModel

from ...core.vicon_manager import vicon_manager

router = APIRouter(prefix="/api/vicon", tags=["vicon"])


class VICONConnectRequest(BaseModel):
    host: str
    port: int = 801


@router.get("/connection")
async def get_connection():
    saved = vicon_manager.saved_connection
    return {
        "host": saved[0] if saved else None,
        "port": saved[1] if saved else 801,
        "connected": vicon_manager.is_connected,
    }


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

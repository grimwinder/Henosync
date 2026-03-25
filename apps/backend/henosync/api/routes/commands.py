from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from ...core.node_registry import node_registry
from ...plugin_system.registry import plugin_registry

router = APIRouter(prefix="/api/nodes", tags=["commands"])


class CommandRequest(BaseModel):
    capability: str
    params: dict[str, Any] = {}


@router.post("/{node_id}/command")
async def send_command(node_id: str, command: CommandRequest):
    """Send a command to a node."""
    node = node_registry.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    plugin_instance = plugin_registry.get_instance(node_id)
    if not plugin_instance:
        raise HTTPException(
            status_code=400,
            detail="Node has no active plugin instance"
        )

    result = await plugin_instance.send_command(
        node,
        command.capability,
        command.params
    )
    return result.model_dump()


@router.get("/{node_id}/stream_url")
async def get_stream_url(node_id: str):
    """Get the video stream URL for a node if available."""
    node = node_registry.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    plugin_instance = plugin_registry.get_instance(node_id)
    if not plugin_instance:
        raise HTTPException(
            status_code=400,
            detail="Node has no active plugin instance"
        )

    url = await plugin_instance.get_video_stream_url(node)
    return {"stream_url": url}
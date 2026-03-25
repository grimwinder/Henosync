from fastapi import APIRouter, HTTPException
from ...models import NodeCreate, NodeUpdate
from ...core.node_registry import node_registry

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("/")
async def list_nodes():
    """Get all nodes."""
    nodes = node_registry.get_all_nodes()
    return {"nodes": [n.model_dump() for n in nodes]}


@router.post("/")
async def add_node(node_create: NodeCreate):
    """Add a new node."""
    try:
        node = await node_registry.add_node(node_create)
        return node.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{node_id}")
async def get_node(node_id: str):
    """Get a specific node by id."""
    node = node_registry.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.model_dump()


@router.delete("/{node_id}")
async def remove_node(node_id: str):
    """Remove a node."""
    success = await node_registry.remove_node(node_id)
    if not success:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"success": True}


@router.post("/{node_id}/reconnect")
async def reconnect_node(node_id: str):
    """Trigger a reconnection attempt for a node."""
    success = await node_registry.reconnect_node(node_id)
    if not success:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"success": True}
from fastapi import APIRouter
from ...core.failsafe_manager import failsafe_manager

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.post("/emergency-stop")
async def emergency_stop():
    """
    Trigger emergency stop on all connected nodes immediately.
    Invokes get_safe_state on every online node and aborts
    any active mission. Cannot be cancelled once triggered.
    """
    await failsafe_manager.emergency_stop_all()
    return {
        "success": True,
        "message": "Emergency stop triggered on all nodes"
    }
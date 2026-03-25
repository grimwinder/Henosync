from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import WebSocket
from pathlib import Path
from ..plugin_system.loader import PluginLoader
from ..core.node_registry import node_registry
from .routes.nodes import router as nodes_router
import logging
from .websocket_server import telemetry_websocket_handler, events_websocket_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PLUGINS_DIR = Path(__file__).parent.parent.parent.parent.parent / "plugins"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Henosync Backend",
        version="0.1.0",
        description="Henosync core engine API"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(nodes_router)

    @app.on_event("startup")
    async def startup():
        logger.info("Henosync backend starting...")

        # Load plugins first
        loader = PluginLoader(PLUGINS_DIR)
        count = loader.load_all()
        logger.info(f"Plugin loading complete — {count} plugins loaded")

        # Initialize node registry
        await node_registry.initialize()
        logger.info("Node registry ready")

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Henosync backend shutting down...")
        await node_registry.shutdown()

    @app.get("/health")
    async def health():
        nodes = node_registry.get_all_nodes()
        return {
            "status": "ok",
            "version": "0.1.0",
            "nodes_total": len(nodes),
            "nodes_online": len(node_registry.get_online_nodes())
        }

    @app.get("/api/plugins")
    async def list_plugins():
        from ..plugin_system.registry import plugin_registry
        return {"plugins": plugin_registry.list_plugins()}
    
    @app.websocket("/ws/telemetry")
    async def telemetry_ws(websocket: WebSocket):
        await telemetry_websocket_handler(websocket)

    @app.websocket("/ws/events")
    async def events_ws(websocket: WebSocket):
        await events_websocket_handler(websocket)

    return app
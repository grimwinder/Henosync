import asyncio
import uvicorn
from henosync.api.app import create_app

app = create_app()

if __name__ == "__main__":
    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
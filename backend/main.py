from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from backend.core.config import settings
from backend.core.database import init_database
from backend.services.scheduler_service import scheduler_service
from backend.api.routes_agents import router as agents_router
from backend.api.routes_chat import router as chat_router
from backend.api.routes_tasks import router as tasks_router
from backend.api.routes_system import router as system_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mas.main")


@asynccontextmanager
async def lifespan(app: Any) -> AsyncGenerator[None, None]:
    """Application lifecycle manager: database init and scheduler service."""
    logger.info("Initializing SQLite database tables and seed agents...")
    await init_database()

    logger.info("Starting Autonomous Scheduler Service...")
    await scheduler_service.start()

    yield

    logger.info("Shutting down Autonomous Scheduler Service...")
    await scheduler_service.stop()


# FastAPI setup with graceful fallback
try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    app = FastAPI(
        title="Autonomous Multi-Agent System (MAS) API",
        description="Local, autonomous multi-agent platform inspired by Grok with LangGraph supervisor orchestration.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Standardized Exception Handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled API exception on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": str(exc),
                "path": request.url.path,
            },
        )

    # Include Routers
    app.include_router(agents_router)
    app.include_router(chat_router)
    app.include_router(tasks_router)
    app.include_router(system_router)

except ImportError:
    class MockFastAPIApp:
        """Mock app for running or testing outside FastAPI runtime."""
        def __init__(self) -> None:
            self.title = "Autonomous MAS API (Mock Mode)"
    app = MockFastAPIApp()  # type: ignore


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.port, reload=True)

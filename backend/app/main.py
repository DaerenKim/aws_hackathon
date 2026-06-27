"""FastAPI application entry point for Hackathon Studio API.

Configures the application with CORS middleware, includes all API routers,
and provides a health check endpoint. Uses a lifespan handler to ensure
the workspace directory exists at startup.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.deliverables import router as deliverables_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Ensures the workspace directory and required subdirectories exist
    before the application starts serving requests.
    """
    workspace_path = Path(
        os.environ.get("WORKSPACE_PATH", "./shared_workspace")
    ).resolve()

    # Create workspace and standard subdirectories
    workspace_path.mkdir(parents=True, exist_ok=True)
    (workspace_path / "inputs").mkdir(exist_ok=True)
    (workspace_path / "logs").mkdir(exist_ok=True)

    yield


app = FastAPI(
    title="Hackathon Studio API",
    description="Autonomous multi-agent AI software studio that transforms hackathon inputs into a complete MVP.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(deliverables_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Simple status object indicating the service is running.
    """
    return {"status": "healthy"}

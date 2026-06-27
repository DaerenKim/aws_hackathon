"""Shared dependency injection for FastAPI routes.

Provides singleton instances of core services (workspace, state manager,
ollama client) via FastAPI's Depends() mechanism, configured through
environment variables.
"""

import os
from pathlib import Path
from functools import lru_cache

from app.services.workspace import WorkspaceService
from app.services.state_manager import StateManager
from app.services.ollama_client import OllamaClient
from app.models.artifacts import OllamaConfig


def _get_workspace_path() -> Path:
    """Resolve workspace path from environment variable.

    Uses WORKSPACE_PATH env var, defaulting to ./shared_workspace
    relative to the backend directory.
    """
    workspace_path = os.environ.get("WORKSPACE_PATH", "./shared_workspace")
    return Path(workspace_path).resolve()


@lru_cache()
def get_workspace_service() -> WorkspaceService:
    """Singleton WorkspaceService instance.

    Returns:
        WorkspaceService configured with the workspace path.
    """
    workspace_path = _get_workspace_path()
    workspace_path.mkdir(parents=True, exist_ok=True)
    return WorkspaceService(workspace_root=workspace_path)


@lru_cache()
def get_state_manager() -> StateManager:
    """Singleton StateManager instance.

    Returns:
        StateManager configured with the project_state.json path
        within the workspace.
    """
    workspace_path = _get_workspace_path()
    state_file = workspace_path / "project_state.json"
    return StateManager(state_file_path=state_file)


@lru_cache()
def get_ollama_client() -> OllamaClient:
    """Singleton OllamaClient instance.

    Configurable via environment variables:
    - OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
    - OLLAMA_MODEL: Model name (default: llama3)
    - OLLAMA_TIMEOUT: Request timeout in seconds (default: 120)

    Returns:
        Configured OllamaClient instance.
    """
    config = OllamaConfig(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.environ.get("OLLAMA_MODEL", "llama3"),
        timeout_seconds=float(os.environ.get("OLLAMA_TIMEOUT", "120")),
    )
    return OllamaClient(config=config)

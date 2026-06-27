"""Unit tests for the Backend Engineer Agent."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from backend.app.agents.backend_engineer import (
    BackendEngineerAgent,
    AI_SERVICE_MAX_RETRIES,
    AI_SERVICE_TIMEOUT_SECONDS,
)
from backend.app.models.artifacts import AgentResult
from backend.app.models.project_state import AgentStatus
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


# Sample architecture content that includes AI integration
ARCHITECTURE_WITH_AI = """\
# Architecture

## API Endpoints

- POST /api/tasks - Create a new task
- GET /api/tasks - List all tasks
- GET /api/tasks/{id} - Get task details
- POST /api/tasks/{id}/prioritize - AI-powered priority scoring

## AI Service Integration

The application uses OpenAI GPT-4 for task prioritization.
Each AI call has a 30s timeout with 3 retries.

## Database Schema

- tasks table: id, title, description, priority, created_at
- users table: id, name, email

## Tech Stack

- FastAPI + Pydantic
- SQLite via SQLAlchemy
- OpenAI API for AI features
"""

# Sample architecture without AI integration
ARCHITECTURE_NO_AI = """\
# Architecture

## API Endpoints

- POST /api/items - Create an item
- GET /api/items - List items
- DELETE /api/items/{id} - Delete an item

## Database Schema

- items table: id, name, quantity, created_at

## Tech Stack

- FastAPI + Pydantic
- SQLite
"""

# LLM response mocks
MOCK_PLAN = """\
1. Endpoints: POST /api/tasks, GET /api/tasks, GET /api/tasks/{id}, POST /api/tasks/{id}/prioritize
2. Models: Task, TaskCreate, TaskResponse
3. Database: tasks, users tables
4. AI: OpenAI integration for prioritization
5. Dependencies: fastapi, sqlalchemy, openai, httpx
"""

MOCK_REQUIREMENTS = """\
fastapi
uvicorn[standard]
pydantic
pytest
httpx
sqlalchemy
openai
python-multipart
"""

MOCK_MODELS = '''\
"""Data models for the backend application."""

from pydantic import BaseModel, Field
from datetime import datetime


class TaskCreate(BaseModel):
    """Request model for creating a task."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class TaskResponse(BaseModel):
    """Response model for a task."""
    id: int
    title: str
    description: str
    priority: int = 0
    created_at: datetime
'''

MOCK_AI_SERVICE = '''\
"""AI service integration with timeout, retry, and fallback."""

import asyncio
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

AI_TIMEOUT = 30
MAX_RETRIES = 3


@dataclass
class AIResponse:
    """Response from AI service."""
    success: bool
    content: str
    error: str | None = None


class AIServiceError(Exception):
    """Raised when AI service fails after all retries."""
    pass


async def call_ai_service(prompt: str) -> AIResponse:
    """Call AI service with timeout and retry logic."""
    api_key = os.environ.get("OPENAI_API_KEY", "")

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "gpt-4", "messages": [{"role": "user", "content": prompt}]},
                )
                response.raise_for_status()
                data = response.json()
                return AIResponse(success=True, content=data["choices"][0]["message"]["content"])
        except Exception as e:
            logger.warning(f"AI service attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** (attempt + 1))

    # Fallback response
    logger.error("AI service failed after all retries")
    return AIResponse(success=False, content="", error="AI service unavailable after retries")
'''

MOCK_ROUTES = '''\
"""FastAPI route definitions."""

import logging
from fastapi import APIRouter, HTTPException

from models import TaskCreate, TaskResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate):
    """Create a new task."""
    logger.info(f"Creating task: {task.title}")
    return TaskResponse(id=1, title=task.title, description=task.description, priority=0, created_at="2024-01-01T00:00:00")


@router.get("/api/tasks")
async def list_tasks():
    """List all tasks."""
    return []
'''

MOCK_MAIN = '''\
"""FastAPI application entry point."""

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Hackathon API", description="Generated backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")))
'''

MOCK_TESTS = '''\
"""Unit tests for the backend API."""

import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_task_success(client):
    response = await client.post("/api/tasks", json={"title": "Test Task"})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_task_error(client):
    response = await client.post("/api/tasks", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks(client):
    response = await client.get("/api/tasks")
    assert response.status_code == 200
'''


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create workspace with required directories."""
    ws = WorkspaceService(workspace_root=tmp_path)
    (tmp_path / "inputs").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "backend").mkdir(exist_ok=True)
    return ws


@pytest_asyncio.fixture
async def state_manager(tmp_path: Path) -> StateManager:
    """Create state manager with project_planner marked as completed."""
    state_file = tmp_path / "project_state.json"
    manager = StateManager(state_file_path=state_file)
    await manager.read_state()
    # Mark project_planner as completed so we can read architecture.md
    await manager.update_agent_status("project_planner", AgentStatus.COMPLETED)
    return manager


@pytest_asyncio.fixture
async def ollama_client() -> OllamaClient:
    """Create OllamaClient with mocked generate returning varied responses."""
    client = OllamaClient()
    client.generate = AsyncMock(
        side_effect=[
            MOCK_PLAN,
            MOCK_REQUIREMENTS,
            MOCK_MODELS,
            MOCK_AI_SERVICE,
            MOCK_ROUTES,
            MOCK_MAIN,
            MOCK_TESTS,
        ]
    )
    return client


@pytest_asyncio.fixture
async def ollama_client_no_ai() -> OllamaClient:
    """Create OllamaClient for architecture without AI integration."""
    client = OllamaClient()
    client.generate = AsyncMock(
        side_effect=[
            MOCK_PLAN,
            MOCK_REQUIREMENTS,
            MOCK_MODELS,
            MOCK_ROUTES,
            MOCK_MAIN,
            MOCK_TESTS,
        ]
    )
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> BackendEngineerAgent:
    """Create Backend Engineer Agent with AI integration architecture."""
    return BackendEngineerAgent(
        agent_name="backend_engineer",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


@pytest_asyncio.fixture
async def agent_no_ai(
    ollama_client_no_ai: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> BackendEngineerAgent:
    """Create Backend Engineer Agent without AI integration."""
    return BackendEngineerAgent(
        agent_name="backend_engineer",
        ollama_client=ollama_client_no_ai,
        workspace=workspace,
        state_manager=state_manager,
    )


async def _write_architecture(workspace: WorkspaceService, content: str) -> None:
    """Helper to write architecture.md to workspace."""
    await workspace.write_file("architecture.md", content, agent_name=None)


class TestMissingArchitecture:
    """Tests for handling missing architecture.md."""

    @pytest.mark.asyncio
    async def test_fails_when_architecture_missing(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should return failure when architecture.md does not exist."""
        result = await agent.execute({})

        assert result.success is False
        assert "architecture.md" in result.error

    @pytest.mark.asyncio
    async def test_fails_when_planner_not_completed(
        self,
        workspace: WorkspaceService,
        state_manager: StateManager,
        ollama_client: OllamaClient,
    ) -> None:
        """Should fail when project_planner status is not completed."""
        # Reset planner status to pending
        await state_manager.update_agent_status("project_planner", AgentStatus.PENDING)
        await _write_architecture(workspace, ARCHITECTURE_WITH_AI)

        agent = BackendEngineerAgent(
            agent_name="backend_engineer",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )
        result = await agent.execute({})

        assert result.success is False
        assert "architecture.md" in result.error


class TestSuccessfulGeneration:
    """Tests for successful backend code generation."""

    @pytest.mark.asyncio
    async def test_generates_all_files_with_ai(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should generate all backend files when AI integration is specified."""
        await _write_architecture(workspace, ARCHITECTURE_WITH_AI)

        result = await agent.execute({})

        assert result.success is True
        assert "backend/requirements.txt" in result.artifacts_produced
        assert "backend/models.py" in result.artifacts_produced
        assert "backend/ai_service.py" in result.artifacts_produced
        assert "backend/routes.py" in result.artifacts_produced
        assert "backend/main.py" in result.artifacts_produced
        assert "backend/test_main.py" in result.artifacts_produced

    @pytest.mark.asyncio
    async def test_generates_files_without_ai(
        self, agent_no_ai: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should skip ai_service.py when no AI integration specified."""
        await _write_architecture(workspace, ARCHITECTURE_NO_AI)

        result = await agent_no_ai.execute({})

        assert result.success is True
        assert "backend/ai_service.py" not in result.artifacts_produced
        assert "backend/requirements.txt" in result.artifacts_produced
        assert "backend/models.py" in result.artifacts_produced
        assert "backend/routes.py" in result.artifacts_produced
        assert "backend/main.py" in result.artifacts_produced
        assert "backend/test_main.py" in result.artifacts_produced

    @pytest.mark.asyncio
    async def test_files_written_to_workspace(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should write generated files to the workspace backend/ directory."""
        await _write_architecture(workspace, ARCHITECTURE_WITH_AI)

        await agent.execute({})

        # Verify files exist in workspace
        assert await workspace.file_exists("backend/requirements.txt")
        assert await workspace.file_exists("backend/models.py")
        assert await workspace.file_exists("backend/routes.py")
        assert await workspace.file_exists("backend/main.py")
        assert await workspace.file_exists("backend/test_main.py")

    @pytest.mark.asyncio
    async def test_requirements_includes_fastapi(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should ensure requirements.txt includes fastapi."""
        await _write_architecture(workspace, ARCHITECTURE_WITH_AI)

        await agent.execute({})

        content = await workspace.read_file("backend/requirements.txt")
        assert "fastapi" in content.lower()

    @pytest.mark.asyncio
    async def test_duration_tracked(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should track execution duration."""
        await _write_architecture(workspace, ARCHITECTURE_WITH_AI)

        result = await agent.execute({})

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_llm_called_with_architecture(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """Should pass architecture content to LLM in prompts."""
        await _write_architecture(workspace, ARCHITECTURE_WITH_AI)

        await agent.execute({})

        # The first call should be for the implementation plan
        first_call = agent.ollama_client.generate.call_args_list[0]
        prompt = first_call.args[0]
        assert "API Endpoints" in prompt or "architecture" in prompt.lower()


class TestAIIntegrationDetection:
    """Tests for _architecture_has_ai_integration detection."""

    def test_detects_openai_keyword(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should detect AI integration when 'openai' is mentioned."""
        assert agent._architecture_has_ai_integration("Uses OpenAI for inference")

    def test_detects_claude_keyword(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should detect AI integration when 'claude' is mentioned."""
        assert agent._architecture_has_ai_integration("Integrates with Claude API")

    def test_detects_gpt_keyword(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should detect AI integration when 'gpt' is mentioned."""
        assert agent._architecture_has_ai_integration("Uses GPT-4 for analysis")

    def test_detects_llm_keyword(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should detect AI integration when 'llm' is mentioned."""
        assert agent._architecture_has_ai_integration("LLM-powered features")

    def test_no_ai_for_plain_architecture(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should return False when no AI keywords present."""
        assert not agent._architecture_has_ai_integration(
            "Simple CRUD API with FastAPI and PostgreSQL"
        )

    def test_case_insensitive_detection(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should detect AI keywords regardless of case."""
        assert agent._architecture_has_ai_integration("OPENAI integration")
        assert agent._architecture_has_ai_integration("AI SERVICE layer")


class TestErrorCases:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_error_includes_agent_name(
        self, agent: BackendEngineerAgent, workspace: WorkspaceService
    ) -> None:
        """AgentResult should include the agent name on failure."""
        result = await agent.execute({})

        assert result.agent_name == "backend_engineer"

    @pytest.mark.asyncio
    async def test_returns_empty_artifacts_on_failure(
        self, agent: BackendEngineerAgent
    ) -> None:
        """Should return empty artifacts list on failure."""
        result = await agent.execute({})

        assert result.artifacts_produced == []

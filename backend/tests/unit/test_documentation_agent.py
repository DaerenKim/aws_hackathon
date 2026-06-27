"""Unit tests for the Documentation Agent."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from backend.app.agents.documentation import (
    DocumentationAgent,
    MIN_DOC_LENGTH,
    OUTPUT_FILES,
)
from backend.app.models.artifacts import AgentResult
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


# Sample content that exceeds MIN_DOC_LENGTH (200 chars)
SAMPLE_README = """# MyProject

## Overview

MyProject is an AI-powered hackathon submission that helps developers build faster.
It combines automated code generation with intelligent task scheduling.

## Setup Instructions

### Backend
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
npm install
npm run dev
```

## Usage

1. Upload your hackathon brief
2. Review the generated plan
3. Approve and let the AI build

## Technology Stack

- Backend: FastAPI (Python 3.11)
- Frontend: Next.js 14, TypeScript, TailwindCSS
- LLM: Ollama (local inference)
- Database: SQLite
"""

SAMPLE_DEV_GUIDE = """# Developer Guide

## Code Organization

```
backend/       - FastAPI server and agents
frontend/      - Next.js dashboard
shared_workspace/ - Runtime artifacts
```

## Local Development Setup

1. Install Python 3.11+ and Node.js 18+
2. Clone the repository
3. Install backend dependencies: `pip install -r backend/requirements.txt`
4. Install frontend dependencies: `cd frontend && npm install`
5. Start Ollama: `ollama serve`

## Contribution Guidelines

- Create feature branches from `main`
- Write tests for new functionality
- Run linting before submitting PRs

## Architecture Overview

The system uses a hub-and-spoke model with a central orchestrator coordinating 10 specialized AI agents.
"""

SAMPLE_API_DOCS = """# API Documentation

## Overview

Base URL: `http://localhost:8000/api`

## Endpoints

### POST /api/inputs/upload
Upload hackathon brief or judging rubric files.

**Request:** multipart/form-data with file field
**Response:** `{"status": "uploaded", "filename": "brief.pdf"}`

### POST /api/inputs/submit
Submit project idea and optional tech stack.

**Request Body:**
```json
{"project_idea": "string", "tech_stack": "string | null"}
```

**Response:** `{"status": "validated"}`

### GET /api/workflow/state
Get the current project state.

**Response:** ProjectState JSON object

## Error Handling

All errors return `{"detail": "error message"}` with appropriate HTTP status codes.
"""


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create workspace with required directories."""
    ws = WorkspaceService(workspace_root=tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    return ws


@pytest_asyncio.fixture
async def state_manager(tmp_path: Path) -> StateManager:
    """Create state manager."""
    state_file = tmp_path / "project_state.json"
    manager = StateManager(state_file_path=state_file)
    await manager.read_state()
    return manager


@pytest_asyncio.fixture
async def ollama_client() -> OllamaClient:
    """Create OllamaClient with mocked generate."""
    client = OllamaClient()
    client.generate = AsyncMock(
        side_effect=[SAMPLE_README, SAMPLE_DEV_GUIDE, SAMPLE_API_DOCS]
    )
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> DocumentationAgent:
    """Create Documentation Agent."""
    return DocumentationAgent(
        agent_name="documentation",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


async def _write_source_artifacts(workspace: WorkspaceService) -> None:
    """Helper to write all source artifacts to workspace."""
    await workspace.write_file(
        "project_spec.md",
        "# Project Spec\n## Refined Idea\nAn AI task manager.\n## MVP Scope\nCore features.",
    )
    await workspace.write_file(
        "architecture.md",
        "# Architecture\n## Tech Stack\nFastAPI, Next.js\n## Endpoints\nPOST /api/inputs",
    )
    await workspace.write_file(
        "backend/requirements.txt",
        "fastapi==0.104.1\nuvicorn==0.24.0\npydantic==2.5.0\n",
        agent_name=None,
    )
    await workspace.write_file(
        "frontend/package.json",
        '{"name": "hackathon-frontend", "scripts": {"dev": "next dev", "build": "next build"}, "dependencies": {"next": "14.0.0"}}',
        agent_name=None,
    )


class TestSuccessfulGeneration:
    """Tests for successful documentation generation."""

    @pytest.mark.asyncio
    async def test_generates_all_three_docs(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should generate README.md, developer_guide.md, and api_docs.md."""
        await _write_source_artifacts(workspace)

        result = await agent.execute({})

        assert result.success is True
        assert set(result.artifacts_produced) == set(OUTPUT_FILES)

    @pytest.mark.asyncio
    async def test_writes_docs_to_workspace(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should write all docs to the workspace root."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        for filename in OUTPUT_FILES:
            assert await workspace.file_exists(filename)
            content = await workspace.read_file(filename)
            assert len(content) >= MIN_DOC_LENGTH

    @pytest.mark.asyncio
    async def test_duration_tracked(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should track execution duration."""
        await _write_source_artifacts(workspace)

        result = await agent.execute({})

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_calls_llm_three_times(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should call LLM once per document."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        assert agent.ollama_client.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_uses_technical_writer_system_prompt(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should use the technical writer system prompt."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        for call in agent.ollama_client.generate.call_args_list:
            system = call.kwargs.get("system", "")
            assert "technical writer" in system.lower() or "documentation" in system


class TestMissingSourceArtifacts:
    """Tests for graceful handling of missing source artifacts."""

    @pytest.mark.asyncio
    async def test_succeeds_with_no_sources(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should still generate docs when no source artifacts exist."""
        # No source artifacts written — all missing

        result = await agent.execute({})

        assert result.success is True
        assert len(result.artifacts_produced) == 3

    @pytest.mark.asyncio
    async def test_succeeds_with_partial_sources(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should succeed with only some source artifacts available."""
        await workspace.write_file(
            "project_spec.md",
            "# Project\nSome project spec content here.",
        )

        result = await agent.execute({})

        assert result.success is True
        assert len(result.artifacts_produced) == 3

    @pytest.mark.asyncio
    async def test_includes_missing_artifacts_in_prompt(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should tell LLM about missing artifacts so it can note incomplete sections."""
        # Only project_spec.md available
        await workspace.write_file(
            "project_spec.md", "# Project\nSpec content."
        )

        await agent.execute({})

        # Check that the prompts mention missing artifacts
        first_call = agent.ollama_client.generate.call_args_list[0]
        prompt = first_call.args[0]
        assert "MISSING" in prompt or "missing" in prompt.lower()


class TestMinimumLengthValidation:
    """Tests for the ≥200 character requirement."""

    @pytest.mark.asyncio
    async def test_fails_when_doc_too_short(
        self,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should fail if a generated doc is below 200 chars after retry."""
        short_content = "# README\nToo short."
        client = OllamaClient()
        # All calls return short content (initial + retry for each doc)
        client.generate = AsyncMock(return_value=short_content)

        agent = DocumentationAgent(
            agent_name="documentation",
            ollama_client=client,
            workspace=workspace,
            state_manager=state_manager,
        )

        result = await agent.execute({})

        assert result.success is False
        assert "below the required minimum" in result.error or "characters" in result.error

    @pytest.mark.asyncio
    async def test_retries_when_initial_generation_short(
        self,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should retry generation when initial output is too short."""
        short_content = "# README\nToo short."
        client = OllamaClient()
        # First call short, retry returns valid content for README
        # Then normal for dev guide and api docs
        client.generate = AsyncMock(
            side_effect=[
                short_content,     # README first attempt (short)
                SAMPLE_README,     # README retry (valid)
                SAMPLE_DEV_GUIDE,  # dev guide first attempt (valid)
                SAMPLE_API_DOCS,   # api docs first attempt (valid)
            ]
        )

        agent = DocumentationAgent(
            agent_name="documentation",
            ollama_client=client,
            workspace=workspace,
            state_manager=state_manager,
        )
        await _write_source_artifacts(workspace)

        result = await agent.execute({})

        assert result.success is True
        # 4 calls: short README + retry README + dev guide + api docs
        assert client.generate.call_count == 4

    def test_validate_length_accepts_valid(self) -> None:
        """Should accept content at or above 200 chars."""
        assert DocumentationAgent._validate_length("x" * 200) is True
        assert DocumentationAgent._validate_length("x" * 500) is True

    def test_validate_length_rejects_short(self) -> None:
        """Should reject content below 200 chars."""
        assert DocumentationAgent._validate_length("x" * 199) is False
        assert DocumentationAgent._validate_length("") is False


class TestSourceReading:
    """Tests for _read_sources method."""

    @pytest.mark.asyncio
    async def test_reads_all_available_sources(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should read all existing source artifacts."""
        await _write_source_artifacts(workspace)

        sources, missing = await agent._read_sources()

        assert "project_spec.md" in sources
        assert "architecture.md" in sources
        assert "backend/requirements.txt" in sources
        assert "frontend/package.json" in sources
        assert len(missing) == 0

    @pytest.mark.asyncio
    async def test_reports_missing_sources(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should report which sources are missing."""
        # Don't write any sources
        sources, missing = await agent._read_sources()

        assert len(sources) == 0
        assert "project_spec.md" in missing
        assert "architecture.md" in missing

    @pytest.mark.asyncio
    async def test_handles_empty_source_file(
        self, agent: DocumentationAgent, workspace: WorkspaceService
    ) -> None:
        """Should treat empty source files as missing."""
        await workspace.write_file("project_spec.md", "")

        sources, missing = await agent._read_sources()

        assert "project_spec.md" not in sources
        assert "project_spec.md" in missing
        assert "empty" in missing["project_spec.md"].lower()

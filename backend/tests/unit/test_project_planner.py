"""Unit tests for the Project Planner Agent."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from backend.app.agents.project_planner import (
    ProjectPlannerAgent,
    REQUIRED_SECTIONS,
)
from backend.app.models.artifacts import AgentResult
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


# A valid project spec with all required sections
VALID_PROJECT_SPEC = """# Project Specification

## Refined Idea

A smart task management tool that uses AI to automatically prioritize
and schedule tasks based on deadlines and team capacity.

## Elevator Pitch

TaskFlow AI helps hackathon teams stay organized by auto-prioritizing
tasks based on deadlines. It integrates with GitHub to track progress.
Teams can ship faster with less coordination overhead.

## Target Users

- Hackathon teams (2-5 members)
- Student developers
- First-time hackathon participants

## MVP Scope

- Task creation and assignment
- AI-powered priority scoring
- Simple Kanban board view
- GitHub integration for commits

## Stretch Goals

- Real-time collaboration
- Slack notifications
- Historical analytics

## Timeline

- Phase 1 (0-4h): Backend API + data models
- Phase 2 (4-8h): Frontend Kanban board
- Phase 3 (8-10h): AI prioritization
- Phase 4 (10-12h): Polish and demo prep

## Constraints Applied

- Time: 12-hour hackathon duration limits MVP to 4 core features
- Team: 3-person team constrains parallel development tracks
- Theme: "Developer Productivity" — scoped to task management domain
"""

TECH_STACK_RECOMMENDATION = """- Frontend: Next.js with TypeScript
- Backend: FastAPI (Python)
- Database: SQLite for simplicity
- Key libraries: LangChain, TailwindCSS, shadcn/ui
- Justification: Fast iteration, strong typing, good hackathon DX.
"""


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create workspace with inputs directory."""
    ws = WorkspaceService(workspace_root=tmp_path)
    (tmp_path / "inputs").mkdir(exist_ok=True)
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
    client.generate = AsyncMock(return_value=VALID_PROJECT_SPEC)
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> ProjectPlannerAgent:
    """Create Project Planner Agent."""
    return ProjectPlannerAgent(
        agent_name="project_planner",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


async def _write_required_inputs(workspace: WorkspaceService) -> None:
    """Helper to write the minimum required inputs."""
    await workspace.write_file(
        "inputs/hackathon_brief.txt",
        "24-hour hackathon. Theme: Developer Productivity. Team size: 3.",
    )
    await workspace.write_file(
        "inputs/project_idea.txt",
        "An AI-powered task manager for hackathon teams.",
    )


class TestMissingInputs:
    """Tests for handling missing required inputs."""

    @pytest.mark.asyncio
    async def test_fails_when_brief_missing(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should return failure when hackathon_brief.txt is missing."""
        await workspace.write_file("inputs/project_idea.txt", "My idea")

        result = await agent.execute({})

        assert result.success is False
        assert "hackathon_brief.txt" in result.error

    @pytest.mark.asyncio
    async def test_fails_when_idea_missing(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should return failure when project_idea.txt is missing."""
        await workspace.write_file("inputs/hackathon_brief.txt", "Brief content")

        result = await agent.execute({})

        assert result.success is False
        assert "project_idea.txt" in result.error

    @pytest.mark.asyncio
    async def test_fails_when_all_inputs_missing(
        self, agent: ProjectPlannerAgent
    ) -> None:
        """Should return failure listing all missing inputs."""
        result = await agent.execute({})

        assert result.success is False
        assert "hackathon_brief.txt" in result.error
        assert "project_idea.txt" in result.error


class TestSuccessfulGeneration:
    """Tests for successful project specification generation."""

    @pytest.mark.asyncio
    async def test_generates_project_spec(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should generate and save project_spec.md on success."""
        await _write_required_inputs(workspace)

        result = await agent.execute({})

        assert result.success is True
        assert "project_spec.md" in result.artifacts_produced
        content = await workspace.read_file("project_spec.md")
        assert "## Refined Idea" in content

    @pytest.mark.asyncio
    async def test_calls_llm_with_system_prompt(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should call LLM with the product manager system prompt."""
        await _write_required_inputs(workspace)

        await agent.execute({})

        agent.ollama_client.generate.assert_called()
        call_kwargs = agent.ollama_client.generate.call_args.kwargs
        system_prompt = call_kwargs.get("system", "")
        assert "product manager" in system_prompt.lower() or "project_planner" in system_prompt

    @pytest.mark.asyncio
    async def test_includes_brief_in_prompt(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should include the hackathon brief content in the LLM prompt."""
        await _write_required_inputs(workspace)

        await agent.execute({})

        call_args = agent.ollama_client.generate.call_args
        prompt = call_args.args[0]
        assert "Developer Productivity" in prompt

    @pytest.mark.asyncio
    async def test_includes_idea_in_prompt(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should include the project idea in the LLM prompt."""
        await _write_required_inputs(workspace)

        await agent.execute({})

        # First call is the spec generation (second is tech recommendation)
        first_call = agent.ollama_client.generate.call_args_list[0]
        prompt = first_call.args[0]
        assert "AI-powered task manager" in prompt

    @pytest.mark.asyncio
    async def test_includes_rubric_when_present(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should include judging rubric in prompt when available."""
        await _write_required_inputs(workspace)
        await workspace.write_file(
            "inputs/judging_rubric.txt",
            "Innovation: 30%, Technical: 40%, Presentation: 30%",
        )

        await agent.execute({})

        # First call is the spec generation
        first_call = agent.ollama_client.generate.call_args_list[0]
        prompt = first_call.args[0]
        assert "Innovation: 30%" in prompt

    @pytest.mark.asyncio
    async def test_includes_tech_stack_when_present(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should include preferred tech stack in prompt when available."""
        await _write_required_inputs(workspace)
        await workspace.write_file(
            "inputs/tech_stack.txt",
            "Next.js, FastAPI, PostgreSQL",
        )

        await agent.execute({})

        call_args = agent.ollama_client.generate.call_args
        prompt = call_args.args[0]
        assert "Next.js, FastAPI, PostgreSQL" in prompt

    @pytest.mark.asyncio
    async def test_duration_tracked(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should track execution duration."""
        await _write_required_inputs(workspace)

        result = await agent.execute({})

        assert result.duration_seconds > 0


class TestTechStackRecommendation:
    """Tests for tech stack recommendation when none provided."""

    @pytest.mark.asyncio
    async def test_recommends_tech_stack_when_missing(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should ask LLM for tech stack recommendation when not provided."""
        await _write_required_inputs(workspace)
        # First call returns spec, second returns tech recommendation
        agent.ollama_client.generate = AsyncMock(
            side_effect=[VALID_PROJECT_SPEC, TECH_STACK_RECOMMENDATION]
        )

        result = await agent.execute({})

        assert result.success is True
        content = await workspace.read_file("project_spec.md")
        assert "## Recommended Tech Stack" in content

    @pytest.mark.asyncio
    async def test_skips_recommendation_when_tech_stack_provided(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should NOT ask for recommendation when tech stack is provided."""
        await _write_required_inputs(workspace)
        await workspace.write_file("inputs/tech_stack.txt", "React, Django")

        await agent.execute({})

        # Should only call generate once (for the spec itself)
        assert agent.ollama_client.generate.call_count == 1


class TestRetryOnMissingSections:
    """Tests for retry logic when sections are missing."""

    @pytest.mark.asyncio
    async def test_retries_when_sections_missing(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should retry generation when required sections are missing."""
        await _write_required_inputs(workspace)
        await workspace.write_file("inputs/tech_stack.txt", "React")

        incomplete_spec = "## Refined Idea\nSome idea\n## Elevator Pitch\nPitch."
        # First call returns incomplete, second returns complete
        agent.ollama_client.generate = AsyncMock(
            side_effect=[incomplete_spec, VALID_PROJECT_SPEC]
        )

        result = await agent.execute({})

        assert result.success is True
        # Should have called generate twice (retry)
        assert agent.ollama_client.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_proceeds_after_max_retries(
        self, agent: ProjectPlannerAgent, workspace: WorkspaceService
    ) -> None:
        """Should proceed with incomplete spec after max retries."""
        await _write_required_inputs(workspace)
        await workspace.write_file("inputs/tech_stack.txt", "React")

        incomplete_spec = "## Refined Idea\nSome idea\n## Elevator Pitch\nPitch."
        # All calls return incomplete
        agent.ollama_client.generate = AsyncMock(return_value=incomplete_spec)

        result = await agent.execute({})

        # Should still succeed (with warning logged)
        assert result.success is True
        # MAX_RETRIES + 1 attempts = 3 calls
        assert agent.ollama_client.generate.call_count == 3


class TestFindMissingSections:
    """Tests for _find_missing_sections helper."""

    def test_all_sections_present(self, agent: ProjectPlannerAgent) -> None:
        """Should return empty list when all sections present."""
        missing = agent._find_missing_sections(VALID_PROJECT_SPEC)
        assert missing == []

    def test_detects_missing_section(self, agent: ProjectPlannerAgent) -> None:
        """Should detect missing sections."""
        partial = "## Refined Idea\nContent\n## Target Users\nUsers"
        missing = agent._find_missing_sections(partial)
        assert "## Elevator Pitch" in missing
        assert "## MVP Scope" in missing

    def test_case_insensitive_matching(self, agent: ProjectPlannerAgent) -> None:
        """Should match sections case-insensitively."""
        spec_with_different_case = VALID_PROJECT_SPEC.replace(
            "## Refined Idea", "## REFINED IDEA"
        )
        missing = agent._find_missing_sections(spec_with_different_case)
        assert missing == []

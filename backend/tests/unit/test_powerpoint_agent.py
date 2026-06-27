"""Unit tests for the PowerPoint Agent."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from backend.app.agents.powerpoint import (
    MAX_SLIDES,
    MIN_SLIDES,
    MIN_SPEAKER_NOTES_LENGTH,
    PPTX_FILENAME,
    REQUIRED_TOPICS,
    SPEAKER_NOTES_FILENAME,
    PowerPointAgent,
)
from backend.app.models.artifacts import AgentResult
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


# Sample LLM response with all required topics
SAMPLE_SLIDE_JSON = json.dumps([
    {
        "topic": "problem_statement",
        "title": "The Problem We Solve",
        "bullets": [
            "Users struggle with manual hackathon project setup",
            "Time wasted on boilerplate instead of innovation",
            "No unified system for coordinating development tasks",
        ],
        "speaker_notes": (
            "Let me tell you about the core problem we identified. "
            "Hackathon participants spend too much time on setup and coordination."
        ),
    },
    {
        "topic": "solution_overview",
        "title": "Hackathon Studio: AI-Powered Development",
        "bullets": [
            "10 specialized AI agents working in parallel",
            "From idea to MVP in hours, not days",
            "Automated testing, documentation, and deployment",
            "Human approval gates for quality control",
        ],
        "speaker_notes": (
            "Our solution is Hackathon Studio - an autonomous multi-agent AI system "
            "that transforms your hackathon idea into a working MVP with full documentation."
        ),
    },
    {
        "topic": "technical_architecture",
        "title": "Architecture Overview",
        "bullets": [
            "FastAPI backend with LangGraph orchestration",
            "Next.js frontend with real-time SSE updates",
            "Local LLM via Ollama - no API keys needed",
            "Shared workspace for agent collaboration",
        ],
        "speaker_notes": (
            "The architecture uses a hub-and-spoke model. "
            "A central orchestrator coordinates specialized agents through "
            "a state machine built with LangGraph."
        ),
    },
    {
        "topic": "demo_screenshots",
        "title": "Live Demo",
        "bullets": [
            "Input collection and validation",
            "Real-time agent monitoring dashboard",
            "Approval gates with human review",
            "Final deliverables download",
        ],
        "speaker_notes": (
            "Here we can see the application in action. The dashboard shows "
            "real-time progress of each agent as they collaborate to build the MVP."
        ),
    },
    {
        "topic": "team_tooling",
        "title": "Built With",
        "bullets": [
            "Python 3.11 + FastAPI + LangGraph",
            "Next.js 14 + TypeScript + TailwindCSS",
            "Ollama for local LLM inference",
            "python-pptx, Playwright, FFmpeg",
        ],
        "speaker_notes": (
            "Our tech stack was chosen for rapid development and reliability. "
            "Everything runs locally - no external API dependencies required for core functionality."
        ),
    },
    {
        "topic": "future_roadmap",
        "title": "What's Next",
        "bullets": [
            "Phase 1: Enhanced code generation quality",
            "Phase 2: Multi-language support",
            "Phase 3: Team collaboration features",
            "Phase 4: Cloud deployment automation",
        ],
        "speaker_notes": (
            "Looking ahead, we plan to enhance code generation quality, "
            "add support for more languages and frameworks, and enable "
            "team collaboration features."
        ),
    },
])


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create workspace with required directories."""
    ws = WorkspaceService(workspace_root=tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "ppt").mkdir(exist_ok=True)
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
    client.generate = AsyncMock(return_value=SAMPLE_SLIDE_JSON)
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> PowerPointAgent:
    """Create PowerPoint Agent."""
    return PowerPointAgent(
        agent_name="powerpoint",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


async def _write_source_artifacts(workspace: WorkspaceService) -> None:
    """Helper to write source artifacts to workspace."""
    await workspace.write_file(
        "project_spec.md",
        "# Project Spec\n## Refined Idea\nAn AI-powered hackathon tool.\n"
        "## Elevator Pitch\nBuild MVPs in hours.\n"
        "## Target Users\nHackathon participants.\n"
        "## MVP Scope\n- Agent orchestration\n- Code generation\n",
    )
    await workspace.write_file(
        "architecture.md",
        "# Architecture\n## Tech Stack\nFastAPI, Next.js, LangGraph\n"
        "## System Components\n- Orchestrator\n- 10 Agents\n- Shared Workspace\n",
    )


class TestSuccessfulGeneration:
    """Tests for successful presentation generation."""

    @pytest.mark.asyncio
    async def test_generates_pptx_and_notes(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should generate both presentation.pptx and speaker_notes.md."""
        await _write_source_artifacts(workspace)

        result = await agent.execute({})

        assert result.success is True
        assert PPTX_FILENAME in result.artifacts_produced
        assert SPEAKER_NOTES_FILENAME in result.artifacts_produced

    @pytest.mark.asyncio
    async def test_pptx_is_valid_ooxml(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should produce a valid OOXML ZIP file."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        pptx_path = workspace.workspace_root / "ppt" / "presentation.pptx"
        assert pptx_path.exists()
        assert zipfile.is_zipfile(pptx_path)

        with zipfile.ZipFile(pptx_path) as zf:
            names = zf.namelist()
            assert "[Content_Types].xml" in names

    @pytest.mark.asyncio
    async def test_pptx_has_minimum_slides(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should contain at least 6 slides (Requirement 11.1)."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        pptx_path = workspace.workspace_root / "ppt" / "presentation.pptx"
        with zipfile.ZipFile(pptx_path) as zf:
            slide_files = [
                n for n in zf.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]
            assert len(slide_files) >= MIN_SLIDES

    @pytest.mark.asyncio
    async def test_duration_tracked(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should track execution duration."""
        await _write_source_artifacts(workspace)

        result = await agent.execute({})

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_calls_llm_for_content(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should call LLM to generate slide content."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        assert agent.ollama_client.generate.call_count >= 1

    @pytest.mark.asyncio
    async def test_speaker_notes_markdown_written(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should write speaker_notes.md with structured content."""
        await _write_source_artifacts(workspace)

        await agent.execute({})

        notes_path = workspace.workspace_root / "ppt" / "speaker_notes.md"
        assert notes_path.exists()
        content = notes_path.read_text()
        assert "# Speaker Notes" in content
        assert "## Slide" in content


class TestMissingSourceArtifacts:
    """Tests for graceful handling of missing source artifacts."""

    @pytest.mark.asyncio
    async def test_succeeds_with_no_sources(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should still generate a presentation when no source artifacts exist (Req 11.6)."""
        result = await agent.execute({})

        assert result.success is True
        assert PPTX_FILENAME in result.artifacts_produced

    @pytest.mark.asyncio
    async def test_succeeds_with_partial_sources(
        self, agent: PowerPointAgent, workspace: WorkspaceService
    ) -> None:
        """Should succeed with only project_spec.md available."""
        await workspace.write_file(
            "project_spec.md",
            "# Project\n## Refined Idea\nAn AI tool for hackathons.",
        )

        result = await agent.execute({})

        assert result.success is True
        assert len(result.artifacts_produced) == 2


class TestSlideValidation:
    """Tests for the _validate_slides method."""

    def test_adds_missing_required_topics(self) -> None:
        """Should add placeholder slides for any missing required topics."""
        agent = PowerPointAgent.__new__(PowerPointAgent)

        # Only provide one slide
        slides = [
            {
                "topic": "problem_statement",
                "title": "Problem",
                "bullets": ["Issue 1"],
                "speaker_notes": "x" * 60,
            }
        ]

        result = agent._validate_slides(slides, [])

        topics = {s["topic"] for s in result}
        for req in REQUIRED_TOPICS:
            assert req in topics, f"Missing required topic: {req}"

    def test_ensures_minimum_speaker_notes_length(self) -> None:
        """Should pad speaker notes that are below 50 characters (Req 11.4)."""
        agent = PowerPointAgent.__new__(PowerPointAgent)

        slides = [
            {
                "topic": "problem_statement",
                "title": "Problem",
                "bullets": ["Issue"],
                "speaker_notes": "Short",  # < 50 chars
            }
        ]

        result = agent._validate_slides(slides, [])

        for slide in result:
            assert len(slide["speaker_notes"]) >= MIN_SPEAKER_NOTES_LENGTH

    def test_adds_title_slide_if_missing(self) -> None:
        """Should insert a title slide at the beginning."""
        agent = PowerPointAgent.__new__(PowerPointAgent)

        slides = [
            {
                "topic": "problem_statement",
                "title": "Problem",
                "bullets": ["Issue"],
                "speaker_notes": "x" * 60,
            }
        ]

        result = agent._validate_slides(slides, [])

        assert result[0]["topic"] == "title"

    def test_enforces_max_slides(self) -> None:
        """Should not exceed MAX_SLIDES (15)."""
        agent = PowerPointAgent.__new__(PowerPointAgent)

        # Create more than MAX_SLIDES slides
        slides = [
            {
                "topic": f"extra_{i}",
                "title": f"Slide {i}",
                "bullets": ["Point"],
                "speaker_notes": "x" * 60,
            }
            for i in range(20)
        ]

        result = agent._validate_slides(slides, [])

        assert len(result) <= MAX_SLIDES


class TestPptxBuilding:
    """Tests for the _build_pptx method."""

    def test_produces_non_empty_bytes(self) -> None:
        """Should produce non-zero bytes output."""
        agent = PowerPointAgent.__new__(PowerPointAgent)
        slides = agent._validate_slides([], [])

        result = agent._build_pptx(slides, [])

        assert len(result) > 0
        assert isinstance(result, bytes)

    def test_produces_valid_zip(self) -> None:
        """Should produce a valid ZIP file."""
        agent = PowerPointAgent.__new__(PowerPointAgent)
        slides = agent._validate_slides([], [])

        result = agent._build_pptx(slides, [])

        buffer = io.BytesIO(result)
        assert zipfile.is_zipfile(buffer)


class TestSlideResponseParsing:
    """Tests for _parse_slide_response method."""

    def test_parses_valid_json(self) -> None:
        """Should parse a valid JSON array."""
        agent = PowerPointAgent.__new__(PowerPointAgent)

        result = agent._parse_slide_response(SAMPLE_SLIDE_JSON)

        assert len(result) == 6
        assert result[0]["topic"] == "problem_statement"

    def test_parses_json_in_code_block(self) -> None:
        """Should extract JSON from markdown code blocks."""
        agent = PowerPointAgent.__new__(PowerPointAgent)
        response = f"Here is the content:\n```json\n{SAMPLE_SLIDE_JSON}\n```"

        result = agent._parse_slide_response(response)

        assert len(result) == 6

    def test_returns_empty_list_on_invalid_json(self) -> None:
        """Should return empty list when JSON parsing fails."""
        agent = PowerPointAgent.__new__(PowerPointAgent)

        result = agent._parse_slide_response("This is not JSON at all")

        assert result == []

    def test_handles_json_with_surrounding_text(self) -> None:
        """Should find JSON array within surrounding text."""
        agent = PowerPointAgent.__new__(PowerPointAgent)
        response = f"Sure, here are the slides:\n{SAMPLE_SLIDE_JSON}\nHope that helps!"

        result = agent._parse_slide_response(response)

        assert len(result) == 6


class TestSpeakerNotesMarkdown:
    """Tests for _build_speaker_notes_markdown method."""

    def test_contains_header(self) -> None:
        """Should start with a Speaker Notes header."""
        agent = PowerPointAgent.__new__(PowerPointAgent)
        slides = [
            {"title": "Test", "speaker_notes": "Notes content here."}
        ]

        result = agent._build_speaker_notes_markdown(slides)

        assert "# Speaker Notes" in result

    def test_contains_slide_entries(self) -> None:
        """Should contain an entry for each slide."""
        agent = PowerPointAgent.__new__(PowerPointAgent)
        slides = [
            {"title": "First", "speaker_notes": "First notes."},
            {"title": "Second", "speaker_notes": "Second notes."},
        ]

        result = agent._build_speaker_notes_markdown(slides)

        assert "## Slide 1: First" in result
        assert "## Slide 2: Second" in result
        assert "First notes." in result
        assert "Second notes." in result

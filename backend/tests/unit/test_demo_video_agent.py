"""Unit tests for the Demo Video Agent."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from backend.app.agents.demo_video import (
    DEMO_VIDEO_SYSTEM_PROMPT,
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    MIN_HEIGHT,
    MIN_WIDTH,
    DemoVideoAgent,
    _check_ffmpeg_available,
    _check_playwright_available,
    _format_srt_time,
    _wrap_text,
    generate_demo_script_md,
    generate_srt_from_steps,
)
from backend.app.models.artifacts import AgentResult
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


# Sample demo steps for testing
SAMPLE_DEMO_STEPS = [
    {
        "action": "Navigate to home page",
        "url": "/",
        "duration_seconds": 15,
        "narration": "Welcome to our application dashboard.",
    },
    {
        "action": "Click on Create Project",
        "url": "/projects/new",
        "duration_seconds": 20,
        "narration": "Users can create new projects with a simple form.",
    },
    {
        "action": "Fill in project details",
        "url": "",
        "duration_seconds": 15,
        "narration": "The form accepts project name and description.",
    },
    {
        "action": "Submit the form",
        "url": "",
        "duration_seconds": 15,
        "narration": "After submitting, the project is created instantly.",
    },
]

SAMPLE_LLM_RESPONSE = json.dumps(SAMPLE_DEMO_STEPS)

SAMPLE_ARCHITECTURE = """# Architecture
## System Components
- Dashboard: /dashboard
- Project Creator: /projects/new
- API: /api/v1

## User Paths
1. User visits dashboard
2. User creates a new project
3. User views project details
"""


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create workspace with required directories."""
    ws = WorkspaceService(workspace_root=tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "video").mkdir(exist_ok=True)
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
    client.generate = AsyncMock(return_value=SAMPLE_LLM_RESPONSE)
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> DemoVideoAgent:
    """Create Demo Video Agent."""
    return DemoVideoAgent(
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


class TestSrtGeneration:
    """Tests for SRT subtitle generation."""

    def test_generates_valid_srt(self) -> None:
        """Should generate properly formatted SRT from steps."""
        result = generate_srt_from_steps(SAMPLE_DEMO_STEPS)

        assert "00:00:00,000 --> 00:00:15,000" in result
        assert "Welcome to our application" in result

    def test_skips_steps_without_narration(self) -> None:
        """Should skip steps that have no narration."""
        steps = [
            {"action": "Wait", "duration_seconds": 5, "narration": ""},
            {"action": "Click", "duration_seconds": 10, "narration": "Hello world"},
        ]

        result = generate_srt_from_steps(steps)

        # Should start at 5s (after the empty narration step)
        assert "00:00:05,000 --> 00:00:15,000" in result
        assert "Hello world" in result

    def test_empty_steps_returns_empty_string(self) -> None:
        """Should return empty string for no steps."""
        result = generate_srt_from_steps([])
        assert result == ""

    def test_wraps_long_narration(self) -> None:
        """Should wrap narration longer than 42 characters."""
        steps = [
            {
                "narration": (
                    "This is a very long narration text that should be "
                    "wrapped across multiple lines"
                ),
                "duration_seconds": 10,
            }
        ]

        result = generate_srt_from_steps(steps)

        # Should have multiple lines in the subtitle text
        lines = result.strip().split("\n")
        # SRT entry: index, timestamp, text line 1, text line 2, blank
        assert len(lines) >= 4


class TestFormatSrtTime:
    """Tests for SRT timestamp formatting."""

    def test_zero_seconds(self) -> None:
        """Should format 0 as 00:00:00,000."""
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_seconds_only(self) -> None:
        """Should format seconds correctly."""
        assert _format_srt_time(15.0) == "00:00:15,000"

    def test_minutes_and_seconds(self) -> None:
        """Should format minutes and seconds correctly."""
        assert _format_srt_time(75.5) == "00:01:15,500"

    def test_hours_minutes_seconds(self) -> None:
        """Should format hours, minutes, seconds correctly."""
        assert _format_srt_time(3661.0) == "01:01:01,000"

    def test_milliseconds(self) -> None:
        """Should include milliseconds."""
        assert _format_srt_time(1.123) == "00:00:01,123"


class TestWrapText:
    """Tests for text wrapping utility."""

    def test_short_text_unchanged(self) -> None:
        """Should not wrap text shorter than max."""
        result = _wrap_text("Hello world", max_chars=42)
        assert result == "Hello world"

    def test_wraps_long_text(self) -> None:
        """Should wrap text exceeding max chars."""
        text = "This is a very long text that should definitely be wrapped"
        result = _wrap_text(text, max_chars=20)
        lines = result.split("\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 25  # Allow some overflow for word boundaries

    def test_empty_text(self) -> None:
        """Should handle empty text."""
        result = _wrap_text("")
        assert result == ""


class TestDemoScriptMd:
    """Tests for markdown demo script generation."""

    def test_includes_overview(self) -> None:
        """Should include overview section with total duration."""
        result = generate_demo_script_md(SAMPLE_DEMO_STEPS)

        assert "# Demo Video Script" in result
        assert "## Overview" in result
        assert "Total Duration" in result
        assert "65 seconds" in result  # 15 + 20 + 15 + 15

    def test_includes_all_steps(self) -> None:
        """Should include all demo steps."""
        result = generate_demo_script_md(SAMPLE_DEMO_STEPS)

        assert "### Step 1" in result
        assert "### Step 2" in result
        assert "### Step 3" in result
        assert "### Step 4" in result

    def test_includes_step_details(self) -> None:
        """Should include action, URL, duration, narration per step."""
        result = generate_demo_script_md(SAMPLE_DEMO_STEPS)

        assert "Navigate to home page" in result
        assert "/projects/new" in result
        assert "Welcome to our application" in result

    def test_includes_resolution(self) -> None:
        """Should mention the target resolution."""
        result = generate_demo_script_md(SAMPLE_DEMO_STEPS)
        assert f"{MIN_WIDTH}x{MIN_HEIGHT}" in result

    def test_empty_steps(self) -> None:
        """Should produce valid markdown even with no steps."""
        result = generate_demo_script_md([])
        assert "# Demo Video Script" in result
        assert "0 seconds" in result


class TestValidateDemoSteps:
    """Tests for the _validate_demo_steps method."""

    def test_normalizes_step_fields(self, agent: DemoVideoAgent) -> None:
        """Should normalize all fields to expected types."""
        # Use enough steps so total >= 60s and no scaling happens
        steps = [
            {
                "action": "Visit page",
                "url": "/test",
                "duration_seconds": "15",
                "narration": "Test narration",
            },
            {"action": "Step 2", "url": "/a", "duration_seconds": "15", "narration": "N"},
            {"action": "Step 3", "url": "/b", "duration_seconds": "15", "narration": "N"},
            {"action": "Step 4", "url": "/c", "duration_seconds": "15", "narration": "N"},
        ]

        result = agent._validate_demo_steps(steps)

        assert result[0]["action"] == "Visit page"
        assert result[0]["url"] == "/test"
        assert result[0]["duration_seconds"] == 15
        assert result[0]["narration"] == "Test narration"

    def test_clamps_duration_min(self, agent: DemoVideoAgent) -> None:
        """Should clamp individual step duration to minimum of 5s."""
        steps = [{"action": "Quick", "duration_seconds": 1}]

        result = agent._validate_demo_steps(steps)

        assert result[0]["duration_seconds"] >= 5

    def test_clamps_duration_max(self, agent: DemoVideoAgent) -> None:
        """Should clamp individual step duration to maximum of 30s."""
        steps = [{"action": "Long", "duration_seconds": 60}]

        result = agent._validate_demo_steps(steps)

        assert result[0]["duration_seconds"] <= 30

    def test_scales_up_short_total(self, agent: DemoVideoAgent) -> None:
        """Should scale up durations if total is below 60s."""
        steps = [
            {"action": f"Step {i}", "duration_seconds": 5}
            for i in range(5)
        ]
        # Total = 25s, should be scaled up

        result = agent._validate_demo_steps(steps)
        total = sum(s["duration_seconds"] for s in result)

        assert total >= MIN_DURATION_SECONDS

    def test_scales_down_long_total(self, agent: DemoVideoAgent) -> None:
        """Should scale down durations if total exceeds 300s."""
        steps = [
            {"action": f"Step {i}", "duration_seconds": 30}
            for i in range(15)
        ]
        # Total = 450s, should be scaled down

        result = agent._validate_demo_steps(steps)
        total = sum(s["duration_seconds"] for s in result)

        assert total <= MAX_DURATION_SECONDS

    def test_empty_steps(self, agent: DemoVideoAgent) -> None:
        """Should handle empty step list."""
        result = agent._validate_demo_steps([])
        assert result == []


class TestPrerequisiteChecks:
    """Tests for prerequisite availability checks."""

    @patch("backend.app.agents.demo_video.shutil.which")
    def test_ffmpeg_available(self, mock_which) -> None:
        """Should return True when ffmpeg is on PATH."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        assert _check_ffmpeg_available() is True

    @patch("backend.app.agents.demo_video.shutil.which")
    def test_ffmpeg_not_available(self, mock_which) -> None:
        """Should return False when ffmpeg is not on PATH."""
        mock_which.return_value = None
        assert _check_ffmpeg_available() is False

    def test_playwright_check(self) -> None:
        """Should return True/False based on import availability."""
        # This test just verifies the function runs without error
        result = _check_playwright_available()
        assert isinstance(result, bool)


class TestExecuteFailures:
    """Tests for graceful failure handling in execute()."""

    @pytest.mark.asyncio
    @patch("backend.app.agents.demo_video._check_playwright_available")
    async def test_fails_without_playwright(
        self,
        mock_pw,
        agent: DemoVideoAgent,
        workspace: WorkspaceService,
    ) -> None:
        """Should return failure when Playwright is not installed (Req 12.7)."""
        mock_pw.return_value = False

        result = await agent.execute({})

        assert result.success is False
        assert "Playwright" in result.error
        assert result.artifacts_produced == []

    @pytest.mark.asyncio
    @patch("backend.app.agents.demo_video._check_playwright_available")
    @patch("backend.app.agents.demo_video._check_ffmpeg_available")
    async def test_fails_without_ffmpeg(
        self,
        mock_ffmpeg,
        mock_pw,
        agent: DemoVideoAgent,
        workspace: WorkspaceService,
    ) -> None:
        """Should return failure when FFmpeg is not installed (Req 12.7)."""
        mock_pw.return_value = True
        mock_ffmpeg.return_value = False

        result = await agent.execute({})

        assert result.success is False
        assert "FFmpeg" in result.error
        assert result.artifacts_produced == []

    @pytest.mark.asyncio
    @patch("backend.app.agents.demo_video._check_playwright_available")
    @patch("backend.app.agents.demo_video._check_ffmpeg_available")
    async def test_fails_without_architecture(
        self,
        mock_ffmpeg,
        mock_pw,
        agent: DemoVideoAgent,
        workspace: WorkspaceService,
    ) -> None:
        """Should return failure when architecture.md is missing."""
        mock_pw.return_value = True
        mock_ffmpeg.return_value = True
        # Don't write architecture.md

        result = await agent.execute({})

        assert result.success is False
        assert "architecture.md" in result.error

    @pytest.mark.asyncio
    @patch("backend.app.agents.demo_video._check_playwright_available")
    @patch("backend.app.agents.demo_video._check_ffmpeg_available")
    async def test_fails_when_app_not_running(
        self,
        mock_ffmpeg,
        mock_pw,
        agent: DemoVideoAgent,
        workspace: WorkspaceService,
    ) -> None:
        """Should return failure when app is not running and no start command (Req 12.7)."""
        mock_pw.return_value = True
        mock_ffmpeg.return_value = True
        await workspace.write_file("architecture.md", SAMPLE_ARCHITECTURE)

        # Mock LLM to return demo steps
        agent.ollama_client.generate = AsyncMock(
            return_value=SAMPLE_LLM_RESPONSE
        )

        # Patch _check_app_running to return False
        with patch.object(agent, "_check_app_running", return_value=False):
            result = await agent.execute({"app_url": "http://localhost:9999"})

        assert result.success is False
        assert "not running" in result.error

    @pytest.mark.asyncio
    @patch("backend.app.agents.demo_video._check_playwright_available")
    @patch("backend.app.agents.demo_video._check_ffmpeg_available")
    async def test_fails_when_demo_script_generation_fails(
        self,
        mock_ffmpeg,
        mock_pw,
        agent: DemoVideoAgent,
        workspace: WorkspaceService,
    ) -> None:
        """Should return failure when LLM cannot generate a valid demo script."""
        mock_pw.return_value = True
        mock_ffmpeg.return_value = True
        await workspace.write_file("architecture.md", SAMPLE_ARCHITECTURE)

        # Mock LLM to return invalid JSON
        agent.ollama_client.generate = AsyncMock(
            return_value="This is not valid JSON"
        )

        result = await agent.execute({})

        assert result.success is False
        assert "demo script" in result.error.lower()


class TestDemoScriptGeneration:
    """Tests for the _generate_demo_script method."""

    @pytest.mark.asyncio
    async def test_parses_valid_llm_response(
        self, agent: DemoVideoAgent
    ) -> None:
        """Should parse a valid JSON array from LLM response."""
        agent.ollama_client.generate = AsyncMock(
            return_value=SAMPLE_LLM_RESPONSE
        )

        result = await agent._generate_demo_script(SAMPLE_ARCHITECTURE)

        assert len(result) == 4
        assert result[0]["action"] == "Navigate to home page"

    @pytest.mark.asyncio
    async def test_handles_json_in_code_block(
        self, agent: DemoVideoAgent
    ) -> None:
        """Should extract JSON from markdown code blocks."""
        agent.ollama_client.generate = AsyncMock(
            return_value=f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        )

        result = await agent._generate_demo_script(SAMPLE_ARCHITECTURE)

        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(
        self, agent: DemoVideoAgent
    ) -> None:
        """Should return empty list on invalid JSON."""
        agent.ollama_client.generate = AsyncMock(
            return_value="Not valid JSON at all"
        )

        result = await agent._generate_demo_script(SAMPLE_ARCHITECTURE)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_array(
        self, agent: DemoVideoAgent
    ) -> None:
        """Should return empty list if LLM returns empty array."""
        agent.ollama_client.generate = AsyncMock(return_value="[]")

        result = await agent._generate_demo_script(SAMPLE_ARCHITECTURE)

        assert result == []


class TestAgentName:
    """Tests for agent identity."""

    def test_agent_name_is_demo_video(self, agent: DemoVideoAgent) -> None:
        """Should have agent_name 'demo_video'."""
        assert agent.agent_name == "demo_video"


class TestDurationTracking:
    """Tests for execution duration tracking."""

    @pytest.mark.asyncio
    @patch("backend.app.agents.demo_video._check_playwright_available")
    async def test_duration_is_positive(
        self,
        mock_pw,
        agent: DemoVideoAgent,
    ) -> None:
        """Should always return positive duration_seconds."""
        mock_pw.return_value = False  # Fail fast

        result = await agent.execute({})

        assert result.duration_seconds > 0

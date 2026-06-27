"""Unit tests for the QA Agent."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from backend.app.agents.qa import (
    MAX_FIX_CYCLES,
    QAAgent,
    generate_testing_report,
    parse_test_results,
)
from backend.app.models.artifacts import AgentResult
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


# Sample LLM responses for testing
ALL_PASS_RESPONSE = """TESTS_RUN: 10
TESTS_PASSED: 10
TESTS_FAILED: 0

BUGS:
NONE
"""

BACKEND_BUGS_RESPONSE = """TESTS_RUN: 8
TESTS_PASSED: 6
TESTS_FAILED: 2

BUGS:
- ID: BUG-001 | Severity: critical | Description: Unhandled null pointer in auth endpoint | Agent: backend_engineer
- ID: BUG-002 | Severity: minor | Description: Missing docstring on utility function | Agent: backend_engineer
"""

FRONTEND_BUGS_RESPONSE = """TESTS_RUN: 5
TESTS_PASSED: 4
TESTS_FAILED: 1

BUGS:
- ID: BUG-003 | Severity: major | Description: Login form does not validate email format | Agent: frontend_engineer
"""

UI_BUGS_RESPONSE = """TESTS_RUN: 3
TESTS_PASSED: 2
TESTS_FAILED: 1

BUGS:
- ID: BUG-004 | Severity: major | Description: Navigation breaks on mobile viewport | Agent: frontend_engineer
"""

FIX_SUGGESTIONS_RESPONSE = """- BUG-001: Add null check before accessing user object in auth middleware
- BUG-003: Add email regex validation in the login form onSubmit handler
- BUG-004: Fix responsive CSS breakpoint for nav component at 360px width
"""


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create workspace with required directories."""
    ws = WorkspaceService(workspace_root=tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "backend").mkdir(exist_ok=True)
    (tmp_path / "frontend").mkdir(exist_ok=True)
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
    """Create OllamaClient with mocked generate (all tests pass by default)."""
    client = OllamaClient()
    client.generate = AsyncMock(return_value=ALL_PASS_RESPONSE)
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> QAAgent:
    """Create QA Agent."""
    return QAAgent(
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


async def _write_workspace_artifacts(workspace: WorkspaceService) -> None:
    """Write minimum workspace artifacts needed for QA agent to run."""
    await workspace.write_file(
        "architecture.md",
        "# Architecture\n## API Endpoints\n- POST /api/auth/login\n- GET /api/tasks",
    )
    await workspace.write_file(
        "project_spec.md",
        "# Project Spec\n## MVP Scope\n- User login\n- Task management\n",
    )
    await workspace.write_file(
        "backend/main.py",
        "from fastapi import FastAPI\napp = FastAPI()\n",
    )
    await workspace.write_file(
        "frontend/page.tsx",
        "export default function Home() { return <div>App</div>; }\n",
    )


class TestParseTestResults:
    """Tests for the parse_test_results utility function."""

    def test_parses_all_pass(self) -> None:
        """Should parse response with no bugs."""
        results = parse_test_results(ALL_PASS_RESPONSE)
        assert results["tests_run"] == 10
        assert results["tests_passed"] == 10
        assert results["tests_failed"] == 0
        assert results["bugs"] == []

    def test_parses_bugs(self) -> None:
        """Should parse response with bugs."""
        results = parse_test_results(BACKEND_BUGS_RESPONSE)
        assert results["tests_run"] == 8
        assert results["tests_passed"] == 6
        assert results["tests_failed"] == 2
        assert len(results["bugs"]) == 2
        assert results["bugs"][0]["id"] == "BUG-001"
        assert results["bugs"][0]["severity"] == "critical"
        assert results["bugs"][0]["agent"] == "backend_engineer"
        assert results["bugs"][1]["severity"] == "minor"

    def test_handles_empty_response(self) -> None:
        """Should return zeros for empty/malformed response."""
        results = parse_test_results("")
        assert results["tests_run"] == 0
        assert results["tests_passed"] == 0
        assert results["tests_failed"] == 0
        assert results["bugs"] == []


class TestGenerateTestingReport:
    """Tests for the generate_testing_report utility function."""

    def test_generates_all_sections(self) -> None:
        """Should generate report with all required sections."""
        backend_r = {"tests_run": 8, "tests_passed": 8, "tests_failed": 0, "bugs": []}
        frontend_r = {"tests_run": 5, "tests_passed": 5, "tests_failed": 0, "bugs": []}
        ui_r = {"tests_run": 3, "tests_passed": 3, "tests_failed": 0, "bugs": []}

        report = generate_testing_report(backend_r, frontend_r, ui_r)

        assert "# Testing Report" in report
        assert "## Test Summary" in report
        assert "## Unit Tests (Backend - Pytest)" in report
        assert "## Frontend Tests (Vitest)" in report
        assert "## UI Tests (Playwright)" in report
        assert "## Bug Report" in report
        assert "## Recommendations" in report

    def test_includes_bug_table(self) -> None:
        """Should include bug table when bugs are present."""
        backend_r = {
            "tests_run": 5,
            "tests_passed": 4,
            "tests_failed": 1,
            "bugs": [{"id": "BUG-001", "severity": "critical", "description": "Crash", "agent": "backend_engineer"}],
        }
        frontend_r = {"tests_run": 3, "tests_passed": 3, "tests_failed": 0, "bugs": []}
        ui_r = {"tests_run": 2, "tests_passed": 2, "tests_failed": 0, "bugs": []}

        report = generate_testing_report(backend_r, frontend_r, ui_r)

        assert "BUG-001" in report
        assert "Critical" in report
        assert "backend_engineer" in report

    def test_no_bugs_message(self) -> None:
        """Should show 'no bugs' message when all clear."""
        ok = {"tests_run": 5, "tests_passed": 5, "tests_failed": 0, "bugs": []}
        report = generate_testing_report(ok, ok, ok)
        assert "No bugs found" in report

    def test_pass_rate_calculation(self) -> None:
        """Should calculate correct pass rate."""
        r = {"tests_run": 10, "tests_passed": 8, "tests_failed": 2, "bugs": []}
        report = generate_testing_report(r, r, r)
        assert "80.0%" in report

    def test_fix_cycle_displayed(self) -> None:
        """Should show fix cycle count when > 0."""
        ok = {"tests_run": 5, "tests_passed": 5, "tests_failed": 0, "bugs": []}
        report = generate_testing_report(ok, ok, ok, fix_cycle=2)
        assert "2/3" in report


class TestQAAgentExecution:
    """Tests for the QA Agent execute() method."""

    @pytest.mark.asyncio
    async def test_success_when_all_tests_pass(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should succeed when all tests pass with no critical/major bugs."""
        await _write_workspace_artifacts(workspace)

        result = await agent.execute({})

        assert result.success is True
        assert "testing_report.md" in result.artifacts_produced
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_writes_testing_report(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should write testing_report.md to workspace."""
        await _write_workspace_artifacts(workspace)

        await agent.execute({})

        content = await workspace.read_file("testing_report.md")
        assert "# Testing Report" in content
        assert "## Test Summary" in content

    @pytest.mark.asyncio
    async def test_fails_when_architecture_missing(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should fail when architecture.md is missing."""
        result = await agent.execute({})

        assert result.success is False
        assert "architecture.md" in result.error

    @pytest.mark.asyncio
    async def test_fails_with_critical_bugs(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should fail when critical bugs are found."""
        await _write_workspace_artifacts(workspace)
        agent.ollama_client.generate = AsyncMock(
            side_effect=[
                BACKEND_BUGS_RESPONSE,
                ALL_PASS_RESPONSE,
                ALL_PASS_RESPONSE,
                FIX_SUGGESTIONS_RESPONSE,
            ]
        )

        result = await agent.execute({})

        assert result.success is False
        assert "BUGS_FOUND" in result.error
        assert "backend_engineer" in result.error

    @pytest.mark.asyncio
    async def test_halts_after_max_fix_cycles(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should halt and report unresolved bugs after MAX_FIX_CYCLES."""
        await _write_workspace_artifacts(workspace)
        agent.ollama_client.generate = AsyncMock(
            side_effect=[
                BACKEND_BUGS_RESPONSE,
                ALL_PASS_RESPONSE,
                ALL_PASS_RESPONSE,
                FIX_SUGGESTIONS_RESPONSE,
            ]
        )

        result = await agent.execute({"fix_cycle": MAX_FIX_CYCLES})

        assert result.success is False
        assert "unresolved" in result.error.lower()
        assert "testing_report.md" in result.artifacts_produced

    @pytest.mark.asyncio
    async def test_routes_bugs_to_responsible_agents(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should identify responsible agents for critical/major bugs."""
        await _write_workspace_artifacts(workspace)
        # Backend has critical bug, frontend test has major bug
        agent.ollama_client.generate = AsyncMock(
            side_effect=[
                BACKEND_BUGS_RESPONSE,
                FRONTEND_BUGS_RESPONSE,
                ALL_PASS_RESPONSE,
                FIX_SUGGESTIONS_RESPONSE,
            ]
        )

        result = await agent.execute({})

        assert result.success is False
        assert "backend_engineer" in result.error
        assert "frontend_engineer" in result.error

    @pytest.mark.asyncio
    async def test_calls_llm_with_qa_system_prompt(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should call LLM with the QA system prompt."""
        await _write_workspace_artifacts(workspace)

        await agent.execute({})

        calls = agent.ollama_client.generate.call_args_list
        # All calls should have the QA system prompt
        for call in calls:
            system = call.kwargs.get("system", "")
            assert "QA engineer" in system or "qa" in system.lower()

    @pytest.mark.asyncio
    async def test_duration_tracked(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should track execution duration."""
        await _write_workspace_artifacts(workspace)

        result = await agent.execute({})

        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_handles_empty_backend_directory(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should handle missing backend code gracefully."""
        await workspace.write_file("architecture.md", "# Arch\n## API\n- GET /health")

        result = await agent.execute({})

        # Should still succeed (LLM will analyze what's available)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_fix_cycle_incremented_in_error(
        self, agent: QAAgent, workspace: WorkspaceService
    ) -> None:
        """Should report current fix cycle number in error when bugs found."""
        await _write_workspace_artifacts(workspace)
        agent.ollama_client.generate = AsyncMock(
            side_effect=[
                BACKEND_BUGS_RESPONSE,
                ALL_PASS_RESPONSE,
                ALL_PASS_RESPONSE,
                FIX_SUGGESTIONS_RESPONSE,
            ]
        )

        result = await agent.execute({"fix_cycle": 1})

        assert "2/3" in result.error  # fix_cycle + 1

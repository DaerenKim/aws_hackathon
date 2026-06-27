"""Unit tests for the BaseAgent abstract class."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from backend.app.agents.base import AGENT_TIMEOUT_SECONDS, BaseAgent
from backend.app.models.artifacts import AgentResult
from backend.app.models.project_state import AgentStatus
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    async def execute(self, context: dict) -> AgentResult:
        """Simple execute that returns success."""
        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=["test_output.md"],
            duration_seconds=1.0,
        )


class FailingAgent(BaseAgent):
    """Agent that raises an exception during execute."""

    async def execute(self, context: dict) -> AgentResult:
        raise RuntimeError("Something went wrong")


class SlowAgent(BaseAgent):
    """Agent that takes too long to execute (for timeout testing)."""

    async def execute(self, context: dict) -> AgentResult:
        await asyncio.sleep(10)  # Will be timed out
        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=[],
            duration_seconds=10.0,
        )


class FailureResultAgent(BaseAgent):
    """Agent that returns a failure result without raising."""

    async def execute(self, context: dict) -> AgentResult:
        return AgentResult(
            agent_name=self.agent_name,
            success=False,
            artifacts_produced=[],
            error="Artifact validation failed",
            duration_seconds=2.0,
        )


@pytest_asyncio.fixture
async def workspace(tmp_path: Path) -> WorkspaceService:
    """Create a workspace service with a temp directory."""
    ws = WorkspaceService(workspace_root=tmp_path)
    # Create logs directory
    (tmp_path / "logs").mkdir(exist_ok=True)
    return ws


@pytest_asyncio.fixture
async def state_manager(tmp_path: Path) -> StateManager:
    """Create a state manager with a temp state file."""
    state_file = tmp_path / "project_state.json"
    manager = StateManager(state_file_path=state_file)
    # Initialize state
    await manager.read_state()
    return manager


@pytest_asyncio.fixture
async def ollama_client() -> OllamaClient:
    """Create an OllamaClient (methods will be mocked in tests)."""
    return OllamaClient()


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> ConcreteAgent:
    """Create a ConcreteAgent for testing."""
    return ConcreteAgent(
        agent_name="project_planner",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


class TestInit:
    """Tests for BaseAgent constructor."""

    def test_stores_agent_name(self, agent: ConcreteAgent) -> None:
        assert agent.agent_name == "project_planner"

    def test_stores_dependencies(
        self,
        agent: ConcreteAgent,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        assert agent.ollama_client is ollama_client
        assert agent.workspace is workspace
        assert agent.state_manager is state_manager


class TestRun:
    """Tests for the run() wrapper method."""

    @pytest.mark.asyncio
    async def test_successful_run_sets_completed(
        self, agent: ConcreteAgent, state_manager: StateManager
    ) -> None:
        """Should set status to IN_PROGRESS then COMPLETED on success."""
        result = await agent.run({})

        assert result.success is True
        status = await state_manager.get_agent_status("project_planner")
        assert status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_exception_sets_failed(
        self,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should set status to FAILED when execute() raises."""
        agent = FailingAgent(
            agent_name="project_planner",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )
        result = await agent.run({})

        assert result.success is False
        assert "RuntimeError" in result.error
        assert "Something went wrong" in result.error
        status = await state_manager.get_agent_status("project_planner")
        assert status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_timeout_sets_failed(
        self,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should set status to FAILED when execute() exceeds timeout."""
        agent = SlowAgent(
            agent_name="project_planner",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )
        # Patch timeout to a very short duration for testing
        with patch("backend.app.agents.base.AGENT_TIMEOUT_SECONDS", 0.1):
            result = await agent.run({})

        assert result.success is False
        assert "timed out" in result.error
        status = await state_manager.get_agent_status("project_planner")
        assert status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_failure_result_sets_failed(
        self,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should set FAILED when execute returns success=False."""
        agent = FailureResultAgent(
            agent_name="project_planner",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )
        result = await agent.run({})

        assert result.success is False
        assert result.error == "Artifact validation failed"
        status = await state_manager.get_agent_status("project_planner")
        assert status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_failure_logs_to_failures_log(
        self,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should log failure details to logs/failures.log."""
        agent = FailingAgent(
            agent_name="project_planner",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )
        await agent.run({})

        content = await workspace.read_file("logs/failures.log")
        assert "project_planner" in content
        assert "RuntimeError" in content


class TestReadArtifact:
    """Tests for read_artifact()."""

    @pytest.mark.asyncio
    async def test_reads_when_producing_agent_completed(
        self, agent: ConcreteAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should read artifact when producing agent is completed."""
        # Setup: write a file and mark agent as completed
        await workspace.write_file("project_spec.md", "# Project Spec")
        await state_manager.update_agent_status(
            "project_planner", AgentStatus.COMPLETED
        )

        content = await agent.read_artifact("project_spec.md", "project_planner")
        assert content == "# Project Spec"

    @pytest.mark.asyncio
    async def test_raises_when_producing_agent_not_completed(
        self, agent: ConcreteAgent, state_manager: StateManager
    ) -> None:
        """Should raise PermissionError when producing agent is not completed."""
        # Agent is still PENDING
        with pytest.raises(PermissionError, match="expected 'completed'"):
            await agent.read_artifact("project_spec.md", "project_planner")

    @pytest.mark.asyncio
    async def test_raises_when_producing_agent_in_progress(
        self, agent: ConcreteAgent, state_manager: StateManager
    ) -> None:
        """Should raise PermissionError when producing agent is in_progress."""
        await state_manager.update_agent_status(
            "backend_engineer", AgentStatus.IN_PROGRESS
        )
        with pytest.raises(PermissionError):
            await agent.read_artifact("backend/main.py", "backend_engineer")


class TestWriteArtifact:
    """Tests for write_artifact()."""

    @pytest.mark.asyncio
    async def test_writes_to_allowed_path(
        self, agent: ConcreteAgent, workspace: WorkspaceService
    ) -> None:
        """Should write artifact when path is within agent boundary."""
        await agent.write_artifact("project_spec.md", "# Spec Content")

        content = await workspace.read_file("project_spec.md")
        assert content == "# Spec Content"

    @pytest.mark.asyncio
    async def test_raises_when_writing_outside_boundary(
        self,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Should raise PermissionError for unauthorized paths."""
        agent = ConcreteAgent(
            agent_name="project_planner",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )
        with pytest.raises(PermissionError):
            await agent.write_artifact("backend/main.py", "code")


class TestLlmGenerate:
    """Tests for llm_generate()."""

    @pytest.mark.asyncio
    async def test_calls_ollama_with_system_prompt(
        self, agent: ConcreteAgent
    ) -> None:
        """Should call ollama_client.generate with agent-specific system prompt."""
        agent.ollama_client.generate = AsyncMock(return_value="LLM response")

        result = await agent.llm_generate("Tell me about Python")

        agent.ollama_client.generate.assert_called_once()
        call_args = agent.ollama_client.generate.call_args
        # Check prompt is passed as first positional arg
        assert call_args.args[0] == "Tell me about Python"
        # System prompt should contain agent name (passed as keyword)
        system_arg = call_args.kwargs.get("system", "")
        assert "project_planner" in system_arg
        assert result == "LLM response"

    @pytest.mark.asyncio
    async def test_appends_additional_system_instructions(
        self, agent: ConcreteAgent
    ) -> None:
        """Should append additional system instructions to agent prefix."""
        agent.ollama_client.generate = AsyncMock(return_value="response")

        await agent.llm_generate("prompt", system="Be concise.")

        call_args = agent.ollama_client.generate.call_args
        system_arg = call_args.kwargs.get("system", "")
        assert "project_planner" in system_arg
        assert "Be concise." in system_arg


class TestLlmChat:
    """Tests for llm_chat()."""

    @pytest.mark.asyncio
    async def test_calls_ollama_chat_with_system(
        self, agent: ConcreteAgent
    ) -> None:
        """Should call ollama_client.chat with messages and system prompt."""
        agent.ollama_client.chat = AsyncMock(return_value="chat response")
        messages = [{"role": "user", "content": "Hello"}]

        result = await agent.llm_chat(messages)

        agent.ollama_client.chat.assert_called_once()
        assert result == "chat response"


class TestUpdateStatus:
    """Tests for update_status()."""

    @pytest.mark.asyncio
    async def test_updates_agent_status(
        self, agent: ConcreteAgent, state_manager: StateManager
    ) -> None:
        """Should update the agent's status in project state."""
        await agent.update_status(AgentStatus.IN_PROGRESS)

        status = await state_manager.get_agent_status("project_planner")
        assert status == AgentStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_updates_with_error(
        self, agent: ConcreteAgent, state_manager: StateManager
    ) -> None:
        """Should store error message when provided."""
        await agent.update_status(AgentStatus.FAILED, error="Test error")

        state = await state_manager.read_state()
        assert state.agents["project_planner"].error == "Test error"


class TestLog:
    """Tests for log()."""

    @pytest.mark.asyncio
    async def test_creates_agent_log_file(
        self, agent: ConcreteAgent, workspace: WorkspaceService
    ) -> None:
        """Should create a log file for the agent."""
        await agent.log("Test log message")

        content = await workspace.read_file("logs/agent_project_planner.log")
        assert "Test log message" in content

    @pytest.mark.asyncio
    async def test_appends_timestamp(
        self, agent: ConcreteAgent, workspace: WorkspaceService
    ) -> None:
        """Should include ISO timestamp in log entries."""
        await agent.log("Message with timestamp")

        content = await workspace.read_file("logs/agent_project_planner.log")
        # ISO format contains T separator and timezone info
        assert "T" in content
        assert "Message with timestamp" in content

    @pytest.mark.asyncio
    async def test_appends_to_existing_log(
        self, agent: ConcreteAgent, workspace: WorkspaceService
    ) -> None:
        """Should append to existing log, not overwrite."""
        await agent.log("First message")
        await agent.log("Second message")

        content = await workspace.read_file("logs/agent_project_planner.log")
        assert "First message" in content
        assert "Second message" in content

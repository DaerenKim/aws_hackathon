"""Unit tests for the StateManager service."""

import json
from pathlib import Path

import pytest
import pytest_asyncio

from backend.app.models.project_state import (
    AgentStatus,
    PhaseStatus,
    ProjectState,
)
from backend.app.services.state_manager import AGENT_NAMES, StateManager


@pytest_asyncio.fixture
async def state_file(tmp_path: Path) -> Path:
    """Return a path for a state file in a temporary directory."""
    return tmp_path / "project_state.json"


@pytest_asyncio.fixture
async def manager(state_file: Path) -> StateManager:
    """Create a StateManager instance with a temp state file."""
    return StateManager(state_file_path=state_file)


class TestReadState:
    """Tests for read_state()."""

    @pytest.mark.asyncio
    async def test_initializes_state_file_if_missing(
        self, manager: StateManager, state_file: Path
    ) -> None:
        """Should create state file with defaults when it doesn't exist."""
        assert not state_file.exists()

        state = await manager.read_state()

        assert state_file.exists()
        assert state.phase == PhaseStatus.PLANNING
        assert len(state.agents) == len(AGENT_NAMES)
        for name in AGENT_NAMES:
            assert name in state.agents
            assert state.agents[name].status == AgentStatus.PENDING

    @pytest.mark.asyncio
    async def test_reads_existing_state_file(
        self, manager: StateManager, state_file: Path
    ) -> None:
        """Should parse an existing state file correctly."""
        # Initialize first
        state = await manager.read_state()
        # Modify and re-read
        await manager.update_agent_status("qa", AgentStatus.IN_PROGRESS)

        state = await manager.read_state()
        assert state.agents["qa"].status == AgentStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_initializes_approval_gates(
        self, manager: StateManager
    ) -> None:
        """Should create three approval gates."""
        state = await manager.read_state()
        assert 1 in state.approval_gates
        assert 2 in state.approval_gates
        assert 3 in state.approval_gates
        for gate in state.approval_gates.values():
            assert gate.pending is False
            assert gate.revision_count == 0


class TestUpdateAgentStatus:
    """Tests for update_agent_status()."""

    @pytest.mark.asyncio
    async def test_updates_status_to_in_progress(
        self, manager: StateManager
    ) -> None:
        """Should set status and started_at timestamp."""
        await manager.read_state()  # Initialize
        await manager.update_agent_status("project_planner", AgentStatus.IN_PROGRESS)

        state = await manager.read_state()
        agent = state.agents["project_planner"]
        assert agent.status == AgentStatus.IN_PROGRESS
        assert agent.started_at is not None

    @pytest.mark.asyncio
    async def test_updates_status_to_completed(
        self, manager: StateManager
    ) -> None:
        """Should set status and completed_at timestamp."""
        await manager.read_state()  # Initialize
        await manager.update_agent_status("backend_engineer", AgentStatus.COMPLETED)

        state = await manager.read_state()
        agent = state.agents["backend_engineer"]
        assert agent.status == AgentStatus.COMPLETED
        assert agent.completed_at is not None

    @pytest.mark.asyncio
    async def test_updates_status_to_failed_with_error(
        self, manager: StateManager
    ) -> None:
        """Should set status, completed_at, and error message."""
        await manager.read_state()  # Initialize
        await manager.update_agent_status(
            "frontend_engineer", AgentStatus.FAILED, error="Timeout after 600s"
        )

        state = await manager.read_state()
        agent = state.agents["frontend_engineer"]
        assert agent.status == AgentStatus.FAILED
        assert agent.completed_at is not None
        assert agent.error == "Timeout after 600s"

    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(
        self, manager: StateManager
    ) -> None:
        """Should raise ValueError for unrecognized agent names."""
        await manager.read_state()  # Initialize
        with pytest.raises(ValueError, match="Unknown agent"):
            await manager.update_agent_status("unknown_agent", AgentStatus.IN_PROGRESS)

    @pytest.mark.asyncio
    async def test_updates_updated_at_timestamp(
        self, manager: StateManager
    ) -> None:
        """Should update the updated_at timestamp on every write."""
        state_before = await manager.read_state()
        original_updated_at = state_before.updated_at

        await manager.update_agent_status("qa", AgentStatus.IN_PROGRESS)

        state_after = await manager.read_state()
        assert state_after.updated_at >= original_updated_at


class TestSetPhase:
    """Tests for set_phase()."""

    @pytest.mark.asyncio
    async def test_sets_phase(self, manager: StateManager) -> None:
        """Should update the workflow phase."""
        await manager.read_state()  # Initialize
        await manager.set_phase(PhaseStatus.DEVELOPMENT)

        state = await manager.read_state()
        assert state.phase == PhaseStatus.DEVELOPMENT

    @pytest.mark.asyncio
    async def test_sets_phase_to_complete(self, manager: StateManager) -> None:
        """Should allow setting phase to complete."""
        await manager.read_state()  # Initialize
        await manager.set_phase(PhaseStatus.COMPLETE)

        state = await manager.read_state()
        assert state.phase == PhaseStatus.COMPLETE


class TestGetAgentStatus:
    """Tests for get_agent_status()."""

    @pytest.mark.asyncio
    async def test_returns_pending_by_default(
        self, manager: StateManager
    ) -> None:
        """Should return pending for newly initialized agents."""
        status = await manager.get_agent_status("github")
        assert status == AgentStatus.PENDING

    @pytest.mark.asyncio
    async def test_returns_updated_status(
        self, manager: StateManager
    ) -> None:
        """Should reflect status changes."""
        await manager.update_agent_status("documentation", AgentStatus.COMPLETED)
        status = await manager.get_agent_status("documentation")
        assert status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(
        self, manager: StateManager
    ) -> None:
        """Should raise ValueError for unknown agent."""
        with pytest.raises(ValueError, match="Unknown agent"):
            await manager.get_agent_status("nonexistent")


class TestIsArtifactReady:
    """Tests for is_artifact_ready()."""

    @pytest.mark.asyncio
    async def test_returns_true_when_agent_completed(
        self, manager: StateManager
    ) -> None:
        """Should return True when producing agent is completed."""
        await manager.update_agent_status("project_planner", AgentStatus.COMPLETED)

        result = await manager.is_artifact_ready(
            "project_spec.md", "project_planner"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_agent_pending(
        self, manager: StateManager
    ) -> None:
        """Should return False when producing agent is still pending."""
        await manager.read_state()  # Initialize

        result = await manager.is_artifact_ready(
            "project_spec.md", "project_planner"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_agent_in_progress(
        self, manager: StateManager
    ) -> None:
        """Should return False when producing agent is in progress."""
        await manager.update_agent_status("backend_engineer", AgentStatus.IN_PROGRESS)

        result = await manager.is_artifact_ready(
            "backend/main.py", "backend_engineer"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_agent_failed(
        self, manager: StateManager
    ) -> None:
        """Should return False when producing agent has failed."""
        await manager.update_agent_status(
            "frontend_engineer", AgentStatus.FAILED, error="Build error"
        )

        result = await manager.is_artifact_ready(
            "frontend/package.json", "frontend_engineer"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(
        self, manager: StateManager
    ) -> None:
        """Should raise ValueError for unknown producing agent."""
        await manager.read_state()  # Initialize
        with pytest.raises(ValueError, match="Unknown agent"):
            await manager.is_artifact_ready("file.txt", "unknown_agent")


class TestAtomicWrites:
    """Tests for atomic file write behavior."""

    @pytest.mark.asyncio
    async def test_state_file_is_valid_json_after_write(
        self, manager: StateManager, state_file: Path
    ) -> None:
        """State file should always contain valid JSON."""
        await manager.read_state()  # Initialize
        await manager.update_agent_status("qa", AgentStatus.IN_PROGRESS)

        # Manually read and parse to confirm valid JSON
        content = state_file.read_text()
        parsed = json.loads(content)
        assert parsed["agents"]["qa"]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_no_temp_files_left_after_write(
        self, manager: StateManager, state_file: Path
    ) -> None:
        """Should not leave temporary files after successful write."""
        await manager.read_state()  # Initialize
        await manager.update_agent_status("integration", AgentStatus.COMPLETED)

        # Check no .tmp files remain
        tmp_files = list(state_file.parent.glob("state_*.tmp"))
        assert len(tmp_files) == 0

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        nested_path = tmp_path / "deep" / "nested" / "project_state.json"
        manager = StateManager(state_file_path=nested_path)

        state = await manager.read_state()
        assert nested_path.exists()
        assert state.phase == PhaseStatus.PLANNING

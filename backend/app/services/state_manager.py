"""State Manager service for project_state.json.

Provides atomic read/write operations for the project state file,
ensuring no partial state corruption through temp-file-then-replace writes.
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from app.models.project_state import (
    AgentPhase,
    AgentStatus,
    ApprovalGateState,
    PhaseStatus,
    ProjectState,
)

# All agent names that the system tracks
AGENT_NAMES: list[str] = [
    "project_planner",
    "judge_optimizer",
    "backend_engineer",
    "frontend_engineer",
    "integration",
    "qa",
    "documentation",
    "powerpoint",
    "demo_video",
    "github",
]


class StateManager:
    """Manages project_state.json with atomic file operations.

    Ensures state consistency by:
    - Writing to a temporary file first, then using os.replace() for atomic swap
    - Updating the `updated_at` timestamp on every write
    - Initializing state file if it doesn't exist
    """

    def __init__(self, state_file_path: Path) -> None:
        """Initialize the StateManager.

        Args:
            state_file_path: Path to the project_state.json file.
        """
        self._state_file_path = state_file_path

    @property
    def state_file_path(self) -> Path:
        """Return the path to the state file."""
        return self._state_file_path

    async def read_state(self) -> ProjectState:
        """Read and parse the project state JSON file.

        If the state file does not exist, initializes it with default state
        (all agents set to "pending", phase set to "planning").

        Returns:
            The parsed ProjectState.
        """
        if not self._state_file_path.exists():
            await self._initialize_state()

        async with aiofiles.open(self._state_file_path, mode="r") as f:
            content = await f.read()

        return ProjectState.model_validate_json(content)

    async def update_agent_status(
        self,
        agent: str,
        status: AgentStatus,
        error: str | None = None,
    ) -> None:
        """Atomically update one agent's status with timestamps.

        Args:
            agent: The agent name to update.
            status: The new status for the agent.
            error: Optional error message (typically set when status is FAILED).

        Raises:
            ValueError: If the agent name is not recognized.
        """
        state = await self.read_state()

        if agent not in state.agents:
            raise ValueError(
                f"Unknown agent: '{agent}'. Valid agents: {list(state.agents.keys())}"
            )

        now = datetime.now(timezone.utc)
        agent_phase = state.agents[agent]

        # Update status
        agent_phase.status = status

        # Update timestamps based on new status
        if status == AgentStatus.IN_PROGRESS:
            agent_phase.started_at = now
        elif status in (AgentStatus.COMPLETED, AgentStatus.FAILED):
            agent_phase.completed_at = now

        # Set error message
        agent_phase.error = error

        state.updated_at = now
        await self._write_state(state)

    async def set_phase(self, phase: PhaseStatus) -> None:
        """Update the current workflow phase.

        Args:
            phase: The new workflow phase.
        """
        state = await self.read_state()
        state.phase = phase
        state.updated_at = datetime.now(timezone.utc)
        await self._write_state(state)

    async def get_agent_status(self, agent: str) -> AgentStatus:
        """Return the current status of a single agent.

        Args:
            agent: The agent name to query.

        Returns:
            The agent's current status.

        Raises:
            ValueError: If the agent name is not recognized.
        """
        state = await self.read_state()

        if agent not in state.agents:
            raise ValueError(
                f"Unknown agent: '{agent}'. Valid agents: {list(state.agents.keys())}"
            )

        return state.agents[agent].status

    async def is_artifact_ready(
        self, artifact_path: str, producing_agent: str
    ) -> bool:
        """Check if an artifact is ready for consumption.

        An artifact is considered ready only if the producing agent's
        status is "completed".

        Args:
            artifact_path: Path to the artifact (unused in check, kept for interface).
            producing_agent: Name of the agent that produces the artifact.

        Returns:
            True if the producing agent's status is "completed", False otherwise.

        Raises:
            ValueError: If the producing_agent name is not recognized.
        """
        state = await self.read_state()

        if producing_agent not in state.agents:
            raise ValueError(
                f"Unknown agent: '{producing_agent}'. "
                f"Valid agents: {list(state.agents.keys())}"
            )

        return state.agents[producing_agent].status == AgentStatus.COMPLETED

    async def _initialize_state(self) -> None:
        """Initialize the state file with default values.

        All agents start with "pending" status, phase is "planning",
        and three approval gates are created.
        """
        now = datetime.now(timezone.utc)

        agents = {name: AgentPhase() for name in AGENT_NAMES}

        approval_gates = {
            1: ApprovalGateState(gate_number=1),
            2: ApprovalGateState(gate_number=2),
            3: ApprovalGateState(gate_number=3),
        }

        state = ProjectState(
            phase=PhaseStatus.PLANNING,
            agents=agents,
            approval_gates=approval_gates,
            created_at=now,
            updated_at=now,
        )

        await self._write_state(state)

    async def _write_state(self, state: ProjectState) -> None:
        """Atomically write state to the JSON file.

        Uses a write-to-temp-then-replace strategy to prevent partial
        state corruption in case of crashes or power loss.

        Args:
            state: The complete project state to persist.
        """
        # Ensure parent directory exists
        self._state_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize state to JSON
        json_content = state.model_dump_json(indent=2)

        # Write to a temporary file in the same directory (same filesystem)
        # then atomically replace the target file
        dir_path = self._state_file_path.parent
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp", prefix="state_", dir=str(dir_path)
        )
        try:
            async with aiofiles.open(fd, mode="w", closefd=True) as f:
                await f.write(json_content)

            # Atomic replace — guaranteed by POSIX on same filesystem
            os.replace(tmp_path, self._state_file_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

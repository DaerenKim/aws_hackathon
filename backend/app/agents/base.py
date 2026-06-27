"""Base agent abstract class for all Hackathon Studio agents.

Provides shared infrastructure for LLM interaction, workspace I/O,
state management, timeout enforcement, and structured logging.
All specialized agents inherit from BaseAgent and implement execute().
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.models.artifacts import AgentResult
from app.models.project_state import AgentStatus
from app.services.ollama_client import OllamaClient
from app.services.state_manager import StateManager
from app.services.workspace import WorkspaceService

logger = logging.getLogger(__name__)

# Maximum execution time for any single agent run (seconds)
AGENT_TIMEOUT_SECONDS: float = 600.0


class BaseAgent(ABC):
    """Base class for all Hackathon Studio agents.

    Provides:
    - Abstract execute() method for subclass implementation
    - run() wrapper with timeout enforcement and status management
    - Workspace read/write with state validation and boundary enforcement
    - LLM generation/chat with agent-specific system prompts
    - Status updates to project_state.json
    - Structured logging to per-agent log files
    """

    def __init__(
        self,
        agent_name: str,
        ollama_client: OllamaClient,
        workspace: WorkspaceService,
        state_manager: StateManager,
    ) -> None:
        """Initialize the base agent.

        Args:
            agent_name: Unique identifier for this agent (e.g., "project_planner").
            ollama_client: Client for interacting with the local Ollama LLM.
            workspace: Service for file operations in the shared workspace.
            state_manager: Service for reading/updating project_state.json.
        """
        self.agent_name = agent_name
        self.ollama_client = ollama_client
        self.workspace = workspace
        self.state_manager = state_manager

    @abstractmethod
    async def execute(self, context: dict) -> AgentResult:
        """Execute the agent's primary task.

        Must be implemented by subclasses. Contains the core logic
        for the agent's specialized role.

        Args:
            context: Dictionary of contextual information needed for execution.
                     Contents vary by agent type.

        Returns:
            AgentResult indicating success/failure, artifacts produced,
            and execution duration.
        """
        ...

    async def run(self, context: dict) -> AgentResult:
        """Execute the agent with timeout enforcement and status management.

        Wraps execute() with:
        - Status set to IN_PROGRESS before execution
        - 600-second asyncio timeout
        - Status set to COMPLETED on success
        - Status set to FAILED on timeout or exception
        - Failure logging to logs/failures.log

        Args:
            context: Dictionary of contextual information passed to execute().

        Returns:
            AgentResult from execute(), or a failure result on timeout/error.
        """
        start_time = time.monotonic()

        # Mark agent as in-progress
        await self.update_status(AgentStatus.IN_PROGRESS)
        await self.log(f"Agent '{self.agent_name}' starting execution.")

        try:
            async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                result = await self.execute(context)

            # On successful completion
            if result.success:
                await self.update_status(AgentStatus.COMPLETED)
                await self.log(
                    f"Agent '{self.agent_name}' completed successfully "
                    f"in {result.duration_seconds:.1f}s. "
                    f"Artifacts: {result.artifacts_produced}"
                )
            else:
                # Agent returned a failure result
                await self.update_status(AgentStatus.FAILED, error=result.error)
                await self._log_failure(result.error or "Agent returned failure result")

            return result

        except TimeoutError:
            elapsed = time.monotonic() - start_time
            error_msg = (
                f"Agent '{self.agent_name}' timed out after "
                f"{AGENT_TIMEOUT_SECONDS:.0f}s (elapsed: {elapsed:.1f}s)"
            )
            logger.error(error_msg)
            await self.update_status(AgentStatus.FAILED, error=error_msg)
            await self._log_failure(error_msg)

            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=elapsed,
            )

        except Exception as e:
            elapsed = time.monotonic() - start_time
            error_msg = (
                f"Agent '{self.agent_name}' failed with exception: "
                f"{type(e).__name__}: {str(e)}"
            )
            logger.error(error_msg, exc_info=True)
            await self.update_status(AgentStatus.FAILED, error=error_msg)
            await self._log_failure(error_msg)

            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=elapsed,
            )

    async def read_artifact(self, path: str, producing_agent: str) -> str:
        """Read an artifact from the shared workspace with state validation.

        Checks that the producing agent's status is "completed" before
        allowing the read, enforcing Requirement 14.4.

        Args:
            path: Relative path to the artifact in the workspace.
            producing_agent: Name of the agent that produced this artifact.

        Returns:
            The text content of the artifact.

        Raises:
            PermissionError: If the producing agent's status is not "completed".
            FileNotFoundError: If the artifact file does not exist.
        """
        # Validate that the producing agent has completed
        is_ready = await self.state_manager.is_artifact_ready(path, producing_agent)
        if not is_ready:
            status = await self.state_manager.get_agent_status(producing_agent)
            raise PermissionError(
                f"Cannot read artifact '{path}': producing agent "
                f"'{producing_agent}' has status '{status.value}', "
                f"expected 'completed'."
            )

        return await self.workspace.read_file(path)

    async def write_artifact(self, path: str, content: str | bytes) -> None:
        """Write an artifact to the shared workspace with boundary enforcement.

        Enforces that this agent can only write to its designated
        output paths as defined in AGENT_WRITE_BOUNDARIES.

        Args:
            path: Relative path in the workspace to write to.
            content: Text or binary content to write.

        Raises:
            PermissionError: If the path is outside this agent's write boundary.
            ValueError: If path traversal is detected.
        """
        await self.workspace.write_file(path, content, agent_name=self.agent_name)
        await self.log(f"Wrote artifact: {path}")

    async def llm_generate(self, prompt: str, system: str | None = None) -> str:
        """Generate LLM response via Ollama with agent-specific system prompt.

        Prepends an agent-specific system prompt prefix to provide context
        about the agent's role. Callers can provide additional system
        instructions that are appended.

        Args:
            prompt: The user prompt for text generation.
            system: Optional additional system instructions. Appended to
                    the agent-specific prefix.

        Returns:
            The generated text response from Ollama.
        """
        full_system = self._build_system_prompt(system)
        return await self.ollama_client.generate(prompt, system=full_system)

    async def llm_chat(self, messages: list[dict], system: str | None = None) -> str:
        """Chat with the LLM via Ollama with agent-specific system prompt.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            system: Optional additional system instructions. Appended to
                    the agent-specific prefix.

        Returns:
            The assistant's response content.
        """
        full_system = self._build_system_prompt(system)
        return await self.ollama_client.chat(messages, system=full_system)

    async def update_status(
        self, status: AgentStatus, error: str | None = None
    ) -> None:
        """Update this agent's status in project_state.json.

        Args:
            status: The new status to set.
            error: Optional error message (typically set for FAILED status).
        """
        await self.state_manager.update_agent_status(
            agent=self.agent_name,
            status=status,
            error=error,
        )

    async def log(self, message: str) -> None:
        """Append a log message to the agent's log file.

        Writes to logs/agent_{name}.log in the workspace with timestamp.

        Args:
            message: The log message to record.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        log_line = f"[{timestamp}] {message}\n"
        log_path = f"logs/agent_{self.agent_name}.log"

        try:
            # Read existing content and append (workspace write_file overwrites)
            existing = ""
            if await self.workspace.file_exists(log_path):
                existing = await self.workspace.read_file(log_path)
            await self.workspace.write_file(
                log_path, existing + log_line, agent_name=None
            )
        except Exception as e:
            # Fallback to Python logger if workspace write fails
            logger.warning(
                "Failed to write agent log for '%s': %s", self.agent_name, e
            )
            logger.info("[%s] %s", self.agent_name, message)

    def _build_system_prompt(self, additional: str | None = None) -> str:
        """Build the full system prompt with agent-specific prefix.

        Args:
            additional: Optional additional system instructions to append.

        Returns:
            Complete system prompt string.
        """
        prefix = (
            f"You are the {self.agent_name} agent in Hackathon Studio, "
            f"an autonomous AI software development system. "
            f"Your role is to produce high-quality artifacts for a hackathon project."
        )
        if additional:
            return f"{prefix}\n\n{additional}"
        return prefix

    async def _log_failure(self, error_msg: str) -> None:
        """Log a failure to both the agent log and the shared failures.log.

        Args:
            error_msg: Description of the failure.
        """
        await self.log(f"FAILURE: {error_msg}")

        # Also append to the shared failures.log
        timestamp = datetime.now(timezone.utc).isoformat()
        failure_line = f"[{timestamp}] [{self.agent_name}] {error_msg}\n"
        failure_log_path = "logs/failures.log"

        try:
            existing = ""
            if await self.workspace.file_exists(failure_log_path):
                existing = await self.workspace.read_file(failure_log_path)
            await self.workspace.write_file(
                failure_log_path, existing + failure_line, agent_name=None
            )
        except Exception as e:
            logger.warning("Failed to write to failures.log: %s", e)

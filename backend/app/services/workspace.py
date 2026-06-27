"""Workspace service for shared file system operations.

Manages all file I/O within the shared workspace directory, enforcing
agent write boundaries and providing artifact validation support.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

import aiofiles
import aiofiles.os

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Result of an artifact validation check."""

    valid: bool
    errors: list[str] = []


@runtime_checkable
class ArtifactValidator(Protocol):
    """Protocol for artifact validators.

    Each validator implements format-specific checks for agent outputs.
    """

    async def validate(self, file_path: Path) -> ValidationResult: ...


# Agent write boundary definitions: maps agent name to allowed path prefixes/files.
AGENT_WRITE_BOUNDARIES: dict[str, list[str]] = {
    "project_planner": [
        "project_spec.md",
        "architecture.md",
        "roadmap.md",
        "api_design.md",
        "folder_structure.md",
    ],
    "judge_optimizer": [
        "judge_analysis.md",
        "score_prediction.md",
        "feature_priority.md",
    ],
    "backend_engineer": ["backend/"],
    "frontend_engineer": ["frontend/"],
    "integration": ["backend/", "frontend/", "logs/"],
    "qa": ["testing_report.md", "coverage_report.md", "bugs.md", "logs/"],
    "documentation": [
        "README.md",
        "developer_guide.md",
        "api_docs.md",
        "docs/",
    ],
    "powerpoint": ["ppt/"],
    "demo_video": ["video/"],
    "github": [".gitignore", "LICENSE"],
}


class WorkspaceService:
    """File operations for the shared workspace.

    Provides async read/write access to the shared workspace directory,
    enforces agent write boundaries, and supports artifact validation.
    """

    def __init__(self, workspace_root: Path) -> None:
        """Initialize workspace service.

        Args:
            workspace_root: Absolute path to the shared workspace directory.
        """
        self.workspace_root = workspace_root.resolve()

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path within workspace, preventing path traversal.

        Args:
            relative_path: Path relative to workspace root.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If the path escapes the workspace root.
        """
        resolved = (self.workspace_root / relative_path).resolve()
        if not str(resolved).startswith(str(self.workspace_root)):
            raise ValueError(
                f"Path traversal detected: '{relative_path}' resolves outside "
                f"workspace root '{self.workspace_root}'"
            )
        return resolved

    def _check_agent_boundary(self, relative_path: str, agent_name: str) -> None:
        """Enforce agent write boundaries.

        Each agent can only write to its designated area as defined
        in AGENT_WRITE_BOUNDARIES.

        Args:
            relative_path: Path relative to workspace root.
            agent_name: Name of the agent attempting to write.

        Raises:
            PermissionError: If the agent is not allowed to write to the path.
        """
        if agent_name not in AGENT_WRITE_BOUNDARIES:
            raise PermissionError(
                f"Unknown agent '{agent_name}' has no write permissions defined. "
                f"Known agents: {list(AGENT_WRITE_BOUNDARIES.keys())}"
            )

        allowed_paths = AGENT_WRITE_BOUNDARIES[agent_name]
        normalized = relative_path.replace("\\", "/")

        for allowed in allowed_paths:
            if allowed.endswith("/"):
                # Directory prefix — path must start with this prefix
                if normalized.startswith(allowed) or normalized == allowed.rstrip("/"):
                    return
            else:
                # Exact file match
                if normalized == allowed:
                    return

        raise PermissionError(
            f"Agent '{agent_name}' is not allowed to write to '{relative_path}'. "
            f"Allowed paths: {allowed_paths}"
        )

    async def write_file(
        self,
        relative_path: str,
        content: str | bytes,
        agent_name: str | None = None,
    ) -> None:
        """Write content to a file in the workspace.

        Creates parent directories if they don't exist. Enforces agent
        write boundaries when agent_name is provided.

        Args:
            relative_path: Path relative to workspace root.
            content: File content (str for text, bytes for binary).
            agent_name: Name of the writing agent (None skips boundary check).

        Raises:
            ValueError: If path traversal is detected.
            PermissionError: If agent is not allowed to write to path.
        """
        resolved = self._resolve_path(relative_path)

        if agent_name is not None:
            self._check_agent_boundary(relative_path, agent_name)

        # Create parent directories if needed
        resolved.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            async with aiofiles.open(resolved, mode="wb") as f:
                await f.write(content)
        else:
            async with aiofiles.open(resolved, mode="w", encoding="utf-8") as f:
                await f.write(content)

    async def read_file(self, relative_path: str) -> str:
        """Read text content from a file in the workspace.

        Args:
            relative_path: Path relative to workspace root.

        Returns:
            Text content of the file.

        Raises:
            ValueError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
        """
        resolved = self._resolve_path(relative_path)

        if not resolved.exists():
            raise FileNotFoundError(
                f"File not found in workspace: '{relative_path}'"
            )

        async with aiofiles.open(resolved, mode="r", encoding="utf-8") as f:
            return await f.read()

    async def file_exists(self, relative_path: str) -> bool:
        """Check if a file exists in the workspace.

        Args:
            relative_path: Path relative to workspace root.

        Returns:
            True if the file exists, False otherwise.

        Raises:
            ValueError: If path traversal is detected.
        """
        resolved = self._resolve_path(relative_path)
        return resolved.exists()

    async def list_files(self, directory: str) -> list[str]:
        """List files in a workspace subdirectory.

        Args:
            directory: Directory path relative to workspace root.

        Returns:
            List of relative file paths within the directory.

        Raises:
            ValueError: If path traversal is detected.
            FileNotFoundError: If the directory does not exist.
        """
        resolved = self._resolve_path(directory)

        if not resolved.exists():
            raise FileNotFoundError(
                f"Directory not found in workspace: '{directory}'"
            )

        if not resolved.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: '{directory}'"
            )

        files: list[str] = []
        for item in resolved.iterdir():
            if item.is_file():
                files.append(str(item.relative_to(self.workspace_root)))

        return sorted(files)

    async def validate_artifact(
        self,
        relative_path: str,
        validator: ArtifactValidator,
    ) -> ValidationResult:
        """Run a validator against an artifact in the workspace.

        Args:
            relative_path: Path to the artifact relative to workspace root.
            validator: An ArtifactValidator implementation to run.

        Returns:
            ValidationResult indicating whether the artifact is valid.

        Raises:
            ValueError: If path traversal is detected.
            FileNotFoundError: If the artifact does not exist.
        """
        resolved = self._resolve_path(relative_path)

        if not resolved.exists():
            return ValidationResult(
                valid=False,
                errors=[f"Artifact not found: '{relative_path}'"],
            )

        return await validator.validate(resolved)

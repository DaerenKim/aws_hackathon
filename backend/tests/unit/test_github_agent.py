"""Unit tests for the GitHub Agent."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from backend.app.agents.github import (
    COMMIT_STRUCTURE,
    GITIGNORE_CONTENT,
    GitHubAgent,
    MAX_RETRIES,
    MIT_LICENSE_TEMPLATE,
    RETRY_DELAY_SECONDS,
)
from backend.app.models.artifacts import AgentResult
from backend.app.models.project_state import AgentStatus
from backend.app.services.ollama_client import OllamaClient
from backend.app.services.state_manager import StateManager
from backend.app.services.workspace import WorkspaceService


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
    """Create OllamaClient (not used by GitHub agent, but required by base)."""
    client = OllamaClient()
    client.generate = AsyncMock(return_value="")
    return client


@pytest_asyncio.fixture
async def agent(
    ollama_client: OllamaClient,
    workspace: WorkspaceService,
    state_manager: StateManager,
) -> GitHubAgent:
    """Create GitHub Agent."""
    return GitHubAgent(
        agent_name="github",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )


async def _write_workspace_content(
    workspace: WorkspaceService, state_manager: StateManager
) -> None:
    """Write sample workspace content and mark project_planner as completed."""
    # Mark project_planner as completed so read_artifact can succeed
    await state_manager.update_agent_status(
        agent="project_planner", status=AgentStatus.COMPLETED
    )
    await workspace.write_file(
        "project_spec.md",
        "# Smart Task Manager\n\n## Refined Idea\nAn AI-powered task manager.",
    )
    await workspace.write_file(
        "README.md",
        "# Smart Task Manager\n\nAn AI project for hackathons.",
    )
    await workspace.write_file(
        "backend/app/main.py",
        'from fastapi import FastAPI\napp = FastAPI()\n',
        agent_name=None,
    )
    await workspace.write_file(
        "frontend/package.json",
        '{"name": "hackathon-frontend", "dependencies": {"next": "14.0.0"}}',
        agent_name=None,
    )


class TestMissingGitHubToken:
    """Tests for when GITHUB_TOKEN is not set."""

    @pytest.mark.asyncio
    async def test_fails_without_github_token(
        self, agent: GitHubAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should fail with descriptive error when GITHUB_TOKEN is not set."""
        await _write_workspace_content(workspace, state_manager)

        with patch.dict(os.environ, {}, clear=True):
            # Ensure GITHUB_TOKEN is explicitly not set
            os.environ.pop("GITHUB_TOKEN", None)
            result = await agent.execute({})

        assert result.success is False
        assert "GITHUB_TOKEN" in result.error
        assert result.artifacts_produced == []

    @pytest.mark.asyncio
    async def test_error_message_is_descriptive(
        self, agent: GitHubAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should provide guidance about the token scope needed."""
        await _write_workspace_content(workspace, state_manager)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_TOKEN", None)
            result = await agent.execute({})

        assert "repo" in result.error.lower() or "personal access token" in result.error.lower()


class TestRepoNameDerivation:
    """Tests for _derive_repo_name logic."""

    def test_extracts_from_h1_heading(self, agent: GitHubAgent) -> None:
        """Should extract repo name from the first H1 heading."""
        spec = "# Smart Task Manager\n\n## Overview\nSome content."
        name = agent._derive_repo_name(spec)
        assert name == "smart-task-manager"

    def test_sanitizes_special_characters(self, agent: GitHubAgent) -> None:
        """Should replace special characters with hyphens."""
        spec = "# My Project!!! (v2.0)\n\nContent."
        name = agent._derive_repo_name(spec)
        assert name == "my-project-v2-0"

    def test_lowercases_name(self, agent: GitHubAgent) -> None:
        """Should lowercase the repo name."""
        spec = "# UPPERCASE PROJECT\n\nContent."
        name = agent._derive_repo_name(spec)
        assert name == "uppercase-project"

    def test_truncates_long_names(self, agent: GitHubAgent) -> None:
        """Should truncate names longer than 100 characters."""
        spec = "# " + "A" * 200 + "\n\nContent."
        name = agent._derive_repo_name(spec)
        assert len(name) <= 100

    def test_fallback_when_no_heading(self, agent: GitHubAgent) -> None:
        """Should fall back to 'hackathon-project' if no suitable name."""
        spec = ""
        name = agent._derive_repo_name(spec)
        assert name == "hackathon-project"

    def test_strips_leading_trailing_hyphens(self, agent: GitHubAgent) -> None:
        """Should strip leading/trailing hyphens from the name."""
        spec = "# ---My Project---\n\nContent."
        name = agent._derive_repo_name(spec)
        assert not name.startswith("-")
        assert not name.endswith("-")


class TestGitignoreAndLicense:
    """Tests for .gitignore and LICENSE generation."""

    @pytest.mark.asyncio
    async def test_writes_gitignore(
        self, agent: GitHubAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should write .gitignore with Python and Node.js patterns."""
        await _write_workspace_content(workspace, state_manager)

        # We need to mock GitHub API calls since we're testing file writing
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}):
            with patch(
                "backend.app.agents.github.GitHubAgent._create_repository"
            ) as mock_create:
                mock_create.side_effect = Exception("API error")
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await agent.execute({})

        # Even though the API call failed, .gitignore should have been written
        assert await workspace.file_exists(".gitignore")
        content = await workspace.read_file(".gitignore")
        assert "__pycache__/" in content
        assert "node_modules/" in content
        assert ".env" in content

    @pytest.mark.asyncio
    async def test_writes_mit_license(
        self, agent: GitHubAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should write MIT LICENSE file."""
        await _write_workspace_content(workspace, state_manager)

        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}):
            with patch(
                "backend.app.agents.github.GitHubAgent._create_repository"
            ) as mock_create:
                mock_create.side_effect = Exception("API error")
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await agent.execute({})

        assert await workspace.file_exists("LICENSE")
        content = await workspace.read_file("LICENSE")
        assert "MIT License" in content
        assert "Permission is hereby granted" in content


class TestRetryLogic:
    """Tests for retry logic on GitHub API errors."""

    @pytest.mark.asyncio
    async def test_retries_on_api_error(
        self, agent: GitHubAgent, workspace: WorkspaceService
    ) -> None:
        """Should retry up to 3 times with delay on API errors."""
        call_count = 0

        def failing_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("API rate limited")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await agent._retry_github_operation(
                operation_name="test_op",
                operation=failing_operation,
            )

        assert result is None
        assert call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_succeeds_on_second_attempt(
        self, agent: GitHubAgent, workspace: WorkspaceService
    ) -> None:
        """Should succeed if retry works."""
        call_count = 0
        mock_repo = MagicMock()

        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary error")
            return mock_repo

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await agent._retry_github_operation(
                operation_name="test_op",
                operation=flaky_operation,
            )

        assert result == mock_repo
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_fails_with_error_after_all_retries(
        self, agent: GitHubAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should return failure result after all retries exhausted."""
        await _write_workspace_content(workspace, state_manager)

        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}):
            with patch(
                "backend.app.agents.github.GitHubAgent._create_repository"
            ) as mock_create:
                mock_create.side_effect = Exception("Name conflict")
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await agent.execute({})

        assert result.success is False
        assert "after" in result.error.lower() or "failed" in result.error.lower()


class TestCommitPathMatching:
    """Tests for _matches_commit_paths logic."""

    def test_matches_directory_prefix(self, agent: GitHubAgent) -> None:
        """Should match files under a directory prefix."""
        assert agent._matches_commit_paths("backend/app/main.py", ["backend/"])
        assert agent._matches_commit_paths("frontend/src/app.tsx", ["frontend/"])

    def test_matches_exact_file(self, agent: GitHubAgent) -> None:
        """Should match exact file names."""
        assert agent._matches_commit_paths("README.md", ["README.md", ".gitignore"])
        assert agent._matches_commit_paths(".gitignore", [".gitignore", "LICENSE"])

    def test_no_match(self, agent: GitHubAgent) -> None:
        """Should not match files outside commit paths."""
        assert not agent._matches_commit_paths("other.txt", ["backend/"])
        assert not agent._matches_commit_paths("backend_extra/file.py", ["backend/"])


class TestMissingProjectSpec:
    """Tests for when project_spec.md is unavailable."""

    @pytest.mark.asyncio
    async def test_fails_without_project_spec(
        self, agent: GitHubAgent, workspace: WorkspaceService
    ) -> None:
        """Should fail if project_spec.md cannot be read."""
        # Don't write project_spec.md

        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}):
            result = await agent.execute({})

        assert result.success is False
        assert "project_spec.md" in result.error


class TestDurationTracking:
    """Tests for execution time tracking."""

    @pytest.mark.asyncio
    async def test_tracks_duration(
        self, agent: GitHubAgent, workspace: WorkspaceService, state_manager: StateManager
    ) -> None:
        """Should track execution duration."""
        await _write_workspace_content(workspace, state_manager)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_TOKEN", None)
            result = await agent.execute({})

        assert result.duration_seconds >= 0

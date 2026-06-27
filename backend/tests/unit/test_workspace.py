"""Unit tests for WorkspaceService."""

import pytest
from pathlib import Path

from app.services.workspace import (
    WorkspaceService,
    ArtifactValidator,
    ValidationResult,
    AGENT_WRITE_BOUNDARIES,
)


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    """Create a temporary workspace root directory."""
    return tmp_path / "workspace"


@pytest.fixture
def service(workspace_root: Path) -> WorkspaceService:
    """Create a WorkspaceService instance with a temp workspace."""
    workspace_root.mkdir(parents=True)
    return WorkspaceService(workspace_root)


class TestPathValidation:
    """Test path traversal prevention."""

    def test_resolve_path_normal(self, service: WorkspaceService) -> None:
        resolved = service._resolve_path("project_spec.md")
        assert str(resolved).startswith(str(service.workspace_root))

    def test_resolve_path_subdirectory(self, service: WorkspaceService) -> None:
        resolved = service._resolve_path("backend/app/main.py")
        assert str(resolved).startswith(str(service.workspace_root))

    def test_resolve_path_traversal_rejected(self, service: WorkspaceService) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            service._resolve_path("../../etc/passwd")

    def test_resolve_path_traversal_hidden(self, service: WorkspaceService) -> None:
        with pytest.raises(ValueError, match="Path traversal detected"):
            service._resolve_path("backend/../../secret.txt")


class TestAgentBoundaries:
    """Test agent write boundary enforcement."""

    def test_project_planner_allowed_file(self, service: WorkspaceService) -> None:
        # Should not raise
        service._check_agent_boundary("project_spec.md", "project_planner")

    def test_project_planner_denied_file(self, service: WorkspaceService) -> None:
        with pytest.raises(PermissionError, match="not allowed to write"):
            service._check_agent_boundary("backend/main.py", "project_planner")

    def test_backend_engineer_allowed_directory(self, service: WorkspaceService) -> None:
        service._check_agent_boundary("backend/app/main.py", "backend_engineer")

    def test_backend_engineer_denied_outside(self, service: WorkspaceService) -> None:
        with pytest.raises(PermissionError, match="not allowed to write"):
            service._check_agent_boundary("frontend/src/app.tsx", "backend_engineer")

    def test_integration_allowed_multiple_dirs(self, service: WorkspaceService) -> None:
        service._check_agent_boundary("backend/fix.py", "integration")
        service._check_agent_boundary("frontend/fix.tsx", "integration")
        service._check_agent_boundary("logs/fix.log", "integration")

    def test_unknown_agent_denied(self, service: WorkspaceService) -> None:
        with pytest.raises(PermissionError, match="Unknown agent"):
            service._check_agent_boundary("anything.txt", "unknown_agent")

    def test_qa_allowed_files_and_dirs(self, service: WorkspaceService) -> None:
        service._check_agent_boundary("testing_report.md", "qa")
        service._check_agent_boundary("logs/test.log", "qa")

    def test_documentation_allowed(self, service: WorkspaceService) -> None:
        service._check_agent_boundary("README.md", "documentation")
        service._check_agent_boundary("docs/guide.md", "documentation")

    def test_github_allowed(self, service: WorkspaceService) -> None:
        service._check_agent_boundary(".gitignore", "github")
        service._check_agent_boundary("LICENSE", "github")


class TestWriteFile:
    """Test async file writing."""

    @pytest.mark.asyncio
    async def test_write_text_file(self, service: WorkspaceService) -> None:
        await service.write_file("project_spec.md", "# Project Spec")
        path = service.workspace_root / "project_spec.md"
        assert path.exists()
        assert path.read_text() == "# Project Spec"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, service: WorkspaceService) -> None:
        await service.write_file("backend/app/main.py", "print('hello')")
        path = service.workspace_root / "backend" / "app" / "main.py"
        assert path.exists()

    @pytest.mark.asyncio
    async def test_write_binary_file(self, service: WorkspaceService) -> None:
        content = b"\x00\x01\x02\x03"
        await service.write_file("output.bin", content)
        path = service.workspace_root / "output.bin"
        assert path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_write_with_agent_boundary_check(self, service: WorkspaceService) -> None:
        await service.write_file("backend/app.py", "code", agent_name="backend_engineer")
        path = service.workspace_root / "backend" / "app.py"
        assert path.exists()

    @pytest.mark.asyncio
    async def test_write_agent_boundary_violation(self, service: WorkspaceService) -> None:
        with pytest.raises(PermissionError):
            await service.write_file("frontend/app.tsx", "code", agent_name="backend_engineer")

    @pytest.mark.asyncio
    async def test_write_no_agent_skips_boundary(self, service: WorkspaceService) -> None:
        # Orchestrator writes (agent_name=None) skip boundary check
        await service.write_file("anywhere/file.txt", "content")
        path = service.workspace_root / "anywhere" / "file.txt"
        assert path.exists()

    @pytest.mark.asyncio
    async def test_write_path_traversal_blocked(self, service: WorkspaceService) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            await service.write_file("../../evil.sh", "rm -rf /")


class TestReadFile:
    """Test async file reading."""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, service: WorkspaceService) -> None:
        (service.workspace_root / "test.md").write_text("hello world")
        content = await service.read_file("test.md")
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, service: WorkspaceService) -> None:
        with pytest.raises(FileNotFoundError, match="File not found"):
            await service.read_file("missing.txt")

    @pytest.mark.asyncio
    async def test_read_path_traversal_blocked(self, service: WorkspaceService) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            await service.read_file("../../etc/passwd")


class TestFileExists:
    """Test file existence checks."""

    @pytest.mark.asyncio
    async def test_existing_file(self, service: WorkspaceService) -> None:
        (service.workspace_root / "exists.md").write_text("content")
        assert await service.file_exists("exists.md") is True

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, service: WorkspaceService) -> None:
        assert await service.file_exists("nope.md") is False

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, service: WorkspaceService) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            await service.file_exists("../../etc/passwd")


class TestListFiles:
    """Test directory listing."""

    @pytest.mark.asyncio
    async def test_list_files_in_directory(self, service: WorkspaceService) -> None:
        backend_dir = service.workspace_root / "backend"
        backend_dir.mkdir()
        (backend_dir / "main.py").write_text("app")
        (backend_dir / "utils.py").write_text("util")

        files = await service.list_files("backend")
        assert "backend/main.py" in files
        assert "backend/utils.py" in files
        assert len(files) == 2

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self, service: WorkspaceService) -> None:
        with pytest.raises(FileNotFoundError, match="Directory not found"):
            await service.list_files("nonexistent")

    @pytest.mark.asyncio
    async def test_list_file_not_directory(self, service: WorkspaceService) -> None:
        (service.workspace_root / "file.txt").write_text("not a dir")
        with pytest.raises(NotADirectoryError):
            await service.list_files("file.txt")

    @pytest.mark.asyncio
    async def test_list_excludes_subdirectories(self, service: WorkspaceService) -> None:
        logs_dir = service.workspace_root / "logs"
        logs_dir.mkdir()
        (logs_dir / "app.log").write_text("log")
        (logs_dir / "subdir").mkdir()

        files = await service.list_files("logs")
        assert len(files) == 1
        assert "logs/app.log" in files


class TestValidateArtifact:
    """Test artifact validation."""

    @pytest.mark.asyncio
    async def test_validate_existing_artifact(self, service: WorkspaceService) -> None:
        (service.workspace_root / "output.md").write_text("# Valid content")

        class MockValidator:
            async def validate(self, file_path: Path) -> ValidationResult:
                return ValidationResult(valid=True)

        result = await service.validate_artifact("output.md", MockValidator())
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_validate_nonexistent_artifact(self, service: WorkspaceService) -> None:
        class MockValidator:
            async def validate(self, file_path: Path) -> ValidationResult:
                return ValidationResult(valid=True)

        result = await service.validate_artifact("missing.md", MockValidator())
        assert result.valid is False
        assert "Artifact not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_with_failing_validator(self, service: WorkspaceService) -> None:
        (service.workspace_root / "bad.pptx").write_bytes(b"not a real pptx")

        class FailingValidator:
            async def validate(self, file_path: Path) -> ValidationResult:
                return ValidationResult(valid=False, errors=["Invalid OOXML structure"])

        result = await service.validate_artifact("bad.pptx", FailingValidator())
        assert result.valid is False
        assert "Invalid OOXML structure" in result.errors

"""Unit tests for artifact validators."""

import json
import zipfile
from pathlib import Path

import pytest

from app.services.validators import (
    MarkdownNonEmptyValidator,
    Mp4Validator,
    PackageJsonValidator,
    PptxValidator,
    PythonSyntaxValidator,
)
from app.services.workspace import ArtifactValidator


class TestProtocolConformance:
    """Verify all validators satisfy the ArtifactValidator protocol."""

    def test_python_syntax_validator_is_artifact_validator(self) -> None:
        assert isinstance(PythonSyntaxValidator(), ArtifactValidator)

    def test_package_json_validator_is_artifact_validator(self) -> None:
        assert isinstance(PackageJsonValidator(), ArtifactValidator)

    def test_pptx_validator_is_artifact_validator(self) -> None:
        assert isinstance(PptxValidator(), ArtifactValidator)

    def test_mp4_validator_is_artifact_validator(self) -> None:
        assert isinstance(Mp4Validator(), ArtifactValidator)

    def test_markdown_validator_is_artifact_validator(self) -> None:
        assert isinstance(MarkdownNonEmptyValidator(), ArtifactValidator)


class TestPythonSyntaxValidator:
    """Tests for PythonSyntaxValidator."""

    @pytest.fixture
    def validator(self) -> PythonSyntaxValidator:
        return PythonSyntaxValidator()

    @pytest.mark.asyncio
    async def test_valid_directory(
        self, validator: PythonSyntaxValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "main.py").write_text('print("hello")\n')
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
        (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\nuvicorn\n")

        result = await validator.validate(tmp_path)
        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_not_a_directory(
        self, validator: PythonSyntaxValidator, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "not_a_dir.py"
        file_path.write_text("x = 1\n")

        result = await validator.validate(file_path)
        assert result.valid is False
        assert any("directory" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_syntax_error_detected(
        self, validator: PythonSyntaxValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "bad.py").write_text("def foo(\n")
        (tmp_path / "requirements.txt").write_text("fastapi\n")

        result = await validator.validate(tmp_path)
        assert result.valid is False
        assert any("Syntax error" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_requirements_txt(
        self, validator: PythonSyntaxValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")

        result = await validator.validate(tmp_path)
        assert result.valid is False
        assert any("requirements.txt" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_requirements_missing_fastapi(
        self, validator: PythonSyntaxValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "requirements.txt").write_text("flask\ndjango\n")

        result = await validator.validate(tmp_path)
        assert result.valid is False
        assert any("fastapi" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_py_files(
        self, validator: PythonSyntaxValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        (tmp_path / "readme.md").write_text("# Hello\n")

        result = await validator.validate(tmp_path)
        assert result.valid is False
        assert any("No .py files" in e for e in result.errors)


class TestPackageJsonValidator:
    """Tests for PackageJsonValidator."""

    @pytest.fixture
    def validator(self) -> PackageJsonValidator:
        return PackageJsonValidator()

    @pytest.mark.asyncio
    async def test_valid_package_json(
        self, validator: PackageJsonValidator, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "name": "my-app",
                    "dependencies": {"next": "^14.0.0", "react": "^18"},
                    "scripts": {"build": "next build", "dev": "next dev"},
                }
            )
        )

        result = await validator.validate(pkg)
        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_invalid_json(
        self, validator: PackageJsonValidator, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text("{not valid json")

        result = await validator.validate(pkg)
        assert result.valid is False
        assert any("Invalid JSON" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_name(
        self, validator: PackageJsonValidator, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "dependencies": {"next": "^14"},
                    "scripts": {"build": "next build"},
                }
            )
        )

        result = await validator.validate(pkg)
        assert result.valid is False
        assert any("name" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_next_dependency(
        self, validator: PackageJsonValidator, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "name": "app",
                    "dependencies": {"react": "^18"},
                    "scripts": {"build": "vite build"},
                }
            )
        )

        result = await validator.validate(pkg)
        assert result.valid is False
        assert any("next" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_build_script(
        self, validator: PackageJsonValidator, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "name": "app",
                    "dependencies": {"next": "^14"},
                    "scripts": {"dev": "next dev"},
                }
            )
        )

        result = await validator.validate(pkg)
        assert result.valid is False
        assert any("build" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_dependencies_field(
        self, validator: PackageJsonValidator, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "name": "app",
                    "scripts": {"build": "next build"},
                }
            )
        )

        result = await validator.validate(pkg)
        assert result.valid is False
        assert any("dependencies" in e for e in result.errors)


class TestPptxValidator:
    """Tests for PptxValidator."""

    @pytest.fixture
    def validator(self) -> PptxValidator:
        return PptxValidator()

    @pytest.mark.asyncio
    async def test_not_a_zip(
        self, validator: PptxValidator, tmp_path: Path
    ) -> None:
        pptx = tmp_path / "pres.pptx"
        pptx.write_text("not a zip file")

        result = await validator.validate(pptx)
        assert result.valid is False
        assert any("ZIP" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_zip_without_content_types(
        self, validator: PptxValidator, tmp_path: Path
    ) -> None:
        pptx = tmp_path / "pres.pptx"
        with zipfile.ZipFile(pptx, "w") as zf:
            zf.writestr("some_file.xml", "<root/>")

        result = await validator.validate(pptx)
        assert result.valid is False
        assert any("Content_Types" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_too_few_slides(
        self, validator: PptxValidator, tmp_path: Path
    ) -> None:
        pptx = tmp_path / "pres.pptx"
        with zipfile.ZipFile(pptx, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            for i in range(1, 4):  # Only 3 slides
                zf.writestr(f"ppt/slides/slide{i}.xml", "<slide/>")

        result = await validator.validate(pptx)
        assert result.valid is False
        assert any("3 slides" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_pptx_structure(
        self, validator: PptxValidator, tmp_path: Path
    ) -> None:
        pptx = tmp_path / "pres.pptx"
        with zipfile.ZipFile(pptx, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            for i in range(1, 8):  # 7 slides (>= 6)
                zf.writestr(f"ppt/slides/slide{i}.xml", "<slide/>")

        result = await validator.validate(pptx)
        assert result.valid is True
        assert result.errors == []


class TestMp4Validator:
    """Tests for Mp4Validator."""

    @pytest.fixture
    def validator(self) -> Mp4Validator:
        return Mp4Validator()

    @pytest.mark.asyncio
    async def test_empty_file(
        self, validator: Mp4Validator, tmp_path: Path
    ) -> None:
        mp4 = tmp_path / "video.mp4"
        mp4.write_bytes(b"")

        result = await validator.validate(mp4)
        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_nonexistent_file(
        self, validator: Mp4Validator, tmp_path: Path
    ) -> None:
        mp4 = tmp_path / "missing.mp4"

        result = await validator.validate(mp4)
        assert result.valid is False
        assert any("Cannot access" in e for e in result.errors)


class TestMarkdownNonEmptyValidator:
    """Tests for MarkdownNonEmptyValidator."""

    @pytest.fixture
    def validator(self) -> MarkdownNonEmptyValidator:
        return MarkdownNonEmptyValidator()

    @pytest.mark.asyncio
    async def test_valid_content(
        self, validator: MarkdownNonEmptyValidator, tmp_path: Path
    ) -> None:
        md = tmp_path / "readme.md"
        md.write_text("# Title\n\n" + "Content " * 50)

        result = await validator.validate(md)
        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_empty_file(
        self, validator: MarkdownNonEmptyValidator, tmp_path: Path
    ) -> None:
        md = tmp_path / "empty.md"
        md.write_text("")

        result = await validator.validate(md)
        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_too_short(
        self, validator: MarkdownNonEmptyValidator, tmp_path: Path
    ) -> None:
        md = tmp_path / "short.md"
        md.write_text("# Short\n\nNot enough content here.")

        result = await validator.validate(md)
        assert result.valid is False
        assert any("200" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_exactly_200_chars(
        self, validator: MarkdownNonEmptyValidator, tmp_path: Path
    ) -> None:
        md = tmp_path / "exact.md"
        md.write_text("x" * 200)

        result = await validator.validate(md)
        assert result.valid is True
        assert result.errors == []

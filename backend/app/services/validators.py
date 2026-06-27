"""Artifact validators for agent output integrity checks.

Each validator implements the ArtifactValidator protocol from workspace.py,
providing format-specific validation for different agent outputs:
- PythonSyntaxValidator: Backend Python code and requirements.txt
- PackageJsonValidator: Frontend package.json structure
- PptxValidator: PowerPoint OOXML file structure
- Mp4Validator: Video file stream and duration
- MarkdownNonEmptyValidator: Markdown content length
"""

import ast
import json
import subprocess
import zipfile
from pathlib import Path

from app.services.workspace import ValidationResult


class PythonSyntaxValidator:
    """Validates backend Python output.

    Checks that:
    - The given path is a directory containing .py files
    - All .py files have valid Python syntax (ast.parse)
    - A requirements.txt exists and lists 'fastapi' as a dependency
    """

    async def validate(self, file_path: Path) -> ValidationResult:
        """Validate a backend directory for Python syntax and dependencies.

        Args:
            file_path: Path to the backend/ directory.

        Returns:
            ValidationResult with valid=True if all checks pass.
        """
        errors: list[str] = []

        if not file_path.is_dir():
            return ValidationResult(
                valid=False,
                errors=[f"Expected a directory, got: '{file_path}'"],
            )

        # Find all .py files recursively
        py_files = list(file_path.rglob("*.py"))
        if not py_files:
            errors.append("No .py files found in backend directory")

        # Check syntax of each .py file
        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                ast.parse(source, filename=str(py_file))
            except SyntaxError as e:
                errors.append(
                    f"Syntax error in {py_file.relative_to(file_path)}: "
                    f"line {e.lineno}: {e.msg}"
                )
            except (OSError, UnicodeDecodeError) as e:
                errors.append(
                    f"Cannot read {py_file.relative_to(file_path)}: {e}"
                )

        # Check requirements.txt exists and contains fastapi
        requirements_path = file_path / "requirements.txt"
        if not requirements_path.exists():
            errors.append("requirements.txt not found in backend directory")
        else:
            try:
                content = requirements_path.read_text(encoding="utf-8").lower()
                if "fastapi" not in content:
                    errors.append(
                        "requirements.txt does not list 'fastapi' as a dependency"
                    )
            except (OSError, UnicodeDecodeError) as e:
                errors.append(f"Cannot read requirements.txt: {e}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)


class PackageJsonValidator:
    """Validates frontend package.json structure.

    Checks that:
    - The file is valid JSON
    - It has a "name" field
    - It has a "dependencies" field
    - "next" is listed in dependencies
    - "scripts" has a "build" entry
    """

    async def validate(self, file_path: Path) -> ValidationResult:
        """Validate a package.json file for required fields.

        Args:
            file_path: Path to the package.json file.

        Returns:
            ValidationResult with valid=True if all checks pass.
        """
        errors: list[str] = []

        # Parse as JSON
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                errors=[f"Invalid JSON in package.json: {e}"],
            )
        except (OSError, UnicodeDecodeError) as e:
            return ValidationResult(
                valid=False,
                errors=[f"Cannot read package.json: {e}"],
            )

        # Check required fields
        if "name" not in data:
            errors.append("package.json missing 'name' field")

        if "dependencies" not in data:
            errors.append("package.json missing 'dependencies' field")
        else:
            deps = data["dependencies"]
            if not isinstance(deps, dict):
                errors.append("package.json 'dependencies' is not an object")
            elif "next" not in deps:
                errors.append(
                    "package.json 'dependencies' does not include 'next'"
                )

        # Check scripts.build
        scripts = data.get("scripts")
        if not isinstance(scripts, dict):
            errors.append("package.json missing 'scripts' field")
        elif "build" not in scripts:
            errors.append("package.json 'scripts' missing 'build' entry")

        return ValidationResult(valid=len(errors) == 0, errors=errors)


class PptxValidator:
    """Validates PowerPoint OOXML file structure.

    Checks that:
    - The file is a valid ZIP archive
    - It contains [Content_Types].xml (OOXML signature)
    - It contains at least 6 slides (ppt/slides/slide*.xml)
    """

    async def validate(self, file_path: Path) -> ValidationResult:
        """Validate a .pptx file for OOXML structure and slide count.

        Args:
            file_path: Path to the .pptx file.

        Returns:
            ValidationResult with valid=True if all checks pass.
        """
        errors: list[str] = []

        # Check valid ZIP
        if not zipfile.is_zipfile(file_path):
            return ValidationResult(
                valid=False,
                errors=[f"File is not a valid ZIP archive: '{file_path.name}'"],
            )

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = zf.namelist()

                # Check OOXML signature
                if "[Content_Types].xml" not in names:
                    errors.append(
                        "Missing [Content_Types].xml — not a valid OOXML file"
                    )

                # Count slides
                slide_entries = [
                    n
                    for n in names
                    if n.startswith("ppt/slides/slide")
                    and n.endswith(".xml")
                ]
                slide_count = len(slide_entries)

                if slide_count < 6:
                    errors.append(
                        f"PPTX contains {slide_count} slides, "
                        f"minimum required is 6"
                    )
        except zipfile.BadZipFile as e:
            return ValidationResult(
                valid=False,
                errors=[f"Corrupted ZIP archive: {e}"],
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors)


class Mp4Validator:
    """Validates MP4 video files.

    Checks that:
    - The file has size > 0
    - ffprobe can decode it and finds at least one video stream
    - Duration is at least 5 seconds
    - Falls back to size > 1000 bytes check if ffprobe is unavailable
    """

    async def validate(self, file_path: Path) -> ValidationResult:
        """Validate an MP4 file for video stream and duration.

        Args:
            file_path: Path to the .mp4 file.

        Returns:
            ValidationResult with valid=True if all checks pass.
        """
        errors: list[str] = []

        # Check file size > 0
        try:
            file_size = file_path.stat().st_size
        except OSError as e:
            return ValidationResult(
                valid=False,
                errors=[f"Cannot access file: {e}"],
            )

        if file_size == 0:
            return ValidationResult(
                valid=False,
                errors=["MP4 file is empty (0 bytes)"],
            )

        # Try ffprobe for detailed checks
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                errors.append(
                    "ffprobe failed to decode the MP4 file — "
                    "file may be corrupted or not a valid video"
                )
                return ValidationResult(valid=False, errors=errors)

            probe_data = json.loads(result.stdout)

            # Check for video stream
            streams = probe_data.get("streams", [])
            video_streams = [
                s for s in streams if s.get("codec_type") == "video"
            ]
            if not video_streams:
                errors.append("MP4 file does not contain a video stream")

            # Check duration >= 5 seconds
            format_info = probe_data.get("format", {})
            duration_str = format_info.get("duration")
            if duration_str is not None:
                try:
                    duration = float(duration_str)
                    if duration < 5.0:
                        errors.append(
                            f"MP4 duration is {duration:.1f}s, "
                            f"minimum required is 5s"
                        )
                except (ValueError, TypeError):
                    errors.append("Cannot parse MP4 duration from ffprobe output")
            else:
                errors.append("ffprobe did not report duration for the file")

        except FileNotFoundError:
            # ffprobe not available — fallback to file size check
            if file_size <= 1000:
                errors.append(
                    "ffprobe not available; fallback check failed — "
                    f"file size is {file_size} bytes (must be > 1000 bytes)"
                )
        except subprocess.TimeoutExpired:
            errors.append("ffprobe timed out while probing the MP4 file")
        except (json.JSONDecodeError, KeyError) as e:
            errors.append(f"Failed to parse ffprobe output: {e}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)


class MarkdownNonEmptyValidator:
    """Validates markdown files for minimum content length.

    Checks that:
    - The file is non-empty
    - Content length is at least 200 characters
    """

    async def validate(self, file_path: Path) -> ValidationResult:
        """Validate a markdown file for minimum content length.

        Args:
            file_path: Path to the .md file.

        Returns:
            ValidationResult with valid=True if content >= 200 chars.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return ValidationResult(
                valid=False,
                errors=[f"Cannot read markdown file: {e}"],
            )

        if len(content) == 0:
            return ValidationResult(
                valid=False,
                errors=["Markdown file is empty"],
            )

        if len(content) < 200:
            return ValidationResult(
                valid=False,
                errors=[
                    f"Markdown content is {len(content)} characters, "
                    f"minimum required is 200"
                ],
            )

        return ValidationResult(valid=True, errors=[])


# Convenience mapping from agent name to the appropriate validator instance.
# Used by the orchestrator when validating agent outputs after completion.
AGENT_VALIDATORS: dict[str, list[tuple[str, "PythonSyntaxValidator | PackageJsonValidator | PptxValidator | Mp4Validator | MarkdownNonEmptyValidator"]]] = {
    "backend_engineer": [
        ("backend/", PythonSyntaxValidator()),
    ],
    "frontend_engineer": [
        ("frontend/package.json", PackageJsonValidator()),
    ],
    "powerpoint": [
        ("ppt/presentation.pptx", PptxValidator()),
    ],
    "demo_video": [
        ("video/demo.mp4", Mp4Validator()),
    ],
    "documentation": [
        ("README.md", MarkdownNonEmptyValidator()),
        ("developer_guide.md", MarkdownNonEmptyValidator()),
        ("api_docs.md", MarkdownNonEmptyValidator()),
    ],
}

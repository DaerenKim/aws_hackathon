"""Input collection API endpoints.

Handles file uploads (hackathon brief, judging rubric) and text submissions
(project idea, tech stack). Validates inputs and stores them in the workspace.

Requirements: 1.1-1.8
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.inputs import (
    UploadedFile as UploadedFileModel,
    ValidationError as InputValidationError,
    ValidationResult,
)

router = APIRouter(prefix="/api/inputs", tags=["inputs"])

# Constants
MAX_FILE_SIZE = 10_485_760  # 10MB
ALLOWED_FORMATS = {"pdf", "docx", "txt"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}

# In-memory state for the current session's input collection
_upload_state: dict[str, UploadedFileModel] = {}
_text_state: dict[str, str | None] = {}
_validation_result: ValidationResult = ValidationResult(valid=False, errors=[])


def _get_workspace_inputs_dir() -> Path:
    """Get the workspace inputs directory path."""
    workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "./shared_workspace"))
    inputs_dir = workspace_root / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    return inputs_dir


def _get_file_extension(filename: str) -> str:
    """Extract file extension from filename (lowercase, no dot)."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _detect_format_from_content_type(content_type: str | None) -> str | None:
    """Detect file format from content type header."""
    if content_type and content_type in ALLOWED_CONTENT_TYPES:
        return ALLOWED_CONTENT_TYPES[content_type]
    return None


def _detect_format(filename: str, content_type: str | None) -> str | None:
    """Detect file format from filename extension or content type."""
    ext = _get_file_extension(filename)
    if ext in ALLOWED_FORMATS:
        return ext
    return _detect_format_from_content_type(content_type)


async def _extract_text_from_pdf(content: bytes) -> str:
    """Extract text content from a PDF file."""
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(content))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception:
        return ""


async def _extract_text_from_docx(content: bytes) -> str:
    """Extract text content from a DOCX file."""
    try:
        from docx import Document
        import io

        doc = Document(io.BytesIO(content))
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        return "\n".join(text_parts)
    except Exception:
        return ""


async def _extract_text_from_txt(content: bytes) -> str:
    """Extract text content from a plain text file."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content.decode("latin-1")
        except Exception:
            return ""


async def _extract_text(content: bytes, file_format: str) -> str:
    """Extract text from file content based on format."""
    extractors = {
        "pdf": _extract_text_from_pdf,
        "docx": _extract_text_from_docx,
        "txt": _extract_text_from_txt,
    }
    extractor = extractors.get(file_format)
    if extractor is None:
        return ""
    return await extractor(content)


def _validate_file(
    filename: str,
    content_type: str | None,
    size: int,
    extracted_text: str,
    field_name: str,
) -> list[InputValidationError]:
    """Validate a single uploaded file and return any errors."""
    errors: list[InputValidationError] = []

    # Check format
    file_format = _detect_format(filename, content_type)
    if file_format is None:
        errors.append(
            InputValidationError(
                field=field_name,
                reason="unsupported_format",
                detail=f"File '{filename}' has an unsupported format. Accepted formats: PDF, DOCX, TXT.",
            )
        )
        return errors  # No point checking further if format is invalid

    # Check size
    if size > MAX_FILE_SIZE:
        errors.append(
            InputValidationError(
                field=field_name,
                reason="size_exceeded",
                detail=f"File '{filename}' exceeds the 10MB size limit ({size} bytes).",
            )
        )

    if size == 0:
        errors.append(
            InputValidationError(
                field=field_name,
                reason="empty_content",
                detail=f"File '{filename}' is empty (0 bytes).",
            )
        )
        return errors

    # Check text extraction
    if not extracted_text.strip():
        errors.append(
            InputValidationError(
                field=field_name,
                reason="unextractable_text",
                detail=f"Could not extract text content from '{filename}'.",
            )
        )

    return errors


def _validate_all_inputs() -> ValidationResult:
    """Validate all collected inputs and return the result."""
    errors: list[InputValidationError] = []

    # Check required uploads
    if "hackathon_brief" not in _upload_state:
        errors.append(
            InputValidationError(
                field="hackathon_brief",
                reason="empty_content",
                detail="Hackathon brief document is required.",
            )
        )

    if "judging_rubric" not in _upload_state:
        errors.append(
            InputValidationError(
                field="judging_rubric",
                reason="empty_content",
                detail="Judging rubric document is required.",
            )
        )

    # Check required text input
    project_idea = _text_state.get("project_idea")
    if not project_idea:
        errors.append(
            InputValidationError(
                field="project_idea",
                reason="length_constraint",
                detail="Project idea is required (1-5000 characters).",
            )
        )
    elif len(project_idea) > 5000:
        errors.append(
            InputValidationError(
                field="project_idea",
                reason="length_constraint",
                detail=f"Project idea exceeds 5000 characters ({len(project_idea)} chars).",
            )
        )

    # Check optional tech stack length
    tech_stack = _text_state.get("tech_stack")
    if tech_stack and len(tech_stack) > 2000:
        errors.append(
            InputValidationError(
                field="tech_stack",
                reason="length_constraint",
                detail=f"Tech stack exceeds 2000 characters ({len(tech_stack)} chars).",
            )
        )

    valid = len(errors) == 0
    return ValidationResult(valid=valid, errors=errors)


@router.post("/upload", response_model=ValidationResult)
async def upload_file(
    file: UploadFile = File(...),
    field_name: str = Form(...),
) -> ValidationResult:
    """Upload a file (hackathon brief or judging rubric).

    Accepts PDF, DOCX, or TXT files up to 10MB. Extracts text content
    and validates the file. Stores in workspace inputs/ directory.

    Args:
        file: The uploaded file.
        field_name: Which input this file is for ('hackathon_brief' or 'judging_rubric').

    Returns:
        ValidationResult with any errors found during validation.
    """
    global _validation_result

    if field_name not in ("hackathon_brief", "judging_rubric"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid field_name: '{field_name}'. Must be 'hackathon_brief' or 'judging_rubric'.",
        )

    # Read file content
    content = await file.read()
    size = len(content)
    filename = file.filename or "unknown"
    content_type = file.content_type

    # Detect format
    file_format = _detect_format(filename, content_type)

    # Validate file basics
    errors = _validate_file(filename, content_type, size, "", field_name)

    # Only attempt text extraction if format and size are valid
    extracted_text = ""
    if file_format and size > 0 and size <= MAX_FILE_SIZE:
        extracted_text = await _extract_text(content, file_format)
        # Re-validate with extracted text
        errors = _validate_file(filename, content_type, size, extracted_text, field_name)

    if errors:
        result = ValidationResult(valid=False, errors=errors)
        _validation_result = _validate_all_inputs()
        return result

    # Store the uploaded file in workspace
    inputs_dir = _get_workspace_inputs_dir()
    file_path = inputs_dir / filename
    file_path.write_bytes(content)

    # Update upload state
    _upload_state[field_name] = UploadedFileModel(
        filename=filename,
        content_type=content_type or "application/octet-stream",
        size=size,
        extracted_text=extracted_text,
    )

    # Recalculate overall validation
    _validation_result = _validate_all_inputs()

    return ValidationResult(valid=True, errors=[])


@router.post("/submit", response_model=ValidationResult)
async def submit_text_inputs(
    project_idea: str = Form(default=""),
    tech_stack: Optional[str] = Form(default=None),
) -> ValidationResult:
    """Submit project idea and optional tech stack text inputs.

    Args:
        project_idea: Free-form text describing the project idea (1-5000 chars).
        tech_stack: Optional preferred technology stack (≤2000 chars).

    Returns:
        ValidationResult with any errors found during validation.
    """
    global _validation_result

    errors: list[InputValidationError] = []

    # Validate project idea
    if not project_idea or len(project_idea.strip()) == 0:
        errors.append(
            InputValidationError(
                field="project_idea",
                reason="length_constraint",
                detail="Project idea is required and cannot be empty.",
            )
        )
    elif len(project_idea) > 5000:
        errors.append(
            InputValidationError(
                field="project_idea",
                reason="length_constraint",
                detail=f"Project idea exceeds 5000 characters ({len(project_idea)} chars).",
            )
        )

    # Validate tech stack (optional)
    if tech_stack and len(tech_stack) > 2000:
        errors.append(
            InputValidationError(
                field="tech_stack",
                reason="length_constraint",
                detail=f"Tech stack exceeds 2000 characters ({len(tech_stack)} chars).",
            )
        )

    if errors:
        _validation_result = ValidationResult(valid=False, errors=errors)
        return _validation_result

    # Store text inputs
    _text_state["project_idea"] = project_idea.strip()
    _text_state["tech_stack"] = tech_stack.strip() if tech_stack else None

    # Save to workspace
    inputs_dir = _get_workspace_inputs_dir()
    (inputs_dir / "project_idea.txt").write_text(project_idea.strip(), encoding="utf-8")
    if tech_stack:
        (inputs_dir / "tech_stack.txt").write_text(tech_stack.strip(), encoding="utf-8")

    # Recalculate overall validation
    _validation_result = _validate_all_inputs()

    return ValidationResult(valid=True, errors=[])


@router.get("/status", response_model=ValidationResult)
async def get_validation_status() -> ValidationResult:
    """Get the current validation status of all inputs.

    Returns the overall validation result including which required inputs
    are still missing and any validation errors.

    Returns:
        ValidationResult indicating whether all inputs are valid.
    """
    return _validate_all_inputs()

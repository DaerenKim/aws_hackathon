"""Pydantic models for input collection and validation.

Defines the schema for user-uploaded files, the input package,
and validation results used by the Input Collector.
"""

from pydantic import BaseModel, Field


class UploadedFile(BaseModel):
    """Represents an uploaded document (hackathon brief or judging rubric)."""

    filename: str
    content_type: str  # "application/pdf" | "application/vnd.openxmlformats..." | "text/plain"
    size: int = Field(..., gt=0, le=10_485_760)  # Max 10MB
    extracted_text: str


class InputPackage(BaseModel):
    """The complete set of user-provided inputs for project generation."""

    hackathon_brief: UploadedFile
    judging_rubric: UploadedFile
    project_idea: str = Field(..., min_length=1, max_length=5000)
    tech_stack: str | None = Field(default=None, max_length=2000)


class ValidationError(BaseModel):
    """A single validation error for an input field."""

    field: str
    reason: str  # "unsupported_format" | "empty_content" | "unextractable_text" | "size_exceeded" | "length_constraint"
    detail: str


class ValidationResult(BaseModel):
    """Result of validating the input package."""

    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)

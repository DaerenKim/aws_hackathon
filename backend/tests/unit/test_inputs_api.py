"""Unit tests for the input collection API endpoints.

Tests file upload, text submission, and validation status endpoints.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.routes import inputs
from app.api.routes.inputs import router


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module-level state between tests."""
    inputs._upload_state.clear()
    inputs._text_state.clear()
    inputs._validation_result = inputs.ValidationResult(valid=False, errors=[])
    yield
    inputs._upload_state.clear()
    inputs._text_state.clear()


@pytest.fixture
def app():
    """Create a FastAPI app with the inputs router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def temp_workspace(tmp_path):
    """Set up a temporary workspace directory."""
    workspace = tmp_path / "shared_workspace"
    workspace.mkdir()
    with patch.dict(os.environ, {"WORKSPACE_ROOT": str(workspace)}):
        yield workspace


class TestUploadEndpoint:
    """Tests for POST /api/inputs/upload."""

    def test_upload_valid_txt_file(self, client, temp_workspace):
        """Upload a valid TXT file for hackathon brief."""
        content = b"This is a valid hackathon brief document with enough content."
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", content, "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is True
        assert result["errors"] == []

    def test_upload_valid_pdf_file(self, client, temp_workspace):
        """Upload a valid PDF file (minimal PDF structure)."""
        # Minimal valid PDF content
        pdf_content = (
            b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
            b"0000000058 00000 n \n0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n206\n%%EOF"
        )
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.pdf", pdf_content, "application/pdf")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        # PDF without text content will fail extraction
        # This tests the extraction failure path
        if not result["valid"]:
            assert any(e["reason"] == "unextractable_text" for e in result["errors"])

    def test_upload_unsupported_format(self, client, temp_workspace):
        """Upload a file with unsupported format."""
        content = b"some binary data"
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.jpg", content, "image/jpeg")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert len(result["errors"]) >= 1
        assert result["errors"][0]["reason"] == "unsupported_format"
        assert result["errors"][0]["field"] == "hackathon_brief"

    def test_upload_empty_file(self, client, temp_workspace):
        """Upload an empty file."""
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", b"", "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert any(e["reason"] == "empty_content" for e in result["errors"])

    def test_upload_oversized_file(self, client, temp_workspace):
        """Upload a file exceeding 10MB."""
        content = b"x" * (10_485_761)  # Just over 10MB
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", content, "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert any(e["reason"] == "size_exceeded" for e in result["errors"])

    def test_upload_invalid_field_name(self, client, temp_workspace):
        """Upload with an invalid field name."""
        content = b"Some content"
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", content, "text/plain")},
            data={"field_name": "invalid_field"},
        )
        assert response.status_code == 400

    def test_upload_stores_file_in_workspace(self, client, temp_workspace):
        """Verify uploaded file is stored in workspace inputs/ directory."""
        content = b"This is a hackathon brief with meaningful content."
        client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", content, "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        inputs_dir = temp_workspace / "inputs"
        assert (inputs_dir / "brief.txt").exists()
        assert (inputs_dir / "brief.txt").read_bytes() == content


class TestSubmitEndpoint:
    """Tests for POST /api/inputs/submit."""

    def test_submit_valid_inputs(self, client, temp_workspace):
        """Submit valid project idea and tech stack."""
        response = client.post(
            "/api/inputs/submit",
            data={
                "project_idea": "Build an AI-powered code review tool",
                "tech_stack": "Python, FastAPI, React",
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is True
        assert result["errors"] == []

    def test_submit_without_tech_stack(self, client, temp_workspace):
        """Submit with project idea only (tech stack is optional)."""
        response = client.post(
            "/api/inputs/submit",
            data={"project_idea": "Build an AI chatbot"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is True

    def test_submit_empty_project_idea(self, client, temp_workspace):
        """Submit with empty project idea."""
        response = client.post(
            "/api/inputs/submit",
            data={"project_idea": ""},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert any(e["field"] == "project_idea" for e in result["errors"])
        assert any(e["reason"] == "length_constraint" for e in result["errors"])

    def test_submit_project_idea_too_long(self, client, temp_workspace):
        """Submit with project idea exceeding 5000 chars."""
        response = client.post(
            "/api/inputs/submit",
            data={"project_idea": "x" * 5001},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert any(
            e["field"] == "project_idea" and e["reason"] == "length_constraint"
            for e in result["errors"]
        )

    def test_submit_tech_stack_too_long(self, client, temp_workspace):
        """Submit with tech stack exceeding 2000 chars."""
        response = client.post(
            "/api/inputs/submit",
            data={
                "project_idea": "Valid idea",
                "tech_stack": "x" * 2001,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert any(
            e["field"] == "tech_stack" and e["reason"] == "length_constraint"
            for e in result["errors"]
        )

    def test_submit_stores_text_in_workspace(self, client, temp_workspace):
        """Verify text inputs are stored in workspace."""
        client.post(
            "/api/inputs/submit",
            data={
                "project_idea": "Build something great",
                "tech_stack": "Python, React",
            },
        )
        inputs_dir = temp_workspace / "inputs"
        assert (inputs_dir / "project_idea.txt").exists()
        assert (inputs_dir / "tech_stack.txt").exists()
        assert (inputs_dir / "project_idea.txt").read_text() == "Build something great"


class TestStatusEndpoint:
    """Tests for GET /api/inputs/status."""

    def test_status_initially_invalid(self, client, temp_workspace):
        """Status should be invalid when no inputs have been provided."""
        response = client.get("/api/inputs/status")
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_status_valid_after_all_inputs(self, client, temp_workspace):
        """Status should be valid after all required inputs are provided."""
        # Upload hackathon brief
        client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", b"Valid brief content here", "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        # Upload judging rubric
        client.post(
            "/api/inputs/upload",
            files={"file": ("rubric.txt", b"Valid rubric content here", "text/plain")},
            data={"field_name": "judging_rubric"},
        )
        # Submit text inputs
        client.post(
            "/api/inputs/submit",
            data={"project_idea": "Build an AI tool"},
        )
        # Check status
        response = client.get("/api/inputs/status")
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is True
        assert result["errors"] == []

    def test_status_reports_missing_fields(self, client, temp_workspace):
        """Status should report which required fields are missing."""
        # Only upload brief
        client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", b"Valid brief content", "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        response = client.get("/api/inputs/status")
        result = response.json()
        assert result["valid"] is False
        # Should report missing rubric and project idea
        fields_with_errors = [e["field"] for e in result["errors"]]
        assert "judging_rubric" in fields_with_errors
        assert "project_idea" in fields_with_errors


class TestTextExtraction:
    """Tests for text extraction from various file formats."""

    def test_extract_text_from_txt(self, client, temp_workspace):
        """TXT files should have their content directly extracted."""
        content = b"This is plain text content for the hackathon brief."
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.txt", content, "text/plain")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is True

    def test_extract_text_from_docx_format_detected_by_extension(self, client, temp_workspace):
        """DOCX files detected by extension even with generic content type."""
        # Not a valid DOCX, but testing format detection by extension
        content = b"Not actually a DOCX file"
        response = client.post(
            "/api/inputs/upload",
            files={"file": ("brief.docx", content, "application/octet-stream")},
            data={"field_name": "hackathon_brief"},
        )
        assert response.status_code == 200
        result = response.json()
        # Will fail text extraction since it's not a real DOCX
        assert result["valid"] is False
        assert any(e["reason"] == "unextractable_text" for e in result["errors"])

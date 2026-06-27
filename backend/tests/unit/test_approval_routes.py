"""Unit tests for the approval gate endpoints.

Tests the POST /api/workflow/approve and POST /api/workflow/request-change
endpoints to ensure they correctly update state and handle edge cases.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.approval import router, _get_state_manager, MAX_REVISION_CYCLES
from app.models.project_state import (
    AgentPhase,
    AgentStatus,
    ApprovalGateState,
    PhaseStatus,
    ProjectState,
)
from app.services.state_manager import StateManager


@pytest.fixture
def app():
    """Create a FastAPI test app with the approval router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def tmp_state_file(tmp_path):
    """Create a temporary state file with a pending approval gate."""
    state_file = tmp_path / "project_state.json"
    now = datetime.now(timezone.utc)

    state = ProjectState(
        phase=PhaseStatus.PLANNING,
        agents={
            "project_planner": AgentPhase(status=AgentStatus.COMPLETED),
            "judge_optimizer": AgentPhase(status=AgentStatus.COMPLETED),
            "backend_engineer": AgentPhase(status=AgentStatus.PENDING),
            "frontend_engineer": AgentPhase(status=AgentStatus.PENDING),
            "integration": AgentPhase(status=AgentStatus.PENDING),
            "qa": AgentPhase(status=AgentStatus.PENDING),
            "documentation": AgentPhase(status=AgentStatus.PENDING),
            "powerpoint": AgentPhase(status=AgentStatus.PENDING),
            "demo_video": AgentPhase(status=AgentStatus.PENDING),
            "github": AgentPhase(status=AgentStatus.PENDING),
        },
        approval_gates={
            1: ApprovalGateState(gate_number=1, pending=True),
            2: ApprovalGateState(gate_number=2, pending=False),
            3: ApprovalGateState(gate_number=3, pending=False),
        },
        created_at=now,
        updated_at=now,
    )

    state_file.write_text(state.model_dump_json(indent=2))
    return state_file


@pytest.fixture
def mock_state_manager(tmp_state_file):
    """Patch _get_state_manager to use a temporary state file."""
    sm = StateManager(state_file_path=tmp_state_file)
    with patch(
        "app.api.routes.approval._get_state_manager", return_value=sm
    ):
        yield sm


class TestApproveEndpoint:
    """Tests for POST /api/workflow/approve."""

    def test_approve_clears_pending_flag(self, client, mock_state_manager):
        """Approving a pending gate should clear the pending flag."""
        response = client.post(
            "/api/workflow/approve",
            json={"gate_number": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Gate 1 approved. Workflow will resume shortly."

        # Verify state was updated
        state = data["state"]
        gate_1 = state["approval_gates"]["1"]
        assert gate_1["pending"] is False

    def test_approve_non_pending_gate_returns_409(self, client, mock_state_manager):
        """Approving a gate that is not pending returns a conflict error."""
        response = client.post(
            "/api/workflow/approve",
            json={"gate_number": 2},
        )

        assert response.status_code == 409
        assert "not currently pending" in response.json()["detail"]

    def test_approve_invalid_gate_number(self, client, mock_state_manager):
        """Providing an invalid gate number returns a validation error."""
        response = client.post(
            "/api/workflow/approve",
            json={"gate_number": 4},
        )

        assert response.status_code == 422  # Pydantic validation error

    def test_approve_missing_gate_number(self, client, mock_state_manager):
        """Missing gate_number in request body returns validation error."""
        response = client.post(
            "/api/workflow/approve",
            json={},
        )

        assert response.status_code == 422


class TestRequestChangeEndpoint:
    """Tests for POST /api/workflow/request-change."""

    def test_request_change_increments_revision_count(
        self, client, mock_state_manager
    ):
        """Requesting a change should increment the revision counter."""
        response = client.post(
            "/api/workflow/request-change",
            json={
                "gate_number": 1,
                "feedback": "Please add more detail to the architecture.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        state = data["state"]
        gate_1 = state["approval_gates"]["1"]
        assert gate_1["revision_count"] == 1
        assert gate_1["feedback"] == "Please add more detail to the architecture."

    def test_request_change_clears_pending_for_revision_loop(
        self, client, mock_state_manager
    ):
        """After requesting a change, pending is cleared so the graph loops."""
        response = client.post(
            "/api/workflow/request-change",
            json={
                "gate_number": 1,
                "feedback": "Revise the timeline.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        state = data["state"]
        gate_1 = state["approval_gates"]["1"]
        assert gate_1["pending"] is False

    def test_request_change_non_pending_gate_returns_409(
        self, client, mock_state_manager
    ):
        """Requesting change on a non-pending gate returns a conflict error."""
        response = client.post(
            "/api/workflow/request-change",
            json={
                "gate_number": 2,
                "feedback": "Fix the tests.",
            },
        )

        assert response.status_code == 409

    def test_request_change_max_revisions_returns_422(
        self, client, mock_state_manager, tmp_state_file
    ):
        """After max revision cycles, further requests are rejected."""
        # Set revision_count to max
        import json as json_mod

        state_data = json_mod.loads(tmp_state_file.read_text())
        state_data["approval_gates"]["1"]["revision_count"] = MAX_REVISION_CYCLES
        tmp_state_file.write_text(json_mod.dumps(state_data, default=str))

        response = client.post(
            "/api/workflow/request-change",
            json={
                "gate_number": 1,
                "feedback": "One more change please.",
            },
        )

        assert response.status_code == 422
        assert "Maximum revision cycles" in response.json()["detail"]

    def test_request_change_empty_feedback_returns_422(
        self, client, mock_state_manager
    ):
        """Empty feedback string should be rejected by validation."""
        response = client.post(
            "/api/workflow/request-change",
            json={
                "gate_number": 1,
                "feedback": "",
            },
        )

        assert response.status_code == 422

    def test_request_change_message_includes_revision_count(
        self, client, mock_state_manager
    ):
        """The response message should show the current revision count."""
        response = client.post(
            "/api/workflow/request-change",
            json={
                "gate_number": 1,
                "feedback": "Add error handling.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert f"revision 1/{MAX_REVISION_CYCLES}" in data["message"]

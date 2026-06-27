"""Unit tests for conditional edge functions.

Tests the routing logic for LangGraph conditional edges used in the
orchestrator state graph.
"""

import pytest

from backend.app.orchestrator.edges import (
    MAX_QA_FIX_CYCLES,
    MAX_REVISION_CYCLES,
    route_after_approval,
    route_after_qa,
    route_to_next_phase,
)


def _make_state(**overrides) -> dict:
    """Create a base OrchestratorState with optional overrides."""
    base = {
        "phase": "planning",
        "agents_status": {},
        "approval_pending": False,
        "approval_gate": 1,
        "error": None,
        "revision_count": 0,
        "workspace_path": "/tmp/workspace",
        "config": {},
    }
    base.update(overrides)
    return base


class TestRouteAfterApproval:
    """Tests for route_after_approval edge function."""

    def test_returns_wait_when_approval_pending(self):
        state = _make_state(approval_pending=True, approval_gate=1)
        assert route_after_approval(state) == "wait"

    def test_returns_wait_when_pending_regardless_of_gate(self):
        for gate in [1, 2, 3]:
            state = _make_state(approval_pending=True, approval_gate=gate)
            assert route_after_approval(state) == "wait"

    def test_gate_1_approved_routes_to_parallel_development(self):
        state = _make_state(approval_pending=False, approval_gate=1)
        assert route_after_approval(state) == "parallel_development"

    def test_gate_2_approved_routes_to_parallel_delivery(self):
        state = _make_state(approval_pending=False, approval_gate=2)
        assert route_after_approval(state) == "parallel_delivery"

    def test_gate_3_approved_routes_to_complete(self):
        state = _make_state(approval_pending=False, approval_gate=3)
        assert route_after_approval(state) == "complete"

    def test_revision_at_gate_1_routes_to_architecture_design(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=1,
            agents_status={"gate_1_revision": "requested"},
            revision_count=1,
        )
        assert route_after_approval(state) == "architecture_design"

    def test_revision_at_gate_2_routes_to_qa_testing(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=2,
            agents_status={"gate_2_revision": "requested"},
            revision_count=2,
        )
        assert route_after_approval(state) == "qa_testing"

    def test_revision_at_gate_3_routes_to_parallel_delivery(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=3,
            agents_status={"gate_3_revision": "requested"},
            revision_count=1,
        )
        assert route_after_approval(state) == "parallel_delivery"

    def test_revision_with_generic_flag(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=1,
            agents_status={"revision": "requested"},
            revision_count=0,
        )
        assert route_after_approval(state) == "architecture_design"

    def test_max_revisions_escalates(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=1,
            agents_status={"gate_1_revision": "requested"},
            revision_count=MAX_REVISION_CYCLES,
        )
        assert route_after_approval(state) == "escalate"

    def test_exactly_at_max_revisions_escalates(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=2,
            agents_status={"gate_2_revision": "requested"},
            revision_count=5,
        )
        assert route_after_approval(state) == "escalate"

    def test_one_below_max_revisions_still_loops(self):
        state = _make_state(
            approval_pending=False,
            approval_gate=1,
            agents_status={"gate_1_revision": "requested"},
            revision_count=4,
        )
        assert route_after_approval(state) == "architecture_design"


class TestRouteAfterQA:
    """Tests for route_after_qa edge function."""

    def test_qa_completed_routes_to_approval_gate_2(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "completed"},
            approval_gate=2,
        )
        assert route_after_qa(state) == "approval_gate_2"

    def test_qa_failed_routes_to_parallel_development(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "failed"},
            revision_count=0,
        )
        assert route_after_qa(state) == "parallel_development"

    def test_qa_bugs_found_routes_to_parallel_development(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "in_progress", "qa_bugs": "found"},
            revision_count=1,
        )
        assert route_after_qa(state) == "parallel_development"

    def test_qa_critical_bugs_found_routes_to_parallel_development(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "in_progress", "qa_critical_bugs": "2"},
            revision_count=0,
        )
        assert route_after_qa(state) == "parallel_development"

    def test_qa_major_bugs_found_routes_to_parallel_development(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "in_progress", "qa_major_bugs": "3"},
            revision_count=1,
        )
        assert route_after_qa(state) == "parallel_development"

    def test_qa_max_fix_cycles_escalates(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "failed"},
            revision_count=MAX_QA_FIX_CYCLES,
        )
        assert route_after_qa(state) == "escalate"

    def test_qa_one_below_max_still_loops(self):
        state = _make_state(
            phase="development",
            agents_status={"qa": "failed"},
            revision_count=MAX_QA_FIX_CYCLES - 1,
        )
        assert route_after_qa(state) == "parallel_development"

    def test_qa_pending_routes_to_approval_gate_2(self):
        """Edge case: QA hasn't run yet, default to approval gate."""
        state = _make_state(
            phase="development",
            agents_status={"qa": "pending"},
        )
        assert route_after_qa(state) == "approval_gate_2"


class TestRouteToNextPhase:
    """Tests for route_to_next_phase edge function."""

    def test_planning_routes_to_approval_gate_1(self):
        state = _make_state(phase="planning")
        assert route_to_next_phase(state) == "approval_gate_1"

    def test_development_routes_to_integration(self):
        state = _make_state(phase="development")
        assert route_to_next_phase(state) == "integration"

    def test_delivery_routes_to_approval_gate_3(self):
        state = _make_state(phase="delivery")
        assert route_to_next_phase(state) == "approval_gate_3"

    def test_complete_routes_to_complete(self):
        state = _make_state(phase="complete")
        assert route_to_next_phase(state) == "complete"

    def test_unknown_phase_routes_to_escalate(self):
        state = _make_state(phase="unknown")
        assert route_to_next_phase(state) == "escalate"


class TestConstants:
    """Tests for module-level constants."""

    def test_max_revision_cycles_is_5(self):
        assert MAX_REVISION_CYCLES == 5

    def test_max_qa_fix_cycles_is_3(self):
        assert MAX_QA_FIX_CYCLES == 3

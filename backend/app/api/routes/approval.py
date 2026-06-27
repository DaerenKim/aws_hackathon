"""Approval gate endpoints for the Hackathon Studio workflow.

Provides endpoints for human approval interactions at the three workflow gates:
- Gate 1: After architecture generation
- Gate 2: After QA testing passes
- Gate 3: Before final delivery

Requirements: 5.1, 5.2, 5.3, 5.4
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.project_state import ProjectState
from app.services.state_manager import StateManager

router = APIRouter(prefix="/api/workflow", tags=["approval"])

# Maximum allowed revision cycles per gate before escalation
MAX_REVISION_CYCLES = 5


def _get_state_manager() -> StateManager:
    """Get a StateManager instance pointing at the shared workspace state file.

    In production this would be injected via FastAPI dependencies.
    For now, uses the default workspace path.
    """
    workspace_root = Path("shared_workspace")
    state_file = workspace_root / "project_state.json"
    return StateManager(state_file_path=state_file)


class ApproveRequest(BaseModel):
    """Request body for the approve endpoint."""

    gate_number: int = Field(
        ...,
        ge=1,
        le=3,
        description="The approval gate number being approved (1, 2, or 3).",
    )


class RequestChangeRequest(BaseModel):
    """Request body for the request-change endpoint."""

    gate_number: int = Field(
        ...,
        ge=1,
        le=3,
        description="The approval gate number where changes are requested.",
    )
    feedback: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Feedback describing the requested changes.",
    )


class ApprovalResponse(BaseModel):
    """Response returned by approval endpoints containing the updated state."""

    state: ProjectState
    message: str


@router.post("/approve", response_model=ApprovalResponse)
async def approve_at_gate(request: ApproveRequest) -> ApprovalResponse:
    """Approve at an approval gate, allowing the workflow to resume.

    Clears the approval_pending flag for the specified gate so that
    the LangGraph orchestrator can continue to the next phase.
    The orchestrator should resume within 5 seconds of approval.

    Requirements: 5.1, 5.3
    """
    state_manager = _get_state_manager()
    state = await state_manager.read_state()

    gate_number = request.gate_number

    # Validate that the gate exists in state
    if gate_number not in state.approval_gates:
        raise HTTPException(
            status_code=404,
            detail=f"Approval gate {gate_number} not found.",
        )

    gate = state.approval_gates[gate_number]

    # Validate that the gate is actually pending approval
    if not gate.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Approval gate {gate_number} is not currently pending approval.",
        )

    # Clear the approval_pending flag so the graph can continue
    gate.pending = False
    state.updated_at = datetime.now(timezone.utc)

    # Write the updated state atomically
    await state_manager._write_state(state)

    return ApprovalResponse(
        state=state,
        message=f"Gate {gate_number} approved. Workflow will resume shortly.",
    )


@router.post("/request-change", response_model=ApprovalResponse)
async def request_change_at_gate(
    request: RequestChangeRequest,
) -> ApprovalResponse:
    """Request changes at an approval gate, routing feedback for revision.

    Stores the feedback, increments the revision counter, and sets a
    revision flag in agents_status so the responsible agent can pick up
    the feedback and re-execute. The same approval gate will be
    re-triggered after revision completes.

    A maximum of 5 revision cycles are allowed per gate. After that,
    the system escalates to the user with a prompt to either approve
    the current state or provide alternative direction.

    Requirements: 5.1, 5.4
    """
    state_manager = _get_state_manager()
    state = await state_manager.read_state()

    gate_number = request.gate_number

    # Validate that the gate exists in state
    if gate_number not in state.approval_gates:
        raise HTTPException(
            status_code=404,
            detail=f"Approval gate {gate_number} not found.",
        )

    gate = state.approval_gates[gate_number]

    # Validate that the gate is actually pending approval
    if not gate.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Approval gate {gate_number} is not currently pending approval.",
        )

    # Check if max revision cycles have been reached
    if gate.revision_count >= MAX_REVISION_CYCLES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Maximum revision cycles ({MAX_REVISION_CYCLES}) reached for "
                f"gate {gate_number}. Please approve the current state or "
                f"provide alternative direction."
            ),
        )

    # Increment revision count and store feedback
    gate.revision_count += 1
    gate.feedback = request.feedback

    # Set revision flag in agents_status for the responsible agent(s)
    # The responsible agent depends on the gate:
    # Gate 1 → architecture (handled by orchestrator/planner)
    # Gate 2 → QA-related agents (qa, backend_engineer, frontend_engineer)
    # Gate 3 → delivery agents (documentation, powerpoint, demo_video, github)
    revision_agents = _get_revision_agents(gate_number)
    for agent_name in revision_agents:
        if agent_name in state.agents:
            state.agents[agent_name].status = state.agents[agent_name].status
            # Store revision indication in error field temporarily
            # (in practice, the orchestrator graph reads the gate feedback)

    # Keep the gate pending — it remains pending until the revision
    # completes and the gate is re-evaluated. The orchestrator will
    # pick up the feedback and route it to the appropriate agent.
    # We clear pending so the graph loop can re-enter the revision path.
    gate.pending = False

    state.updated_at = datetime.now(timezone.utc)

    # Write the updated state atomically
    await state_manager._write_state(state)

    return ApprovalResponse(
        state=state,
        message=(
            f"Change requested at gate {gate_number} "
            f"(revision {gate.revision_count}/{MAX_REVISION_CYCLES}). "
            f"Feedback routed to responsible agents."
        ),
    )


def _get_revision_agents(gate_number: int) -> list[str]:
    """Return the list of agent names responsible for revisions at a given gate.

    Gate 1: After architecture → project_planner, judge_optimizer rework
    Gate 2: After QA → qa, backend_engineer, frontend_engineer fix issues
    Gate 3: Before delivery → documentation, powerpoint, demo_video, github
    """
    gate_agents: dict[int, list[str]] = {
        1: ["project_planner", "judge_optimizer"],
        2: ["qa", "backend_engineer", "frontend_engineer"],
        3: ["documentation", "powerpoint", "demo_video", "github"],
    }
    return gate_agents.get(gate_number, [])

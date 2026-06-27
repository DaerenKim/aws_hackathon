"""Workflow control endpoints for the Hackathon Studio orchestrator.

Provides endpoints to start the orchestration pipeline and query the
current project state.

Requirements covered:
- 5.1: Approval gates triggered during workflow execution
- 14.1: Orchestrator maintains project state (readable via /state endpoint)
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.orchestrator.graph import build_orchestrator_graph, get_initial_state
from app.services.state_manager import StateManager

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# Default workspace path — configurable via environment in production
WORKSPACE_PATH = Path("workspace")
STATE_FILE_PATH = WORKSPACE_PATH / "project_state.json"


class WorkflowStartResponse(BaseModel):
    """Response returned immediately when the workflow is started."""

    status: str
    message: str


class WorkflowStateResponse(BaseModel):
    """Response containing the current project state."""

    phase: str
    agents: dict
    approval_gates: dict
    created_at: str
    updated_at: str


async def _run_orchestrator(workspace_path: str, config: dict | None = None) -> None:
    """Execute the compiled orchestrator graph as a background task.

    This function is invoked via FastAPI BackgroundTasks so the /start
    endpoint can return immediately while the pipeline runs.

    Args:
        workspace_path: Absolute path to the shared workspace directory.
        config: Optional configuration overrides for the orchestrator.
    """
    graph = build_orchestrator_graph()
    initial_state = get_initial_state(workspace_path, config)
    await graph.ainvoke(initial_state)


@router.post("/start", response_model=WorkflowStartResponse)
async def start_workflow(background_tasks: BackgroundTasks) -> WorkflowStartResponse:
    """Start the orchestration pipeline.

    Launches the compiled LangGraph state graph execution as a background
    task and returns immediately with a status response. The graph will
    run through all phases (Planning → Development → Delivery) with
    approval gates pausing execution at configured checkpoints.

    Returns:
        WorkflowStartResponse with status indicating the pipeline was launched.
    """
    workspace_path = str(WORKSPACE_PATH.resolve())

    # Ensure workspace directory exists
    WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)

    background_tasks.add_task(_run_orchestrator, workspace_path)

    return WorkflowStartResponse(
        status="started",
        message="Orchestration pipeline launched in background.",
    )


@router.get("/state", response_model=WorkflowStateResponse)
async def get_workflow_state() -> WorkflowStateResponse:
    """Return the current project state.

    Reads project_state.json via the StateManager service to provide
    the current workflow phase, all agent statuses, and approval gate states.

    Returns:
        WorkflowStateResponse with the full current project state.

    Raises:
        HTTPException: If the state file cannot be read.
    """
    state_manager = StateManager(STATE_FILE_PATH)

    try:
        state = await state_manager.read_state()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read project state: {str(e)}",
        )

    return WorkflowStateResponse(
        phase=state.phase.value,
        agents={
            name: {
                "status": agent_phase.status.value,
                "started_at": agent_phase.started_at.isoformat() if agent_phase.started_at else None,
                "completed_at": agent_phase.completed_at.isoformat() if agent_phase.completed_at else None,
                "error": agent_phase.error,
            }
            for name, agent_phase in state.agents.items()
        },
        approval_gates={
            str(gate_num): {
                "gate_number": gate.gate_number,
                "pending": gate.pending,
                "revision_count": gate.revision_count,
                "feedback": gate.feedback,
            }
            for gate_num, gate in state.approval_gates.items()
        },
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
    )

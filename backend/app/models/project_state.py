"""Pydantic models for project state tracking.

Defines the schema for project_state.json which serves as the single
source of truth for all agent statuses and workflow phase progression.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class AgentStatus(str, Enum):
    """Status of an individual agent's execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PhaseStatus(str, Enum):
    """Current workflow phase of the orchestrator."""

    PLANNING = "planning"
    DEVELOPMENT = "development"
    DELIVERY = "delivery"
    COMPLETE = "complete"


class AgentPhase(BaseModel):
    """Tracks the execution state of a single agent."""

    status: AgentStatus = AgentStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class ApprovalGateState(BaseModel):
    """Tracks the state of a human approval gate."""

    gate_number: int
    pending: bool = False
    revision_count: int = 0
    feedback: str | None = None


class ProjectState(BaseModel):
    """Complete project state persisted to project_state.json.

    This is the single source of truth for the orchestrator, tracking
    which phase the project is in, each agent's status, and approval gate states.
    """

    phase: PhaseStatus
    agents: dict[str, AgentPhase]
    approval_gates: dict[int, ApprovalGateState]
    created_at: datetime
    updated_at: datetime

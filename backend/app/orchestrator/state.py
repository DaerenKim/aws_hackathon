"""LangGraph state schema for the Hackathon Studio orchestrator.

This module defines the OrchestratorState TypedDict which serves as the
state schema for the LangGraph StateGraph. The state is passed between
graph nodes and updated as agents execute through the workflow phases.
"""

from typing import TypedDict


class OrchestratorState(TypedDict):
    """State schema for the LangGraph orchestrator state graph.

    This TypedDict defines the shape of state that flows through the
    LangGraph StateGraph. Each node function receives and returns this
    state, enabling coordinated agent execution across phases.

    Attributes:
        phase: Current workflow phase - one of "planning", "development",
            "delivery", or "complete".
        agents_status: Maps agent name to its current status string
            (e.g. "pending", "in_progress", "completed", "failed").
        approval_pending: Whether an approval gate is currently active
            and awaiting human response.
        approval_gate: Current gate number (1, 2, or 3). Gate 1 follows
            architecture design, gate 2 follows QA, gate 3 follows delivery.
        error: Error message if the workflow has failed, None otherwise.
        revision_count: Number of revision requests at the current approval
            gate. Maximum of 5 before escalation to the user.
        workspace_path: Absolute path to the shared workspace directory
            where all agents read and write artifacts.
        config: Configuration overrides including model name, timeouts,
            and other runtime parameters.
    """

    phase: str
    agents_status: dict[str, str]
    approval_pending: bool
    approval_gate: int
    error: str | None
    revision_count: int
    workspace_path: str
    config: dict

"""Conditional edge functions for the LangGraph orchestrator.

These functions are used by LangGraph's add_conditional_edges() to determine
which node to transition to based on the current state. Each function receives
the OrchestratorState and returns a string node name.

Requirements covered:
- 5.1: Approval gate pauses execution
- 5.3: Resume execution on approval within 5s
- 5.4: Max 5 revision cycles per gate with escalation
- 9.5: Route critical/major bugs to responsible agents
- 9.6: Trigger approval gate 2 when QA passes
- 9.7: Halt after 3 QA fix cycles if unresolved
"""

from backend.app.orchestrator.state import OrchestratorState

# Maximum revision cycles allowed per approval gate before escalation
MAX_REVISION_CYCLES = 5

# Maximum QA bug-fix cycles before halting
MAX_QA_FIX_CYCLES = 3


def route_after_approval(state: OrchestratorState) -> str:
    """Route after an approval gate based on user response.

    Determines the next node after an approval gate checkpoint.
    Three outcomes:
    - User hasn't responded yet → stay waiting
    - User approved → advance to next phase
    - User requested revision → loop back (with cycle limit)

    Args:
        state: Current orchestrator state.

    Returns:
        String node name for LangGraph routing:
        - "wait": Approval still pending
        - "parallel_development": Gate 1 approved, start dev phase
        - "parallel_delivery": Gate 2 approved, start delivery phase
        - "complete": Gate 3 approved, workflow done
        - "escalate": Max revision cycles exceeded
        - Previous node name: Revision requested, re-execute
    """
    # If approval is still pending, stay paused
    if state["approval_pending"]:
        return "wait"

    # Check if a revision was requested
    revision_requested = _is_revision_requested(state)

    if revision_requested:
        # Increment and check revision count
        revision_count = state["revision_count"]

        if revision_count >= MAX_REVISION_CYCLES:
            return "escalate"

        # Route back to the appropriate node for revision based on gate
        gate = state["approval_gate"]
        if gate == 1:
            return "architecture_design"
        elif gate == 2:
            return "qa_testing"
        elif gate == 3:
            return "parallel_delivery"
        return "escalate"

    # User approved — route to next phase based on current gate
    gate = state["approval_gate"]

    if gate == 1:
        return "parallel_development"
    elif gate == 2:
        return "parallel_delivery"
    elif gate == 3:
        return "complete"

    # Fallback for unexpected gate values
    return "escalate"


def route_after_qa(state: OrchestratorState) -> str:
    """Route after QA testing based on test results.

    Determines next step after QA agent completes:
    - All tests pass (no critical/major bugs) → approval gate 2
    - Bugs found → route back to development for fixes
    - Max fix cycles exceeded → halt/escalate

    Args:
        state: Current orchestrator state.

    Returns:
        String node name for LangGraph routing:
        - "approval_gate_2": QA passed, proceed to gate 2
        - "parallel_development": Bugs found, fix and retest
        - "escalate": Max QA fix cycles exceeded
    """
    qa_status = state["agents_status"].get("qa", "pending")

    # Check if QA completed successfully (no critical/major bugs)
    if qa_status == "completed":
        return "approval_gate_2"

    # Check if QA found bugs that need fixing
    if qa_status == "failed" or _has_bugs_found(state):
        # Check if we've exceeded max QA fix cycles
        revision_count = state["revision_count"]
        if revision_count >= MAX_QA_FIX_CYCLES:
            return "escalate"

        # Route back to development for bug fixes
        return "parallel_development"

    # QA is still in progress or pending — shouldn't normally reach here
    # but handle gracefully
    return "approval_gate_2"


def route_to_next_phase(state: OrchestratorState) -> str:
    """General routing based on current workflow phase.

    Routes to the appropriate next step based on the current phase.
    Used for sequential transitions between major workflow phases.

    Args:
        state: Current orchestrator state.

    Returns:
        String node name for LangGraph routing:
        - "approval_gate_1": After planning phase completes
        - "integration": After development phase completes
        - "approval_gate_3": After delivery phase completes
        - "complete": Already in complete phase
    """
    phase = state["phase"]

    if phase == "planning":
        return "approval_gate_1"
    elif phase == "development":
        return "integration"
    elif phase == "delivery":
        return "approval_gate_3"
    elif phase == "complete":
        return "complete"

    # Fallback
    return "escalate"


def _is_revision_requested(state: OrchestratorState) -> bool:
    """Check if a revision was requested at the current approval gate.

    Looks for a revision flag in the agents_status dict. The approval
    gate handler sets this when the user requests changes.

    Args:
        state: Current orchestrator state.

    Returns:
        True if revision was requested, False otherwise.
    """
    agents_status = state["agents_status"]

    # Check for explicit revision flag set by approval gate handler
    revision_key = f"gate_{state['approval_gate']}_revision"
    if agents_status.get(revision_key) == "requested":
        return True

    # Also check for a generic revision indicator
    if agents_status.get("revision") == "requested":
        return True

    return False


def _has_bugs_found(state: OrchestratorState) -> bool:
    """Check if QA agent found critical or major bugs.

    Inspects the agents_status for QA bug indicators that signal
    the need to loop back to development for fixes.

    Args:
        state: Current orchestrator state.

    Returns:
        True if bugs were found requiring fixes, False otherwise.
    """
    agents_status = state["agents_status"]

    # Check for explicit bugs-found flag set by QA node
    if agents_status.get("qa_bugs") == "found":
        return True

    # Check for bug severity indicators
    if agents_status.get("qa_critical_bugs", "0") != "0":
        return True
    if agents_status.get("qa_major_bugs", "0") != "0":
        return True

    return False

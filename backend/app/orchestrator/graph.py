"""LangGraph state graph definition for the Hackathon Studio orchestrator.

Wires all node functions and conditional edges into a compiled StateGraph
that drives the multi-agent workflow through Planning → Development → Delivery
phases with approval gates at critical milestones.

Requirements covered:
- 5.5: Three approval gates enforced
- 14.1: Orchestrator maintains project state through graph execution
- 14.2: Parallel execution for backend + frontend (Development phase)
- 14.3: Parallel execution for delivery agents (Delivery phase)
"""

from langgraph.graph import END, StateGraph

from app.orchestrator.edges import (
    route_after_approval,
    route_after_qa,
)
from app.orchestrator.nodes import (
    handle_approval_gate,
    run_architecture_design,
    run_integration,
    run_judge_optimizer,
    run_parallel_delivery,
    run_parallel_development,
    run_project_planner,
    run_qa,
)
from app.orchestrator.state import OrchestratorState


def build_orchestrator_graph():
    """Build and compile the LangGraph state graph for the orchestrator.

    Creates a StateGraph with all workflow nodes and conditional edges,
    representing the full hackathon studio pipeline:

    project_planning → judge_optimization → architecture_design →
    approval_gate_1 → [conditional] → parallel_development →
    integration → qa_testing → [conditional] → approval_gate_2 →
    [conditional] → parallel_delivery → approval_gate_3 →
    [conditional] → END

    Returns:
        CompiledGraph: The compiled LangGraph state graph ready for execution.
    """
    # Create the state graph with OrchestratorState as the state schema
    graph = StateGraph(OrchestratorState)

    # --- Add all nodes ---
    graph.add_node("project_planning", run_project_planner)
    graph.add_node("judge_optimization", run_judge_optimizer)
    graph.add_node("architecture_design", run_architecture_design)
    graph.add_node("approval_gate_1", _approval_gate_1)
    graph.add_node("parallel_development", run_parallel_development)
    graph.add_node("integration", run_integration)
    graph.add_node("qa_testing", run_qa)
    graph.add_node("approval_gate_2", _approval_gate_2)
    graph.add_node("parallel_delivery", run_parallel_delivery)
    graph.add_node("approval_gate_3", _approval_gate_3)

    # --- Add sequential edges ---
    graph.add_edge("project_planning", "judge_optimization")
    graph.add_edge("judge_optimization", "architecture_design")
    graph.add_edge("architecture_design", "approval_gate_1")

    # --- Conditional edge after approval gate 1 ---
    # Routes to: parallel_development (approved), architecture_design (revision), or END (escalate)
    graph.add_conditional_edges(
        "approval_gate_1",
        route_after_approval,
        {
            "parallel_development": "parallel_development",
            "architecture_design": "architecture_design",
            "escalate": END,
            "wait": "approval_gate_1",
        },
    )

    # --- Sequential edges through development phase ---
    graph.add_edge("parallel_development", "integration")
    graph.add_edge("integration", "qa_testing")

    # --- Conditional edge after QA testing ---
    # Routes to: approval_gate_2 (pass), parallel_development (bugs), or END (escalate)
    graph.add_conditional_edges(
        "qa_testing",
        route_after_qa,
        {
            "approval_gate_2": "approval_gate_2",
            "parallel_development": "parallel_development",
            "escalate": END,
        },
    )

    # --- Conditional edge after approval gate 2 ---
    # Routes to: parallel_delivery (approved), qa_testing (revision), or END (escalate)
    graph.add_conditional_edges(
        "approval_gate_2",
        route_after_approval,
        {
            "parallel_delivery": "parallel_delivery",
            "qa_testing": "qa_testing",
            "escalate": END,
            "wait": "approval_gate_2",
        },
    )

    # --- Sequential edge from delivery to gate 3 ---
    graph.add_edge("parallel_delivery", "approval_gate_3")

    # --- Conditional edge after approval gate 3 ---
    # Routes to: END (approved/complete), parallel_delivery (revision), or END (escalate)
    graph.add_conditional_edges(
        "approval_gate_3",
        route_after_approval,
        {
            "complete": END,
            "parallel_delivery": "parallel_delivery",
            "escalate": END,
            "wait": "approval_gate_3",
        },
    )

    # --- Set entry point ---
    graph.set_entry_point("project_planning")

    # --- Compile and return ---
    return graph.compile()


async def _approval_gate_1(state: OrchestratorState) -> OrchestratorState:
    """Approval gate 1 node wrapper — sets gate number to 1.

    Triggered after architecture design completes. Presents architecture.md
    and roadmap.md for human review.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated state with approval gate 1 active.
    """
    state["approval_gate"] = 1
    return await handle_approval_gate(state)


async def _approval_gate_2(state: OrchestratorState) -> OrchestratorState:
    """Approval gate 2 node wrapper — sets gate number to 2.

    Triggered after QA testing passes. Presents testing_report.md
    for human review.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated state with approval gate 2 active.
    """
    state["approval_gate"] = 2
    return await handle_approval_gate(state)


async def _approval_gate_3(state: OrchestratorState) -> OrchestratorState:
    """Approval gate 3 node wrapper — sets gate number to 3.

    Triggered after all delivery agents complete. Presents the repository
    URL and all final deliverables for human review.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated state with approval gate 3 active.
    """
    state["approval_gate"] = 3
    return await handle_approval_gate(state)


def get_initial_state(workspace_path: str, config: dict | None = None) -> OrchestratorState:
    """Create a valid initial OrchestratorState for starting a workflow run.

    This convenience function provides a properly initialized state dict
    that can be passed to the compiled graph's invoke/ainvoke method.

    Args:
        workspace_path: Absolute path to the shared workspace directory.
        config: Optional configuration overrides (model name, timeouts, etc.).

    Returns:
        OrchestratorState: A fully initialized state dictionary ready for
            graph execution.
    """
    return OrchestratorState(
        phase="planning",
        agents_status={
            "project_planner": "pending",
            "judge_optimizer": "pending",
            "architecture_design": "pending",
            "backend_engineer": "pending",
            "frontend_engineer": "pending",
            "integration": "pending",
            "qa": "pending",
            "documentation": "pending",
            "powerpoint": "pending",
            "demo_video": "pending",
            "github": "pending",
        },
        approval_pending=False,
        approval_gate=0,
        error=None,
        revision_count=0,
        workspace_path=workspace_path,
        config=config or {},
    )

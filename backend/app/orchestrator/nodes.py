"""LangGraph node functions for the Hackathon Studio orchestrator.

Each node function takes an OrchestratorState, instantiates the
appropriate agent(s), executes them, and returns the updated state.
Parallel nodes use asyncio.gather for concurrent agent execution.

Requirements: 14.1, 14.2, 14.3
"""

import asyncio
import logging
from pathlib import Path

from app.models.artifacts import OllamaConfig
from app.orchestrator.state import OrchestratorState
from app.services.ollama_client import OllamaClient
from app.services.state_manager import StateManager
from app.services.workspace import WorkspaceService

logger = logging.getLogger(__name__)


def _create_services(
    state: OrchestratorState,
) -> tuple[OllamaClient, WorkspaceService, StateManager]:
    """Create shared service instances from orchestrator state.

    Args:
        state: Current orchestrator state containing workspace_path and config.

    Returns:
        Tuple of (OllamaClient, WorkspaceService, StateManager).
    """
    workspace_path = Path(state["workspace_path"])
    config = state.get("config", {})

    # Build OllamaConfig from state config overrides
    ollama_config = OllamaConfig(
        base_url=config.get("ollama_base_url", "http://localhost:11434"),
        model=config.get("model", "llama3"),
        timeout_seconds=config.get("timeout_seconds", 120.0),
        max_retries=config.get("max_retries", 3),
        retry_delay_seconds=config.get("retry_delay_seconds", 2.0),
        temperature=config.get("temperature", 0.7),
    )

    ollama_client = OllamaClient(config=ollama_config)
    workspace = WorkspaceService(workspace_root=workspace_path)
    state_manager = StateManager(
        state_file_path=workspace_path / "project_state.json"
    )

    return ollama_client, workspace, state_manager


async def run_project_planner(state: OrchestratorState) -> OrchestratorState:
    """Execute the Project Planner Agent node.

    Instantiates ProjectPlannerAgent, runs it to produce project_spec.md,
    and updates the orchestrator state with the result.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with project_planner status.
    """
    from app.agents.project_planner import ProjectPlannerAgent

    ollama_client, workspace, state_manager = _create_services(state)

    agent = ProjectPlannerAgent(
        agent_name="project_planner",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )

    try:
        result = await agent.run({})
        state["agents_status"]["project_planner"] = (
            "completed" if result.success else "failed"
        )
        if not result.success:
            state["error"] = result.error
    except Exception as e:
        logger.error("Project planner node failed: %s", e, exc_info=True)
        state["agents_status"]["project_planner"] = "failed"
        state["error"] = f"Project planner failed: {str(e)}"

    return state


async def run_judge_optimizer(state: OrchestratorState) -> OrchestratorState:
    """Execute the Judge Optimizer Agent node.

    Instantiates JudgeOptimizerAgent, runs it to produce judge_analysis.md,
    and updates the orchestrator state with the result.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with judge_optimizer status.
    """
    from app.agents.judge_optimizer import JudgeOptimizerAgent

    ollama_client, workspace, state_manager = _create_services(state)

    agent = JudgeOptimizerAgent(
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )

    try:
        result = await agent.run({})
        state["agents_status"]["judge_optimizer"] = (
            "completed" if result.success else "failed"
        )
        if not result.success:
            state["error"] = result.error
    except Exception as e:
        logger.error("Judge optimizer node failed: %s", e, exc_info=True)
        state["agents_status"]["judge_optimizer"] = "failed"
        state["error"] = f"Judge optimizer failed: {str(e)}"

    return state


async def run_architecture_design(state: OrchestratorState) -> OrchestratorState:
    """Execute the Architecture Design node.

    Uses the LLM (OllamaClient) directly to generate architecture.md and
    roadmap.md based on the optimized project plan, then writes them to
    the workspace.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with architecture design status.
    """
    ollama_client, workspace, state_manager = _create_services(state)

    try:
        # Read prerequisite artifacts
        project_spec = await workspace.read_file("project_spec.md")
        judge_analysis = await workspace.read_file("judge_analysis.md")

        tech_stack = ""
        if await workspace.file_exists("inputs/tech_stack.txt"):
            tech_stack = await workspace.read_file("inputs/tech_stack.txt")

        # Generate architecture.md
        arch_prompt = _build_architecture_prompt(
            project_spec=project_spec,
            judge_analysis=judge_analysis,
            tech_stack=tech_stack,
        )
        arch_system = (
            "You are a senior software architect. Generate a detailed technical "
            "architecture specification in Markdown. Include system diagrams "
            "(text-based), folder structure, API endpoints, database schema, "
            "component hierarchy, and integration points."
        )
        architecture_md = await ollama_client.generate(
            arch_prompt, system=arch_system
        )
        await workspace.write_file("architecture.md", architecture_md, agent_name=None)

        # Generate roadmap.md
        roadmap_prompt = _build_roadmap_prompt(
            project_spec=project_spec,
            architecture_md=architecture_md,
        )
        roadmap_system = (
            "You are a project manager. Generate an ordered task breakdown "
            "with agent assignments, dependency graph, and phased execution plan."
        )
        roadmap_md = await ollama_client.generate(
            roadmap_prompt, system=roadmap_system
        )
        await workspace.write_file("roadmap.md", roadmap_md, agent_name=None)

        # Validate outputs are non-empty
        if not architecture_md.strip() or not roadmap_md.strip():
            state["agents_status"]["architecture_design"] = "failed"
            state["error"] = (
                "Architecture generation produced empty output"
            )
            return state

        # Update state
        state["agents_status"]["architecture_design"] = "completed"
        state["phase"] = "planning"

    except Exception as e:
        logger.error("Architecture design node failed: %s", e, exc_info=True)
        state["agents_status"]["architecture_design"] = "failed"
        state["error"] = f"Architecture design failed: {str(e)}"

    return state


async def handle_approval_gate(state: OrchestratorState) -> OrchestratorState:
    """Handle an approval gate checkpoint.

    Sets approval_pending to True and updates the current approval gate
    number. The workflow will pause here until a human approves or
    requests changes via the API.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with approval_pending set.
    """
    # Determine which gate we're at based on current phase and progress
    gate_number = state.get("approval_gate", 1)

    # Set the gate as pending
    state["approval_pending"] = True
    state["approval_gate"] = gate_number

    logger.info("Approval gate %d activated. Awaiting human approval.", gate_number)

    return state


async def run_parallel_development(state: OrchestratorState) -> OrchestratorState:
    """Execute Backend and Frontend Engineer agents in parallel.

    Uses asyncio.gather to run both agents concurrently. Failure of one
    agent does not block the other from completing (fault isolation).

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with both agents' statuses.
    """
    from app.agents.backend_engineer import BackendEngineerAgent
    from app.agents.frontend_engineer import FrontendEngineerAgent

    ollama_client, workspace, state_manager = _create_services(state)

    backend_agent = BackendEngineerAgent(
        agent_name="backend_engineer",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )
    frontend_agent = FrontendEngineerAgent(
        agent_name="frontend_engineer",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )

    # Run both agents in parallel with fault isolation
    results = await asyncio.gather(
        backend_agent.run({}),
        frontend_agent.run({}),
        return_exceptions=True,
    )

    backend_result, frontend_result = results

    # Process backend result
    if isinstance(backend_result, Exception):
        logger.error("Backend engineer raised exception: %s", backend_result)
        state["agents_status"]["backend_engineer"] = "failed"
        state["error"] = f"Backend engineer failed: {str(backend_result)}"
    else:
        state["agents_status"]["backend_engineer"] = (
            "completed" if backend_result.success else "failed"
        )
        if not backend_result.success and not state.get("error"):
            state["error"] = backend_result.error

    # Process frontend result
    if isinstance(frontend_result, Exception):
        logger.error("Frontend engineer raised exception: %s", frontend_result)
        state["agents_status"]["frontend_engineer"] = "failed"
        if not state.get("error"):
            state["error"] = f"Frontend engineer failed: {str(frontend_result)}"
    else:
        state["agents_status"]["frontend_engineer"] = (
            "completed" if frontend_result.success else "failed"
        )
        if not frontend_result.success and not state.get("error"):
            state["error"] = frontend_result.error

    # Update phase
    state["phase"] = "development"

    return state


async def run_integration(state: OrchestratorState) -> OrchestratorState:
    """Execute the Integration Agent node.

    Instantiates IntegrationAgent to connect frontend and backend,
    resolve conflicts, and verify end-to-end connectivity.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with integration status.
    """
    from app.agents.integration import IntegrationAgent

    ollama_client, workspace, state_manager = _create_services(state)

    agent = IntegrationAgent(
        agent_name="integration",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )

    try:
        result = await agent.run({})
        state["agents_status"]["integration"] = (
            "completed" if result.success else "failed"
        )
        if not result.success:
            state["error"] = result.error
    except Exception as e:
        logger.error("Integration node failed: %s", e, exc_info=True)
        state["agents_status"]["integration"] = "failed"
        state["error"] = f"Integration failed: {str(e)}"

    return state


async def run_qa(state: OrchestratorState) -> OrchestratorState:
    """Execute the QA Agent node.

    Instantiates QAAgent to run tests, produce testing_report.md,
    and report any bugs found.

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with QA status.
    """
    from app.agents.qa import QAAgent

    ollama_client, workspace, state_manager = _create_services(state)

    agent = QAAgent(
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )

    try:
        result = await agent.run({})
        state["agents_status"]["qa"] = (
            "completed" if result.success else "failed"
        )
        if not result.success:
            state["error"] = result.error
    except Exception as e:
        logger.error("QA node failed: %s", e, exc_info=True)
        state["agents_status"]["qa"] = "failed"
        state["error"] = f"QA failed: {str(e)}"

    return state


async def run_parallel_delivery(state: OrchestratorState) -> OrchestratorState:
    """Execute all Delivery phase agents in parallel.

    Uses asyncio.gather to run Documentation, PowerPoint, Demo Video,
    and GitHub agents concurrently. Failure of one agent does not block
    the others from completing (fault isolation).

    Args:
        state: Current orchestrator state.

    Returns:
        Updated orchestrator state with all delivery agents' statuses.
    """
    from app.agents.demo_video import DemoVideoAgent
    from app.agents.documentation import DocumentationAgent
    from app.agents.github import GitHubAgent
    from app.agents.powerpoint import PowerPointAgent

    ollama_client, workspace, state_manager = _create_services(state)

    doc_agent = DocumentationAgent(
        agent_name="documentation",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )
    ppt_agent = PowerPointAgent(
        agent_name="powerpoint",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )
    video_agent = DemoVideoAgent(
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )
    github_agent = GitHubAgent(
        agent_name="github",
        ollama_client=ollama_client,
        workspace=workspace,
        state_manager=state_manager,
    )

    # Run all delivery agents in parallel with fault isolation
    results = await asyncio.gather(
        doc_agent.run({}),
        ppt_agent.run({}),
        video_agent.run({}),
        github_agent.run({}),
        return_exceptions=True,
    )

    agent_names = ["documentation", "powerpoint", "demo_video", "github"]

    for agent_name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            logger.error("%s raised exception: %s", agent_name, result)
            state["agents_status"][agent_name] = "failed"
            if not state.get("error"):
                state["error"] = f"{agent_name} failed: {str(result)}"
        else:
            state["agents_status"][agent_name] = (
                "completed" if result.success else "failed"
            )
            if not result.success and not state.get("error"):
                state["error"] = result.error

    # Update phase
    state["phase"] = "delivery"

    return state


def _build_architecture_prompt(
    project_spec: str,
    judge_analysis: str,
    tech_stack: str,
) -> str:
    """Build the LLM prompt for architecture.md generation.

    Args:
        project_spec: Contents of project_spec.md.
        judge_analysis: Contents of judge_analysis.md.
        tech_stack: Preferred tech stack text (may be empty).

    Returns:
        Formatted prompt string.
    """
    parts = [
        "Generate a complete architecture specification in Markdown format.",
        "",
        "The specification MUST contain ALL of these sections:",
        "- ## System Diagram (text-based diagram notation, e.g. ASCII or Mermaid)",
        "- ## Folder Structure (directory names with purpose annotations)",
        "- ## API Endpoints (HTTP method, path, request/response structure for each)",
        "- ## Database Schema (tables, columns, relationships)",
        "- ## Component Hierarchy (UI components mapped to pages)",
        "- ## Integration Points (service-to-service connections with protocols)",
        "",
        "RULES:",
        "- Only reference technologies from the preferred tech stack or project spec.",
        "- Design for a hackathon MVP: keep it simple and buildable quickly.",
        "- API endpoints must be RESTful with clear request/response schemas.",
        "",
        "--- PROJECT SPECIFICATION ---",
        project_spec,
        "",
        "--- JUDGE ANALYSIS ---",
        judge_analysis,
        "",
    ]

    if tech_stack:
        parts.extend([
            "--- PREFERRED TECHNOLOGY STACK ---",
            tech_stack,
            "",
        ])

    parts.append("Generate the architecture specification now.")
    return "\n".join(parts)


def _build_roadmap_prompt(project_spec: str, architecture_md: str) -> str:
    """Build the LLM prompt for roadmap.md generation.

    Args:
        project_spec: Contents of project_spec.md.
        architecture_md: Contents of the generated architecture.md.

    Returns:
        Formatted prompt string.
    """
    return "\n".join([
        "Generate a project roadmap in Markdown format.",
        "",
        "The roadmap MUST contain:",
        "- ## Task Breakdown (ordered list, each task assigned to one agent)",
        "- ## Dependency Graph (which tasks must complete before others begin)",
        "- ## Completion Phases (phases with included tasks and approval gates)",
        "",
        "Available agents:",
        "- project_planner, judge_optimizer (Planning phase)",
        "- backend_engineer, frontend_engineer (Development phase, run in parallel)",
        "- integration (after backend + frontend complete)",
        "- qa (after integration)",
        "- documentation, powerpoint, demo_video, github (Delivery phase, run in parallel)",
        "",
        "Approval Gates:",
        "- Gate 1: After architecture design (before development starts)",
        "- Gate 2: After QA passes (before delivery starts)",
        "- Gate 3: After delivery completes (before final submission)",
        "",
        "--- PROJECT SPECIFICATION ---",
        project_spec,
        "",
        "--- ARCHITECTURE ---",
        architecture_md,
        "",
        "Generate the roadmap now.",
    ])

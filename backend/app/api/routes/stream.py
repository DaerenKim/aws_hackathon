"""SSE streaming endpoints for real-time state changes and agent logs.

Provides Server-Sent Events (SSE) endpoints that the frontend dashboard
connects to for live updates on project state and agent log output.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.models.project_state import ProjectState
from app.services.state_manager import StateManager

router = APIRouter(prefix="/api/stream", tags=["streaming"])

# Default workspace and state file paths (overridable via dependency injection)
DEFAULT_WORKSPACE_ROOT = Path("shared_workspace")
DEFAULT_STATE_FILE = DEFAULT_WORKSPACE_ROOT / "project_state.json"
DEFAULT_LOGS_DIR = DEFAULT_WORKSPACE_ROOT / "logs"

# Polling interval in seconds (≤3s as per requirement 15.2)
POLL_INTERVAL_SECONDS = 3.0


def _get_state_manager() -> StateManager:
    """Get a StateManager instance for the default state file path."""
    return StateManager(DEFAULT_STATE_FILE)


def _format_sse_event(data: dict, event: str | None = None) -> str:
    """Format data as an SSE event string.

    Args:
        data: Dictionary to serialize as JSON in the event data field.
        event: Optional event type name.

    Returns:
        SSE-formatted string: "event: {type}\\ndata: {json}\\n\\n"
    """
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, default=str)}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _state_to_dict(state: ProjectState) -> dict:
    """Convert a ProjectState to a serializable dictionary for SSE events."""
    return {
        "phase": state.phase.value,
        "agents": {
            name: {
                "status": agent.status.value,
                "started_at": agent.started_at.isoformat() if agent.started_at else None,
                "completed_at": agent.completed_at.isoformat() if agent.completed_at else None,
                "error": agent.error,
            }
            for name, agent in state.agents.items()
        },
        "approval_gates": {
            str(gate_num): {
                "gate_number": gate.gate_number,
                "pending": gate.pending,
                "revision_count": gate.revision_count,
                "feedback": gate.feedback,
            }
            for gate_num, gate in state.approval_gates.items()
        },
        "updated_at": state.updated_at.isoformat(),
    }


async def _status_event_generator(request: Request) -> AsyncGenerator[str, None]:
    """Async generator that polls project_state.json and yields SSE events on changes.

    Polls the state file every POLL_INTERVAL_SECONDS and emits an event
    whenever the state has changed from the previously seen state.
    Also emits an initial state event on first connection.

    Args:
        request: The incoming FastAPI request (used for disconnect detection).

    Yields:
        SSE-formatted event strings.
    """
    state_manager = _get_state_manager()
    last_state_json: str | None = None

    # Send initial connection event
    yield _format_sse_event(
        {"message": "connected", "timestamp": datetime.now(timezone.utc).isoformat()},
        event="connected",
    )

    while True:
        # Check if client disconnected
        if await request.is_disconnected():
            break

        try:
            state = await state_manager.read_state()
            current_state_json = state.model_dump_json()

            # Emit event if state has changed (or on first read)
            if current_state_json != last_state_json:
                event_data = _state_to_dict(state)
                event_data["timestamp"] = datetime.now(timezone.utc).isoformat()
                yield _format_sse_event(event_data, event="state_change")
                last_state_json = current_state_json

        except FileNotFoundError:
            # State file doesn't exist yet — send a waiting event
            yield _format_sse_event(
                {
                    "message": "waiting_for_state",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                event="waiting",
            )
        except Exception as e:
            yield _format_sse_event(
                {
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                event="error",
            )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _logs_event_generator(
    agent: str, request: Request
) -> AsyncGenerator[str, None]:
    """Async generator that tails an agent's log file and yields new entries as SSE events.

    Monitors the agent's log file (logs/agent_{name}.log) and emits
    new lines as they are appended. Polls at POLL_INTERVAL_SECONDS.

    Args:
        agent: The agent name whose logs to stream.
        request: The incoming FastAPI request (used for disconnect detection).

    Yields:
        SSE-formatted event strings with log entries.
    """
    log_file = DEFAULT_LOGS_DIR / f"agent_{agent}.log"
    last_position: int = 0

    # Send initial connection event
    yield _format_sse_event(
        {
            "message": "connected",
            "agent": agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        event="connected",
    )

    while True:
        # Check if client disconnected
        if await request.is_disconnected():
            break

        try:
            if log_file.exists():
                file_size = log_file.stat().st_size

                if file_size > last_position:
                    # New content available — read from last known position
                    with open(log_file, "r", encoding="utf-8") as f:
                        f.seek(last_position)
                        new_content = f.read()
                        last_position = f.tell()

                    # Emit each new line as a separate event
                    for line in new_content.splitlines():
                        line = line.strip()
                        if line:
                            yield _format_sse_event(
                                {
                                    "agent": agent,
                                    "entry": line,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                },
                                event="log_entry",
                            )
                elif file_size < last_position:
                    # File was truncated/rotated — reset position
                    last_position = 0

        except Exception as e:
            yield _format_sse_event(
                {
                    "error": str(e),
                    "agent": agent,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                event="error",
            )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@router.get("/status")
async def stream_status(request: Request) -> StreamingResponse:
    """SSE endpoint for real-time project state changes.

    Polls project_state.json every ≤3 seconds and emits SSE events
    whenever the state changes. The frontend dashboard connects to this
    endpoint to display live agent status updates.

    Returns:
        StreamingResponse with media_type text/event-stream.
    """
    return StreamingResponse(
        _status_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/logs/{agent}")
async def stream_logs(agent: str, request: Request) -> StreamingResponse:
    """SSE endpoint for streaming agent log entries.

    Tails the agent's log file and emits new entries as SSE events.
    Log entries appear within 3 seconds of being written.

    Args:
        agent: The agent name whose logs to stream (e.g., "project_planner").

    Returns:
        StreamingResponse with media_type text/event-stream.
    """
    return StreamingResponse(
        _logs_event_generator(agent, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

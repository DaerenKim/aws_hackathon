"""Unit tests for the SSE streaming endpoints."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from backend.app.api.routes.stream import (
    POLL_INTERVAL_SECONDS,
    _format_sse_event,
    _state_to_dict,
    _status_event_generator,
    _logs_event_generator,
)
from backend.app.models.project_state import (
    AgentPhase,
    AgentStatus,
    ApprovalGateState,
    PhaseStatus,
    ProjectState,
)
from backend.app.services.state_manager import AGENT_NAMES, StateManager


class TestFormatSseEvent:
    """Tests for _format_sse_event helper."""

    def test_formats_data_only(self) -> None:
        """Should format data without event type."""
        result = _format_sse_event({"key": "value"})
        assert result == 'data: {"key": "value"}\n\n'

    def test_formats_with_event_type(self) -> None:
        """Should include event type line when specified."""
        result = _format_sse_event({"msg": "hello"}, event="test_event")
        assert "event: test_event\n" in result
        assert 'data: {"msg": "hello"}\n\n' in result

    def test_serializes_datetime(self) -> None:
        """Should serialize datetime objects via default=str."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _format_sse_event({"ts": dt})
        assert "2024-01-15" in result

    def test_ends_with_double_newline(self) -> None:
        """SSE events must end with \\n\\n."""
        result = _format_sse_event({"x": 1})
        assert result.endswith("\n\n")


class TestStateToDictConversion:
    """Tests for _state_to_dict helper."""

    def test_converts_project_state(self) -> None:
        """Should convert ProjectState to a serializable dict."""
        now = datetime.now(timezone.utc)
        state = ProjectState(
            phase=PhaseStatus.DEVELOPMENT,
            agents={
                "project_planner": AgentPhase(
                    status=AgentStatus.COMPLETED,
                    started_at=now,
                    completed_at=now,
                ),
                "backend_engineer": AgentPhase(
                    status=AgentStatus.IN_PROGRESS,
                    started_at=now,
                ),
            },
            approval_gates={
                1: ApprovalGateState(gate_number=1, pending=False),
            },
            created_at=now,
            updated_at=now,
        )

        result = _state_to_dict(state)

        assert result["phase"] == "development"
        assert result["agents"]["project_planner"]["status"] == "completed"
        assert result["agents"]["backend_engineer"]["status"] == "in_progress"
        assert result["agents"]["backend_engineer"]["error"] is None
        assert "1" in result["approval_gates"]
        assert result["approval_gates"]["1"]["pending"] is False

    def test_handles_failed_agent_with_error(self) -> None:
        """Should include error message for failed agents."""
        now = datetime.now(timezone.utc)
        state = ProjectState(
            phase=PhaseStatus.PLANNING,
            agents={
                "qa": AgentPhase(
                    status=AgentStatus.FAILED,
                    error="Timeout after 600s",
                ),
            },
            approval_gates={},
            created_at=now,
            updated_at=now,
        )

        result = _state_to_dict(state)

        assert result["agents"]["qa"]["status"] == "failed"
        assert result["agents"]["qa"]["error"] == "Timeout after 600s"


class TestPollingInterval:
    """Tests for polling configuration."""

    def test_poll_interval_is_at_most_3_seconds(self) -> None:
        """Requirement 15.2: poll at intervals no greater than 3 seconds."""
        assert POLL_INTERVAL_SECONDS <= 3.0

    def test_poll_interval_is_positive(self) -> None:
        """Polling interval should be a positive number."""
        assert POLL_INTERVAL_SECONDS > 0


class TestStatusEventGenerator:
    """Tests for _status_event_generator."""

    @pytest.mark.asyncio
    async def test_emits_connected_event_first(self, tmp_path: Path) -> None:
        """Should emit a connected event as the first event."""
        state_file = tmp_path / "project_state.json"

        # Create a mock request that disconnects after first iteration
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, True])

        with patch(
            "backend.app.api.routes.stream.DEFAULT_STATE_FILE", state_file
        ), patch(
            "backend.app.api.routes.stream._get_state_manager",
            return_value=StateManager(state_file),
        ), patch(
            "backend.app.api.routes.stream.asyncio.sleep",
            new_callable=lambda: AsyncMock,
        ):
            events = []
            async for event in _status_event_generator(mock_request):
                events.append(event)
                if len(events) >= 2:
                    break

        # First event should be "connected"
        assert "event: connected" in events[0]
        assert "connected" in events[0]

    @pytest.mark.asyncio
    async def test_emits_state_change_event(self, tmp_path: Path) -> None:
        """Should emit a state_change event when state is available."""
        state_file = tmp_path / "project_state.json"

        # Initialize state
        manager = StateManager(state_file)
        await manager.read_state()

        # Mock request that disconnects after yielding events
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, False, True])

        with patch(
            "backend.app.api.routes.stream._get_state_manager",
            return_value=manager,
        ), patch(
            "backend.app.api.routes.stream.asyncio.sleep",
            new_callable=lambda: AsyncMock,
        ):
            events = []
            async for event in _status_event_generator(mock_request):
                events.append(event)
                if len(events) >= 2:
                    break

        # Second event should be state_change with phase info
        assert any("state_change" in e for e in events)
        state_event = next(e for e in events if "state_change" in e)
        # Parse the data line
        data_line = [l for l in state_event.split("\n") if l.startswith("data:")][0]
        data_json = json.loads(data_line.replace("data: ", ""))
        assert data_json["phase"] == "planning"


class TestLogsEventGenerator:
    """Tests for _logs_event_generator."""

    @pytest.mark.asyncio
    async def test_emits_connected_event_first(self, tmp_path: Path) -> None:
        """Should emit a connected event with agent name."""
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, True])

        with patch(
            "backend.app.api.routes.stream.DEFAULT_LOGS_DIR", tmp_path
        ), patch(
            "backend.app.api.routes.stream.asyncio.sleep",
            new_callable=lambda: AsyncMock,
        ):
            events = []
            async for event in _logs_event_generator("project_planner", mock_request):
                events.append(event)
                if len(events) >= 1:
                    break

        assert "event: connected" in events[0]
        assert "project_planner" in events[0]

    @pytest.mark.asyncio
    async def test_emits_log_entries_from_file(self, tmp_path: Path) -> None:
        """Should emit log_entry events for new lines in the log file."""
        log_file = tmp_path / "agent_qa.log"
        log_file.write_text("First log line\nSecond log line\n")

        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, False, True])

        with patch(
            "backend.app.api.routes.stream.DEFAULT_LOGS_DIR", tmp_path
        ), patch(
            "backend.app.api.routes.stream.asyncio.sleep",
            new_callable=lambda: AsyncMock,
        ):
            events = []
            async for event in _logs_event_generator("qa", mock_request):
                events.append(event)
                if len(events) >= 3:
                    break

        # Should have connected event + 2 log_entry events
        log_events = [e for e in events if "log_entry" in e]
        assert len(log_events) == 2
        assert "First log line" in log_events[0]
        assert "Second log line" in log_events[1]

    @pytest.mark.asyncio
    async def test_handles_missing_log_file(self, tmp_path: Path) -> None:
        """Should not crash if log file doesn't exist yet."""
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, False, True])

        with patch(
            "backend.app.api.routes.stream.DEFAULT_LOGS_DIR", tmp_path
        ), patch(
            "backend.app.api.routes.stream.asyncio.sleep",
            new_callable=lambda: AsyncMock,
        ):
            events = []
            async for event in _logs_event_generator("nonexistent", mock_request):
                events.append(event)
                if len(events) >= 1:
                    break

        # Should get connected event without errors
        assert "event: connected" in events[0]

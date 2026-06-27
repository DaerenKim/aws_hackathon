"""Pydantic models for agent results, orchestrator events, and configuration.

Defines the schema for agent execution outputs, SSE event payloads,
and Ollama LLM configuration.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """Result returned by an agent after execution."""

    agent_name: str
    success: bool
    artifacts_produced: list[str] = Field(default_factory=list)  # Relative paths in workspace
    error: str | None = None
    duration_seconds: float


class OrchestratorEvent(BaseModel):
    """Event emitted by the orchestrator for real-time streaming via SSE."""

    timestamp: datetime
    event_type: str  # "status_change" | "phase_change" | "approval_required" | "error" | "complete"
    agent: str | None = None
    data: dict = Field(default_factory=dict)


class OllamaConfig(BaseModel):
    """Configuration for the local Ollama LLM server."""

    base_url: str = "http://localhost:11434"
    model: str = "llama3"
    timeout_seconds: float = 120.0
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    temperature: float = 0.7
    context_window: int = 8192

"use client";

import { useState } from "react";

import { AgentStatusCard } from "@/components/agent-status-card";
import { LogViewer } from "@/components/log-viewer";
import { PhaseIndicator } from "@/components/phase-indicator";
import { useProjectState } from "@/hooks/use-project-state";

/** Canonical ordering and display names for the 10 agents. */
const AGENTS = [
  { key: "project_planner", label: "Project Planner" },
  { key: "judge_optimizer", label: "Judge Optimizer" },
  { key: "backend_engineer", label: "Backend Engineer" },
  { key: "frontend_engineer", label: "Frontend Engineer" },
  { key: "integration", label: "Integration" },
  { key: "qa", label: "QA" },
  { key: "documentation", label: "Documentation" },
  { key: "powerpoint", label: "PowerPoint" },
  { key: "demo_video", label: "Demo Video" },
  { key: "github", label: "GitHub" },
] as const;

/**
 * Monitoring Dashboard Page
 *
 * Displays the current workflow phase, all 10 agent status cards (updated in
 * real time via SSE), an agent-selectable log viewer, and failure reasons for
 * failed agents.
 */
export default function MonitorPage() {
  const { state, isLoading, error, isConnected } = useProjectState();
  const [selectedAgent, setSelectedAgent] = useState<string>(AGENTS[0].key);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <p className="text-muted-foreground animate-pulse">
          Loading project state...
        </p>
      </div>
    );
  }

  if (error && !state) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <p className="text-red-600">
          Failed to load project state: {error.message}
        </p>
      </div>
    );
  }

  return (
    <main className="min-h-screen p-4 md:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Connection status indicator */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">
          Monitoring Dashboard
        </h1>
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-green-500" : "bg-gray-400"
            }`}
          />
          {isConnected ? "Live" : "Reconnecting..."}
        </span>
      </div>

      {/* Phase Indicator */}
      {state && <PhaseIndicator currentPhase={state.phase} />}

      {/* Agent Status Cards Grid */}
      <section>
        <h2 className="text-lg font-semibold text-foreground mb-3">
          Agent Status
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {AGENTS.map(({ key, label }) => {
            const agentPhase = state?.agents[key];
            return (
              <AgentStatusCard
                key={key}
                agentName={label}
                status={agentPhase?.status ?? "pending"}
                error={agentPhase?.error}
              />
            );
          })}
        </div>
      </section>

      {/* Log Viewer with Agent Selector */}
      <section>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
          <h2 className="text-lg font-semibold text-foreground">Agent Logs</h2>
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Select agent for log viewing"
          >
            {AGENTS.map(({ key, label }) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <LogViewer agentName={selectedAgent} />
      </section>

      {/* Failed Agents Summary */}
      {state && hasFailedAgents(state.agents) && (
        <section>
          <h2 className="text-lg font-semibold text-red-700 mb-3">
            Failed Agents
          </h2>
          <div className="space-y-2">
            {AGENTS.filter(
              ({ key }) => state.agents[key]?.status === "failed"
            ).map(({ key, label }) => (
              <div
                key={key}
                className="rounded-lg border border-red-200 bg-red-50 p-3"
              >
                <p className="text-sm font-medium text-red-800">{label}</p>
                <p className="text-xs text-red-600 mt-1">
                  {state.agents[key]?.error ?? "Unknown error"}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

/** Check if any agents have a failed status. */
function hasFailedAgents(
  agents: Record<string, { status: string; error?: string | null }>
): boolean {
  return Object.values(agents).some((a) => a.status === "failed");
}

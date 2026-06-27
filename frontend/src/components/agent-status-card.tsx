"use client";

import type { AgentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface AgentStatusCardProps {
  agentName: string;
  status: AgentStatus;
  error?: string | null;
}

const statusConfig: Record<
  AgentStatus,
  { label: string; badgeClass: string }
> = {
  completed: {
    label: "Completed",
    badgeClass: "bg-green-100 text-green-800 border-green-200",
  },
  in_progress: {
    label: "In Progress",
    badgeClass: "bg-blue-100 text-blue-800 border-blue-200",
  },
  pending: {
    label: "Pending",
    badgeClass: "bg-gray-100 text-gray-600 border-gray-200",
  },
  failed: {
    label: "Failed",
    badgeClass: "bg-red-100 text-red-800 border-red-200",
  },
};

/**
 * Displays an agent's name, colored status badge, and optional failure reason.
 */
export function AgentStatusCard({
  agentName,
  status,
  error,
}: AgentStatusCardProps) {
  const { label, badgeClass } = statusConfig[status];

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 shadow-sm",
        status === "failed" && "border-red-200"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-card-foreground truncate">
          {agentName}
        </h3>
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold shrink-0",
            badgeClass
          )}
        >
          {label}
        </span>
      </div>

      {status === "failed" && error && (
        <p className="mt-2 text-xs text-red-600 leading-relaxed break-words">
          {error}
        </p>
      )}
    </div>
  );
}

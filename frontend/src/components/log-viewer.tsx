"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface LogEntry {
  timestamp: string;
  message: string;
}

export interface LogViewerProps {
  agentName: string;
}

/**
 * Real-time log viewer that connects to the SSE endpoint for a specific agent.
 * Displays timestamped log entries in a scrollable container with auto-scroll.
 */
export function LogViewer({ agentName }: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);

  // Track whether user has scrolled up (disable auto-scroll)
  const handleScroll = () => {
    const container = containerRef.current;
    if (!container) return;
    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 40;
    shouldAutoScroll.current = isNearBottom;
  };

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    if (shouldAutoScroll.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  // Connect to SSE endpoint
  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const url = `${baseUrl}/api/stream/logs/${encodeURIComponent(agentName)}`;

    let eventSource: EventSource | null = null;

    const connect = () => {
      eventSource = new EventSource(url);

      eventSource.onopen = () => {
        setConnected(true);
        setError(null);
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as LogEntry;
          setLogs((prev) => [...prev, data]);
        } catch {
          // If not JSON, treat the raw data as a log message
          setLogs((prev) => [
            ...prev,
            { timestamp: new Date().toISOString(), message: event.data },
          ]);
        }
      };

      eventSource.onerror = () => {
        setConnected(false);
        setError("Connection lost. Reconnecting...");
        eventSource?.close();
        // Reconnect after 3 seconds
        setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      eventSource?.close();
    };
  }, [agentName]);

  return (
    <div className="flex flex-col rounded-lg border bg-card shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2 bg-muted/50">
        <h4 className="text-sm font-medium text-card-foreground">
          Logs: {agentName}
        </h4>
        <span
          className={cn(
            "inline-flex items-center gap-1 text-xs",
            connected ? "text-green-600" : "text-muted-foreground"
          )}
        >
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              connected ? "bg-green-500" : "bg-gray-400"
            )}
          />
          {connected ? "Live" : "Disconnected"}
        </span>
      </div>

      {/* Log entries */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto max-h-64 md:max-h-96 p-3 font-mono text-xs space-y-1 bg-background"
      >
        {logs.length === 0 && !error && (
          <p className="text-muted-foreground italic">
            Waiting for log entries...
          </p>
        )}

        {error && (
          <p className="text-yellow-600 italic">{error}</p>
        )}

        {logs.map((entry, index) => (
          <div key={index} className="flex gap-2 leading-relaxed">
            <span className="text-muted-foreground shrink-0">
              {formatTimestamp(entry.timestamp)}
            </span>
            <span className="text-foreground break-words">{entry.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Format an ISO timestamp to a short time string. */
function formatTimestamp(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

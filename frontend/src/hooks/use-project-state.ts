'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient } from '../lib/api';
import type { ProjectState } from '../lib/types';
import { useSSE } from './use-sse';

/** Polling interval in milliseconds when falling back from SSE. */
const POLL_INTERVAL_MS = 5000;

/** Base URL for the backend API (used for SSE endpoint). */
const API_BASE_URL = 'http://localhost:8000';

/**
 * Return type of the useProjectState hook.
 */
export interface UseProjectStateReturn {
  /** The latest project state, or null if not yet loaded. */
  state: ProjectState | null;
  /** Whether the state is currently being loaded for the first time. */
  isLoading: boolean;
  /** Any error from SSE connection or polling. */
  error: Error | null;
  /** Whether the SSE connection is currently active. */
  isConnected: boolean;
}

/**
 * Custom hook for managing project state from the SSE stream.
 *
 * Connects to /api/stream/status SSE endpoint via useSSE.
 * Parses state_change events into ProjectState type.
 * Falls back to polling getWorkflowState() every 5s if SSE fails.
 *
 * @returns Object containing state, loading status, error, and connection status.
 */
export function useProjectState(): UseProjectStateReturn {
  const [state, setState] = useState<ProjectState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pollingError, setPollingError] = useState<Error | null>(null);

  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isPollingRef = useRef(false);

  // Connect to SSE endpoint
  const { events, isConnected, error: sseError } = useSSE(
    `${API_BASE_URL}/api/stream/status`
  );

  // Parse state_change events from SSE into ProjectState
  useEffect(() => {
    if (events.length === 0) return;

    const latestEvent = events[events.length - 1];

    if (latestEvent.type === 'state_change') {
      const data = latestEvent.data;
      // Map SSE event data to ProjectState type
      const projectState: ProjectState = {
        phase: data.phase as ProjectState['phase'],
        agents: data.agents as ProjectState['agents'],
        approval_gates: data.approval_gates as ProjectState['approval_gates'],
        created_at: (data.created_at as string) ?? '',
        updated_at: (data.updated_at as string) ?? data.timestamp as string ?? '',
      };
      setState(projectState);
      setIsLoading(false);
    }
  }, [events]);

  // Poll fallback function
  const pollState = useCallback(async () => {
    try {
      const fetchedState = await apiClient.getWorkflowState();
      setState(fetchedState);
      setIsLoading(false);
      setPollingError(null);
    } catch (err) {
      setPollingError(
        err instanceof Error ? err : new Error('Failed to poll workflow state')
      );
    }
  }, []);

  // Start/stop polling based on SSE connection status
  useEffect(() => {
    if (!isConnected && sseError) {
      // SSE has failed — fall back to polling
      if (!isPollingRef.current) {
        isPollingRef.current = true;
        // Immediately fetch once
        pollState();
        // Then poll on interval
        pollingIntervalRef.current = setInterval(pollState, POLL_INTERVAL_MS);
      }
    } else if (isConnected) {
      // SSE is connected — stop polling if active
      if (isPollingRef.current) {
        isPollingRef.current = false;
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setPollingError(null);
      }
    }

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [isConnected, sseError, pollState]);

  // Determine effective error (prefer SSE error when polling is not active)
  const effectiveError = isPollingRef.current ? pollingError : sseError;

  return {
    state,
    isLoading,
    error: effectiveError,
    isConnected,
  };
}

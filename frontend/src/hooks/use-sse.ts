'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * A parsed SSE event from the server.
 */
export interface SSEEvent {
  /** The event type (e.g., "state_change", "connected", "error"). */
  type: string;
  /** The parsed JSON data from the event's data field. */
  data: Record<string, unknown>;
}

/**
 * Return type of the useSSE hook.
 */
export interface UseSSEReturn {
  /** Array of events received during the current connection session. */
  events: SSEEvent[];
  /** Whether the EventSource is currently connected. */
  isConnected: boolean;
  /** Any connection error that occurred. */
  error: Error | null;
}

/** Maximum number of reconnection attempts before giving up. */
const MAX_RETRIES = 5;

/** Base delay in milliseconds for exponential backoff. */
const BASE_DELAY_MS = 1000;

/**
 * Custom hook for connecting to a Server-Sent Events (SSE) endpoint.
 *
 * Creates an EventSource connection to the given URL, parses incoming events
 * (data field as JSON), handles reconnection on failure with exponential backoff
 * (max 5 retries), and cleans up on unmount.
 *
 * @param url - The SSE endpoint URL to connect to.
 * @returns Object containing events array, connection status, and any error.
 */
export function useSSE(url: string): UseSSEReturn {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // Clean up any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    try {
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
        setError(null);
        retryCountRef.current = 0;
      };

      // Handle named events (state_change, connected, waiting, error, log_entry)
      const handleEvent = (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data) as Record<string, unknown>;
          const sseEvent: SSEEvent = {
            type: e.type || 'message',
            data,
          };
          setEvents((prev) => [...prev, sseEvent]);
        } catch {
          // If data isn't valid JSON, store raw
          const sseEvent: SSEEvent = {
            type: e.type || 'message',
            data: { raw: e.data },
          };
          setEvents((prev) => [...prev, sseEvent]);
        }
      };

      // Register handlers for known event types from backend
      es.addEventListener('connected', handleEvent);
      es.addEventListener('state_change', handleEvent);
      es.addEventListener('waiting', handleEvent);
      es.addEventListener('error', handleEvent as EventListener);
      es.addEventListener('log_entry', handleEvent);

      // Also handle generic messages (no event type)
      es.onmessage = handleEvent;

      es.onerror = () => {
        setIsConnected(false);
        es.close();
        eventSourceRef.current = null;

        if (retryCountRef.current < MAX_RETRIES) {
          const delay = BASE_DELAY_MS * Math.pow(2, retryCountRef.current);
          retryCountRef.current += 1;
          setError(
            new Error(
              `SSE connection lost. Retrying in ${delay}ms (attempt ${retryCountRef.current}/${MAX_RETRIES})...`
            )
          );

          retryTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          setError(
            new Error(
              `SSE connection failed after ${MAX_RETRIES} retries. Please check your connection.`
            )
          );
        }
      };
    } catch (err) {
      setError(
        err instanceof Error ? err : new Error('Failed to create EventSource')
      );
      setIsConnected(false);
    }
  }, [url]);

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
    };
  }, [connect]);

  return { events, isConnected, error };
}

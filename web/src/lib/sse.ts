/** Live event stream hook (SSE) + connection status. */

import { useEffect, useRef, useState } from "react";
import type { AppEvent } from "./api";

export interface LiveEventsOptions {
  enabled?: boolean;
  category?: string;
  level?: string;
  onEvent?: (event: AppEvent) => void;
}

export function useLiveEvents(options: LiveEventsOptions = {}) {
  const { enabled = true, category, level, onEvent } = options;
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!enabled) {
      setConnected(false);
      return;
    }
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (level) params.set("level", level);
    const query = params.toString();

    const source = new EventSource(`/api/events/stream${query ? `?${query}` : ""}`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as AppEvent;
        setEvents((previous) => [event, ...previous].slice(0, 300));
        handlerRef.current?.(event);
      } catch {
        /* ignore malformed frames */
      }
    };

    return () => {
      source.close();
      setConnected(false);
    };
  }, [enabled, category, level]);

  return { connected, events, clear: () => setEvents([]) };
}

import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RoomSnapshot } from "../api/types";

const MAX_ERRORS = 3;
const POLL_MS = 5000;

/** The room snapshot, kept current by the SSE stage stream; after three stream errors, by polling. */
export function useRoomEvents(classAssignmentId: number | null) {
  const [snapshot, setSnapshot] = useState<RoomSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const alive = useRef(true);
  const scope = classAssignmentId === null ? "" : `class_assignment_id=${classAssignmentId}`;

  useEffect(() => {
    alive.current = true;
    let source: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let debounce: ReturnType<typeof setTimeout> | null = null;
    let errors = 0;
    const load = () => api.get<RoomSnapshot>(`/api/room${scope ? `?${scope}` : ""}`)
      .then((s) => { if (alive.current) { setSnapshot(s); setError(null); } return s; })
      .catch((e) => { if (alive.current) setError(e.message); return null; });
    const startPolling = () => { setLive(false); poll = setInterval(load, POLL_MS); };
    load().then((s) => {
      if (!alive.current || !s) return;
      if (typeof EventSource !== "function") { startPolling(); return; }
      const qs = [`after=${s.last_event_id}`, scope].filter(Boolean).join("&");
      source = new EventSource(`/api/room/events?${qs}`);
      source.addEventListener("stage", () => { if (debounce) clearTimeout(debounce); debounce = setTimeout(load, 300); });
      source.onerror = () => { if (++errors >= MAX_ERRORS && source) { source.close(); source = null; startPolling(); } };
    });
    return () => { alive.current = false; source?.close(); if (poll) clearInterval(poll); if (debounce) clearTimeout(debounce); };
  }, [scope]);

  return { snapshot, error, live };
}

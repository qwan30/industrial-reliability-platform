/**
 * Reactive hook for streaming simulation snapshots, observations, and events via SSE.
 */

import { useEffect, useRef } from "react";
import type { LabEvent, Observation, RunSnapshot } from "./types";
import { labStore } from "./store";

export function useLabStream(runId: string | null) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastSequenceRef = useRef<number>(0);
  const lastActivityTimeRef = useRef<number>(Date.now());
  const staleTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!runId) {
      labStore.setConnectionStatus("DISCONNECTED");
      return;
    }

    labStore.setConnectionStatus("CONNECTING");
    lastActivityTimeRef.current = Date.now();

    // Start heartbeat watchdog
    staleTimerRef.current = window.setInterval(() => {
      const elapsed = Date.now() - lastActivityTimeRef.current;
      if (elapsed > 2500) {
        labStore.setConnectionStatus("STALE");
      }
    }, 1000);

    const streamUrl = `/v2/runs/${runId}/stream?after_sequence=${lastSequenceRef.current}`;
    const es = new EventSource(streamUrl);
    eventSourceRef.current = es;

    es.onopen = () => {
      lastActivityTimeRef.current = Date.now();
      labStore.setConnectionStatus("CONNECTED");
    };

    es.onerror = () => {
      labStore.setConnectionStatus("STALE");
    };

    // Listen for snapshot event
    es.addEventListener("snapshot", (event: MessageEvent) => {
      lastActivityTimeRef.current = Date.now();
      labStore.setConnectionStatus("CONNECTED");
      try {
        const snapshot: RunSnapshot = JSON.parse(event.data);
        labStore.setRunSnapshot(snapshot);
      } catch (e) {
        console.error("Failed to parse stream snapshot:", e);
      }
    });

    // Listen for observation event
    es.addEventListener("observation", (event: MessageEvent) => {
      lastActivityTimeRef.current = Date.now();
      labStore.setConnectionStatus("CONNECTED");
      try {
        const payload: LabEvent = JSON.parse(event.data);
        lastSequenceRef.current = Math.max(lastSequenceRef.current, payload.sequence);
        const obs: Observation = payload.payload as unknown as Observation;
        labStore.updateObservations([obs]);
      } catch (e) {
        console.error("Failed to parse observation event:", e);
      }
    });

    // Listen for run_status event
    es.addEventListener("run_status", (event: MessageEvent) => {
      lastActivityTimeRef.current = Date.now();
      labStore.setConnectionStatus("CONNECTED");
      try {
        const payload: LabEvent = JSON.parse(event.data);
        lastSequenceRef.current = Math.max(lastSequenceRef.current, payload.sequence);
      } catch (e) {
        console.error("Failed to parse run_status event:", e);
      }
    });
    return () => {
      clearInterval(staleTimerRef.current as number);
      es.close();
      labStore.setConnectionStatus("DISCONNECTED");
    };
  }, [runId]);
}

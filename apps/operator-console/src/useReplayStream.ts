import { useEffect, useRef, useState } from 'react';
import {
  AlertSummary,
  ConnectionStatus,
  ReplaySession,
  ScorePayload,
  SnapshotPayload,
  StatusPayload,
  TelemetryPayload,
} from './types';

const MAX_CHART_POINTS = 120;

export interface ReplayStreamState {
  connectionStatus: ConnectionStatus;
  replay: ReplaySession | null;
  alerts: AlertSummary[];
  scores: ScorePayload[];
  telemetry: TelemetryPayload[];
  lastEventId: string | null;
  error: string | null;
}

export function useReplayStream(
  replaySessionId: string | null,
  baseUrl = ''
): ReplayStreamState {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('DISCONNECTED');
  const [replay, setReplay] = useState<ReplaySession | null>(null);
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [scores, setScores] = useState<ScorePayload[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryPayload[]>([]);
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lastEventIdRef = useRef<string | null>(null);
  lastEventIdRef.current = lastEventId;

  useEffect(() => {
    if (!replaySessionId) {
      setConnectionStatus('DISCONNECTED');
      setReplay(null);
      setAlerts([]);
      setScores([]);
      setTelemetry([]);
      setLastEventId(null);
      setError(null);
      return;
    }

    let isSubscribed = true;
    let eventSource: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let reconnectDelay = 1000;

    function connect() {
      if (!isSubscribed) return;
      setConnectionStatus((prev) => (prev === 'DISCONNECTED' ? 'CONNECTING' : 'RECONNECTING'));

      const url = `${baseUrl}/v1/replays/${replaySessionId}/stream`;
      eventSource = new EventSource(url);

      eventSource.onopen = () => {
        if (!isSubscribed) return;
        setConnectionStatus('CONNECTED');
        setError(null);
        reconnectDelay = 1000;
      };

      eventSource.addEventListener('snapshot', (e: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const snap: SnapshotPayload = JSON.parse(e.data);
          if (snap.replay) setReplay(snap.replay);
          if (snap.alerts) setAlerts(snap.alerts);
          if (e.lastEventId) {
            setLastEventId(e.lastEventId);
          }
        } catch {
          // ignore malformed snapshot
        }
      });

      eventSource.addEventListener('score', (e: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const scoreData: ScorePayload = JSON.parse(e.data);
          setScores((prev) => {
            const next = [...prev, scoreData];
            return next.length > MAX_CHART_POINTS ? next.slice(-MAX_CHART_POINTS) : next;
          });
          if (e.lastEventId) {
            setLastEventId(e.lastEventId);
          }
        } catch {
          // ignore malformed score
        }
      });

      eventSource.addEventListener('telemetry', (e: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const telemData: TelemetryPayload = JSON.parse(e.data);
          setTelemetry((prev) => {
            const next = [...prev, telemData];
            return next.length > MAX_CHART_POINTS ? next.slice(-MAX_CHART_POINTS) : next;
          });
        } catch {
          // ignore malformed telemetry
        }
      });

      eventSource.addEventListener('alert', (e: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const alertData: AlertSummary = JSON.parse(e.data);
          setAlerts((prev) => {
            const idx = prev.findIndex((a) => a.alert_id === alertData.alert_id);
            if (idx >= 0) {
              const copy = [...prev];
              copy[idx] = alertData;
              return copy;
            }
            return [alertData, ...prev];
          });
          if (e.lastEventId) {
            setLastEventId(e.lastEventId);
          }
        } catch {
          // ignore malformed alert
        }
      });

      eventSource.addEventListener('status', (e: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const statusData: StatusPayload = JSON.parse(e.data);
          setReplay((prev) =>
            prev
              ? {
                  ...prev,
                  state: statusData.state,
                  last_sequence: statusData.last_sequence ?? prev.last_sequence,
                  source_timestamp: statusData.source_timestamp ?? prev.source_timestamp,
                  error_code: statusData.error_code ?? prev.error_code,
                }
              : null
          );
          if (e.lastEventId) {
            setLastEventId(e.lastEventId);
          }
        } catch {
          // ignore malformed status
        }
      });

      eventSource.addEventListener('resync_required', () => {
        if (!isSubscribed) return;
        setScores([]);
        setTelemetry([]);
      });

      eventSource.onerror = () => {
        if (!isSubscribed) return;
        setConnectionStatus('DISCONNECTED');
        setError('Stream disconnected, reconnecting...');
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
        reconnectTimeout = setTimeout(connect, reconnectDelay);
      };
    }

    connect();

    return () => {
      isSubscribed = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
    };
  }, [replaySessionId, baseUrl]);

  return {
    connectionStatus,
    replay,
    alerts,
    scores,
    telemetry,
    lastEventId,
    error,
  };
}

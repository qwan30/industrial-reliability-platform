import {
  AlertDetail,
  AlertSummary,
  DependencyHealth,
  ReplaySession,
  StartReplayParams,
} from './types';

const DEFAULT_BASE_URL = '';

export async function startReplay(
  params: StartReplayParams,
  baseUrl = DEFAULT_BASE_URL
): Promise<{ replay_session_id: string }> {
  const res = await fetch(`${baseUrl}/v1/replays`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error?.message || `Failed to start replay: ${res.statusText}`);
  }
  const json = await res.json();
  return json.data;
}

export async function controlReplay(
  replaySessionId: string,
  action: 'PAUSE' | 'RESUME' | 'STOP',
  baseUrl = DEFAULT_BASE_URL
): Promise<void> {
  const res = await fetch(`${baseUrl}/v1/replays/${replaySessionId}/commands`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error?.message || `Failed to ${action} replay: ${res.statusText}`);
  }
}

export async function getReplay(
  replaySessionId: string,
  baseUrl = DEFAULT_BASE_URL
): Promise<ReplaySession> {
  const res = await fetch(`${baseUrl}/v1/replays/${replaySessionId}`);
  if (!res.ok) {
    throw new Error(`Failed to get replay: ${res.statusText}`);
  }
  const json = await res.json();
  return json.data;
}

export async function listAlerts(
  replaySessionId: string,
  baseUrl = DEFAULT_BASE_URL
): Promise<AlertSummary[]> {
  const res = await fetch(`${baseUrl}/v1/replays/${replaySessionId}/alerts`);
  if (!res.ok) {
    throw new Error(`Failed to list alerts: ${res.statusText}`);
  }
  const json = await res.json();
  return json.data?.alerts || [];
}

export async function getAlertDetail(
  alertId: string,
  baseUrl = DEFAULT_BASE_URL
): Promise<AlertDetail> {
  const res = await fetch(`${baseUrl}/v1/alerts/${alertId}`);
  if (!res.ok) {
    throw new Error(`Failed to get alert detail: ${res.statusText}`);
  }
  const json = await res.json();
  return json.data;
}

export async function checkHealth(baseUrl = DEFAULT_BASE_URL): Promise<DependencyHealth> {
  try {
    const res = await fetch(`${baseUrl}/healthz`);
    const isOk = res.ok;
    return {
      api: isOk,
      database: isOk,
    };
  } catch {
    return {
      api: false,
      database: false,
    };
  }
}

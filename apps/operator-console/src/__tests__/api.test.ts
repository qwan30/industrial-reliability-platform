import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  startReplay,
  controlReplay,
  getReplay,
  listAlerts,
  getAlertDetail,
  checkHealth,
} from '../api';

describe('api client', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('startReplay posts valid params and returns session id', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { replay_session_id: 'rep-123' },
      }),
    } as unknown as Response);

    const result = await startReplay({
      range_start: '2020-04-18T00:00:00',
      range_end: '2020-04-18T02:00:00',
      speed: 100,
    });

    expect(result.replay_session_id).toBe('rep-123');
    expect(global.fetch).toHaveBeenCalledWith(
      '/v1/replays',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
  });

  it('startReplay throws error on failure with structured error', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Unprocessable Entity',
      json: async () => ({ error: { message: 'Invalid range' } }),
    } as unknown as Response);

    await expect(
      startReplay({
        range_start: '2020-04-18T02:00:00',
        range_end: '2020-04-18T00:00:00',
        speed: 100,
      })
    ).rejects.toThrow('Invalid range');
  });

  it('startReplay throws error on failure with fallback statusText', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Bad Request',
      json: async () => {
        throw new Error('invalid json');
      },
    } as unknown as Response);

    await expect(
      startReplay({
        range_start: '2020-04-18T02:00:00',
        range_end: '2020-04-18T00:00:00',
        speed: 100,
      })
    ).rejects.toThrow('Failed to start replay: Bad Request');
  });

  it('controlReplay sends action and resolves on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    } as unknown as Response);

    await expect(controlReplay('rep-123', 'PAUSE')).resolves.toBeUndefined();
    expect(global.fetch).toHaveBeenCalledWith(
      '/v1/replays/rep-123/commands',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ action: 'PAUSE' }),
      })
    );
  });

  it('controlReplay throws error on failure with structured message', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Conflict',
      json: async () => ({ error: { message: 'Replay cannot be paused' } }),
    } as unknown as Response);

    await expect(controlReplay('rep-123', 'PAUSE')).rejects.toThrow('Replay cannot be paused');
  });

  it('controlReplay throws error on failure with fallback statusText', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Internal Error',
      json: async () => {
        throw new Error('invalid json');
      },
    } as unknown as Response);

    await expect(controlReplay('rep-123', 'PAUSE')).rejects.toThrow('Failed to PAUSE replay: Internal Error');
  });

  it('getReplay retrieves replay session info', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { replay_session_id: 'rep-123', state: 'RUNNING' },
      }),
    } as unknown as Response);

    const res = await getReplay('rep-123');
    expect(res.replay_session_id).toBe('rep-123');
    expect(res.state).toBe('RUNNING');
  });

  it('getReplay throws error on non-ok status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
    } as unknown as Response);

    await expect(getReplay('rep-not-found')).rejects.toThrow('Failed to get replay: Not Found');
  });

  it('listAlerts retrieves alert list', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { alerts: [{ alert_id: 'alt-1', state: 'OPEN' }] },
      }),
    } as unknown as Response);

    const res = await listAlerts('rep-123');
    expect(res).toHaveLength(1);
    expect(res[0].alert_id).toBe('alt-1');
  });

  it('listAlerts returns empty list when data is empty', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: null,
      }),
    } as unknown as Response);

    const res = await listAlerts('rep-123');
    expect(res).toEqual([]);
  });

  it('listAlerts throws error on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Service Unavailable',
    } as unknown as Response);

    await expect(listAlerts('rep-123')).rejects.toThrow('Failed to list alerts: Service Unavailable');
  });

  it('getAlertDetail retrieves detail record', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { alert: { alert_id: 'alt-1' }, events: [], evidence: [], decisions: [] },
      }),
    } as unknown as Response);

    const res = await getAlertDetail('alt-1');
    expect(res.alert.alert_id).toBe('alt-1');
  });

  it('getAlertDetail throws error on non-ok status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
    } as unknown as Response);

    await expect(getAlertDetail('alt-none')).rejects.toThrow('Failed to get alert detail: Not Found');
  });

  it('checkHealth returns health status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    } as unknown as Response);

    const res = await checkHealth();
    expect(res.api).toBe(true);
    expect(res.database).toBe(true);
  });

  it('checkHealth returns false on error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const res = await checkHealth();
    expect(res.api).toBe(false);
    expect(res.database).toBe(false);
  });
});

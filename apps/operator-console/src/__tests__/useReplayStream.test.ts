import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useReplayStream } from '../useReplayStream';

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(event: string, callback: (e: MessageEvent) => void) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }

  removeEventListener(event: string, callback: (e: MessageEvent) => void) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((cb) => cb !== callback);
    }
  }

  emit(event: string, data: unknown, lastEventId = '') {
    const messageEvent = {
      data: typeof data === 'string' ? data : JSON.stringify(data),
      lastEventId,
    } as MessageEvent;

    if (this.listeners[event]) {
      this.listeners[event].forEach((cb) => cb(messageEvent));
    }
  }

  close() {
    // closed
  }
}

describe('useReplayStream hook', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    (global as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('remains disconnected when replaySessionId is null', () => {
    const { result } = renderHook(() => useReplayStream(null));
    expect(result.current.connectionStatus).toBe('DISCONNECTED');
    expect(result.current.replay).toBeNull();
  });

  it('connects to stream and processes snapshot, score, telemetry, alert, status events', () => {
    const { result } = renderHook(() => useReplayStream('rep-123', 'http://127.0.0.1:8000'));
    expect(result.current.connectionStatus).toBe('CONNECTING');

    const es = MockEventSource.instances[0];
    expect(es).toBeDefined();

    act(() => {
      es.onopen?.();
    });
    expect(result.current.connectionStatus).toBe('CONNECTED');

    // Emit snapshot
    act(() => {
      es.emit(
        'snapshot',
        {
          replay: {
            replay_session_id: 'rep-123',
            state: 'RUNNING',
            model_version: 'v1',
          },
          alerts: [],
        },
        'snap-1'
      );
    });
    expect(result.current.replay?.replay_session_id).toBe('rep-123');
    expect(result.current.lastEventId).toBe('snap-1');

    // Emit score
    act(() => {
      es.emit(
        'score',
        {
          score: 1.5,
          threshold: 1.0,
          is_anomaly: true,
        },
        'score-1'
      );
    });
    expect(result.current.scores).toHaveLength(1);
    expect(result.current.scores[0].score).toBe(1.5);
    expect(result.current.lastEventId).toBe('score-1');

    // Emit telemetry
    act(() => {
      es.emit('telemetry', {
        machine_id: 'm1',
        tp2: 1.0,
        tp3: 2.0,
        h1: 0.5,
        oil_temperature: 50,
        motor_current: 3.0,
        comp: 1,
        towers: 1,
        mpg: 1,
      });
    });
    expect(result.current.telemetry).toHaveLength(1);

    // Emit new alert
    act(() => {
      es.emit(
        'alert',
        {
          alert_id: 'alt-1',
          replay_session_id: 'rep-123',
          machine_id: 'm1',
          state: 'OPEN',
          first_detection: '2020-04-18T00:00:00',
          last_detection: '2020-04-18T00:05:00',
        },
        'alert-1'
      );
    });
    expect(result.current.alerts).toHaveLength(1);
    expect(result.current.alerts[0].alert_id).toBe('alt-1');

    // Emit updated alert (state: RESOLVED)
    act(() => {
      es.emit(
        'alert',
        {
          alert_id: 'alt-1',
          replay_session_id: 'rep-123',
          machine_id: 'm1',
          state: 'RESOLVED',
          first_detection: '2020-04-18T00:00:00',
          last_detection: '2020-04-18T00:05:00',
          resolved_at: '2020-04-18T00:10:00',
        },
        'alert-2'
      );
    });
    expect(result.current.alerts).toHaveLength(1);
    expect(result.current.alerts[0].state).toBe('RESOLVED');

    // Emit status event
    act(() => {
      es.emit(
        'status',
        {
          state: 'PAUSED',
          last_sequence: 42,
          source_timestamp: '2020-04-18T00:10:00',
        },
        'status-1'
      );
    });
    expect(result.current.replay?.state).toBe('PAUSED');
    expect(result.current.replay?.last_sequence).toBe(42);

    // Emit resync_required
    act(() => {
      es.emit('resync_required', {});
    });
    expect(result.current.scores).toHaveLength(0);
    expect(result.current.telemetry).toHaveLength(0);
  });

  it('handles malformed events safely', () => {
    renderHook(() => useReplayStream('rep-123'));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit('snapshot', 'invalid-json');
      es.emit('score', 'invalid-json');
      es.emit('telemetry', 'invalid-json');
      es.emit('alert', 'invalid-json');
      es.emit('status', 'invalid-json');
    });
  });

  it('handles onerror and sets reconnecting state with timer', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useReplayStream('rep-123'));
    const es = MockEventSource.instances[0];

    act(() => {
      es.onerror?.();
    });
    expect(result.current.connectionStatus).toBe('DISCONNECTED');
    expect(result.current.error).toBe('Stream disconnected, reconnecting...');

    // Fast forward timer to trigger reconnect
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(MockEventSource.instances.length).toBe(2);

    vi.useRealTimers();
  });

  it('handles status event when replay is null', () => {
    renderHook(() => useReplayStream('rep-123'));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit('status', { state: 'RUNNING' });
    });
  });

  it('handles status event with undefined optional fields and retains prev fields', () => {
    const { result } = renderHook(() => useReplayStream('rep-123'));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit(
        'snapshot',
        {
          replay: {
            replay_session_id: 'rep-123',
            state: 'RUNNING',
            model_version: 'v1',
            last_sequence: 10,
            source_timestamp: '2020-04-18T00:00:00',
            error_code: null,
          },
          alerts: [],
        },
        'snap-1'
      );
    });

    act(() => {
      es.emit('status', { state: 'COMPLETED' }, 'status-2');
    });

    expect(result.current.replay?.state).toBe('COMPLETED');
    expect(result.current.replay?.last_sequence).toBe(10);
    expect(result.current.replay?.source_timestamp).toBe('2020-04-18T00:00:00');
  });

  it('ignores callbacks after unmount', () => {
    const { unmount } = renderHook(() => useReplayStream('rep-123'));
    const es = MockEventSource.instances[0];

    unmount();

    act(() => {
      es.onopen?.();
      es.emit('snapshot', {});
      es.emit('score', {});
      es.emit('telemetry', {});
      es.emit('alert', {});
      es.emit('status', {});
      es.emit('resync_required', {});
      es.onerror?.();
    });
  });
});

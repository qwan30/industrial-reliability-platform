import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '../App';

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

  close() {}
}

describe('App component integration', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    MockEventSource.instances = [];
    (global as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('renders header, panels, and allows manual session connect', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    } as unknown as Response);

    render(<App />);

    expect(screen.getByText(/Industrial Reliability Platform - Operator Console/i)).toBeInTheDocument();
    expect(screen.getByTestId('replay-controls')).toBeInTheDocument();
    expect(screen.getByTestId('dependency-health-panel')).toBeInTheDocument();
    expect(screen.getByTestId('live-charts')).toBeInTheDocument();
    expect(screen.getByTestId('alert-panel')).toBeInTheDocument();

    const input = screen.getByTestId('session-id-input');
    const connectBtn = screen.getByTestId('connect-session-btn');

    fireEvent.change(input, { target: { value: 'session-abc-123' } });
    fireEvent.click(connectBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
      expect(MockEventSource.instances[0].url).toContain('session-abc-123');
    });
  });

  it('starts replay through controls and establishes stream', async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/v1/replays') && !url.includes('/commands')) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: { replay_session_id: 'rep-uuid-999' },
          }),
        } as unknown as Response;
      }
      return {
        ok: true,
        json: async () => ({ status: 'ok' }),
      } as unknown as Response;
    });

    render(<App />);

    const startBtn = screen.getByTestId('start-replay-btn');
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
      expect(MockEventSource.instances[0].url).toContain('rep-uuid-999');
    });
  });
});

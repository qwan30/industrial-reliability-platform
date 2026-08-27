import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AlertPanel } from '../AlertPanel';
import { AlertSummary } from '../../types';

describe('AlertPanel component', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  const mockAlerts: AlertSummary[] = [
    {
      alert_id: 'alt-100',
      replay_session_id: 'rep-1',
      machine_id: 'metropt3',
      state: 'OPEN',
      first_detection: '2020-04-18T00:00:00',
      last_detection: '2020-04-18T00:05:00',
      resolved_at: null,
      latest_decision_id: 'dec-1',
      policy_sha256: 'c'.repeat(64),
    },
    {
      alert_id: 'alt-200',
      replay_session_id: 'rep-1',
      machine_id: 'metropt3',
      state: 'RESOLVED',
      first_detection: '2020-04-18T01:00:00',
      last_detection: '2020-04-18T01:05:00',
      resolved_at: '2020-04-18T01:10:00',
      latest_decision_id: 'dec-2',
      policy_sha256: 'd'.repeat(64),
    },
  ];

  it('renders empty placeholder when no alerts', () => {
    render(<AlertPanel alerts={[]} />);
    expect(screen.getByTestId('no-alerts')).toHaveTextContent(/no alerts detected/i);
  });

  it('renders alert list with status badges', () => {
    render(<AlertPanel alerts={mockAlerts} />);

    expect(screen.getByTestId('alert-item-alt-100')).toBeInTheDocument();
    expect(screen.getByTestId('alert-badge-alt-100')).toHaveTextContent('OPEN');
    expect(screen.getByTestId('alert-item-alt-200')).toBeInTheDocument();
    expect(screen.getByTestId('alert-badge-alt-200')).toHaveTextContent('RESOLVED');
  });

  it('fetches and expands alert detail, timeline, and decisions on click', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          alert: mockAlerts[0],
          events: [{ action: 'OPENED', source_timestamp: '2020-04-18T00:00:00' }],
          evidence: [
            { feature_name: 'tp2_mean', feature_value: 2.5, robust_deviation: 3.2 },
          ],
          decisions: [
            {
              decision_id: 'dec-1',
              source_timestamp: '2020-04-18T00:00:00',
              score: 1400.0,
              threshold: 1200.0,
              is_anomaly: true,
            },
          ],
          rca: null,
        },
      }),
    } as unknown as Response);

    render(<AlertPanel alerts={mockAlerts} />);

    const alertCard = screen.getByTestId('alert-item-alt-100');
    fireEvent.click(alertCard);

    await waitFor(() => {
      expect(screen.getByTestId('alert-detail-drawer')).toBeInTheDocument();
      expect(screen.getByTestId('evidence-table')).toBeInTheDocument();
      expect(screen.getByText('tp2_mean')).toBeInTheDocument();
      expect(screen.getByTestId('alert-event-timeline')).toHaveTextContent('OPENED');
      expect(screen.getByTestId('alert-decision-table')).toHaveTextContent('1400.000');
      expect(screen.getByTestId('alert-decision-table')).toHaveTextContent('1200.000');
    });

    // Clicking again collapses drawer
    fireEvent.click(alertCard);
    expect(screen.queryByTestId('alert-detail-drawer')).not.toBeInTheDocument();
  });


  it('displays error when fetching alert detail fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Server Error',
    } as unknown as Response);

    render(<AlertPanel alerts={mockAlerts} />);

    fireEvent.click(screen.getByTestId('alert-item-alt-100'));

    await waitFor(() => {
      expect(screen.getByText(/Failed to get alert detail: Server Error/i)).toBeInTheDocument();
    });
  });
});

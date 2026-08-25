import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RcaPanel } from '../RcaPanel';
import { RcaReportV1 } from '../../types';

describe('RcaPanel component', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  const sampleReport: RcaReportV1 = {
    schema_version: 'rca-report-v1',
    message_id: 'msg-1',
    replay_session_id: 'rep-1',
    source_dataset_sha256: '0'.repeat(64),
    contract_sha256: '1'.repeat(64),
    source_timestamp: '2020-04-18T00:05:00',
    emitted_at: '2020-04-18T00:05:01Z',
    report_id: 'rca-100',
    alert_id: 'alt-100',
    status: 'COMPLETE',
    summary: 'Elevated discharge pressure observed across compressor duty cycle.',
    observations: [
      {
        claim: 'tp2_mean deviation exceeded 1.5 bar baseline.',
        evidence_ids: ['evidence-111111111111111111111111'],
      },
    ],
    uncertainty: ['Anomaly evidence does not prove a mechanical root cause.'],
    next_checks: ['Inspect intake check valve.'],
    evidence_ids: ['evidence-111111111111111111111111'],
    evidence_bundle_sha256: 'b'.repeat(64),
    provider_model: 'gpt-4o',
  };

  it('renders initial empty state with Generate RCA button', () => {
    render(<RcaPanel alertId="alt-100" initialReport={null} />);
    expect(screen.getByTestId('rca-panel')).toBeInTheDocument();
    expect(screen.getByTestId('generate-rca-btn')).toBeInTheDocument();
    expect(screen.getByText(/No root-cause analysis has been generated/i)).toBeInTheDocument();
  });

  it('renders complete report when initialReport is provided', () => {
    render(<RcaPanel alertId="alt-100" initialReport={sampleReport} />);
    expect(screen.getByTestId('rca-status-badge')).toHaveTextContent('COMPLETE');
    expect(screen.getByTestId('rca-summary')).toHaveTextContent(/Elevated discharge pressure/i);
    expect(screen.getByTestId('rca-citation-badge')).toHaveTextContent('evidence-111111111111111111111111');
    expect(screen.getByTestId('rca-uncertainty')).toHaveTextContent(/does not prove a mechanical root cause/i);
  });

  it('calls generateRca on button click and renders generated report', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: sampleReport, error: null }),
    } as any);

    render(<RcaPanel alertId="alt-100" initialReport={null} />);
    const btn = screen.getByTestId('generate-rca-btn');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId('rca-status-badge')).toHaveTextContent('COMPLETE');
      expect(screen.getByTestId('rca-summary')).toHaveTextContent(/Elevated discharge pressure/i);
    });
  });

  it('handles generation error gracefully', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: 'Internal Server Error',
      json: async () => ({ error: { message: 'Provider timeout' } }),
    } as any);

    render(<RcaPanel alertId="alt-100" initialReport={null} />);
    fireEvent.click(screen.getByTestId('generate-rca-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('rca-error')).toHaveTextContent(/Provider timeout/i);
    });
  });
});

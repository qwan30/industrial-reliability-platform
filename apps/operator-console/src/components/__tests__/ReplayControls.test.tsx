import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReplayControls } from '../ReplayControls';
import { ReplaySession } from '../../types';

describe('ReplayControls component', () => {
  const mockReplay: ReplaySession = {
    replay_session_id: 'session-12345678',
    source_dataset_sha256: 'a'.repeat(64),
    contract_sha256: 'b'.repeat(64),
    model_version: 'champion-v1',
    state: 'RUNNING',
    last_sequence: 100,
    source_timestamp: '2020-04-18T01:00:00',
    error_code: null,
    updated_at: '2026-08-24T12:00:00',
  };

  it('renders start replay form when no active session', () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const onControl = vi.fn().mockResolvedValue(undefined);

    render(<ReplayControls replay={null} onStart={onStart} onControl={onControl} />);

    expect(screen.getByTestId('start-replay-btn')).toBeInTheDocument();
    expect(screen.getByLabelText(/start time/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/end time/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/speed/i)).toBeInTheDocument();
  });

  it('submits valid range on start button click', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const onControl = vi.fn().mockResolvedValue(undefined);

    render(<ReplayControls replay={null} onStart={onStart} onControl={onControl} />);

    const startBtn = screen.getByTestId('start-replay-btn');
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(onStart).toHaveBeenCalledWith(
        expect.objectContaining({
          speed: 100,
        })
      );
    });
  });

  it('displays error message when range is invalid', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const onControl = vi.fn().mockResolvedValue(undefined);

    render(<ReplayControls replay={null} onStart={onStart} onControl={onControl} />);

    const startInput = screen.getByLabelText(/start time/i);
    const endInput = screen.getByLabelText(/end time/i);

    fireEvent.change(startInput, { target: { value: '2020-04-18T05:00' } });
    fireEvent.change(endInput, { target: { value: '2020-04-18T01:00' } });

    const form = screen.getByTestId('replay-controls').querySelector('form');
    fireEvent.submit(form!);

    expect(screen.getByTestId('replay-error')).toHaveTextContent(/start time must precede/i);
  });

  it('renders active controls and state badge for RUNNING replay', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const onControl = vi.fn().mockResolvedValue(undefined);

    render(<ReplayControls replay={mockReplay} onStart={onStart} onControl={onControl} />);

    expect(screen.getByTestId('replay-state-badge')).toHaveTextContent('RUNNING');
    expect(screen.getByTestId('pause-replay-btn')).toBeInTheDocument();
    expect(screen.getByTestId('stop-replay-btn')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('pause-replay-btn'));
    await waitFor(() => {
      expect(onControl).toHaveBeenCalledWith('PAUSE');
    });

    fireEvent.click(screen.getByTestId('stop-replay-btn'));
    await waitFor(() => {
      expect(onControl).toHaveBeenCalledWith('STOP');
    });
  });

  it('renders resume button for PAUSED replay', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const onControl = vi.fn().mockResolvedValue(undefined);

    const pausedReplay: ReplaySession = { ...mockReplay, state: 'PAUSED' };
    render(<ReplayControls replay={pausedReplay} onStart={onStart} onControl={onControl} />);

    expect(screen.getByTestId('replay-state-badge')).toHaveTextContent('PAUSED');
    expect(screen.getByTestId('resume-replay-btn')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('resume-replay-btn'));
    await waitFor(() => {
      expect(onControl).toHaveBeenCalledWith('RESUME');
    });
  });

  it('displays error when onStart rejects', async () => {
    const onStart = vi.fn().mockRejectedValue(new Error('Network error starting replay'));
    const onControl = vi.fn().mockResolvedValue(undefined);

    render(<ReplayControls replay={null} onStart={onStart} onControl={onControl} />);

    fireEvent.click(screen.getByTestId('start-replay-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('replay-error')).toHaveTextContent('Network error starting replay');
    });
  });

  it('displays error when onControl rejects', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    const onControl = vi.fn().mockRejectedValue(new Error('Failed to stop'));

    render(<ReplayControls replay={mockReplay} onStart={onStart} onControl={onControl} />);

    fireEvent.click(screen.getByTestId('stop-replay-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('replay-error')).toHaveTextContent('Failed to stop');
    });
  });
});

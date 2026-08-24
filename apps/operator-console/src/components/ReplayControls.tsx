import React, { useState } from 'react';
import { ReplaySession, StartReplayParams } from '../types';

export interface ReplayControlsProps {
  replay: ReplaySession | null;
  onStart: (params: StartReplayParams) => Promise<void>;
  onControl: (action: 'PAUSE' | 'RESUME' | 'STOP') => Promise<void>;
  disabled?: boolean;
}

export function ReplayControls({
  replay,
  onStart,
  onControl,
  disabled = false,
}: ReplayControlsProps) {
  const [rangeStart, setRangeStart] = useState('2020-04-17T23:00');
  const [rangeEnd, setRangeEnd] = useState('2020-04-18T03:00');
  const [speed, setSpeed] = useState<1 | 100 | 1000>(100);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isValidRange = rangeStart < rangeEnd;
  const isRunning = replay?.state === 'RUNNING';
  const isPaused = replay?.state === 'PAUSED';
  const hasActiveSession = Boolean(replay && (isRunning || isPaused));

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValidRange) {
      setErrorMessage('Start time must precede end time');
      return;
    }
    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      await onStart({
        range_start: rangeStart,
        range_end: rangeEnd,
        speed,
      });
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to start replay');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleControl = async (action: 'PAUSE' | 'RESUME' | 'STOP') => {
    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      await onControl(action);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : `Failed to ${action}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section
      data-testid="replay-controls"
      style={{
        backgroundColor: '#1e293b',
        borderRadius: '8px',
        padding: '1.25rem',
        border: '1px solid #334155',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#f8fafc' }}>
          Replay Control Plane
        </h2>
        {replay && (
          <span
            data-testid="replay-state-badge"
            style={{
              padding: '0.25rem 0.625rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              backgroundColor:
                replay.state === 'RUNNING'
                  ? '#065f46'
                  : replay.state === 'PAUSED'
                  ? '#854d0e'
                  : replay.state === 'COMPLETED'
                  ? '#1e3a8a'
                  : '#374151',
              color: '#f8fafc',
            }}
          >
            {replay.state}
          </span>
        )}
      </div>

      <form
        onSubmit={handleStart}
        style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label htmlFor="range-start-input" style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Start Time
          </label>
          <input
            id="range-start-input"
            type="datetime-local"
            value={rangeStart}
            onChange={(e) => setRangeStart(e.target.value)}
            disabled={disabled || hasActiveSession || isSubmitting}
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#f8fafc',
              padding: '0.375rem 0.5rem',
              fontSize: '0.875rem',
            }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label htmlFor="range-end-input" style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            End Time
          </label>
          <input
            id="range-end-input"
            type="datetime-local"
            value={rangeEnd}
            onChange={(e) => setRangeEnd(e.target.value)}
            disabled={disabled || hasActiveSession || isSubmitting}
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#f8fafc',
              padding: '0.375rem 0.5rem',
              fontSize: '0.875rem',
            }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label htmlFor="speed-select" style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Speed
          </label>
          <select
            id="speed-select"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value) as 1 | 100 | 1000)}
            disabled={disabled || hasActiveSession || isSubmitting}
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#f8fafc',
              padding: '0.375rem 0.5rem',
              fontSize: '0.875rem',
            }}
          >
            <option value={1}>1x (Realtime)</option>
            <option value={100}>100x</option>
            <option value={1000}>1000x</option>
          </select>
        </div>

        {!hasActiveSession ? (
          <button
            type="submit"
            data-testid="start-replay-btn"
            disabled={disabled || isSubmitting || !isValidRange}
            style={{
              backgroundColor: '#0284c7',
              color: '#ffffff',
              border: 'none',
              borderRadius: '4px',
              padding: '0.45rem 1rem',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: disabled || isSubmitting || !isValidRange ? 'not-allowed' : 'pointer',
              opacity: disabled || isSubmitting || !isValidRange ? 0.6 : 1,
            }}
          >
            Start Replay
          </button>
        ) : (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {isRunning && (
              <button
                type="button"
                data-testid="pause-replay-btn"
                onClick={() => handleControl('PAUSE')}
                disabled={disabled || isSubmitting}
                style={{
                  backgroundColor: '#f59e0b',
                  color: '#000000',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '0.45rem 0.875rem',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Pause
              </button>
            )}
            {isPaused && (
              <button
                type="button"
                data-testid="resume-replay-btn"
                onClick={() => handleControl('RESUME')}
                disabled={disabled || isSubmitting}
                style={{
                  backgroundColor: '#10b981',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '0.45rem 0.875rem',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Resume
              </button>
            )}
            <button
              type="button"
              data-testid="stop-replay-btn"
              onClick={() => handleControl('STOP')}
              disabled={disabled || isSubmitting}
              style={{
                backgroundColor: '#ef4444',
                color: '#ffffff',
                border: 'none',
                borderRadius: '4px',
                padding: '0.45rem 0.875rem',
                fontSize: '0.875rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Stop
            </button>
          </div>
        )}
      </form>

      {errorMessage && (
        <div data-testid="replay-error" style={{ color: '#ef4444', fontSize: '0.875rem' }}>
          {errorMessage}
        </div>
      )}

      {replay && (
        <div
          data-testid="replay-telemetry-info"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '0.5rem',
            fontSize: '0.8125rem',
            color: '#94a3b8',
            borderTop: '1px solid #334155',
            paddingTop: '0.75rem',
          }}
        >
          <div>
            Session: <strong style={{ color: '#f8fafc' }}>{replay.replay_session_id.slice(0, 8)}...</strong>
          </div>
          <div>
            Source Time: <strong style={{ color: '#f8fafc' }}>{replay.source_timestamp || 'N/A'}</strong>
          </div>
          <div>
            Sequence: <strong style={{ color: '#f8fafc' }}>{replay.last_sequence ?? 'N/A'}</strong>
          </div>
          <div>
            Model: <strong style={{ color: '#f8fafc' }}>{replay.model_version}</strong>
          </div>
        </div>
      )}
    </section>
  );
}

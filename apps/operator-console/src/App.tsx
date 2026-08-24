import { useEffect, useState, type FormEvent } from 'react';
import { checkHealth, controlReplay, startReplay } from './api';
import { AlertPanel } from './components/AlertPanel';
import { DependencyHealthPanel } from './components/DependencyHealthPanel';
import { LiveCharts } from './components/LiveCharts';
import { ReplayControls } from './components/ReplayControls';
import { DependencyHealth, StartReplayParams } from './types';
import { useReplayStream } from './useReplayStream';

export function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [manualSessionInput, setManualSessionInput] = useState('');
  const [health, setHealth] = useState<DependencyHealth>({ api: true, database: true });

  const { connectionStatus, replay, alerts, scores, telemetry, lastEventId, error } =
    useReplayStream(sessionId);

  useEffect(() => {
    let isMounted = true;
    const pollHealth = async () => {
      const h = await checkHealth();
      if (isMounted) setHealth(h);
    };

    pollHealth();
    const interval = setInterval(pollHealth, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleStart = async (params: StartReplayParams) => {
    const res = await startReplay(params);
    setSessionId(res.replay_session_id);
    setManualSessionInput(res.replay_session_id);
  };

  const handleControl = async (action: 'PAUSE' | 'RESUME' | 'STOP') => {
    if (!sessionId) return;
    await controlReplay(sessionId, action);
  };

  const handleManualSessionSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (manualSessionInput.trim()) {
      setSessionId(manualSessionInput.trim());
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#0f172a',
        color: '#f8fafc',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* App Header */}
      <header
        style={{
          borderBottom: '1px solid #334155',
          backgroundColor: '#1e293b',
          padding: '1rem 1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: '#38bdf8',
              boxShadow: '0 0 10px #38bdf8',
            }}
          />
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.025em' }}>
            Industrial Reliability Platform - Operator Console
          </h1>
        </div>

        <form
          onSubmit={handleManualSessionSubmit}
          style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}
        >
          <input
            type="text"
            data-testid="session-id-input"
            placeholder="Replay Session UUID"
            value={manualSessionInput}
            onChange={(e) => setManualSessionInput(e.target.value)}
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#f8fafc',
              padding: '0.35rem 0.6rem',
              fontSize: '0.8125rem',
              width: '240px',
            }}
          />
          <button
            type="submit"
            data-testid="connect-session-btn"
            style={{
              backgroundColor: '#334155',
              color: '#f8fafc',
              border: '1px solid #475569',
              borderRadius: '4px',
              padding: '0.35rem 0.75rem',
              fontSize: '0.8125rem',
              cursor: 'pointer',
            }}
          >
            Connect
          </button>
        </form>
      </header>

      {/* Main Grid Layout */}
      <main
        style={{
          flex: 1,
          padding: '1.5rem',
          display: 'grid',
          gridTemplateColumns: 'minmax(300px, 360px) minmax(500px, 1fr) minmax(320px, 380px)',
          gap: '1.5rem',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Replay Controls & Health */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <ReplayControls
            replay={replay}
            onStart={handleStart}
            onControl={handleControl}
            disabled={!health.api}
          />
          <DependencyHealthPanel
            health={health}
            connectionStatus={connectionStatus}
            lastEventId={lastEventId}
          />
          {error && (
            <div
              data-testid="stream-error-banner"
              style={{
                backgroundColor: '#7f1d1d',
                color: '#fca5a5',
                padding: '0.75rem',
                borderRadius: '6px',
                fontSize: '0.8125rem',
              }}
            >
              {error}
            </div>
          )}
        </div>

        {/* Center Column: Live Charts */}
        <div>
          <LiveCharts scores={scores} telemetry={telemetry} />
        </div>

        {/* Right Column: Alert Evidence Panel */}
        <div>
          <AlertPanel alerts={alerts} />
        </div>
      </main>
    </div>
  );
}

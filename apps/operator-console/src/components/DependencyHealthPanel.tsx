import React from 'react';
import { ConnectionStatus, DependencyHealth } from '../types';

export interface DependencyHealthPanelProps {
  health: DependencyHealth;
  connectionStatus: ConnectionStatus;
  lastEventId: string | null;
}

export function DependencyHealthPanel({
  health,
  connectionStatus,
  lastEventId,
}: DependencyHealthPanelProps) {
  const getStatusColor = (status: ConnectionStatus) => {
    switch (status) {
      case 'CONNECTED':
        return '#10b981';
      case 'CONNECTING':
      case 'RECONNECTING':
        return '#f59e0b';
      case 'DISCONNECTED':
      default:
        return '#ef4444';
    }
  };

  return (
    <aside
      data-testid="dependency-health-panel"
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
      <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#f8fafc' }}>
        System Health & Links
      </h2>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.875rem', color: '#94a3b8' }}>API Gateway</span>
          <span
            data-testid="health-api-badge"
            style={{
              padding: '0.2rem 0.5rem',
              borderRadius: '4px',
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: health.api ? '#065f46' : '#7f1d1d',
              color: health.api ? '#6ee7b7' : '#fca5a5',
            }}
          >
            {health.api ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.875rem', color: '#94a3b8' }}>PostgreSQL Store</span>
          <span
            data-testid="health-db-badge"
            style={{
              padding: '0.2rem 0.5rem',
              borderRadius: '4px',
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: health.database ? '#065f46' : '#7f1d1d',
              color: health.database ? '#6ee7b7' : '#fca5a5',
            }}
          >
            {health.database ? 'READY' : 'UNREACHABLE'}
          </span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.875rem', color: '#94a3b8' }}>SSE Stream</span>
          <span
            data-testid="stream-status-badge"
            style={{
              padding: '0.2rem 0.5rem',
              borderRadius: '4px',
              fontSize: '0.75rem',
              fontWeight: 700,
              color: '#ffffff',
              backgroundColor: getStatusColor(connectionStatus),
            }}
          >
            {connectionStatus}
          </span>
        </div>

        {lastEventId && (
          <div
            style={{
              fontSize: '0.75rem',
              color: '#64748b',
              marginTop: '0.25rem',
              wordBreak: 'break-all',
            }}
          >
            Last Event ID: <span style={{ color: '#94a3b8' }}>{lastEventId}</span>
          </div>
        )}
      </div>
    </aside>
  );
}

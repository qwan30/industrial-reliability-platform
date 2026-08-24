import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DependencyHealthPanel } from '../DependencyHealthPanel';

describe('DependencyHealthPanel component', () => {
  it('renders online badges and connected stream status', () => {
    render(
      <DependencyHealthPanel
        health={{ api: true, database: true }}
        connectionStatus="CONNECTED"
        lastEventId="event-999"
      />
    );

    expect(screen.getByTestId('health-api-badge')).toHaveTextContent('ONLINE');
    expect(screen.getByTestId('health-db-badge')).toHaveTextContent('READY');
    expect(screen.getByTestId('stream-status-badge')).toHaveTextContent('CONNECTED');
    expect(screen.getByText(/event-999/)).toBeInTheDocument();
  });

  it('renders offline badges when health checks fail', () => {
    render(
      <DependencyHealthPanel
        health={{ api: false, database: false }}
        connectionStatus="DISCONNECTED"
        lastEventId={null}
      />
    );

    expect(screen.getByTestId('health-api-badge')).toHaveTextContent('OFFLINE');
    expect(screen.getByTestId('health-db-badge')).toHaveTextContent('UNREACHABLE');
    expect(screen.getByTestId('stream-status-badge')).toHaveTextContent('DISCONNECTED');
  });

  it('renders reconnecting stream status badge', () => {
    render(
      <DependencyHealthPanel
        health={{ api: true, database: true }}
        connectionStatus="RECONNECTING"
        lastEventId={null}
      />
    );

    expect(screen.getByTestId('stream-status-badge')).toHaveTextContent('RECONNECTING');
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LiveCharts } from '../LiveCharts';
import { ScorePayload, TelemetryPayload } from '../../types';

describe('LiveCharts component', () => {
  it('renders placeholders when data streams are empty', () => {
    render(<LiveCharts scores={[]} telemetry={[]} />);

    expect(screen.getByTestId('no-score-data')).toBeInTheDocument();
    expect(screen.getByTestId('no-telemetry-data')).toBeInTheDocument();
  });

  it('renders SVG score chart and threshold line when scores present', () => {
    const scores: ScorePayload[] = [
      { score: 0.5, threshold: 1.0, is_anomaly: false, source_timestamp: '2020-04-18T00:00:00' },
      { score: 1.8, threshold: 1.0, is_anomaly: true, source_timestamp: '2020-04-18T00:05:00' },
    ];
    const telemetry: TelemetryPayload[] = [
      { machine_id: 'm1', tp2: 2.5, tp3: 3.5, h1: 1.0, oil_temperature: 65, motor_current: 4.0, comp: 1, towers: 1, mpg: 1 },
      { machine_id: 'm1', tp2: 2.8, tp3: 3.8, h1: 1.1, oil_temperature: 66, motor_current: 4.2, comp: 1, towers: 1, mpg: 1 },
    ];

    render(<LiveCharts scores={scores} telemetry={telemetry} />);

    expect(screen.getByTestId('score-svg-chart')).toBeInTheDocument();
    expect(screen.getByTestId('threshold-line')).toBeInTheDocument();
    expect(screen.getByTestId('score-polyline')).toBeInTheDocument();
    expect(screen.getByTestId('score-dot-0')).toBeInTheDocument();
    expect(screen.getByTestId('score-dot-1')).toBeInTheDocument();

    // Hover tooltip for score
    fireEvent.mouseEnter(screen.getByTestId('score-dot-1'));
    expect(screen.getByTestId('score-tooltip')).toHaveTextContent('YES');
    fireEvent.mouseLeave(screen.getByTestId('score-dot-1'));

    // Telemetry chart checks
    expect(screen.getByTestId('telemetry-svg-chart')).toBeInTheDocument();
    expect(screen.getByTestId('telem-tp2-line')).toBeInTheDocument();
  });
});

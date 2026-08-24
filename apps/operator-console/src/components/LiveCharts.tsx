import { useState } from 'react';
import { ScorePayload, TelemetryPayload } from '../types';

export interface LiveChartsProps {
  scores: ScorePayload[];
  telemetry: TelemetryPayload[];
}

export function LiveCharts({ scores, telemetry }: LiveChartsProps) {
  const [hoveredScoreIdx, setHoveredScoreIdx] = useState<number | null>(null);
  const [hoveredTelemIdx, setHoveredTelemIdx] = useState<number | null>(null);

  const width = 640;
  const height = 180;
  const padding = { top: 20, right: 30, bottom: 30, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // Score Chart Math
  const maxScore = Math.max(2.5, ...scores.map((s) => s.score));
  const minScore = 0;
  const scoreY = (val: number) =>
    padding.top + chartH - ((val - minScore) / (maxScore - minScore)) * chartH;
  const scoreX = (idx: number) =>
    padding.left + (scores.length > 1 ? (idx / (scores.length - 1)) * chartW : chartW / 2);

  const scorePoints = scores
    .map((s, i) => `${scoreX(i).toFixed(1)},${scoreY(s.score).toFixed(1)}`)
    .join(' ');

  const thresholdY = scoreY(1.0);

  // Telemetry Chart Math
  const maxTelem = Math.max(10, ...telemetry.map((t) => Math.max(t.tp2, t.tp3, t.oil_temperature / 10, t.motor_current)));
  const minTelem = 0;
  const telemY = (val: number) =>
    padding.top + chartH - ((val - minTelem) / (maxTelem - minTelem)) * chartH;
  const telemX = (idx: number) =>
    padding.left + (telemetry.length > 1 ? (idx / (telemetry.length - 1)) * chartW : chartW / 2);

  const tp2Points = telemetry
    .map((t, i) => `${telemX(i).toFixed(1)},${telemY(t.tp2).toFixed(1)}`)
    .join(' ');
  const tp3Points = telemetry
    .map((t, i) => `${telemX(i).toFixed(1)},${telemY(t.tp3).toFixed(1)}`)
    .join(' ');
  const oilPoints = telemetry
    .map((t, i) => `${telemX(i).toFixed(1)},${telemY(t.oil_temperature / 10).toFixed(1)}`)
    .join(' ');

  return (
    <section
      data-testid="live-charts"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
      }}
    >
      {/* Anomaly Score Chart */}
      <div
        data-testid="score-chart-container"
        style={{
          backgroundColor: '#1e293b',
          borderRadius: '8px',
          padding: '1rem',
          border: '1px solid #334155',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#f8fafc' }}>
            Live Anomaly Score & Robust Threshold
          </h3>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Threshold: <strong style={{ color: '#ef4444' }}>1.0</strong> | Points: {scores.length}
          </span>
        </div>

        {scores.length === 0 ? (
          <div
            data-testid="no-score-data"
            style={{
              height: `${height}px`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#64748b',
              fontSize: '0.875rem',
            }}
          >
            Awaiting score stream data...
          </div>
        ) : (
          <div style={{ position: 'relative' }}>
            <svg
              data-testid="score-svg-chart"
              viewBox={`0 0 ${width} ${height}`}
              style={{ width: '100%', height: 'auto', overflow: 'visible' }}
            >
              {/* Grid Lines */}
              <line
                x1={padding.left}
                y1={padding.top + chartH}
                x2={padding.left + chartW}
                y2={padding.top + chartH}
                stroke="#334155"
                strokeWidth="1"
              />
              <line
                x1={padding.left}
                y1={padding.top}
                x2={padding.left}
                y2={padding.top + chartH}
                stroke="#334155"
                strokeWidth="1"
              />

              {/* Threshold Line */}
              <line
                data-testid="threshold-line"
                x1={padding.left}
                y1={thresholdY}
                x2={padding.left + chartW}
                y2={thresholdY}
                stroke="#ef4444"
                strokeWidth="2"
                strokeDasharray="4 4"
              />
              <text
                x={padding.left + 5}
                y={thresholdY - 5}
                fill="#ef4444"
                fontSize="10"
                fontWeight="bold"
              >
                Threshold 1.0
              </text>

              {/* Score Polyline */}
              {scores.length > 1 && (
                <polyline
                  data-testid="score-polyline"
                  fill="none"
                  stroke="#38bdf8"
                  strokeWidth="2"
                  points={scorePoints}
                />
              )}

              {/* Data Points */}
              {scores.map((s, idx) => {
                const cx = scoreX(idx);
                const cy = scoreY(s.score);
                const isHovered = hoveredScoreIdx === idx;
                return (
                  <circle
                    key={idx}
                    data-testid={`score-dot-${idx}`}
                    cx={cx}
                    cy={cy}
                    r={s.is_anomaly ? 5 : isHovered ? 4 : 2}
                    fill={s.is_anomaly ? '#ef4444' : '#38bdf8'}
                    stroke={s.is_anomaly ? '#ffffff' : 'none'}
                    strokeWidth={s.is_anomaly ? 1.5 : 0}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredScoreIdx(idx)}
                    onMouseLeave={() => setHoveredScoreIdx(null)}
                  />
                );
              })}
            </svg>

            {hoveredScoreIdx !== null && scores[hoveredScoreIdx] && (
              <div
                data-testid="score-tooltip"
                style={{
                  position: 'absolute',
                  top: '10px',
                  right: '10px',
                  backgroundColor: '#0f172a',
                  border: '1px solid #475569',
                  borderRadius: '4px',
                  padding: '0.5rem',
                  fontSize: '0.75rem',
                  color: '#f8fafc',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
                }}
              >
                <div>Score: <strong>{scores[hoveredScoreIdx].score.toFixed(4)}</strong></div>
                <div>Anomaly: <strong>{scores[hoveredScoreIdx].is_anomaly ? 'YES' : 'NO'}</strong></div>
                {scores[hoveredScoreIdx].source_timestamp && (
                  <div>Time: {scores[hoveredScoreIdx].source_timestamp}</div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Telemetry Multi-Signal Chart */}
      <div
        data-testid="telemetry-chart-container"
        style={{
          backgroundColor: '#1e293b',
          borderRadius: '8px',
          padding: '1rem',
          border: '1px solid #334155',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#f8fafc' }}>
            Downsampled Analog Telemetry Signals
          </h3>
          <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem' }}>
            <span style={{ color: '#38bdf8' }}>● TP2 (bar)</span>
            <span style={{ color: '#34d399' }}>● TP3 (bar)</span>
            <span style={{ color: '#fbbf24' }}>● Oil Temp / 10 (°C)</span>
          </div>
        </div>

        {telemetry.length === 0 ? (
          <div
            data-testid="no-telemetry-data"
            style={{
              height: `${height}px`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#64748b',
              fontSize: '0.875rem',
            }}
          >
            Awaiting telemetry stream data...
          </div>
        ) : (
          <div style={{ position: 'relative' }}>
            <svg
              data-testid="telemetry-svg-chart"
              viewBox={`0 0 ${width} ${height}`}
              style={{ width: '100%', height: 'auto', overflow: 'visible' }}
            >
              {/* Grid Lines */}
              <line
                x1={padding.left}
                y1={padding.top + chartH}
                x2={padding.left + chartW}
                y2={padding.top + chartH}
                stroke="#334155"
                strokeWidth="1"
              />
              <line
                x1={padding.left}
                y1={padding.top}
                x2={padding.left}
                y2={padding.top + chartH}
                stroke="#334155"
                strokeWidth="1"
              />

              {/* Signals */}
              {telemetry.length > 1 && (
                <>
                  <polyline
                    data-testid="telem-tp2-line"
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="1.5"
                    points={tp2Points}
                  />
                  <polyline
                    data-testid="telem-tp3-line"
                    fill="none"
                    stroke="#34d399"
                    strokeWidth="1.5"
                    points={tp3Points}
                  />
                  <polyline
                    data-testid="telem-oil-line"
                    fill="none"
                    stroke="#fbbf24"
                    strokeWidth="1.5"
                    points={oilPoints}
                  />
                </>
              )}

              {/* Interactive points */}
              {telemetry.map((t, idx) => {
                const cx = telemX(idx);
                const cy = telemY(t.tp2);
                return (
                  <circle
                    key={idx}
                    cx={cx}
                    cy={cy}
                    r={hoveredTelemIdx === idx ? 4 : 2}
                    fill="#38bdf8"
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoveredTelemIdx(idx)}
                    onMouseLeave={() => setHoveredTelemIdx(null)}
                  />
                );
              })}
            </svg>

            {hoveredTelemIdx !== null && telemetry[hoveredTelemIdx] && (
              <div
                data-testid="telemetry-tooltip"
                style={{
                  position: 'absolute',
                  top: '10px',
                  right: '10px',
                  backgroundColor: '#0f172a',
                  border: '1px solid #475569',
                  borderRadius: '4px',
                  padding: '0.5rem',
                  fontSize: '0.75rem',
                  color: '#f8fafc',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
                }}
              >
                <div>Machine: <strong>{telemetry[hoveredTelemIdx].machine_id}</strong></div>
                <div>TP2: <strong>{telemetry[hoveredTelemIdx].tp2.toFixed(2)} bar</strong></div>
                <div>TP3: <strong>{telemetry[hoveredTelemIdx].tp3.toFixed(2)} bar</strong></div>
                <div>Oil Temp: <strong>{telemetry[hoveredTelemIdx].oil_temperature.toFixed(1)} °C</strong></div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

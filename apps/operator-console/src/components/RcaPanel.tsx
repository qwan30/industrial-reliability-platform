import React, { useState } from 'react';
import { RcaReportV1 } from '../types';
import { generateRca } from '../api';

interface RcaPanelProps {
  alertId: string;
  initialReport: RcaReportV1 | null;
  baseUrl?: string;
}

export const RcaPanel: React.FC<RcaPanelProps> = ({
  alertId,
  initialReport,
  baseUrl,
}) => {
  const [report, setReport] = useState<RcaReportV1 | null>(initialReport);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const generated = await generateRca(alertId, baseUrl);
      setReport(generated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate root-cause analysis');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        backgroundColor: '#1e293b',
        border: '1px solid #334155',
        borderRadius: '0.5rem',
        padding: '1rem',
        marginTop: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
      data-testid="rca-panel"
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <h4 style={{ margin: 0, fontSize: '0.875rem', fontWeight: 600, color: '#f8fafc' }}>
            Grounded Root-Cause Analysis
          </h4>
          {report && (
            <span
              style={{
                padding: '0.125rem 0.5rem',
                fontSize: '0.75rem',
                fontWeight: 500,
                borderRadius: '9999px',
                backgroundColor: report.status === 'COMPLETE' ? '#064e3b' : '#78350f',
                color: report.status === 'COMPLETE' ? '#10b981' : '#f59e0b',
                border: `1px solid ${report.status === 'COMPLETE' ? '#047857' : '#b45309'}`,
              }}
              data-testid="rca-status-badge"
            >
              {report.status}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={isLoading}
          aria-busy={isLoading}
          style={{
            padding: '0.25rem 0.75rem',
            fontSize: '0.75rem',
            fontWeight: 500,
            backgroundColor: isLoading ? '#1e3a8a' : '#2563eb',
            opacity: isLoading ? 0.6 : 1.0,
            color: '#ffffff',
            borderRadius: '0.25rem',
            border: 'none',
            cursor: isLoading ? 'not-allowed' : 'pointer',
          }}
          data-testid="generate-rca-btn"
        >
          {isLoading ? 'Generating RCA...' : report ? 'Regenerate RCA' : 'Generate RCA'}
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: '0.5rem',
            fontSize: '0.75rem',
            backgroundColor: '#4c0519',
            border: '1px solid #9f1239',
            color: '#fda4af',
            borderRadius: '0.25rem',
          }}
          data-testid="rca-error"
        >
          {error}
        </div>
      )}

      {report ? (
        <div
          aria-live="polite"
          style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.75rem' }}
          data-testid="rca-content"
        >
          <div
            style={{
              padding: '0.75rem',
              backgroundColor: '#0f172a',
              borderRadius: '0.25rem',
              border: '1px solid #334155',
            }}
          >
            <span style={{ fontWeight: 600, color: '#94a3b8', display: 'block', marginBottom: '0.25rem' }}>
              Executive Summary
            </span>
            <p style={{ margin: 0, color: '#f8fafc', lineHeight: 1.5 }} data-testid="rca-summary">
              {report.summary}
            </p>
          </div>

          {report.observations.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span style={{ fontWeight: 600, color: '#94a3b8', display: 'block' }}>
                Grounded Observations
              </span>
              <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.375rem' }} data-testid="rca-observations">
                {report.observations.map((obs, idx) => (
                  <li
                    key={idx}
                    style={{
                      padding: '0.5rem',
                      backgroundColor: '#0f172a',
                      borderRadius: '0.25rem',
                      border: '1px solid #334155',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.25rem',
                    }}
                  >
                    <span style={{ color: '#f8fafc' }}>{obs.claim}</span>
                    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.25rem', marginTop: '0.25rem' }}>
                      <span style={{ fontSize: '0.625rem', color: '#94a3b8' }}>Citations:</span>
                      {obs.evidence_ids.map((evId) => (
                        <span
                          key={evId}
                          style={{
                            padding: '0.125rem 0.375rem',
                            backgroundColor: '#334155',
                            color: '#38bdf8',
                            borderRadius: '0.25rem',
                            fontSize: '0.625rem',
                            fontFamily: 'monospace',
                          }}
                          data-testid="rca-citation-badge"
                        >
                          {evId}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.uncertainty.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span style={{ fontWeight: 600, color: '#94a3b8', display: 'block' }}>
                Uncertainty & Limitations
              </span>
              <ul style={{ margin: 0, paddingLeft: '1rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.125rem' }} data-testid="rca-uncertainty">
                {report.uncertainty.map((u, idx) => (
                  <li key={idx}>{u}</li>
                ))}
              </ul>
            </div>
          )}

          {report.next_checks.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span style={{ fontWeight: 600, color: '#94a3b8', display: 'block' }}>
                Recommended Checks
              </span>
              <ul style={{ margin: 0, paddingLeft: '1rem', color: '#f8fafc', display: 'flex', flexDirection: 'column', gap: '0.125rem' }} data-testid="rca-next-checks">
                {report.next_checks.map((nc, idx) => (
                  <li key={idx}>{nc}</li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ paddingTop: '0.5rem', borderTop: '1px solid #334155', fontSize: '0.625rem', color: '#94a3b8', display: 'flex', justifyContent: 'space-between' }}>
            <span>Bundle SHA: {report.evidence_bundle_sha256.substring(0, 12)}...</span>
            {report.provider_model && <span>Model: {report.provider_model}</span>}
          </div>
        </div>
      ) : (
        <p style={{ margin: 0, fontSize: '0.75rem', color: '#94a3b8', fontStyle: 'italic' }}>
          No root-cause analysis has been generated for this alert yet. Click "Generate RCA" to inspect grounded telemetry evidence.
        </p>
      )}
    </div>
  );
};


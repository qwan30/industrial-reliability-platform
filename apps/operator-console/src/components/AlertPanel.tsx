import { useState } from 'react';
import { AlertDetail, AlertSummary } from '../types';
import { getAlertDetail } from '../api';

export interface AlertPanelProps {
  alerts: AlertSummary[];
  baseUrl?: string;
}

export function AlertPanel({ alerts, baseUrl = '' }: AlertPanelProps) {
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [alertDetail, setAlertDetail] = useState<AlertDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const handleSelectAlert = async (alertId: string) => {
    if (selectedAlertId === alertId) {
      setSelectedAlertId(null);
      setAlertDetail(null);
      return;
    }
    setSelectedAlertId(alertId);
    setIsLoadingDetail(true);
    setDetailError(null);
    try {
      const detail = await getAlertDetail(alertId, baseUrl);
      setAlertDetail(detail);
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : 'Failed to fetch alert details');
      setAlertDetail(null);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  return (
    <section
      data-testid="alert-panel"
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
          Alert Lifecycle & Evidence
        </h2>
        <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
          Total: <strong>{alerts.length}</strong>
        </span>
      </div>

      {alerts.length === 0 ? (
        <div
          data-testid="no-alerts"
          style={{
            padding: '2rem 1rem',
            textAlign: 'center',
            color: '#64748b',
            fontSize: '0.875rem',
          }}
        >
          No alerts detected for current session.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {alerts.map((alert) => {
            const isSelected = selectedAlertId === alert.alert_id;
            return (
              <div
                key={alert.alert_id}
                data-testid={`alert-item-${alert.alert_id}`}
                onClick={() => handleSelectAlert(alert.alert_id)}
                style={{
                  backgroundColor: isSelected ? '#334155' : '#0f172a',
                  border: `1px solid ${isSelected ? '#38bdf8' : '#475569'}`,
                  borderRadius: '6px',
                  padding: '0.75rem',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span
                      data-testid={`alert-badge-${alert.alert_id}`}
                      style={{
                        padding: '0.15rem 0.45rem',
                        borderRadius: '4px',
                        fontSize: '0.6875rem',
                        fontWeight: 700,
                        backgroundColor: alert.state === 'OPEN' ? '#ef4444' : '#10b981',
                        color: '#ffffff',
                      }}
                    >
                      {alert.state}
                    </span>
                    <strong style={{ fontSize: '0.875rem', color: '#f8fafc' }}>
                      {alert.machine_id}
                    </strong>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                    ID: {alert.alert_id.slice(0, 8)}...
                  </span>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginTop: '0.5rem',
                    fontSize: '0.75rem',
                    color: '#94a3b8',
                  }}
                >
                  <span>First: {alert.first_detection}</span>
                  <span>Last: {alert.last_detection}</span>
                </div>

                {isSelected && (
                  <div
                    data-testid="alert-detail-drawer"
                    style={{
                      marginTop: '0.75rem',
                      paddingTop: '0.75rem',
                      borderTop: '1px solid #475569',
                      fontSize: '0.8125rem',
                      color: '#f8fafc',
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {isLoadingDetail && <div>Loading evidence details...</div>}
                    {detailError && <div style={{ color: '#ef4444' }}>{detailError}</div>}
                    {alertDetail && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div style={{ fontWeight: 600, color: '#38bdf8' }}>
                          Evidence Attribution:
                        </div>
                        {alertDetail.evidence && alertDetail.evidence.length > 0 ? (
                          <table
                            data-testid="evidence-table"
                            style={{
                              width: '100%',
                              borderCollapse: 'collapse',
                              fontSize: '0.75rem',
                            }}
                          >
                            <thead>
                              <tr style={{ borderBottom: '1px solid #475569', textAlign: 'left' }}>
                                <th style={{ padding: '0.25rem' }}>Feature</th>
                                <th style={{ padding: '0.25rem' }}>Value</th>
                                <th style={{ padding: '0.25rem' }}>Deviation</th>
                              </tr>
                            </thead>
                            <tbody>
                              {alertDetail.evidence.map((ev, i) => (
                                <tr key={i} style={{ borderBottom: '1px solid #334155' }}>
                                  <td style={{ padding: '0.25rem' }}>{ev.feature_name}</td>
                                  <td style={{ padding: '0.25rem' }}>{ev.feature_value.toFixed(3)}</td>
                                  <td style={{ padding: '0.25rem', color: '#ef4444', fontWeight: 600 }}>
                                    {ev.robust_deviation.toFixed(3)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <div style={{ color: '#94a3b8' }}>No specific evidence attributes found.</div>
                        )}

                        <div style={{ marginTop: '0.25rem', fontSize: '0.75rem', color: '#94a3b8' }}>
                          Policy SHA: <code>{alert.policy_sha256.slice(0, 12)}...</code>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

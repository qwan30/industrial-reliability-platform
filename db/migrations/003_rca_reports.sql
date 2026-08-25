CREATE TABLE IF NOT EXISTS rca_reports (
    report_id text PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    evidence_bundle_sha256 text NOT NULL,
    status text NOT NULL CHECK (status = 'COMPLETE'),
    provider_model text NOT NULL,
    summary text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_rca_alert_bundle UNIQUE (alert_id, evidence_bundle_sha256)
);

CREATE INDEX IF NOT EXISTS idx_rca_reports_alert_id ON rca_reports(alert_id);

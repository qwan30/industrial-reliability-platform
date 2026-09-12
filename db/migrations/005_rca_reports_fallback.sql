-- Phase 9: Persist evidence-only RCA fallback reports.

ALTER TABLE rca_reports
    ALTER COLUMN provider_model DROP NOT NULL;

ALTER TABLE rca_reports
    DROP CONSTRAINT IF EXISTS rca_reports_status_check;

ALTER TABLE rca_reports
    ADD CONSTRAINT rca_reports_status_check
    CHECK (status IN ('COMPLETE', 'UNAVAILABLE'));

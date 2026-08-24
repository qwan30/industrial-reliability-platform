-- Phase 5: Alert Lifecycle and Persistence Schema

CREATE TABLE IF NOT EXISTS replay_sessions (
  replay_session_id text PRIMARY KEY,
  source_dataset_sha256 char(64) NOT NULL,
  contract_sha256 char(64) NOT NULL,
  model_version text NOT NULL,
  state text NOT NULL CHECK (state IN ('CREATED','RUNNING','PAUSED','STOPPED','COMPLETED','FAILED')),
  last_sequence bigint,
  source_timestamp timestamp,
  error_code text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS score_decisions (
  decision_id text PRIMARY KEY,
  replay_session_id text NOT NULL REFERENCES replay_sessions(replay_session_id),
  window_id text NOT NULL UNIQUE,
  source_timestamp timestamp NOT NULL,
  model_version text NOT NULL,
  score double precision NOT NULL,
  threshold double precision NOT NULL,
  is_anomaly boolean NOT NULL,
  payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
  alert_id text PRIMARY KEY,
  replay_session_id text NOT NULL REFERENCES replay_sessions(replay_session_id),
  machine_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('OPEN','RESOLVED')),
  first_detection timestamp NOT NULL,
  last_detection timestamp NOT NULL,
  resolved_at timestamp,
  latest_decision_id text NOT NULL REFERENCES score_decisions(decision_id),
  policy_sha256 char(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
  message_id text PRIMARY KEY,
  alert_id text NOT NULL REFERENCES alerts(alert_id),
  decision_id text NOT NULL REFERENCES score_decisions(decision_id),
  action text NOT NULL CHECK (action IN ('OPENED','UPDATED','RESOLVED','REOPENED')),
  payload jsonb NOT NULL,
  UNIQUE (alert_id, decision_id, action)
);

CREATE TABLE IF NOT EXISTS evidence_snapshots (
  evidence_id text PRIMARY KEY,
  alert_id text NOT NULL REFERENCES alerts(alert_id),
  decision_id text NOT NULL REFERENCES score_decisions(decision_id),
  payload jsonb NOT NULL,
  UNIQUE (alert_id, decision_id)
);

CREATE TABLE IF NOT EXISTS alert_outbox (
  message_id text PRIMARY KEY REFERENCES alert_events(message_id),
  topic text NOT NULL CHECK (topic = 'irp.alerts.v1'),
  message_key text NOT NULL,
  payload jsonb NOT NULL,
  published_at timestamptz
);

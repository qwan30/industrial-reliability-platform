CREATE TABLE IF NOT EXISTS lab_definitions (
  lab_id uuid PRIMARY KEY,
  name varchar(80) NOT NULL,
  current_revision int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lab_worker_health (
  worker_id uuid PRIMARY KEY,
  heartbeat_at timestamptz NOT NULL,
  kafka_connected bool NOT NULL DEFAULT false,
  analyst_last_poll_at timestamptz NULL
);

CREATE TABLE IF NOT EXISTS lab_baselines (
  baseline_id uuid PRIMARY KEY,
  lab_id uuid NOT NULL,
  lab_revision int NOT NULL,
  definition_digest char(64) NOT NULL,
  status text NOT NULL,
  seed bigint NOT NULL,
  artifact jsonb NULL,
  report jsonb NULL,
  lease_owner uuid NULL,
  lease_until timestamptz NULL,
  fence bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lab_revisions (
  lab_id uuid NOT NULL REFERENCES lab_definitions(lab_id) ON DELETE CASCADE,
  revision int NOT NULL,
  definition jsonb NOT NULL,
  digest char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (lab_id, revision)
);

CREATE TABLE IF NOT EXISTS lab_runs (
  run_id uuid PRIMARY KEY,
  lab_id uuid NOT NULL,
  lab_revision int NOT NULL,
  parent_run_id uuid NULL,
  baseline_id uuid NULL REFERENCES lab_baselines(baseline_id),
  max_ticks bigint NULL,
  model_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('CREATED', 'RUNNING', 'PAUSED', 'STOPPED', 'COMPLETED', 'FAILED')),
  seed bigint NOT NULL,
  speed int NOT NULL CHECK (speed IN (1, 10, 100)),
  tick bigint NOT NULL DEFAULT 0 CHECK (tick >= 0),
  control_revision bigint NOT NULL DEFAULT 0,
  accepted_sequence bigint NOT NULL DEFAULT 0,
  event_sequence bigint NOT NULL DEFAULT 0,
  fence bigint NOT NULL DEFAULT 0,
  lease_owner uuid NULL,
  lease_until timestamptz NULL,
  definition_digest char(64) NOT NULL,
  profile_digest char(64) NOT NULL,
  scene_digest char(64) NOT NULL,
  sampling_digest char(64) NOT NULL,
  checkpoint jsonb NOT NULL,
  bytes_recorded bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lab_id, lab_revision) REFERENCES lab_revisions(lab_id, revision)
);

CREATE TABLE IF NOT EXISTS lab_commands (
  run_id uuid NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
  command_id uuid NOT NULL,
  payload_hash char(64) NOT NULL,
  accepted_sequence bigint NOT NULL,
  action text NOT NULL,
  target_id uuid NULL,
  parameters jsonb NOT NULL,
  status text NOT NULL,
  effective_tick bigint NULL,
  reason_code text NULL,
  control_revision bigint NOT NULL,
  PRIMARY KEY (run_id, command_id),
  UNIQUE (run_id, accepted_sequence)
);

CREATE TABLE IF NOT EXISTS lab_events (
  run_id uuid NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
  sequence bigint NOT NULL,
  event_id uuid NOT NULL UNIQUE,
  kind text NOT NULL,
  tick bigint NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_lab_events_run_tick ON lab_events(run_id, tick);

CREATE TABLE IF NOT EXISTS lab_history (
  run_id uuid NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
  tick bigint NOT NULL,
  frame jsonb NOT NULL,
  PRIMARY KEY (run_id, tick)
);

CREATE TABLE IF NOT EXISTS lab_outbox (
  message_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
  sensor_id uuid NOT NULL,
  tick bigint NOT NULL,
  topic text NOT NULL,
  payload jsonb NOT NULL,
  published_at timestamptz NULL
);

CREATE INDEX IF NOT EXISTS idx_lab_outbox_unpublished ON lab_outbox(run_id, tick, sensor_id) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS lab_analysis_state (
  run_id uuid NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
  sensor_id uuid NOT NULL,
  profile_digest char(64) NOT NULL,
  last_tick bigint NOT NULL,
  state jsonb NOT NULL,
  PRIMARY KEY (run_id, sensor_id, profile_digest)
);

CREATE TABLE IF NOT EXISTS lab_alerts (
  alert_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
  asset_id uuid NOT NULL,
  sensor_id uuid NOT NULL,
  origin text NOT NULL,
  kind text NOT NULL,
  state text NOT NULL,
  first_tick bigint NOT NULL,
  last_tick bigint NOT NULL,
  resolved_tick bigint NULL,
  evidence jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lab_alerts_run_state ON lab_alerts(run_id, state, first_tick);

CREATE TABLE IF NOT EXISTS lab_rca_reports (
  alert_id uuid NOT NULL,
  bundle_sha256 char(64) NOT NULL,
  report jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (alert_id, bundle_sha256)
);

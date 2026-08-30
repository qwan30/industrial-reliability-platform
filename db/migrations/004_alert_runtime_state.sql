CREATE TABLE IF NOT EXISTS alert_runtime_states (
  replay_session_id text NOT NULL REFERENCES replay_sessions(replay_session_id) ON DELETE CASCADE,
  machine_id text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (replay_session_id, machine_id)
);

CREATE TABLE IF NOT EXISTS replay_checkpoints (
  replay_session_id text PRIMARY KEY,
  command_payload jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('RUNNING','PAUSED','STOPPED','COMPLETED','FAILED')),
  last_sequence bigint NOT NULL DEFAULT 0,
  source_timestamp timestamp,
  updated_at timestamptz NOT NULL DEFAULT now()
);


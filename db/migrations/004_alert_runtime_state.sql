CREATE TABLE IF NOT EXISTS alert_runtime_states (
  replay_session_id text NOT NULL REFERENCES replay_sessions(replay_session_id) ON DELETE CASCADE,
  machine_id text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (replay_session_id, machine_id)
);

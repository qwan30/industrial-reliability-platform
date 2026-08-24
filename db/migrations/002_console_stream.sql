CREATE TABLE IF NOT EXISTS console_events (
  stream_sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id text NOT NULL UNIQUE,
  replay_session_id text NOT NULL REFERENCES replay_sessions(replay_session_id),
  event_type text NOT NULL CHECK (event_type IN ('status', 'score', 'alert')),
  source_timestamp timestamp NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS console_events_session_sequence_idx
  ON console_events (replay_session_id, stream_sequence);

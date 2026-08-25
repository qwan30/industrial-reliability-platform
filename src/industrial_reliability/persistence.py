"""PostgreSQL persistence for replay sessions, score decisions, alert lifecycles, evidence, and transactional outbox."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from industrial_reliability.alert_state import AlertState, TransitionResult
from industrial_reliability.console_stream import ConsoleEventV1
from industrial_reliability.runtime_messages import (
    RcaReportV1,
    ReplayStatusV1,
    ScoreDecisionV1,
)


class IdentityMismatchError(ValueError):
    """Raised when an existing ID conflicts with different payload content."""


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot be reached or transactions fail."""


@dataclass(frozen=True, slots=True)
class OutboxRow:
    message_id: UUID
    topic: str
    message_key: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReplaySessionRecord:
    replay_session_id: UUID
    source_dataset_sha256: str
    contract_sha256: str
    model_version: str
    state: str
    last_sequence: int | None
    source_timestamp: datetime | None
    error_code: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AlertSummaryRecord:
    alert_id: UUID
    replay_session_id: UUID
    machine_id: str
    state: str
    first_detection: datetime
    last_detection: datetime
    resolved_at: datetime | None
    latest_decision_id: UUID
    policy_sha256: str


@dataclass(frozen=True, slots=True)
class AlertDetailRecord:
    alert: AlertSummaryRecord
    events: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    rca: dict[str, Any] | None = None


class RuntimeStore:
    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    def check_connection(self, timeout: float = 1.0) -> None:
        with (
            psycopg.connect(self.db_url, connect_timeout=int(timeout)) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1")

    def execute_script(self, sql: str) -> None:
        with psycopg.connect(self.db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(sql)

    def count(
        self,
        table_name: str,
        column: str | None = None,
        value: str | None = None,
    ) -> int:
        # Validate table_name against allowed whitelist to prevent SQL injection
        allowed_tables = {
            "replay_sessions",
            "score_decisions",
            "alerts",
            "alert_events",
            "evidence_snapshots",
            "alert_outbox",
            "console_events",
            "rca_reports",
        }
        if table_name not in allowed_tables:
            raise ValueError(f"Invalid table name: {table_name}")

        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            if column and value:
                allowed_columns = {
                    "replay_session_id",
                    "alert_id",
                    "decision_id",
                    "message_id",
                    "window_id",
                    "report_id",
                }
                if column not in allowed_columns:
                    raise ValueError(f"Invalid column name: {column}")
                cur.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE {column} = %s",
                    (value,),
                )
            else:
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def record_replay_status(self, status: ReplayStatusV1) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO replay_sessions (
                        replay_session_id, source_dataset_sha256, contract_sha256,
                        model_version, state, last_sequence, source_timestamp,
                        error_code, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (replay_session_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        last_sequence = EXCLUDED.last_sequence,
                        source_timestamp = EXCLUDED.source_timestamp,
                        error_code = EXCLUDED.error_code,
                        updated_at = now();
                    """,
                    (
                        str(status.replay_session_id),
                        status.source_dataset_sha256,
                        status.contract_sha256,
                        "champion-statistical-v1",
                        status.state,
                        status.last_sequence,
                        status.source_timestamp,
                        status.error_code,
                    ),
                )
            conn.commit()

    def _ensure_session_exists(
        self,
        cur: psycopg.Cursor[Any],
        decision: ScoreDecisionV1,
    ) -> None:
        cur.execute(
            """
            INSERT INTO replay_sessions (
                replay_session_id, source_dataset_sha256, contract_sha256,
                model_version, state, last_sequence, source_timestamp,
                error_code, updated_at
            ) VALUES (%s, %s, %s, %s, 'RUNNING', NULL, %s, NULL, now())
            ON CONFLICT (replay_session_id) DO NOTHING;
            """,
            (
                str(decision.replay_session_id),
                decision.source_dataset_sha256,
                decision.contract_sha256,
                decision.model_version,
                decision.source_timestamp,
            ),
        )

    def load_alert_state(self, replay_session_id: UUID, machine_id: str) -> AlertState:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            # Find current open alert if any
            cur.execute(
                """
                SELECT alert_id, state, first_detection, last_detection, resolved_at, latest_decision_id
                FROM alerts
                WHERE replay_session_id = %s AND machine_id = %s
                ORDER BY last_detection DESC
                LIMIT 1;
                """,
                (str(replay_session_id), machine_id),
            )
            alert_row = cur.fetchone()
            if not alert_row:
                return AlertState.empty(replay_session_id, machine_id)

            active_id = UUID(alert_row["alert_id"]) if alert_row["state"] == "OPEN" else None
            prev_id = UUID(alert_row["alert_id"]) if alert_row["state"] == "RESOLVED" else None

            # Find latest decision timestamp
            cur.execute(
                """
                SELECT decision_id, source_timestamp
                FROM score_decisions
                WHERE replay_session_id = %s
                ORDER BY source_timestamp DESC
                LIMIT 1;
                """,
                (str(replay_session_id),),
            )
            last_dec_row = cur.fetchone()
            last_dec_id = UUID(last_dec_row["decision_id"]) if last_dec_row else None
            last_ts = last_dec_row["source_timestamp"] if last_dec_row else None

            return AlertState(
                replay_session_id=replay_session_id,
                machine_id=machine_id,
                active_alert_id=active_id,
                previous_alert_id=prev_id,
                first_detection=alert_row["first_detection"],
                last_detection=alert_row["last_detection"],
                resolved_at=alert_row["resolved_at"],
                anomaly_decision_ids=(),
                anomaly_streak=1 if active_id else 0,
                normal_streak=0,
                last_decision_id=last_dec_id,
                last_source_timestamp=last_ts,
            )

    def record_decision_transition(
        self,
        decision: ScoreDecisionV1,
        result: TransitionResult,
    ) -> None:
        decision_payload = decision.model_dump(mode="json")
        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            # 1. Ensure replay session exists
            self._ensure_session_exists(cur, decision)

            # 2. Insert decision
            cur.execute(
                """
                INSERT INTO score_decisions (
                    decision_id, replay_session_id, window_id, source_timestamp,
                    model_version, score, threshold, is_anomaly, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO NOTHING;
                """,
                (
                    str(decision.decision_id),
                    str(decision.replay_session_id),
                    str(decision.window_id),
                    decision.source_timestamp,
                    decision.model_version,
                    decision.score,
                    decision.threshold,
                    decision.is_anomaly,
                    json.dumps(decision_payload),
                ),
            )

            # 3. If event emitted, persist alert, event, evidence, outbox
            if result.event is not None:
                event = result.event
                alert_state_val = "RESOLVED" if event.action == "RESOLVED" else "OPEN"
                resolved_at_val = decision.source_timestamp if event.action == "RESOLVED" else None

                # Upsert alert
                cur.execute(
                    """
                    INSERT INTO alerts (
                        alert_id, replay_session_id, machine_id, state,
                        first_detection, last_detection, resolved_at,
                        latest_decision_id, policy_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (alert_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        last_detection = EXCLUDED.last_detection,
                        resolved_at = EXCLUDED.resolved_at,
                        latest_decision_id = EXCLUDED.latest_decision_id;
                    """,
                    (
                        str(event.alert_id),
                        str(event.replay_session_id),
                        event.machine_id,
                        alert_state_val,
                        event.first_detection,
                        event.last_detection,
                        resolved_at_val,
                        str(decision.decision_id),
                        event.policy_sha256,
                    ),
                )

                # Insert alert_events
                cur.execute(
                    """
                    INSERT INTO alert_events (
                        message_id, alert_id, decision_id, action, payload
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (alert_id, decision_id, action) DO NOTHING;
                    """,
                    (
                        str(event.message_id),
                        str(event.alert_id),
                        str(decision.decision_id),
                        event.action,
                        json.dumps(event.model_dump(mode="json")),
                    ),
                )

                # Insert evidence snapshot if present
                if result.evidence is not None:
                    ev_snapshot = result.evidence
                    cur.execute(
                        """
                        INSERT INTO evidence_snapshots (
                            evidence_id, alert_id, decision_id, payload
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (alert_id, decision_id) DO NOTHING;
                        """,
                        (
                            str(ev_snapshot.evidence_id),
                            str(ev_snapshot.alert_id),
                            str(decision.decision_id),
                            json.dumps(ev_snapshot.model_dump(mode="json")),
                        ),
                    )

                # Insert outbox
                cur.execute(
                    """
                    INSERT INTO alert_outbox (
                        message_id, topic, message_key, payload, published_at
                    ) VALUES (%s, 'irp.alerts.v1', %s, %s, NULL)
                    ON CONFLICT (message_id) DO NOTHING;
                    """,
                    (
                        str(event.message_id),
                        str(event.alert_id),
                        json.dumps(event.model_dump(mode="json")),
                    ),
                )

            conn.commit()

    def next_unpublished_outbox(self) -> OutboxRow | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_id, topic, message_key, payload
                FROM alert_outbox
                WHERE published_at IS NULL
                ORDER BY message_id
                LIMIT 1
                FOR UPDATE SKIP LOCKED;
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            return OutboxRow(
                message_id=UUID(row["message_id"]),
                topic=row["topic"],
                message_key=row["message_key"],
                payload=row["payload"]
                if isinstance(row["payload"], dict)
                else json.loads(row["payload"]),
            )

    def mark_outbox_published(self, message_id: UUID) -> None:
        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE alert_outbox SET published_at = now() WHERE message_id = %s;",
                (str(message_id),),
            )
            conn.commit()

    def get_replay(self, replay_session_id: UUID) -> ReplaySessionRecord | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT replay_session_id, source_dataset_sha256, contract_sha256,
                       model_version, state, last_sequence, source_timestamp,
                       error_code, updated_at
                FROM replay_sessions
                WHERE replay_session_id = %s;
                """,
                (str(replay_session_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return ReplaySessionRecord(
                replay_session_id=UUID(row["replay_session_id"]),
                source_dataset_sha256=row["source_dataset_sha256"],
                contract_sha256=row["contract_sha256"],
                model_version=row["model_version"],
                state=row["state"],
                last_sequence=row["last_sequence"],
                source_timestamp=row["source_timestamp"],
                error_code=row["error_code"],
                updated_at=row["updated_at"],
            )

    def list_alerts(
        self,
        replay_session_id: UUID,
        after: UUID | None = None,
        limit: int = 50,
    ) -> list[AlertSummaryRecord]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            if after:
                cur.execute(
                    """
                    SELECT alert_id, replay_session_id, machine_id, state,
                           first_detection, last_detection, resolved_at,
                           latest_decision_id, policy_sha256
                    FROM alerts
                    WHERE replay_session_id = %s AND alert_id > %s
                    ORDER BY alert_id
                    LIMIT %s;
                    """,
                    (str(replay_session_id), str(after), limit),
                )
            else:
                cur.execute(
                    """
                    SELECT alert_id, replay_session_id, machine_id, state,
                           first_detection, last_detection, resolved_at,
                           latest_decision_id, policy_sha256
                    FROM alerts
                    WHERE replay_session_id = %s
                    ORDER BY alert_id
                    LIMIT %s;
                    """,
                    (str(replay_session_id), limit),
                )
            rows = cur.fetchall()
            return [
                AlertSummaryRecord(
                    alert_id=UUID(r["alert_id"]),
                    replay_session_id=UUID(r["replay_session_id"]),
                    machine_id=r["machine_id"],
                    state=r["state"],
                    first_detection=r["first_detection"],
                    last_detection=r["last_detection"],
                    resolved_at=r["resolved_at"],
                    latest_decision_id=UUID(r["latest_decision_id"]),
                    policy_sha256=r["policy_sha256"],
                )
                for r in rows
            ]

    def get_alert_detail(self, alert_id: UUID) -> AlertDetailRecord | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT alert_id, replay_session_id, machine_id, state,
                       first_detection, last_detection, resolved_at,
                       latest_decision_id, policy_sha256
                FROM alerts
                WHERE alert_id = %s;
                """,
                (str(alert_id),),
            )
            alert_row = cur.fetchone()
            if not alert_row:
                return None

            summary = AlertSummaryRecord(
                alert_id=UUID(alert_row["alert_id"]),
                replay_session_id=UUID(alert_row["replay_session_id"]),
                machine_id=alert_row["machine_id"],
                state=alert_row["state"],
                first_detection=alert_row["first_detection"],
                last_detection=alert_row["last_detection"],
                resolved_at=alert_row["resolved_at"],
                latest_decision_id=UUID(alert_row["latest_decision_id"]),
                policy_sha256=alert_row["policy_sha256"],
            )

            # Events
            cur.execute(
                "SELECT payload FROM alert_events WHERE alert_id = %s ORDER BY message_id;",
                (str(alert_id),),
            )
            events = [
                r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
                for r in cur.fetchall()
            ]

            # Evidence
            cur.execute(
                "SELECT payload FROM evidence_snapshots WHERE alert_id = %s ORDER BY evidence_id;",
                (str(alert_id),),
            )
            evidence = [
                r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
                for r in cur.fetchall()
            ]

            # Decisions
            cur.execute(
                """
                SELECT d.payload
                FROM score_decisions d
                JOIN alert_events e ON e.decision_id = d.decision_id
                WHERE e.alert_id = %s
                ORDER BY d.source_timestamp;
                """,
                (str(alert_id),),
            )
            decisions = [
                r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
                for r in cur.fetchall()
            ]

            # RCA Report if table exists and row found
            rca_payload: dict[str, Any] | None = None
            try:
                cur.execute(
                    """
                    SELECT payload FROM rca_reports
                    WHERE alert_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (str(alert_id),),
                )
                rca_row = cur.fetchone()
                if rca_row:
                    raw_p = rca_row["payload"]
                    rca_payload = raw_p if isinstance(raw_p, dict) else json.loads(raw_p)
            except Exception:
                pass

            return AlertDetailRecord(
                alert=summary,
                events=events,
                evidence=evidence,
                decisions=decisions,
                rca=rca_payload,
            )

    def save_complete_rca(self, report: RcaReportV1) -> RcaReportV1:
        if report.status != "COMPLETE":
            return report

        with (
            psycopg.connect(self.db_url) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            payload_json = json.dumps(report.model_dump(mode="json"))
            cur.execute(
                """
                INSERT INTO rca_reports (
                    report_id, alert_id, evidence_bundle_sha256,
                    status, provider_model, summary, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (alert_id, evidence_bundle_sha256) DO NOTHING;
                """,
                (
                    report.report_id,
                    str(report.alert_id),
                    report.evidence_bundle_sha256,
                    report.status,
                    report.provider_model or "unknown",
                    report.summary,
                    payload_json,
                    report.emitted_at,
                ),
            )
            # Read back stored row to guarantee immutability & payload identity
            cur.execute(
                """
                SELECT payload FROM rca_reports
                WHERE alert_id = %s AND evidence_bundle_sha256 = %s;
                """,
                (str(report.alert_id), report.evidence_bundle_sha256),
            )
            row = cur.fetchone()
            if row:
                existing_payload = (
                    row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
                )
                existing_report = RcaReportV1.model_validate(existing_payload)
                if existing_report.evidence_bundle_sha256 != report.evidence_bundle_sha256:
                    raise IdentityMismatchError("Stored RCA report evidence bundle hash does not match")
                return existing_report
            return report

    def get_rca(
        self, alert_id: str | UUID, evidence_bundle_sha256: str | None = None
    ) -> RcaReportV1 | None:
        with (
            psycopg.connect(self.db_url) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            if evidence_bundle_sha256:
                cur.execute(
                    """
                    SELECT payload FROM rca_reports
                    WHERE alert_id = %s AND evidence_bundle_sha256 = %s
                    LIMIT 1;
                    """,
                    (str(alert_id), evidence_bundle_sha256),
                )
            else:
                cur.execute(
                    """
                    SELECT payload FROM rca_reports
                    WHERE alert_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (str(alert_id),),
                )
            row = cur.fetchone()
            if not row:
                return None
            payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
            return RcaReportV1.model_validate(payload)


    def append_console_event(self, event: ConsoleEventV1) -> None:
        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO console_events (
                    event_id,
                    replay_session_id,
                    event_type,
                    source_timestamp,
                    payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING;
                """,
                (
                    event.event_id,
                    str(event.replay_session_id),
                    event.event_type,
                    event.source_timestamp,
                    json.dumps(event.payload),
                ),
            )

    def events_after(
        self,
        replay_session_id: str,
        after_event_id: str | None = None,
        limit: int = 100,
    ) -> tuple[ConsoleEventV1, ...]:
        with (
            psycopg.connect(self.db_url) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            if after_event_id:
                cur.execute(
                    "SELECT stream_sequence FROM console_events WHERE event_id = %s AND replay_session_id = %s;",
                    (after_event_id, str(replay_session_id)),
                )
                row = cur.fetchone()
                if row is None:
                    return ()
                seq = row["stream_sequence"]
                cur.execute(
                    """
                    SELECT event_id, replay_session_id, event_type, source_timestamp, payload
                    FROM console_events
                    WHERE replay_session_id = %s AND stream_sequence > %s
                    ORDER BY stream_sequence ASC
                    LIMIT %s;
                    """,
                    (str(replay_session_id), seq, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT event_id, replay_session_id, event_type, source_timestamp, payload
                    FROM console_events
                    WHERE replay_session_id = %s
                    ORDER BY stream_sequence ASC
                    LIMIT %s;
                    """,
                    (str(replay_session_id), limit),
                )

            results: list[ConsoleEventV1] = []
            for r in cur.fetchall():
                payload = (
                    r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
                )
                results.append(
                    ConsoleEventV1(
                        event_id=r["event_id"],
                        replay_session_id=r["replay_session_id"],
                        event_type=r["event_type"],
                        source_timestamp=r["source_timestamp"],
                        payload=payload,
                        durable=True,
                    )
                )
            return tuple(results)

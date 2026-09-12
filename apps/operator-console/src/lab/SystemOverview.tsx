import { useEffect, useState } from "react";
import { LabIcon } from "./LabIcon";
import {
  labStore,
  useConnectionSlice,
  useEditorSlice,
  useRunSlice,
} from "./store";
import type { LabAlert, RunSnapshot } from "./types";
import "./system-overview.css";

type Sample = {
  tick: number;
  pressure: number | null;
  flow: number | null;
  observations: number;
  alerts: number;
};
type Metric = "pressure" | "flow" | "observations" | "alerts";
const kindLabels: Record<LabAlert["kind"], string> = {
  ABOVE_LIMIT: "Above limit",
  BELOW_LIMIT: "Below limit",
  MISSING: "Missing observation",
  INVALID: "Invalid observation",
  ANOMALY: "Anomaly detected",
};
const originLabels: Record<LabAlert["origin"], string> = {
  PROCESS_LIMIT: "Process limit",
  DATA_QUALITY: "Data quality",
  ML: "ML detection",
};
function mean(values: number[]): number | null {
  const finite = values.filter(Number.isFinite);
  return finite.length
    ? finite.reduce((sum, value) => sum + value, 0) / finite.length
    : null;
}
function sampleFrom(snapshot: RunSnapshot): Sample {
  const pressure = mean(Object.values(snapshot.physical.pressures_pa));
  return {
    tick: snapshot.tick,
    pressure: pressure === null ? null : pressure / 100000,
    flow: mean(Object.values(snapshot.physical.flows_kg_s)),
    observations: snapshot.observations.length,
    alerts: snapshot.alerts.filter((alert) => alert.state === "OPEN").length,
  };
}
function TrendChart({
  title,
  metric,
  unit,
  color,
  samples,
}: {
  title: string;
  metric: Metric;
  unit: string;
  color: string;
  samples: Sample[];
}) {
  const values = samples.map((sample) => sample[metric]);
  const valid = values.filter(
    (value): value is number => value !== null && Number.isFinite(value),
  );
  const latest = values[values.length - 1];
  const min = Math.min(...valid, 0) * 1.15;
  const max = Math.max(...valid, metric === "flow" ? 0.01 : 1) * 1.15;
  const range = max - min;
  const start = samples[0]?.tick ?? 0,
    end = samples[samples.length - 1]?.tick ?? 0;
  let connected = false;
  const path = samples
    .map((sample) => {
      const value = sample[metric];
      if (value === null || !Number.isFinite(value)) {
        connected = false;
        return "";
      }
      const x = 28 + ((sample.tick - start) / (end - start || 1)) * 270;
      const y = 80 - ((value - min) / range) * 64;
      const command = `${connected ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
      connected = true;
      return command;
    })
    .join(" ");
  return (
    <section className="overview-chart" aria-label={title}>
      <div className="overview-chart-heading">
        <h3>{title}</h3>
        <span style={{ color }}>
          {latest == null
            ? "—"
            : latest.toFixed(
                metric === "observations" || metric === "alerts" ? 0 : 2,
              )}{" "}
          <small>{unit}</small>
        </span>
      </div>
      {valid.length >= 2 ? (
        <svg
          viewBox="0 0 312 108"
          role="img"
          aria-label={`${title} history, latest ${latest ?? "unavailable"} ${unit}`}
        >
          {[16, 48, 80].map((y, index) => (
            <g key={y}>
              <line
                x1="28"
                x2="298"
                y1={y}
                y2={y}
                stroke="#2a3b4b"
                strokeDasharray="3 4"
              />
              <text x="22" y={y + 3} textAnchor="end">
                {(max - (range * index) / 2).toFixed(range < 3 ? 1 : 0)}
              </text>
            </g>
          ))}
          {[28, 96, 164, 232, 298].map((x) => (
            <line
              key={x}
              x1={x}
              x2={x}
              y1="16"
              y2="80"
              stroke="#223240"
              strokeDasharray="3 4"
            />
          ))}
          <path
            d={path}
            fill="none"
            stroke={color}
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <text x="28" y="101">
            {(start * 0.05).toFixed(1)}s
          </text>
          <text x="298" y="101" textAnchor="end">
            {(end * 0.05).toFixed(1)}s
          </text>
        </svg>
      ) : (
        <div className="overview-chart-empty">
          <div className="empty-chart-grid" />
          <span>
            {samples.length
              ? "Collecting simulation samples…"
              : "Start a run to view telemetry"}
          </span>
        </div>
      )}
    </section>
  );
}

export function SystemOverview() {
  const { lab } = useEditorSlice();
  const { snapshot, runId, status } = useRunSlice();
  const { status: connection } = useConnectionSlice();
  const [history, setHistory] = useState<{
    runId: string | null;
    samples: Sample[];
  }>({ runId: null, samples: [] });
  const [filter, setFilter] = useState<"ALL" | "OPEN" | "RESOLVED">("ALL");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [windowSize, setWindowSize] = useState(60);
  useEffect(() => {
    if (!snapshot) return;
    const sample = sampleFrom(snapshot);
    setHistory((previous) => {
      if (
        previous.runId !== snapshot.run_id ||
        sample.tick < (previous.samples[previous.samples.length - 1]?.tick ?? 0)
      )
        return { runId: snapshot.run_id, samples: [sample] };
      if (previous.samples[previous.samples.length - 1]?.tick === sample.tick)
        return previous;
      return {
        runId: snapshot.run_id,
        samples: [...previous.samples.slice(-119), sample],
      };
    });
  }, [snapshot]);
  const samples =
    history.runId === runId ? history.samples.slice(-windowSize) : [];
  const alerts = snapshot?.alerts ?? [];
  const openCount = alerts.filter((alert) => alert.state === "OPEN").length;
  const shownAlerts = alerts.filter(
    (alert) => filter === "ALL" || alert.state === filter,
  );
  const selectedAlert = shownAlerts.find(
    (alert) => `${alert.run_id}:${alert.alert_id}` === selectedKey,
  );
  const observations = snapshot?.observations ?? [];
  const goodCount = observations.filter(
    (observation) =>
      observation.quality === "GOOD" &&
      observation.value !== null &&
      Number.isFinite(observation.value),
  ).length;
  const quality = observations.length
    ? (goodCount / observations.length) * 100
    : null;
  const streamLabel = !snapshot
    ? "Awaiting simulation"
    : connection === "STALE"
      ? "Stream stale · last received values"
      : connection !== "CONNECTED"
        ? "Stream offline · last received values"
        : status === "RUNNING"
          ? "Streaming simulation"
          : `Simulation ${status.toLowerCase()}`;
  function selectAlert(alert: LabAlert) {
    setSelectedKey(`${alert.run_id}:${alert.alert_id}`);
    labStore.selectEntity(alert.asset_id, "ASSET");
    const asset = lab?.assets.find(
      (asset) => asset.asset_id === alert.asset_id,
    );
    if (asset) labStore.focusOn(asset.position_m);
  }
  return (
    <section
      className="system-overview"
      aria-labelledby="system-overview-title"
    >
      <div className="overview-heading">
        <div>
          <h2 id="system-overview-title">System Overview</h2>
          <p>Live telemetry and operational status</p>
        </div>
        <label className="overview-window">
          <span className="sr-only">Chart history window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(Number(event.target.value))}
          >
            <option value={60}>Last 60 samples</option>
            <option value={120}>Last 120 samples</option>
          </select>
        </label>
      </div>
      <div className="overview-stream">
        <span className={`status-dot ${connection.toLowerCase()}`} />
        <span>{streamLabel}</span>
        <span className="overview-stream-source">Simulation data</span>
      </div>
      <div className="overview-metrics">
        <section className="overview-metric">
          <div className="overview-metric-label">
            <LabIcon name="sensor" />
            <h3>Process Alerts</h3>
          </div>
          <div className="overview-metric-value">
            {snapshot ? openCount : "—"}
            <span>open</span>
          </div>
          <p>
            {snapshot
              ? openCount
                ? "Review active exceptions"
                : "No active alerts reported"
              : "Waiting for a run"}
          </p>
          <div
            className={`overview-meter ${openCount ? "warning" : ""}`}
            aria-hidden="true"
          >
            {Array.from({ length: 12 }, (_, i) => (
              <i key={i} className={snapshot ? "filled" : ""} />
            ))}
          </div>
        </section>
        <section className="overview-metric">
          <div className="overview-metric-label">
            <LabIcon name="topology" />
            <h3>Data Quality</h3>
          </div>
          <div className="overview-metric-value">
            {quality === null ? "—" : `${quality.toFixed(1)}%`}
          </div>
          <p>
            {observations.length
              ? `${goodCount} / ${observations.length} valid observations`
              : "No observations received"}
          </p>
          <div className="overview-meter" aria-hidden="true">
            {Array.from({ length: 12 }, (_, i) => (
              <i
                key={i}
                className={
                  quality !== null && i < (quality / 100) * 12 ? "filled" : ""
                }
              />
            ))}
          </div>
        </section>
        <section className="overview-metric">
          <div className="overview-metric-label">
            <LabIcon name="cube" />
            <h3>Connected Lab</h3>
          </div>
          <div className="overview-metric-value">
            {lab?.assets.length ?? "—"}
            <span>assets</span>
          </div>
          <p>
            {lab?.sensors.length ?? 0} sensors · {lab?.pipes.length ?? 0} pipes
          </p>
          <span className="overview-definition">
            Definition v{lab?.revision ?? "—"}
          </span>
        </section>
      </div>
      <div className="overview-charts">
        <TrendChart
          title="Mean pressure"
          metric="pressure"
          unit="bar"
          color="#39c6ef"
          samples={samples}
        />
        <TrendChart
          title="Mean flow"
          metric="flow"
          unit="kg/s"
          color="#50aaff"
          samples={samples}
        />
        <TrendChart
          title="Observations per frame"
          metric="observations"
          unit=""
          color="#be9bfa"
          samples={samples}
        />
        <TrendChart
          title="Open alerts"
          metric="alerts"
          unit=""
          color="#ffa75b"
          samples={samples}
        />
      </div>
      <div
        className={`overview-alerts-layout ${selectedAlert ? "has-detail" : ""}`}
      >
        <section
          className="overview-alerts"
          aria-labelledby="overview-alert-title"
        >
          <div className="overview-alerts-heading">
            <h3 id="overview-alert-title">
              <span className={openCount ? "alert-indicator" : ""}>△</span>{" "}
              Alerts <span className="overview-count">{alerts.length}</span>
            </h3>
            <div
              className="overview-filters"
              role="group"
              aria-label="Filter alerts"
            >
              {(["ALL", "OPEN", "RESOLVED"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-label={`${value[0]}${value.slice(1).toLowerCase()} alerts`}
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {value[0]}
                  {value.slice(1).toLowerCase()}
                </button>
              ))}
            </div>
          </div>
          {shownAlerts.length ? (
            <div className="overview-table-scroll">
              <table aria-label="Simulation alerts">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Status</th>
                    <th>Asset / message</th>
                  </tr>
                </thead>
                <tbody>
                  {shownAlerts.map((alert) => (
                    <tr
                      key={alert.alert_id}
                      className={
                        selectedAlert?.alert_id === alert.alert_id
                          ? "selected"
                          : ""
                      }
                    >
                      <td>{(alert.first_tick * 0.05).toFixed(1)}s</td>
                      <td>
                        <span
                          className={`overview-alert-state ${alert.state.toLowerCase()}`}
                        >
                          {alert.state === "OPEN" ? "Open" : "Resolved"}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => selectAlert(alert)}
                        >
                          <strong>{alert.asset_id}</strong>
                          <span>{kindLabels[alert.kind]}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overview-alerts-empty">
              <span className="empty-alert-icon">
                <LabIcon name="check" size={24} />
              </span>
              <strong>
                {snapshot ? "No matching alerts" : "Ready when you are"}
              </strong>
              <p>
                {snapshot
                  ? "Alerts matching this filter will appear here."
                  : "Start a simulation to monitor process limits, data quality and model detections."}
              </p>
            </div>
          )}
          <div className="overview-alerts-footer">
            <span>Process limits · Data quality · ML</span>
            <span>{snapshot ? `Tick ${snapshot.tick}` : "No active run"}</span>
          </div>
        </section>
        {selectedAlert && (
          <aside
            className="overview-alert-detail"
            aria-labelledby="alert-detail-title"
          >
            <div className="overview-detail-heading">
              <h3 id="alert-detail-title">Alert Details</h3>
              <button
                type="button"
                className="btn-icon"
                aria-label="Close alert details"
                onClick={() => setSelectedKey(null)}
              >
                <LabIcon name="close" size={16} />
              </button>
            </div>
            <span
              className={`overview-alert-state ${selectedAlert.state.toLowerCase()}`}
            >
              {selectedAlert.state}
            </span>
            <h4>{kindLabels[selectedAlert.kind]}</h4>
            <p>
              {originLabels[selectedAlert.origin]} detected on{" "}
              <strong>{selectedAlert.asset_id}</strong>.
            </p>
            <dl>
              <dt>Sensor</dt>
              <dd>{selectedAlert.sensor_id}</dd>
              <dt>First seen</dt>
              <dd>{(selectedAlert.first_tick * 0.05).toFixed(2)}s</dd>
              <dt>Last seen</dt>
              <dd>{(selectedAlert.last_tick * 0.05).toFixed(2)}s</dd>
              <dt>Evidence</dt>
              <dd>{selectedAlert.evidence_ids?.length ?? 0} records</dd>
            </dl>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              aria-label="Investigate alert"
              onClick={() => labStore.setMode("INVESTIGATE")}
            >
              Investigate →
            </button>
            <small>Open the investigation workspace for this asset.</small>
          </aside>
        )}
      </div>
    </section>
  );
}

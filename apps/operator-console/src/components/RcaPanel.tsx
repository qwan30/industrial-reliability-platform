import React, { useState } from 'react';
import { RcaReportV1 } from '../types';
import { generateRca } from '../api';

interface RcaPanelProps {
  alertId: string;
  initialReport: RcaReportV1 | null;
  baseUrl?: string;
}

export const RcaPanel: React.FC<RcaPanelProps> = ({
  alertId,
  initialReport,
  baseUrl,
}) => {
  const [report, setReport] = useState<RcaReportV1 | null>(initialReport);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const generated = await generateRca(alertId, baseUrl);
      setReport(generated);
    } catch (err: any) {
      setError(err.message || 'Failed to generate root-cause analysis');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4 mt-4 space-y-4" data-testid="rca-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <h4 className="text-sm font-semibold text-slate-200">Grounded Root-Cause Analysis</h4>
          {report && (
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                report.status === 'COMPLETE'
                  ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700'
                  : 'bg-amber-900/60 text-amber-300 border border-amber-700'
              }`}
              data-testid="rca-status-badge"
            >
              {report.status}
            </span>
          )}
        </div>
        <button
          onClick={handleGenerate}
          disabled={isLoading}
          className="px-3 py-1 text-xs font-medium bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:opacity-60 text-white rounded transition"
          data-testid="generate-rca-btn"
        >
          {isLoading ? 'Generating RCA...' : report ? 'Regenerate RCA' : 'Generate RCA'}
        </button>
      </div>

      {error && (
        <div className="p-2 text-xs bg-rose-950/60 border border-rose-800 text-rose-300 rounded" data-testid="rca-error">
          {error}
        </div>
      )}

      {report ? (
        <div className="space-y-3 text-xs" data-testid="rca-content">
          <div className="p-3 bg-slate-800/80 rounded border border-slate-700">
            <span className="font-semibold text-slate-300 block mb-1">Executive Summary</span>
            <p className="text-slate-200 leading-relaxed" data-testid="rca-summary">{report.summary}</p>
          </div>

          {report.observations.length > 0 && (
            <div className="space-y-1">
              <span className="font-semibold text-slate-300 block">Grounded Observations</span>
              <ul className="space-y-1.5" data-testid="rca-observations">
                {report.observations.map((obs, idx) => (
                  <li key={idx} className="p-2 bg-slate-800/50 rounded border border-slate-700/80 flex flex-col space-y-1">
                    <span className="text-slate-200">{obs.claim}</span>
                    <div className="flex items-center flex-wrap gap-1 mt-1">
                      <span className="text-[10px] text-slate-400">Citations:</span>
                      {obs.evidence_ids.map((evId) => (
                        <span
                          key={evId}
                          className="px-1.5 py-0.5 bg-slate-700 text-cyan-300 rounded text-[10px] font-mono"
                          data-testid="rca-citation-badge"
                        >
                          {evId}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.uncertainty.length > 0 && (
            <div className="space-y-1">
              <span className="font-semibold text-slate-300 block">Uncertainty & Limitations</span>
              <ul className="list-disc list-inside space-y-0.5 text-slate-400 pl-1" data-testid="rca-uncertainty">
                {report.uncertainty.map((u, idx) => (
                  <li key={idx}>{u}</li>
                ))}
              </ul>
            </div>
          )}

          {report.next_checks.length > 0 && (
            <div className="space-y-1">
              <span className="font-semibold text-slate-300 block">Recommended Checks</span>
              <ul className="list-disc list-inside space-y-0.5 text-slate-300 pl-1" data-testid="rca-next-checks">
                {report.next_checks.map((nc, idx) => (
                  <li key={idx}>{nc}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="pt-2 border-t border-slate-800 text-[10px] text-slate-400 flex justify-between">
            <span>Bundle SHA: {report.evidence_bundle_sha256.substring(0, 12)}...</span>
            {report.provider_model && <span>Model: {report.provider_model}</span>}
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-400 italic">
          No root-cause analysis has been generated for this alert yet. Click "Generate RCA" to inspect grounded telemetry evidence.
        </p>
      )}
    </div>
  );
};

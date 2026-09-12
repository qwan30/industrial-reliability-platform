/**
 * Historical Timeline Scrubber for investigating past simulation frames.
 */

import { useState, useEffect } from "react";
import { useRunSlice, labStore } from "./store";
import { getRunHistory, getRunSnapshot } from "./api";
import type { HistoricalFrame } from "./types";

export function Timeline() {
  const { runId, tick: liveTick, status: runStatus } = useRunSlice();
  const [isHistorical, setIsHistorical] = useState(false);
  const [scrubTick, setScrubTick] = useState(0);
  const [historyFrames, setHistoryFrames] = useState<HistoricalFrame[]>([]);

  // Periodically fetch 1Hz history when running or paused
  useEffect(() => {
    if (!runId || runStatus === "IDLE") {
      setHistoryFrames([]);
      setIsHistorical(false);
      return;
    }

    const fetchHistory = async () => {
      try {
        const frames = await getRunHistory(runId, 0, liveTick, 300);
        setHistoryFrames(frames);
      } catch {
        // Silently tolerate during transitions
      }
    };

    fetchHistory();
    const timer = setInterval(fetchHistory, 3000);
    return () => clearInterval(timer);
  }, [runId, liveTick, runStatus]);

  // Keyboard navigation for timeline: Home / End
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (activeTag === "input" || activeTag === "textarea") return;

      if (e.code === "Home") {
        setIsHistorical(true);
        setScrubTick(0);
      } else if (e.code === "End") {
        handleReturnToLive();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [runId, liveTick]);

  const handleReturnToLive = async () => {
    setIsHistorical(false);
    setScrubTick(liveTick);
    if (runId) {
      try {
        const snap = await getRunSnapshot(runId);
        labStore.setRunSnapshot(snap);
      } catch (err) {
        console.error("Failed to restore live snapshot:", err);
      }
    }
  };

  const handleSliderChange = (newTick: number) => {
    if (newTick < liveTick) {
      setIsHistorical(true);
      setScrubTick(newTick);
      // Find historical frame and update preview telemetry
      const frame = historyFrames.find((f) => f.tick === newTick);
      if (frame && frame.observations) {
        labStore.updateObservations(frame.observations);
      }
    } else {
      handleReturnToLive();
    }
  };

  if (!runId || liveTick === 0) return null;

  const currentDisplayTick = isHistorical ? scrubTick : liveTick;
  const currentSimSeconds = (currentDisplayTick * 0.05).toFixed(1);
  const liveSimSeconds = (liveTick * 0.05).toFixed(1);

  return (
    <div className={`lab-timeline-container ${isHistorical ? "historical-active" : ""}`}>
      {isHistorical && (
        <div className="historical-banner">
          <span className="historical-badge">HISTORICAL VIEW</span>
          <span className="historical-time">Inspecting t = {currentSimSeconds}s (live is {liveSimSeconds}s)</span>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={handleReturnToLive}
          >
            Return to Live
          </button>
        </div>
      )}

      <div className="timeline-scrubber-bar">
        <span className="time-marker">0.0s</span>
        <input
          type="range"
          min="0"
          max={liveTick}
          step="20" // 1 second intervals (20 ticks)
          value={currentDisplayTick}
          onChange={(e) => handleSliderChange(parseInt(e.target.value, 10))}
          className="timeline-slider"
          aria-label="Simulation Timeline Scrub"
        />
        <span className="time-marker">{liveSimSeconds}s</span>
      </div>
    </div>
  );
}

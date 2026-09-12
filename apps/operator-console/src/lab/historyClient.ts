/**
 * Historical frames cache and client for timeline playback and run comparison.
 */

import type { HistoricalFrame } from "./types";
import { getRunHistory } from "./api";

class HistoryClient {
  private cache: Map<string, HistoricalFrame[]> = new Map();

  /**
   * Fetch and cache historical frames for a run.
   */
  async getFrames(
    runId: string,
    fromTick: number = 0,
    toTick?: number,
    limit: number = 500
  ): Promise<HistoricalFrame[]> {
    const key = `${runId}:${fromTick}:${toTick ?? "all"}`;
    const cached = this.cache.get(key);
    if (cached) return cached;

    const frames = await getRunHistory(runId, fromTick, toTick, limit);
    this.cache.set(key, frames);
    return frames;
  }

  /**
   * Find closest cached frame for a target tick.
   */
  findClosestFrame(frames: HistoricalFrame[], targetTick: number): HistoricalFrame | null {
    if (!frames.length) return null;
    let closest = frames[0];
    let minDelta = Math.abs(frames[0].tick - targetTick);

    for (const f of frames) {
      const delta = Math.abs(f.tick - targetTick);
      if (delta < minDelta) {
        minDelta = delta;
        closest = f;
      }
    }
    return closest;
  }

  clear() {
    this.cache.clear();
  }
}

export const historyClient = new HistoryClient();

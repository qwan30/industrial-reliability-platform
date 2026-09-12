/**
 * Command dispatch controller with idempotency, revision tracking, and retry support.
 */

import type { CommandReceipt, CommandRequest, CommandStatus } from "./types";
import { submitCommand } from "./api";
import { labStore } from "./store";

export interface PendingCommandState {
  commandId: string;
  action: string;
  targetId?: string | null;
  parameters: Record<string, unknown>;
  expectedRevision: number;
  status: "PENDING" | CommandStatus;
  error?: string;
}

export class CommandController {
  private pendingCommands: Map<string, PendingCommandState> = new Map();

  /**
   * Dispatch an operational command to the active simulation run.
   */
  async dispatch(
    runId: string,
    action: string,
    targetId: string | null,
    parameters: Record<string, unknown>
  ): Promise<CommandReceipt> {
    const runState = labStore.getState().run;
    const currentControlRevision = runState.snapshot?.control_revision ?? 0;

    const commandId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `cmd-${Date.now()}`;
    const request: CommandRequest = {
      command_id: commandId,
      expected_control_revision: currentControlRevision,
      action,
      target_id: targetId,
      parameters,
    };

    const pendingState: PendingCommandState = {
      commandId,
      action,
      targetId,
      parameters,
      expectedRevision: currentControlRevision,
      status: "PENDING",
    };
    this.pendingCommands.set(commandId, pendingState);

    try {
      const receipt = await submitCommand(runId, request);
      pendingState.status = receipt.status;
      return receipt;
    } catch (err: unknown) {
      const error = err as { code?: string; message?: string };
      pendingState.status = "FAILED";
      pendingState.error = error.message || "Failed to dispatch command";

      if (error.code === "CONTROL_REVISION_CONFLICT") {
        // Revision mismatch: notify user without auto-retrying with altered semantics
        console.warn(`[CommandController] Revision conflict on command ${commandId}`);
      }
      throw err;
    }
  }

  getPending(commandId: string): PendingCommandState | undefined {
    return this.pendingCommands.get(commandId);
  }

  clear() {
    this.pendingCommands.clear();
  }
}

export const commandController = new CommandController();

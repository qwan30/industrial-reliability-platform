/**
 * Unit tests for commandController and operational actuation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { commandController } from "../commandController";

describe("commandController", () => {
  beforeEach(() => {
    commandController.clear();
    vi.restoreAllMocks();
  });

  it("dispatches operational command with current control revision", async () => {
    const mockReceipt = {
      command_id: "cmd-123",
      status: "ACCEPTED",
      accepted_sequence: 1,
      control_revision: 1,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: mockReceipt,
        error: null,
      }),
    } as unknown as Response);

    const receipt = await commandController.dispatch(
      "run-456",
      "SET_VALVE_OPENING",
      "valve-789",
      { opening: 0.5 }
    );

    expect(receipt.status).toBe("ACCEPTED");
    const callArgs = (global.fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0];

    const body = JSON.parse(callArgs[1].body as string);
    expect(body.action).toBe("SET_VALVE_OPENING");
    expect(body.parameters.opening).toBe(0.5);
  });

  it("rejects command when server returns 409 revision conflict", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        success: false,
        data: null,
        error: { code: "CONTROL_REVISION_CONFLICT", message: "Revision mismatch" },
      }),
    } as unknown as Response);

    await expect(
      commandController.dispatch("run-456", "SET_VALVE_OPENING", "valve-789", { opening: 0.2 })
    ).rejects.toThrow(/CONTROL_REVISION_CONFLICT/);
  });
});

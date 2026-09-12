/**
 * API client for Industrial Reliability Virtual Lab v2.
 */

import type {
  ApiResponse,
  CommandReceipt,
  CommandRequest,
  HistoricalFrame,
  LabCatalog,
  LabDefinition,
  LabValidationResult,
  RunSnapshot,
  RunSpec,
} from "./types";

const BASE_URL = "";

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  const body: ApiResponse<T> = await response.json();

  if (!response.ok || !body.success || body.data === null) {
    const errorMsg = body.error?.message || `HTTP error ${response.status}`;
    const code = body.error?.code || "HTTP_ERROR";
    const err = new Error(`[${code}] ${errorMsg}`);
    (err as unknown as { code: string; details?: unknown }).code = code;
    (err as unknown as { code: string; details?: unknown }).details = body.error?.details;
    throw err;
  }

  return body.data;
}

export async function getCatalog(): Promise<LabCatalog> {
  return request<LabCatalog>("/v2/catalog");
}

export async function getReferenceTemplate(): Promise<LabDefinition> {
  return request<LabDefinition>("/v2/templates/reference");
}

export async function listLabs(
  after?: string,
  limit: number = 50
): Promise<
  Array<{
    lab_id: string;
    name: string;
    current_revision: number;
    created_at: string;
  }>
> {
  const query = new URLSearchParams();
  if (after) query.set("after", after);
  if (limit) query.set("limit", limit.toString());
  const qs = query.toString() ? `?${query.toString()}` : "";
  return request(`/v2/labs${qs}`);
}

export async function createLab(
  name: string,
  template: "REFERENCE" | "BLANK" = "REFERENCE"
): Promise<LabDefinition> {
  return request<LabDefinition>("/v2/labs", {
    method: "POST",
    body: JSON.stringify({ name, template }),
  });
}

export async function getLab(labId: string): Promise<LabDefinition> {
  return request<LabDefinition>(`/v2/labs/${labId}`);
}

export async function updateLab(
  labId: string,
  definition: LabDefinition,
  expectedRevision: number
): Promise<LabDefinition> {
  return request<LabDefinition>(`/v2/labs/${labId}`, {
    method: "PUT",
    body: JSON.stringify({
      expected_revision: expectedRevision,
      definition,
    }),
  });
}

export async function validateLabRevision(
  labId: string,
  revision: number
): Promise<LabValidationResult> {
  return request<LabValidationResult>(`/v2/labs/${labId}/validate`, {
    method: "POST",
    body: JSON.stringify({ revision }),
  });
}

export async function createRun(
  spec: RunSpec
): Promise<{
  run_id: string;
  status: string;
  snapshot_url: string;
  stream_url: string;
}> {
  return request("/v2/runs", {
    method: "POST",
    body: JSON.stringify(spec),
  });
}

export async function getRunSnapshot(runId: string): Promise<RunSnapshot> {
  return request<RunSnapshot>(`/v2/runs/${runId}`);
}

export async function submitCommand(
  runId: string,
  command: CommandRequest
): Promise<CommandReceipt> {
  return request<CommandReceipt>(`/v2/runs/${runId}/commands`, {
    method: "POST",
    body: JSON.stringify(command),
  });
}

export async function getRunHistory(
  runId: string,
  fromTick: number = 0,
  toTick?: number,
  limit: number = 300
): Promise<HistoricalFrame[]> {
  const query = new URLSearchParams({ from_tick: fromTick.toString() });
  if (toTick !== undefined) query.set("to_tick", toTick.toString());
  if (limit) query.set("limit", limit.toString());
  return request<HistoricalFrame[]>(`/v2/runs/${runId}/history?${query.toString()}`);
}

export async function checkReadyz(): Promise<{
  database: string;
  worker: string;
  kafka: string;
}> {
  return request("/v2/readyz");
}

import { requireRef } from "./contract.js";

export const DIRECT_INPUT_SCHEMA_VERSION = "missionforge.pi_agent_direct_input.v1";
export const DIRECT_OUTPUT_SCHEMA_VERSION = "missionforge.pi_agent_direct_output.v1";

export type DirectStatus = "completed" | "failed" | "blocked" | "cancelled";
export type JsonObject = Record<string, unknown>;

export interface DirectRuntimeInput {
  schema_version: typeof DIRECT_INPUT_SCHEMA_VERSION;
  benchmark_run_id: string;
  task_id: string;
  seed: number;
  workspace_root: string;
  workspace_ref: string;
  input_ref: string;
  output_ref: string;
  session_ref: string;
  events_ref: string;
  metrics_ref: string;
  initial_user_text_ref: string;
  allowed_source_refs: string[];
  expected_output_refs: string[];
  runtime: {
    runtime_name: "missionforge.pi_agent_direct_benchmark";
    timeout_seconds: number;
    model?: string | null;
    metadata?: JsonObject;
  };
}

export interface DirectRuntimeOutput {
  schema_version: typeof DIRECT_OUTPUT_SCHEMA_VERSION;
  benchmark_run_id: string;
  task_id: string;
  seed: number;
  status: DirectStatus;
  workspace_ref: string;
  produced_artifacts: string[];
  changed_refs: string[];
  failures: string[];
  worker_claims: string[];
  input_ref: string;
  output_ref: string;
  session_ref: string;
  events_ref: string;
  metrics_ref: string;
  duration_ms: number;
  metrics: JsonObject;
}

export function parseDirectRuntimeInput(value: unknown): DirectRuntimeInput {
  const data = requireObject(value, "direct_input");
  const schemaVersion = requireString(data.schema_version, "direct_input.schema_version");
  if (schemaVersion !== DIRECT_INPUT_SCHEMA_VERSION) {
    throw new Error(`Unsupported direct schema_version: ${schemaVersion}`);
  }
  const runtime = parseRuntime(data.runtime);
  return {
    schema_version: DIRECT_INPUT_SCHEMA_VERSION,
    benchmark_run_id: requireSafeId(data.benchmark_run_id, "direct_input.benchmark_run_id"),
    task_id: requireSafeId(data.task_id, "direct_input.task_id"),
    seed: requireNonNegativeInteger(data.seed, "direct_input.seed"),
    workspace_root: requireString(data.workspace_root, "direct_input.workspace_root"),
    workspace_ref: requireRef(data.workspace_ref, "direct_input.workspace_ref"),
    input_ref: requireRef(data.input_ref, "direct_input.input_ref"),
    output_ref: requireRef(data.output_ref, "direct_input.output_ref"),
    session_ref: requireRef(data.session_ref, "direct_input.session_ref"),
    events_ref: requireRef(data.events_ref, "direct_input.events_ref"),
    metrics_ref: requireRef(data.metrics_ref, "direct_input.metrics_ref"),
    initial_user_text_ref: requireRef(data.initial_user_text_ref, "direct_input.initial_user_text_ref"),
    allowed_source_refs: requireRefList(data.allowed_source_refs ?? [], "direct_input.allowed_source_refs"),
    expected_output_refs: requireRefList(data.expected_output_refs ?? [], "direct_input.expected_output_refs"),
    runtime,
  };
}

export function validateDirectRuntimeOutput(output: DirectRuntimeOutput): DirectRuntimeOutput {
  if (output.schema_version !== DIRECT_OUTPUT_SCHEMA_VERSION) {
    throw new Error("Unsupported direct output schema_version");
  }
  requireSafeId(output.benchmark_run_id, "direct_output.benchmark_run_id");
  requireSafeId(output.task_id, "direct_output.task_id");
  requireNonNegativeInteger(output.seed, "direct_output.seed");
  if (!["completed", "failed", "blocked", "cancelled"].includes(output.status)) {
    throw new Error("direct_output.status is invalid");
  }
  requireRef(output.workspace_ref, "direct_output.workspace_ref");
  for (const field of ["produced_artifacts", "changed_refs"] as const) {
    requireRefList(output[field], `direct_output.${field}`);
  }
  requireStringList(output.failures, "direct_output.failures");
  requireStringList(output.worker_claims, "direct_output.worker_claims");
  for (const field of ["input_ref", "output_ref", "session_ref", "events_ref", "metrics_ref"] as const) {
    requireRef(output[field], `direct_output.${field}`);
  }
  requireNonNegativeInteger(output.duration_ms, "direct_output.duration_ms");
  requireObject(output.metrics, "direct_output.metrics");
  return output;
}

function parseRuntime(value: unknown): DirectRuntimeInput["runtime"] {
  const data = requireObject(value, "direct_input.runtime");
  const runtimeName = requireString(data.runtime_name, "direct_input.runtime.runtime_name");
  if (runtimeName !== "missionforge.pi_agent_direct_benchmark") {
    throw new Error("direct_input.runtime.runtime_name must be missionforge.pi_agent_direct_benchmark");
  }
  const model = data.model === undefined || data.model === null ? null : requireString(data.model, "direct_input.runtime.model");
  const metadata = data.metadata === undefined ? {} : requireObject(data.metadata, "direct_input.runtime.metadata");
  return {
    runtime_name: "missionforge.pi_agent_direct_benchmark",
    timeout_seconds: requirePositiveInteger(data.timeout_seconds, "direct_input.runtime.timeout_seconds"),
    model,
    metadata,
  };
}

function requireSafeId(value: unknown, field: string): string {
  const text = requireString(value, field);
  if (text === "." || text === ".." || text.includes("/") || text.includes("\\") || text.includes("\0")) {
    throw new Error(`${field} must be a safe id, not a path`);
  }
  return text;
}

function requireRefList(value: unknown, field: string): string[] {
  return requireArray(value, field).map((item, index) => requireRef(item, `${field}[${index}]`));
}

function requireStringList(value: unknown, field: string): string[] {
  return requireArray(value, field).map((item, index) => requireString(item, `${field}[${index}]`));
}

function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  return value;
}

function requireObject(value: unknown, field: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as JsonObject;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

function requirePositiveInteger(value: unknown, field: string): number {
  const number = requireNonNegativeInteger(value, field);
  if (number < 1) throw new Error(`${field} must be at least 1`);
  return number;
}

function requireNonNegativeInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || typeof value !== "number" || value < 0) {
    throw new Error(`${field} must be a non-negative integer`);
  }
  return value;
}

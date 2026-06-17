import type { RuntimeMetrics } from "./evidence-recorder.js";

export const DEFAULT_RESERVED_OUTPUT_TOKENS = 4096;
export const DEFAULT_RESERVED_RUNTIME_BUFFER_TOKENS = 2048;

export interface ContextBudgetInput {
  estimatedInputTokens: number;
  modelContextWindow: number;
  modelMaxOutputTokens?: number;
  metrics?: Pick<RuntimeMetrics, "input_tokens" | "cache_read_tokens" | "cache_write_tokens">;
}

export interface ContextBudgetDiagnostics {
  schema_version: "missionforge.context_budget.v1";
  estimated_input_tokens: number;
  provider_reported_input_tokens: number;
  model_context_window: number;
  reserved_output_tokens: number;
  reserved_runtime_buffer_tokens: number;
  usable_input_budget: number;
  budget_pressure_ratio: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  allocation: {
    stable_authority_prefix: ContextBudgetSlice;
    long_memory_packet: ContextBudgetSlice;
    middle_projection: ContextBudgetSlice;
    recent_tail: ContextBudgetSlice;
  };
}

export interface ContextBudgetSlice {
  budget_tokens: number;
  policy: string;
}

export function buildContextBudgetDiagnostics(input: ContextBudgetInput): ContextBudgetDiagnostics {
  const contextWindow = positiveInteger(input.modelContextWindow, 128000);
  const reservedOutputTokens = clampReserve(
    positiveInteger(input.modelMaxOutputTokens, DEFAULT_RESERVED_OUTPUT_TOKENS),
    contextWindow,
  );
  const reservedRuntimeBufferTokens = clampReserve(DEFAULT_RESERVED_RUNTIME_BUFFER_TOKENS, contextWindow);
  const usableInputBudget = Math.max(1, contextWindow - reservedOutputTokens - reservedRuntimeBufferTokens);
  const estimatedInputTokens = Math.max(0, Math.floor(input.estimatedInputTokens));
  const pressureRatio = clampRatio(estimatedInputTokens / usableInputBudget);
  const providerReportedInputTokens = positiveInteger(input.metrics?.input_tokens, 0);

  return {
    schema_version: "missionforge.context_budget.v1",
    estimated_input_tokens: estimatedInputTokens,
    provider_reported_input_tokens: providerReportedInputTokens,
    model_context_window: contextWindow,
    reserved_output_tokens: reservedOutputTokens,
    reserved_runtime_buffer_tokens: reservedRuntimeBufferTokens,
    usable_input_budget: usableInputBudget,
    budget_pressure_ratio: pressureRatio,
    cache_read_tokens: positiveInteger(input.metrics?.cache_read_tokens, 0),
    cache_write_tokens: positiveInteger(input.metrics?.cache_write_tokens, 0),
    allocation: allocateBudget(usableInputBudget),
  };
}

function allocateBudget(usableInputBudget: number): ContextBudgetDiagnostics["allocation"] {
  const stable = Math.max(1024, Math.floor(usableInputBudget * 0.12));
  const longMemory = Math.min(3000, Math.max(512, Math.floor(usableInputBudget * 0.03)));
  const recentTail = Math.max(4096, Math.floor(usableInputBudget * 0.35));
  const middle = Math.max(1024, usableInputBudget - stable - longMemory - recentTail);
  return {
    stable_authority_prefix: {
      budget_tokens: stable,
      policy: "always_first_refs_only_authority",
    },
    long_memory_packet: {
      budget_tokens: longMemory,
      policy: "optional_advisory_packet_requires_source_refs",
    },
    middle_projection: {
      budget_tokens: middle,
      policy: "deterministic_message_envelopes_and_ref_stubs",
    },
    recent_tail: {
      budget_tokens: recentTail,
      policy: "full_recent_turns_with_tool_pairs_within_budget",
    },
  };
}

function positiveInteger(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.floor(value) : fallback;
}

function clampReserve(value: number, contextWindow: number): number {
  if (contextWindow <= 1) return 0;
  return Math.min(value, Math.max(0, contextWindow - 1));
}

function clampRatio(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0;
  return value > 1 ? 1 : value;
}

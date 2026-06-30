import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ToolResultMessage } from "@earendil-works/pi-ai";
import type { Model } from "@earendil-works/pi-ai";
import { createHash } from "node:crypto";

import { buildContextBudgetDiagnostics } from "./context-budget.js";
import type { ContextBudgetDiagnostics } from "./context-budget.js";
import type { ContextProjectionConfig, RuntimeInput } from "./contract.js";
import { DEFAULT_CONTEXT_PROJECTION_CONFIG } from "./contract.js";
import type { ToolObservation } from "./context-observations.js";
import type { RuntimeMetrics } from "./evidence-recorder.js";
import type { LongMemoryContext, LongMemoryDiagnostics } from "./long-memory.js";
import { resolveWorkspaceRef, writeJsonFile } from "./paths.js";

export const CONTEXT_PROJECTION_SCHEMA_VERSION = "missionforge.pi_agent_context_projection.v1";
const APPROX_CHARS_PER_TOKEN = 4;
const RECENT_FULL_MESSAGE_COUNT = 8;
const MIDDLE_PROJECTED_MESSAGE_COUNT = 16;

export interface ContextProjectorOptions {
  observations: () => readonly ToolObservation[];
  currentTurnIndex: () => number;
  contextWindow?: () => number;
  metrics?: () => Partial<Pick<RuntimeMetrics, "input_tokens" | "cache_read_tokens" | "cache_write_tokens">>;
  longMemory?: () => LongMemoryContext;
}

export interface ContextProjectionDiagnostics {
  schema_version: typeof CONTEXT_PROJECTION_SCHEMA_VERSION;
  call_id: string;
  created_at: string;
  context_observations_ref: string;
  projection_count: number;
  latest_turn_index: number;
  input_message_count: number;
  projected_message_count: number;
  context_projection_config: ContextProjectionConfig;
  model_context_window: number;
  estimated_input_tokens: number;
  pressure_ratio: number;
  soft_compact_ratio: number;
  hard_compact_ratio: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  projection_strategy: "cache_aware_ref_projection";
  recommended_action: "continue" | "prepare_checkpoint" | "checkpoint_before_next_turn";
  context_budget: ContextBudgetDiagnostics;
  memory_layers: ContextMemoryLayerDiagnostics;
  projected_observations: ProjectedObservationDiagnostic[];
  active_observations: ActiveObservationDiagnostic[];
  warnings: string[];
}

export interface ContextMemoryLayerDiagnostics {
  stable_authority_prefix: {
    source: "system_prompt_and_runtime_input_refs";
    kept_first: true;
  };
  long_memory: {
    provider_enabled: boolean;
    packet_ref: string | null;
    provider: string | null;
    advisory_only: true;
    degraded: boolean;
    memory_count: number;
    catalog_hit_count: number;
    budget_tokens: number;
    estimated_tokens: number;
    warnings: string[];
  };
  archived_history: {
    segment_count: number;
    archived_message_count: number;
    catalog_ref: string | null;
    segment_refs: string[];
  };
  middle_history: {
    message_count: number;
    policy: "message_envelopes_with_projected_large_tool_results";
  };
  recent_tail: {
    message_count: number;
    policy: "full_messages_within_budget";
  };
}

export interface ProjectedObservationDiagnostic {
  observation_id: string;
  tool_call_id: string;
  tool_name: string;
  status: ToolObservation["status"];
  inline_policy: ToolObservation["inline_policy"];
  content_hash: string;
  content_bytes: number;
  content_lines: number;
  raw_ref?: string;
  source_ref?: string;
  source_range?: ToolObservation["source_range"];
  source_hash?: string;
  source_bytes?: number;
  projected_bytes: number;
}

export interface ActiveObservationDiagnostic {
  observation_id: string;
  tool_call_id: string;
  tool_name: string;
  inline_policy: ToolObservation["inline_policy"];
  content_hash: string;
  content_bytes: number;
  raw_ref?: string;
  source_ref?: string;
}

export class ContextProjector {
  private projectionCount = 0;
  private latest?: Omit<
    ContextProjectionDiagnostics,
    | "call_id"
    | "created_at"
    | "context_observations_ref"
    | "context_projection_config"
    | "model_context_window"
    | "soft_compact_ratio"
    | "hard_compact_ratio"
    | "cache_read_tokens"
    | "cache_write_tokens"
    | "recommended_action"
    | "context_budget"
  >;
  private pendingArchive?: PendingArchive;
  private latestModelMaxOutputTokens?: number;

  constructor(private readonly options: ContextProjectorOptions) {}

  project(messages: AgentMessage[], systemPrompt = "", model?: Model<any>, input?: RuntimeInput): AgentMessage[] {
    this.latestModelMaxOutputTokens = typeof model?.maxTokens === "number" ? model.maxTokens : undefined;
    const rendered = this.render(messages, input);
    this.projectionCount += 1;
    this.latest = {
      schema_version: CONTEXT_PROJECTION_SCHEMA_VERSION,
      projection_count: this.projectionCount,
      latest_turn_index: rendered.currentTurnIndex,
      input_message_count: messages.length,
      projected_message_count: rendered.projected.length,
      estimated_input_tokens: estimateProjectedInputTokens(rendered.projected, systemPrompt, model),
      pressure_ratio: 0,
      projection_strategy: "cache_aware_ref_projection",
      memory_layers: rendered.memoryLayers,
      projected_observations: rendered.projectedObservations,
      active_observations: rendered.activeObservations,
      warnings: [],
    };
    return rendered.projected;
  }

  private render(messages: AgentMessage[], input?: RuntimeInput): {
    projected: AgentMessage[];
    currentTurnIndex: number;
    memoryLayers: ContextMemoryLayerDiagnostics;
    projectedObservations: ProjectedObservationDiagnostic[];
    activeObservations: ActiveObservationDiagnostic[];
  } {
    const observations = new Map(
      this.options.observations().map((observation) => [observation.tool_call_id, observation]),
    );
    const currentTurnIndex = this.options.currentTurnIndex();
    const projectedObservations: ProjectedObservationDiagnostic[] = [];
    const activeObservations: ActiveObservationDiagnostic[] = [];
    const archive = buildArchive(messages, input);
    this.pendingArchive = archive;
    const activeMessages = archive ? messages.slice(archive.archivedCount) : messages;
    const projectedMessages = activeMessages.map((message) => {
      if (!isToolResultMessage(message)) return message;
      const observation = observations.get(message.toolCallId);
      if (!observation) return message;
      if (!shouldProject(observation, currentTurnIndex)) {
        if (observation.inline_policy !== "keep") activeObservations.push(activeObservationDiagnostic(observation));
        return message;
      }
      const { details: _details, ...withoutDetails } = message;
      const stub = renderProjectionStub(observation);
      projectedObservations.push(projectedObservationDiagnostic(observation, stub));
      const projectedMessage: ToolResultMessage = {
        ...withoutDetails,
        content: [{ type: "text", text: stub }],
      };
      return projectedMessage;
    });
    const longMemory = this.options.longMemory?.();
    const longMemoryMessages = longMemory?.message ? [longMemory.message] : [];
    const projected = archive
      ? [...longMemoryMessages, renderArchiveMessage(archive), ...projectedMessages]
      : [...longMemoryMessages, ...projectedMessages];
    return {
      projected,
      currentTurnIndex,
      memoryLayers: memoryLayers(messages.length, activeMessages.length, archive, longMemory?.diagnostics),
      projectedObservations,
      activeObservations,
    };
  }

  diagnostics(input: RuntimeInput): ContextProjectionDiagnostics {
    const config = input.context_projection_config ?? DEFAULT_CONTEXT_PROJECTION_CONFIG;
    const latest = this.latest ?? {
      schema_version: CONTEXT_PROJECTION_SCHEMA_VERSION,
      projection_count: 0,
      latest_turn_index: this.options.currentTurnIndex(),
      input_message_count: 0,
      projected_message_count: 0,
      estimated_input_tokens: 0,
      pressure_ratio: 0,
      projection_strategy: "cache_aware_ref_projection" as const,
      memory_layers: memoryLayers(0, 0, undefined, undefined),
      projected_observations: [],
      active_observations: [],
      warnings: [],
    };
    const contextWindow = positiveInteger(this.options.contextWindow?.(), DEFAULT_CONTEXT_WINDOW);
    const estimatedInputTokens = Math.max(0, latest.estimated_input_tokens);
    const metrics = this.options.metrics?.() ?? {};
    const contextBudget = buildContextBudgetDiagnostics({
      estimatedInputTokens,
      modelContextWindow: contextWindow,
      modelMaxOutputTokens: this.latestModelMaxOutputTokens,
      metrics: {
        input_tokens: positiveInteger(metrics.input_tokens, 0),
        cache_read_tokens: positiveInteger(metrics.cache_read_tokens, 0),
        cache_write_tokens: positiveInteger(metrics.cache_write_tokens, 0),
      },
    });
    const pressureRatio = contextBudget.budget_pressure_ratio;
    return {
      ...latest,
      pressure_ratio: pressureRatio,
      call_id: input.call_id,
      created_at: new Date().toISOString(),
      context_observations_ref: input.context_observations_ref,
      context_projection_config: config,
      model_context_window: contextWindow,
      soft_compact_ratio: config.soft_compact_ratio,
      hard_compact_ratio: config.hard_compact_ratio,
      cache_read_tokens: positiveInteger(metrics.cache_read_tokens, 0),
      cache_write_tokens: positiveInteger(metrics.cache_write_tokens, 0),
      context_budget: contextBudget,
      recommended_action: recommendedAction(pressureRatio, config),
    };
  }

  async writeDiagnostics(input: RuntimeInput, workspaceRoot: string): Promise<void> {
    if (this.pendingArchive) {
      await writeArchive(input, workspaceRoot, this.pendingArchive);
    }
    await writeJsonFile(
      resolveWorkspaceRef(workspaceRoot, input.context_projection_ref),
      this.diagnostics(input),
      { workspaceRoot },
    );
  }
}

const DEFAULT_CONTEXT_WINDOW = 128000;

export function contextPressureExceeded(
  diagnostics: Pick<ContextProjectionDiagnostics, "pressure_ratio" | "hard_compact_ratio">,
): boolean {
  return diagnostics.pressure_ratio >= diagnostics.hard_compact_ratio;
}

export function estimateProjectedInputTokens(messages: AgentMessage[], systemPrompt = "", model?: Model<any>): number {
  const promptTokens = estimateTextTokens(systemPrompt);
  const messageTokens = estimateMessagesTokens(messages);
  const toolSchemaTokens = estimateToolSchemaTokens(model);
  return promptTokens + messageTokens + toolSchemaTokens;
}

function estimateMessagesTokens(messages: AgentMessage[]): number {
  const json = JSON.stringify(messages, (_key, value) => {
    if (typeof value === "string") return value;
    return value;
  });
  return estimateTextTokens(json);
}

function estimateTextTokens(text: string): number {
  return Math.ceil(Buffer.byteLength(text, "utf-8") / APPROX_CHARS_PER_TOKEN);
}

function estimateToolSchemaTokens(model?: Model<any>): number {
  if (!model) return 0;
  return 0;
}

function recommendedAction(
  pressureRatio: number,
  config: ContextProjectionConfig,
): ContextProjectionDiagnostics["recommended_action"] {
  if (pressureRatio >= config.hard_compact_ratio) return "checkpoint_before_next_turn";
  if (pressureRatio >= config.soft_compact_ratio) return "prepare_checkpoint";
  return "continue";
}

function positiveInteger(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.floor(value) : fallback;
}

function shouldProject(observation: ToolObservation, currentTurnIndex: number): boolean {
  if (observation.inline_policy === "keep") return false;
  if (observation.inline_policy === "ref_only") return true;
  return currentTurnIndex > observation.turn_index + 1;
}

function renderProjectionStub(observation: ToolObservation): string {
  const lines = [
    "[MissionForge context projection]",
    `schema_version: ${CONTEXT_PROJECTION_SCHEMA_VERSION}`,
    `observation_id: ${observation.observation_id}`,
    `tool_call_id: ${observation.tool_call_id}`,
    `tool_name: ${observation.tool_name}`,
    `status: ${observation.status}`,
    `inline_policy: ${observation.inline_policy}`,
    `content_hash: ${observation.content_hash}`,
    `content_bytes: ${observation.content_bytes}`,
    `content_lines: ${observation.content_lines}`,
  ];
  if (observation.raw_ref) lines.push(`raw_ref: ${observation.raw_ref}`);
  if (observation.source_ref) lines.push(`source_ref: ${observation.source_ref}`);
  if (observation.source_range) lines.push(`source_range: ${formatSourceRange(observation.source_range)}`);
  if (observation.source_hash) lines.push(`source_hash: ${observation.source_hash}`);
  if (observation.source_bytes !== undefined) lines.push(`source_bytes: ${observation.source_bytes}`);
  lines.push("projection_note: full tool result body omitted from active model context; use cited refs under current permissions if needed.");
  return `${lines.join("\n")}\n`;
}

function formatSourceRange(range: NonNullable<ToolObservation["source_range"]>): string {
  const parts: string[] = [];
  if (range.offset !== undefined) parts.push(`offset=${range.offset}`);
  if (range.limit !== undefined) parts.push(`limit=${range.limit}`);
  return parts.length > 0 ? parts.join(",") : "all";
}

function projectedObservationDiagnostic(
  observation: ToolObservation,
  stub: string,
): ProjectedObservationDiagnostic {
  return {
    ...observationDiagnosticBase(observation),
    projected_bytes: Buffer.byteLength(stub, "utf-8"),
  };
}

function activeObservationDiagnostic(observation: ToolObservation): ActiveObservationDiagnostic {
  return {
    observation_id: observation.observation_id,
    tool_call_id: observation.tool_call_id,
    tool_name: observation.tool_name,
    inline_policy: observation.inline_policy,
    content_hash: observation.content_hash,
    content_bytes: observation.content_bytes,
    raw_ref: observation.raw_ref,
    source_ref: observation.source_ref,
  };
}

function observationDiagnosticBase(observation: ToolObservation): Omit<ProjectedObservationDiagnostic, "projected_bytes"> {
  return {
    observation_id: observation.observation_id,
    tool_call_id: observation.tool_call_id,
    tool_name: observation.tool_name,
    status: observation.status,
    inline_policy: observation.inline_policy,
    content_hash: observation.content_hash,
    content_bytes: observation.content_bytes,
    content_lines: observation.content_lines,
    raw_ref: observation.raw_ref,
    source_ref: observation.source_ref,
    source_range: observation.source_range,
    source_hash: observation.source_hash,
    source_bytes: observation.source_bytes,
  };
}

function isToolResultMessage(message: AgentMessage): message is ToolResultMessage {
  return Boolean(
    message &&
      typeof message === "object" &&
      (message as { role?: unknown }).role === "toolResult" &&
      typeof (message as { toolCallId?: unknown }).toolCallId === "string",
  );
}

interface PendingArchive {
  catalog_ref: string;
  segments: PendingArchiveSegment[];
  archivedCount: number;
}

interface PendingArchiveSegment {
  segment_ref: string;
  start_index: number;
  end_index: number;
  message_count: number;
  messages: Array<Record<string, unknown>>;
}

function buildArchive(messages: AgentMessage[], input?: RuntimeInput): PendingArchive | undefined {
  if (!input) return undefined;
  const preserved = RECENT_FULL_MESSAGE_COUNT + MIDDLE_PROJECTED_MESSAGE_COUNT;
  if (messages.length <= preserved) return undefined;
  const archivedCount = adjustArchiveBoundaryForToolPairs(messages, messages.length - preserved);
  if (archivedCount <= 0) return undefined;
  const catalogRef = `${input.attempt_dir_ref}/context/segments/catalog.json`;
  const segmentRef = `${input.attempt_dir_ref}/context/segments/segment-000001.jsonl`;
  const archivedMessages = messages.slice(0, archivedCount).map((message, index) =>
    archivedMessageEnvelope(message, index),
  );
  return {
    catalog_ref: catalogRef,
    archivedCount,
    segments: [
      {
        segment_ref: segmentRef,
        start_index: 0,
        end_index: archivedCount - 1,
        message_count: archivedCount,
        messages: archivedMessages,
      },
    ],
  };
}

function adjustArchiveBoundaryForToolPairs(messages: AgentMessage[], candidate: number): number {
  let boundary = Math.max(0, Math.min(candidate, messages.length));
  while (boundary > 0 && boundary < messages.length) {
    const boundaryMessage = messages[boundary];
    if (!isToolResultMessage(boundaryMessage)) break;
    const assistantIndex = findAssistantToolCallIndex(messages, boundary, boundaryMessage.toolCallId);
    if (assistantIndex === undefined || assistantIndex >= boundary) break;
    boundary = assistantIndex;
  }
  return boundary;
}

function findAssistantToolCallIndex(
  messages: AgentMessage[],
  beforeIndex: number,
  toolCallId: string,
): number | undefined {
  for (let index = beforeIndex - 1; index >= 0; index -= 1) {
    const message = messages[index] as any;
    if (message?.role !== "assistant" || !Array.isArray(message.content)) continue;
    if (message.content.some((block: any) => block?.type === "toolCall" && block.id === toolCallId)) {
      return index;
    }
  }
  return undefined;
}

function memoryLayers(
  totalMessageCount: number,
  activeMessageCount: number,
  archive: PendingArchive | undefined,
  longMemory: LongMemoryDiagnostics | undefined,
): ContextMemoryLayerDiagnostics {
  const recentCount = Math.min(activeMessageCount, RECENT_FULL_MESSAGE_COUNT);
  const middleCount = Math.max(0, activeMessageCount - recentCount);
  return {
    stable_authority_prefix: {
      source: "system_prompt_and_runtime_input_refs",
      kept_first: true,
    },
    long_memory: longMemory ?? {
      provider_enabled: false,
      packet_ref: null,
      provider: null,
      advisory_only: true,
      degraded: true,
      memory_count: 0,
      catalog_hit_count: 0,
      budget_tokens: 0,
      estimated_tokens: 0,
      warnings: ["long_memory context not initialized"],
    },
    archived_history: {
      segment_count: archive?.segments.length ?? 0,
      archived_message_count: archive?.archivedCount ?? 0,
      catalog_ref: archive?.catalog_ref ?? null,
      segment_refs: archive?.segments.map((segment) => segment.segment_ref) ?? [],
    },
    middle_history: {
      message_count: middleCount,
      policy: "message_envelopes_with_projected_large_tool_results",
    },
    recent_tail: {
      message_count: totalMessageCount === 0 ? 0 : recentCount,
      policy: "full_messages_within_budget",
    },
  };
}

function renderArchiveMessage(archive: PendingArchive): AgentMessage {
  const lines = [
    "[MissionForge archived context segment]",
    `schema_version: ${CONTEXT_PROJECTION_SCHEMA_VERSION}`,
    `catalog_ref: ${archive.catalog_ref}`,
    `segment_refs: ${archive.segments.map((segment) => segment.segment_ref).join(", ")}`,
    `archived_message_count: ${archive.archivedCount}`,
    "projection_note: older conversation messages were archived as metadata envelopes; use cited refs under current permissions if needed.",
  ];
  return {
    role: "user",
    content: [{ type: "text", text: `${lines.join("\n")}\n` }],
    timestamp: Date.now(),
  } as AgentMessage;
}

async function writeArchive(input: RuntimeInput, workspaceRoot: string, archive: PendingArchive): Promise<void> {
  const catalog = {
    schema_version: "missionforge.context_segment_catalog.v1",
    call_id: input.call_id,
    created_at: new Date().toISOString(),
    segment_count: archive.segments.length,
    archived_message_count: archive.archivedCount,
    segments: archive.segments.map((segment) => ({
      segment_ref: segment.segment_ref,
      start_index: segment.start_index,
      end_index: segment.end_index,
      message_count: segment.message_count,
      content_hash: hashJson(segment.messages),
    })),
  };
  for (const segment of archive.segments) {
    const lines = segment.messages.map((message) => JSON.stringify(message)).join("\n");
    await writeJsonLines(resolveWorkspaceRef(workspaceRoot, segment.segment_ref), lines, workspaceRoot);
  }
  await writeJsonFile(resolveWorkspaceRef(workspaceRoot, archive.catalog_ref), catalog, { workspaceRoot });
}

function archivedMessageEnvelope(message: AgentMessage, index: number): Record<string, unknown> {
  const raw = message as any;
  const content = Array.isArray(raw.content) ? raw.content : [];
  return {
    schema_version: "missionforge.context_segment_entry.v1",
    index,
    role: typeof raw.role === "string" ? raw.role : "unknown",
    timestamp: typeof raw.timestamp === "number" ? raw.timestamp : undefined,
    stop_reason: typeof raw.stopReason === "string" ? raw.stopReason : undefined,
    tool_call_id: typeof raw.toolCallId === "string" ? raw.toolCallId : undefined,
    tool_name: typeof raw.toolName === "string" ? raw.toolName : undefined,
    is_error: typeof raw.isError === "boolean" ? raw.isError : undefined,
    content_block_count: content.length,
    content_bytes: Buffer.byteLength(JSON.stringify(content), "utf-8"),
    content_hash: hashJson(content),
    note: "metadata envelope only; raw prompt, transcript, provider payload, and tool bodies are not embedded",
  };
}

async function writeJsonLines(path: string, lines: string, workspaceRoot: string): Promise<void> {
  const { mkdir, writeFile } = await import("node:fs/promises");
  const { dirname } = await import("node:path");
  const { prepareWorkspaceWritePath } = await import("./paths.js");
  const safePath = prepareWorkspaceWritePath(path, workspaceRoot);
  await mkdir(dirname(safePath), { recursive: true });
  await writeFile(safePath, `${lines}${lines ? "\n" : ""}`, "utf-8");
}

function hashJson(value: unknown): string {
  return `sha256:${createHash("sha256").update(JSON.stringify(value)).digest("hex")}`;
}

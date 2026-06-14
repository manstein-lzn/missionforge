import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ToolResultMessage } from "@earendil-works/pi-ai";

import type { ContextProjectionConfig, RuntimeInput } from "./contract.js";
import { DEFAULT_CONTEXT_PROJECTION_CONFIG } from "./contract.js";
import type { ToolObservation } from "./context-observations.js";
import { resolveWorkspaceRef, writeJsonFile } from "./paths.js";

export const CONTEXT_PROJECTION_SCHEMA_VERSION = "missionforge.pi_agent_context_projection.v1";

export interface ContextProjectorOptions {
  observations: () => readonly ToolObservation[];
  currentTurnIndex: () => number;
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
  projected_observations: ProjectedObservationDiagnostic[];
  active_observations: ActiveObservationDiagnostic[];
  warnings: string[];
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
    "call_id" | "created_at" | "context_observations_ref" | "context_projection_config"
  >;

  constructor(private readonly options: ContextProjectorOptions) {}

  project(messages: AgentMessage[]): AgentMessage[] {
    const rendered = this.render(messages);
    this.projectionCount += 1;
    this.latest = {
      schema_version: CONTEXT_PROJECTION_SCHEMA_VERSION,
      projection_count: this.projectionCount,
      latest_turn_index: rendered.currentTurnIndex,
      input_message_count: messages.length,
      projected_message_count: rendered.projected.length,
      projected_observations: rendered.projectedObservations,
      active_observations: rendered.activeObservations,
      warnings: [],
    };
    return rendered.projected;
  }

  private render(messages: AgentMessage[]): {
    projected: AgentMessage[];
    currentTurnIndex: number;
    projectedObservations: ProjectedObservationDiagnostic[];
    activeObservations: ActiveObservationDiagnostic[];
  } {
    const observations = new Map(
      this.options.observations().map((observation) => [observation.tool_call_id, observation]),
    );
    const currentTurnIndex = this.options.currentTurnIndex();
    const projectedObservations: ProjectedObservationDiagnostic[] = [];
    const activeObservations: ActiveObservationDiagnostic[] = [];
    const projected = messages.map((message) => {
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
    return {
      projected,
      currentTurnIndex,
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
      projected_observations: [],
      active_observations: [],
      warnings: [],
    };
    return {
      ...latest,
      call_id: input.call_id,
      created_at: new Date().toISOString(),
      context_observations_ref: input.context_observations_ref,
      context_projection_config: config,
    };
  }

  async writeDiagnostics(input: RuntimeInput, workspaceRoot: string): Promise<void> {
    await writeJsonFile(
      resolveWorkspaceRef(workspaceRoot, input.context_projection_ref),
      this.diagnostics(input),
      { workspaceRoot },
    );
  }
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

import type { AgentTool } from "@earendil-works/pi-agent-core";
import { type Static, Type } from "typebox";

import type { PermissionManifest } from "./contract.js";
import type { ToolObservation } from "./context-observations.js";
import type { ContextProjectionDiagnostics } from "./context-projector.js";
import { ToolPermissionEnforcer } from "./permissions.js";

export const CONTEXT_SNAPSHOT_SCHEMA_VERSION = "missionforge.pi_agent_context_snapshot.v1";

const contextSnapshotSchema = Type.Object({
  observation_id: Type.Optional(Type.String({ description: "Optional observation id to inspect." })),
});

type ContextSnapshotInput = Static<typeof contextSnapshotSchema>;

export interface ContextSnapshotToolOptions {
  callId: string;
  workspaceRoot: string;
  permissionManifest: PermissionManifest;
  contextObservationsRef: string;
  contextProjectionRef: string;
  observations: () => readonly ToolObservation[];
  currentTurnIndex: () => number;
  projectionDiagnostics?: () => ContextProjectionDiagnostics | undefined;
}

export interface ContextSnapshot {
  schema_version: typeof CONTEXT_SNAPSHOT_SCHEMA_VERSION;
  call_id: string;
  created_at: string;
  context_observations_ref: string;
  context_projection_ref: string;
  latest_turn_index: number;
  observation_count: number;
  projection: ContextSnapshotProjection;
  observations: ContextSnapshotObservation[];
  warnings: string[];
}

export interface ContextSnapshotProjection {
  projection_count: number;
  projected_observation_count: number;
  active_observation_count: number;
  projected_observation_ids: string[];
  active_observation_ids: string[];
  warnings: string[];
}

export interface ContextSnapshotObservation {
  observation_id: string;
  tool_call_id: string;
  tool_name: string;
  status: ToolObservation["status"];
  turn_index: number;
  inline_policy: ToolObservation["inline_policy"];
  projection_state: "inline" | "projected_stub";
  content_hash: string;
  content_bytes: number;
  content_lines: number;
  raw_ref?: ContextSnapshotRef;
  source_ref?: ContextSnapshotRef;
  source_range?: ToolObservation["source_range"];
  source_hash?: string;
  source_bytes?: number;
}

export interface ContextSnapshotRef {
  ref: string;
  readable: boolean;
  unreadable_reason?: string;
  read_args?: {
    path: string;
    offset?: number;
    limit?: number;
  };
}

export function createContextSnapshotTool(options: ContextSnapshotToolOptions): AgentTool<typeof contextSnapshotSchema> {
  return {
    name: "context_snapshot",
    label: "context_snapshot",
    description:
      "Inspect MissionForge context observations and projection refs. Returns metadata only: refs, hashes, sizes, projection state, and current read permission status. Does not return raw tool output bodies.",
    parameters: contextSnapshotSchema,
    async execute(_toolCallId: string, params: ContextSnapshotInput) {
      const snapshot = buildContextSnapshot(options, params);
      return {
        content: [{ type: "text", text: `${JSON.stringify(snapshot, null, 2)}\n` }],
        details: {
          schema_version: snapshot.schema_version,
          observation_count: snapshot.observation_count,
          projected_observation_count: snapshot.projection.projected_observation_count,
        },
      };
    },
  };
}

export function buildContextSnapshot(
  options: ContextSnapshotToolOptions,
  params: ContextSnapshotInput = {},
): ContextSnapshot {
  const enforcer = new ToolPermissionEnforcer(options.workspaceRoot, options.permissionManifest);
  const diagnostics = options.projectionDiagnostics?.();
  const projectedObservationIds = new Set(
    diagnostics?.projected_observations.map((item) => item.observation_id) ?? [],
  );
  const activeObservationIds = new Set(
    diagnostics?.active_observations.map((item) => item.observation_id) ?? [],
  );
  const currentTurnIndex = options.currentTurnIndex();
  const observations = options.observations()
    .filter((observation) => !params.observation_id || observation.observation_id === params.observation_id)
    .map((observation) => snapshotObservation(observation, {
      currentTurnIndex,
      projectedObservationIds,
      enforcer,
    }));
  const warnings = params.observation_id && observations.length === 0
    ? [`observation_id not found: ${params.observation_id}`]
    : [];

  return {
    schema_version: CONTEXT_SNAPSHOT_SCHEMA_VERSION,
    call_id: options.callId,
    created_at: new Date().toISOString(),
    context_observations_ref: options.contextObservationsRef,
    context_projection_ref: options.contextProjectionRef,
    latest_turn_index: currentTurnIndex,
    observation_count: observations.length,
    projection: {
      projection_count: diagnostics?.projection_count ?? 0,
      projected_observation_count: projectedObservationIds.size,
      active_observation_count: activeObservationIds.size,
      projected_observation_ids: [...projectedObservationIds].sort(),
      active_observation_ids: [...activeObservationIds].sort(),
      warnings: diagnostics?.warnings ?? [],
    },
    observations,
    warnings,
  };
}

function snapshotObservation(
  observation: ToolObservation,
  options: {
    currentTurnIndex: number;
    projectedObservationIds: ReadonlySet<string>;
    enforcer: ToolPermissionEnforcer;
  },
): ContextSnapshotObservation {
  return {
    observation_id: observation.observation_id,
    tool_call_id: observation.tool_call_id,
    tool_name: observation.tool_name,
    status: observation.status,
    turn_index: observation.turn_index,
    inline_policy: observation.inline_policy,
    projection_state: projectionState(observation, options.currentTurnIndex, options.projectedObservationIds),
    content_hash: observation.content_hash,
    content_bytes: observation.content_bytes,
    content_lines: observation.content_lines,
    raw_ref: snapshotRef(options.enforcer, observation.raw_ref),
    source_ref: snapshotRef(options.enforcer, observation.source_ref, observation.source_range),
    source_range: observation.source_range,
    source_hash: observation.source_hash,
    source_bytes: observation.source_bytes,
  };
}

function projectionState(
  observation: ToolObservation,
  currentTurnIndex: number,
  projectedObservationIds: ReadonlySet<string>,
): ContextSnapshotObservation["projection_state"] {
  if (projectedObservationIds.has(observation.observation_id)) return "projected_stub";
  if (observation.inline_policy === "ref_only") return "projected_stub";
  if (observation.inline_policy === "demote_after_turn" && currentTurnIndex > observation.turn_index + 1) {
    return "projected_stub";
  }
  return "inline";
}

function snapshotRef(
  enforcer: ToolPermissionEnforcer,
  ref: string | undefined,
  range: ToolObservation["source_range"] = undefined,
): ContextSnapshotRef | undefined {
  if (!ref) return undefined;
  try {
    enforcer.ensureReadRef(ref);
    const readArgs: NonNullable<ContextSnapshotRef["read_args"]> = { path: ref };
    if (range?.offset !== undefined) readArgs.offset = range.offset;
    if (range?.limit !== undefined) readArgs.limit = range.limit;
    return {
      ref,
      readable: true,
      read_args: readArgs,
    };
  } catch (error) {
    return {
      ref,
      readable: false,
      unreadable_reason: unreadableReason(error),
    };
  }
}

function unreadableReason(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes("ref is denied")) return "ref_denied";
  if (message.includes("outside allowed roots")) return "ref_outside_allowed_roots";
  return "read_not_allowed";
}

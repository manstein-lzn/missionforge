import { Type } from "typebox";
import { ToolPermissionEnforcer } from "./permissions.js";
export const CONTEXT_SNAPSHOT_SCHEMA_VERSION = "missionforge.pi_agent_context_snapshot.v1";
const contextSnapshotSchema = Type.Object({
    observation_id: Type.Optional(Type.String({ description: "Optional observation id to inspect." })),
});
export function createContextSnapshotTool(options) {
    return {
        name: "context_snapshot",
        label: "context_snapshot",
        description: "Inspect MissionForge context observations and projection refs. Returns metadata only: refs, hashes, sizes, projection state, and current read permission status. Does not return raw tool output bodies.",
        parameters: contextSnapshotSchema,
        async execute(_toolCallId, params) {
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
export function buildContextSnapshot(options, params = {}) {
    const enforcer = new ToolPermissionEnforcer(options.workspaceRoot, options.permissionManifest);
    const diagnostics = options.projectionDiagnostics?.();
    const projectedObservationIds = new Set(diagnostics?.projected_observations.map((item) => item.observation_id) ?? []);
    const activeObservationIds = new Set(diagnostics?.active_observations.map((item) => item.observation_id) ?? []);
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
function snapshotObservation(observation, options) {
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
function projectionState(observation, currentTurnIndex, projectedObservationIds) {
    if (projectedObservationIds.has(observation.observation_id))
        return "projected_stub";
    if (observation.inline_policy === "ref_only")
        return "projected_stub";
    if (observation.inline_policy === "demote_after_turn" && currentTurnIndex > observation.turn_index + 1) {
        return "projected_stub";
    }
    return "inline";
}
function snapshotRef(enforcer, ref, range = undefined) {
    if (!ref)
        return undefined;
    try {
        enforcer.ensureReadRef(ref);
        const readArgs = { path: ref };
        if (range?.offset !== undefined)
            readArgs.offset = range.offset;
        if (range?.limit !== undefined)
            readArgs.limit = range.limit;
        return {
            ref,
            readable: true,
            read_args: readArgs,
        };
    }
    catch (error) {
        return {
            ref,
            readable: false,
            unreadable_reason: unreadableReason(error),
        };
    }
}
function unreadableReason(error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("ref is denied"))
        return "ref_denied";
    if (message.includes("outside allowed roots"))
        return "ref_outside_allowed_roots";
    return "read_not_allowed";
}

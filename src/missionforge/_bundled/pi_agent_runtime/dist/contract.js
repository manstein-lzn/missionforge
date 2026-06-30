export const INPUT_SCHEMA_VERSION = "missionforge.pi_agent_runtime_input.v1";
export const OUTPUT_SCHEMA_VERSION = "missionforge.pi_agent_runtime_output.v1";
export const PERMISSION_MANIFEST_SCHEMA_VERSION = "permission_manifest.v1";
export const CAPABILITY_GRANT_SCHEMA_VERSION = "runtime_capability_grant.v1";
export const SANDBOX_PROFILE_SCHEMA_VERSION = "sandbox_profile.v1";
export const EXTENSION_LOCK_SCHEMA_VERSION = "missionforge_extension_lock.v1";
export const EXTENSION_LOAD_REPORT_SCHEMA_VERSION = "missionforge_extension_load_report.v1";
export const CONTEXT_ENGINE_SCHEMA_VERSION = "missionforge.pi_agent_context_engine.v1";
export const CONTEXT_PROJECTION_CONFIG_SCHEMA_VERSION = "missionforge.pi_agent_context_projection_config.v1";
export const RUNTIME_CONTEXT_CHECKPOINT_SCHEMA_VERSION = "missionforge.runtime_context_checkpoint.v1";
export const LONG_MEMORY_PACKET_SCHEMA_VERSION = "missionforge.long_memory_packet.v1";
export const DEFAULT_CONTEXT_LARGE_OBSERVATION_BYTES = 8 * 1024;
export const DEFAULT_CONTEXT_SOFT_COMPACT_RATIO = 0.8;
export const DEFAULT_CONTEXT_HARD_COMPACT_RATIO = 0.9;
export const DEFAULT_CONTEXT_CACHE_AWARE = true;
export const DEFAULT_CONTEXT_PROJECTION_CONFIG = {
    schema_version: CONTEXT_PROJECTION_CONFIG_SCHEMA_VERSION,
    large_observation_bytes: DEFAULT_CONTEXT_LARGE_OBSERVATION_BYTES,
    soft_compact_ratio: DEFAULT_CONTEXT_SOFT_COMPACT_RATIO,
    hard_compact_ratio: DEFAULT_CONTEXT_HARD_COMPACT_RATIO,
    cache_aware: DEFAULT_CONTEXT_CACHE_AWARE,
};
export function parseRuntimeInput(value) {
    const data = requireObject(value, "input");
    const schemaVersion = requireString(data.schema_version, "schema_version");
    if (schemaVersion !== INPUT_SCHEMA_VERSION) {
        throw new Error(`Unsupported schema_version: ${schemaVersion}`);
    }
    const callSpec = parsePiAgentCallSpec(data.call_spec);
    const attemptDirRef = requireRef(data.attempt_dir_ref, "attempt_dir_ref");
    const result = {
        schema_version: INPUT_SCHEMA_VERSION,
        call_id: requireString(data.call_id, "call_id"),
        mission_id: requireString(data.mission_id, "mission_id"),
        iteration: requirePositiveInteger(data.iteration, "iteration"),
        workspace_root: requireString(data.workspace_root, "workspace_root"),
        attempt_dir_ref: attemptDirRef,
        input_ref: requireRef(data.input_ref, "input_ref"),
        output_ref: requireRef(data.output_ref, "output_ref"),
        session_ref: requireRef(data.session_ref, "session_ref"),
        events_ref: requireRef(data.events_ref, "events_ref"),
        metrics_ref: requireRef(data.metrics_ref, "metrics_ref"),
        savepoints_ref: requireRef(data.savepoints_ref, "savepoints_ref"),
        context_observations_ref: data.context_observations_ref === undefined || data.context_observations_ref === null
            ? `${attemptDirRef}/context/tool_observations.jsonl`
            : requireRef(data.context_observations_ref, "context_observations_ref"),
        context_projection_ref: data.context_projection_ref === undefined || data.context_projection_ref === null
            ? `${attemptDirRef}/context/projection.json`
            : requireRef(data.context_projection_ref, "context_projection_ref"),
        context_raw_dir_ref: data.context_raw_dir_ref === undefined || data.context_raw_dir_ref === null
            ? `${attemptDirRef}/context/raw`
            : requireRef(data.context_raw_dir_ref, "context_raw_dir_ref"),
        long_memory_packet_ref: data.long_memory_packet_ref === undefined || data.long_memory_packet_ref === null
            ? null
            : requireRef(data.long_memory_packet_ref, "long_memory_packet_ref"),
        context_projection_config: parseContextProjectionConfig(data.context_projection_config),
        context_engine: parseContextEngineInput(data.context_engine),
        extension_lock_ref: data.extension_lock_ref === undefined || data.extension_lock_ref === null
            ? null
            : requireRef(data.extension_lock_ref, "extension_lock_ref"),
        extension_load_report_ref: data.extension_load_report_ref === undefined || data.extension_load_report_ref === null
            ? `${attemptDirRef}/reports/extension_load_report.json`
            : requireRef(data.extension_load_report_ref, "extension_load_report_ref"),
        piworker_call: parsePiWorkerCall(data.piworker_call),
        call_spec: callSpec,
        permission_manifest: parsePermissionManifest(data.permission_manifest),
        capability_grant: parseCapabilityGrant(data.capability_grant),
        sandbox_profile: parseSandboxProfile(data.sandbox_profile),
        runtime: parseRuntime(data.runtime),
        repair: parseRepair(data.repair),
        resume: parseResume(data.resume),
    };
    if (result.call_id !== callSpec.call_id) {
        throw new Error("input.call_id must match call_spec.call_id");
    }
    if (result.mission_id !== callSpec.mission_id) {
        throw new Error("input.mission_id must match call_spec.mission_id");
    }
    if (result.piworker_call.call_id !== result.call_id) {
        throw new Error("input.piworker_call.call_id must match call_id");
    }
    if (result.piworker_call.contract_id !== result.mission_id) {
        throw new Error("input.piworker_call.contract_id must match mission_id");
    }
    if (!refIsUnder(result.context_observations_ref, result.attempt_dir_ref)) {
        throw new Error("input.context_observations_ref must be inside attempt_dir_ref");
    }
    if (!refIsUnder(result.context_projection_ref, result.attempt_dir_ref)) {
        throw new Error("input.context_projection_ref must be inside attempt_dir_ref");
    }
    if (!refIsUnder(result.context_raw_dir_ref, result.attempt_dir_ref)) {
        throw new Error("input.context_raw_dir_ref must be inside attempt_dir_ref");
    }
    if (result.long_memory_packet_ref !== null && !refIsUnder(result.long_memory_packet_ref, result.attempt_dir_ref)) {
        throw new Error("input.long_memory_packet_ref must be inside attempt_dir_ref");
    }
    if (!refIsUnder(result.extension_load_report_ref, result.attempt_dir_ref)) {
        throw new Error("input.extension_load_report_ref must be inside attempt_dir_ref");
    }
    for (const ref of result.piworker_call.expected_output_refs) {
        if (!callSpec.expected_outputs.includes(ref)) {
            throw new Error("input.piworker_call expected output must be present in call_spec.expected_outputs");
        }
    }
    validateRuntimeAuthority(result);
    return result;
}
export function parseContextEngineInput(value) {
    if (value === undefined || value === null) {
        return emptyContextEngineInput();
    }
    const data = requireObject(value, "context_engine");
    const schemaVersion = requireString(data.schema_version ?? CONTEXT_ENGINE_SCHEMA_VERSION, "context_engine.schema_version");
    if (schemaVersion !== CONTEXT_ENGINE_SCHEMA_VERSION) {
        throw new Error(`Unsupported context_engine.schema_version: ${schemaVersion}`);
    }
    const enabled = requireBoolean(data.enabled ?? false, "context_engine.enabled");
    const contextViewRef = optionalRef(data.context_view_ref, "context_engine.context_view_ref");
    const compileResultRef = optionalRef(data.context_compile_result_ref, "context_engine.context_compile_result_ref");
    const result = {
        schema_version: CONTEXT_ENGINE_SCHEMA_VERSION,
        enabled,
        context_view_ref: contextViewRef,
        context_compile_request_ref: optionalRef(data.context_compile_request_ref, "context_engine.context_compile_request_ref"),
        context_compile_result_ref: compileResultRef,
        context_baseline_ref: optionalRef(data.context_baseline_ref, "context_engine.context_baseline_ref"),
        context_source_snapshot_ref: optionalRef(data.context_source_snapshot_ref, "context_engine.context_source_snapshot_ref"),
        context_epoch_ref: optionalRef(data.context_epoch_ref, "context_engine.context_epoch_ref"),
        context_cache_layout_ref: optionalRef(data.context_cache_layout_ref, "context_engine.context_cache_layout_ref"),
        context_pressure_ref: optionalRef(data.context_pressure_ref, "context_engine.context_pressure_ref"),
        context_turn_safe_point_ref: optionalRef(data.context_turn_safe_point_ref, "context_engine.context_turn_safe_point_ref"),
        context_turn_boundary_ref: optionalRef(data.context_turn_boundary_ref, "context_engine.context_turn_boundary_ref"),
        context_hash: optionalSha256(data.context_hash, "context_engine.context_hash"),
        context_compile_action: optionalString(data.context_compile_action, "context_engine.context_compile_action"),
    };
    if (enabled && (!contextViewRef || !compileResultRef)) {
        throw new Error("context_engine enabled requires context_view_ref and context_compile_result_ref");
    }
    return result;
}
function emptyContextEngineInput() {
    return {
        schema_version: CONTEXT_ENGINE_SCHEMA_VERSION,
        enabled: false,
        context_view_ref: null,
        context_compile_request_ref: null,
        context_compile_result_ref: null,
        context_baseline_ref: null,
        context_source_snapshot_ref: null,
        context_epoch_ref: null,
        context_cache_layout_ref: null,
        context_pressure_ref: null,
        context_turn_safe_point_ref: null,
        context_turn_boundary_ref: null,
        context_hash: null,
        context_compile_action: "",
    };
}
export function parsePermissionManifest(value) {
    const data = requireObject(value, "permission_manifest");
    const schemaVersion = requireString(data.schema_version ?? PERMISSION_MANIFEST_SCHEMA_VERSION, "permission_manifest.schema_version");
    if (schemaVersion !== PERMISSION_MANIFEST_SCHEMA_VERSION) {
        throw new Error(`Unsupported permission_manifest.schema_version: ${schemaVersion}`);
    }
    const networkPolicy = requireString(data.network_policy ?? "disabled", "permission_manifest.network_policy");
    if (!["disabled", "restricted", "enabled"].includes(networkPolicy)) {
        throw new Error("permission_manifest.network_policy must be disabled, restricted, or enabled");
    }
    return {
        manifest_id: requireString(data.manifest_id, "permission_manifest.manifest_id"),
        workspace_policy_ref: data.workspace_policy_ref === undefined || data.workspace_policy_ref === null
            ? null
            : requireRef(data.workspace_policy_ref, "permission_manifest.workspace_policy_ref"),
        readable_refs: requireRefList(data.readable_refs ?? [], "permission_manifest.readable_refs"),
        writable_refs: requireRefList(data.writable_refs ?? [], "permission_manifest.writable_refs"),
        denied_refs: requireRefList(data.denied_refs ?? [], "permission_manifest.denied_refs"),
        allowed_tools: requireStringList(data.allowed_tools ?? ["read", "write", "edit"], "permission_manifest.allowed_tools"),
        allowed_commands: requireStringList(data.allowed_commands ?? [], "permission_manifest.allowed_commands"),
        network_policy: networkPolicy,
        env_allowlist: requireStringList(data.env_allowlist ?? [], "permission_manifest.env_allowlist"),
        secret_ref: data.secret_ref === undefined || data.secret_ref === null
            ? null
            : requireRef(data.secret_ref, "permission_manifest.secret_ref"),
        unsupported_hard_policies: requireStringList(data.unsupported_hard_policies ?? [], "permission_manifest.unsupported_hard_policies"),
        extension_grants: parseExtensionGrants(data.extension_grants ?? []),
        schema_version: PERMISSION_MANIFEST_SCHEMA_VERSION,
    };
}
export function parseExtensionGrant(value) {
    const data = requireObject(value, "extension_grant");
    const capability = requireString(data.capability, "extension_grant.capability");
    if (!isExtensionCapability(capability)) {
        throw new Error("extension_grant.capability is invalid");
    }
    const adapterMode = requireString(data.adapter_mode ?? "missionforge_provider", "extension_grant.adapter_mode");
    if (!isExtensionAdapterMode(adapterMode)) {
        throw new Error("extension_grant.adapter_mode is invalid");
    }
    const requiredEnv = requireStringList(data.required_env ?? [], "extension_grant.required_env");
    for (const name of requiredEnv)
        requireEnvName(name, "extension_grant.required_env[]");
    return {
        grant_id: requireString(data.grant_id, "extension_grant.grant_id"),
        package: requireExtensionPackage(data.package, "extension_grant.package"),
        version_spec: requireString(data.version_spec, "extension_grant.version_spec"),
        capability,
        config_ref: data.config_ref === undefined || data.config_ref === null
            ? null
            : requireRef(data.config_ref, "extension_grant.config_ref"),
        requires_network: requireBoolean(data.requires_network ?? false, "extension_grant.requires_network"),
        requires_bash: requireBoolean(data.requires_bash ?? false, "extension_grant.requires_bash"),
        required_env: requiredEnv,
        sandbox_profile_ref: data.sandbox_profile_ref === undefined || data.sandbox_profile_ref === null
            ? null
            : requireRef(data.sandbox_profile_ref, "extension_grant.sandbox_profile_ref"),
        adapter_mode: adapterMode,
        integrity: data.integrity === undefined || data.integrity === null
            ? null
            : requireString(data.integrity, "extension_grant.integrity"),
        metadata: data.metadata === undefined ? {} : requireObject(data.metadata, "extension_grant.metadata"),
    };
}
export function parseExtensionLock(value) {
    const data = requireObject(value, "extension_lock");
    const schemaVersion = requireString(data.schema_version ?? EXTENSION_LOCK_SCHEMA_VERSION, "extension_lock.schema_version");
    if (schemaVersion !== EXTENSION_LOCK_SCHEMA_VERSION) {
        throw new Error(`Unsupported extension_lock.schema_version: ${schemaVersion}`);
    }
    const lockHash = data.lock_hash === undefined || data.lock_hash === null
        ? undefined
        : requireSha256(data.lock_hash, "extension_lock.lock_hash");
    return {
        schema_version: EXTENSION_LOCK_SCHEMA_VERSION,
        source_permission_manifest_ref: requireRef(data.source_permission_manifest_ref, "extension_lock.source_permission_manifest_ref"),
        compiled_at: requireIsoTimestamp(data.compiled_at, "extension_lock.compiled_at"),
        install_root_ref: requireRef(data.install_root_ref ?? ".missionforge/extensions", "extension_lock.install_root_ref"),
        compiled_by: requireString(data.compiled_by ?? "missionforge.extensions", "extension_lock.compiled_by"),
        extensions: parseExtensionLockEntries(data.extensions ?? []),
        ...(lockHash ? { lock_hash: lockHash } : {}),
    };
}
export function parseExtensionLoadReport(value) {
    const data = requireObject(value, "extension_load_report");
    const schemaVersion = requireString(data.schema_version ?? EXTENSION_LOAD_REPORT_SCHEMA_VERSION, "extension_load_report.schema_version");
    if (schemaVersion !== EXTENSION_LOAD_REPORT_SCHEMA_VERSION) {
        throw new Error(`Unsupported extension_load_report.schema_version: ${schemaVersion}`);
    }
    return {
        schema_version: EXTENSION_LOAD_REPORT_SCHEMA_VERSION,
        call_id: requireString(data.call_id, "extension_load_report.call_id"),
        extension_lock_ref: data.extension_lock_ref === undefined || data.extension_lock_ref === null
            ? null
            : requireRef(data.extension_lock_ref, "extension_load_report.extension_lock_ref"),
        permission_manifest_ref: data.permission_manifest_ref === undefined || data.permission_manifest_ref === null
            ? null
            : requireRef(data.permission_manifest_ref, "extension_load_report.permission_manifest_ref"),
        loaded_extensions: parseExtensionLoadRecords(data.loaded_extensions ?? [], "extension_load_report.loaded_extensions"),
        rejected_extensions: parseExtensionLoadRecords(data.rejected_extensions ?? [], "extension_load_report.rejected_extensions"),
    };
}
export function parseCapabilityGrant(value) {
    const data = requireObject(value, "capability_grant");
    const schemaVersion = requireString(data.schema_version ?? CAPABILITY_GRANT_SCHEMA_VERSION, "capability_grant.schema_version");
    if (schemaVersion !== CAPABILITY_GRANT_SCHEMA_VERSION) {
        throw new Error(`Unsupported capability_grant.schema_version: ${schemaVersion}`);
    }
    const role = requireString(data.role, "capability_grant.role");
    if (![
        "frontdesk_author_piworker",
        "executor_piworker",
        "judge_piworker",
        "repair_piworker",
        "revision_drafter_piworker",
    ].includes(role)) {
        throw new Error("capability_grant.role is invalid");
    }
    const grantHash = data.grant_hash === undefined || data.grant_hash === null
        ? undefined
        : requireSha256(data.grant_hash, "capability_grant.grant_hash");
    return {
        schema_version: CAPABILITY_GRANT_SCHEMA_VERSION,
        grant_id: requireString(data.grant_id, "capability_grant.grant_id"),
        role,
        contract_hash: requireSha256(data.contract_hash, "capability_grant.contract_hash"),
        workspace_policy_ref: requireRef(data.workspace_policy_ref, "capability_grant.workspace_policy_ref"),
        permission_manifest_ref: requireRef(data.permission_manifest_ref, "capability_grant.permission_manifest_ref"),
        workspace_view_ref: requireRef(data.workspace_view_ref, "capability_grant.workspace_view_ref"),
        sandbox_profile_ref: requireRef(data.sandbox_profile_ref, "capability_grant.sandbox_profile_ref"),
        issued_by: requireString(data.issued_by, "capability_grant.issued_by"),
        issued_at: requireIsoTimestamp(data.issued_at, "capability_grant.issued_at"),
        expires_at: requireIsoTimestamp(data.expires_at, "capability_grant.expires_at"),
        parent_grant_ref: data.parent_grant_ref === undefined || data.parent_grant_ref === null
            ? null
            : requireRef(data.parent_grant_ref, "capability_grant.parent_grant_ref"),
        revoked_at: data.revoked_at === undefined || data.revoked_at === null
            ? null
            : requireIsoTimestamp(data.revoked_at, "capability_grant.revoked_at"),
        metadata: data.metadata === undefined ? {} : requireObject(data.metadata, "capability_grant.metadata"),
        ...(grantHash ? { grant_hash: grantHash } : {}),
    };
}
export function parseSandboxProfile(value) {
    const data = requireObject(value, "sandbox_profile");
    const schemaVersion = requireString(data.schema_version ?? SANDBOX_PROFILE_SCHEMA_VERSION, "sandbox_profile.schema_version");
    if (schemaVersion !== SANDBOX_PROFILE_SCHEMA_VERSION) {
        throw new Error(`Unsupported sandbox_profile.schema_version: ${schemaVersion}`);
    }
    const mode = requireString(data.mode, "sandbox_profile.mode");
    if (!["bubblewrap", "nsjail", "subprocess", "unsupported"].includes(mode)) {
        throw new Error("sandbox_profile.mode is invalid");
    }
    const profileHash = data.profile_hash === undefined || data.profile_hash === null
        ? undefined
        : requireSha256(data.profile_hash, "sandbox_profile.profile_hash");
    return {
        schema_version: SANDBOX_PROFILE_SCHEMA_VERSION,
        profile_id: requireString(data.profile_id, "sandbox_profile.profile_id"),
        mode,
        workspace_root_ref: requireRef(data.workspace_root_ref, "sandbox_profile.workspace_root_ref"),
        readable_refs: requireRefList(data.readable_refs ?? [], "sandbox_profile.readable_refs"),
        writable_refs: requireRefList(data.writable_refs ?? [], "sandbox_profile.writable_refs"),
        denied_refs: requireRefList(data.denied_refs ?? [], "sandbox_profile.denied_refs"),
        allowed_tools: requireStringList(data.allowed_tools ?? ["read", "write", "edit"], "sandbox_profile.allowed_tools"),
        network_enabled: requireBoolean(data.network_enabled ?? false, "sandbox_profile.network_enabled"),
        env_allowlist: requireStringList(data.env_allowlist ?? [], "sandbox_profile.env_allowlist"),
        command_allowlist: requireStringList(data.command_allowlist ?? [], "sandbox_profile.command_allowlist"),
        resource_budget: data.resource_budget === undefined ? {} : requireObject(data.resource_budget, "sandbox_profile.resource_budget"),
        ...(profileHash ? { profile_hash: profileHash } : {}),
    };
}
export function parseContextProjectionConfig(value) {
    if (value === undefined || value === null) {
        return { ...DEFAULT_CONTEXT_PROJECTION_CONFIG };
    }
    const data = requireObject(value, "context_projection_config");
    const schemaVersion = requireString(data.schema_version ?? CONTEXT_PROJECTION_CONFIG_SCHEMA_VERSION, "context_projection_config.schema_version");
    if (schemaVersion !== CONTEXT_PROJECTION_CONFIG_SCHEMA_VERSION) {
        throw new Error(`Unsupported context_projection_config.schema_version: ${schemaVersion}`);
    }
    const softCompactRatio = requireRatio(data.soft_compact_ratio ?? DEFAULT_CONTEXT_SOFT_COMPACT_RATIO, "context_projection_config.soft_compact_ratio");
    const hardCompactRatio = requireRatio(data.hard_compact_ratio ?? DEFAULT_CONTEXT_HARD_COMPACT_RATIO, "context_projection_config.hard_compact_ratio");
    if (hardCompactRatio <= softCompactRatio) {
        throw new Error("context_projection_config.hard_compact_ratio must be greater than soft_compact_ratio");
    }
    return {
        schema_version: CONTEXT_PROJECTION_CONFIG_SCHEMA_VERSION,
        large_observation_bytes: requirePositiveInteger(data.large_observation_bytes ?? DEFAULT_CONTEXT_LARGE_OBSERVATION_BYTES, "context_projection_config.large_observation_bytes"),
        soft_compact_ratio: softCompactRatio,
        hard_compact_ratio: hardCompactRatio,
        cache_aware: requireBoolean(data.cache_aware ?? DEFAULT_CONTEXT_CACHE_AWARE, "context_projection_config.cache_aware"),
    };
}
function parseResume(value) {
    if (value === undefined || value === null) {
        return {
            mode: "none",
            boundary: null,
            savepoint_ref: null,
            session_ref: null,
            events_ref: null,
            checkpoint_refs: [],
            summary_artifact_refs: [],
            resume_prompt: null,
        };
    }
    const data = requireObject(value, "resume");
    const mode = requireString(data.mode ?? "none", "resume.mode");
    if (mode !== "none" && mode !== "follow_up") {
        throw new Error("resume.mode must be none or follow_up");
    }
    const boundary = data.boundary === undefined || data.boundary === null
        ? null
        : requireString(data.boundary, "resume.boundary");
    if (boundary !== null && boundary !== "after_completed_turn") {
        throw new Error("resume.boundary must be after_completed_turn");
    }
    const savepointRef = data.savepoint_ref === undefined || data.savepoint_ref === null
        ? null
        : requireRef(data.savepoint_ref, "resume.savepoint_ref");
    const sessionRef = data.session_ref === undefined || data.session_ref === null
        ? null
        : requireRef(data.session_ref, "resume.session_ref");
    const eventsRef = data.events_ref === undefined || data.events_ref === null
        ? null
        : requireRef(data.events_ref, "resume.events_ref");
    const checkpointRefs = requireRefList(data.checkpoint_refs ?? [], "resume.checkpoint_refs");
    const summaryArtifactRefs = requireRefList(data.summary_artifact_refs ?? [], "resume.summary_artifact_refs");
    const resumePrompt = data.resume_prompt === undefined || data.resume_prompt === null
        ? null
        : requireString(data.resume_prompt, "resume.resume_prompt");
    if (mode === "follow_up") {
        if (boundary !== "after_completed_turn") {
            throw new Error("resume.follow_up requires after_completed_turn boundary");
        }
        if (!savepointRef || !sessionRef || !eventsRef) {
            throw new Error("resume.follow_up requires savepoint/session/events refs");
        }
        if (!resumePrompt) {
            throw new Error("resume.follow_up requires resume_prompt");
        }
    }
    return {
        mode,
        boundary,
        savepoint_ref: savepointRef,
        session_ref: sessionRef,
        events_ref: eventsRef,
        checkpoint_refs: checkpointRefs,
        summary_artifact_refs: summaryArtifactRefs,
        resume_prompt: resumePrompt,
    };
}
export function validateOutput(output) {
    if (output.schema_version !== OUTPUT_SCHEMA_VERSION) {
        throw new Error("Unsupported output schema_version");
    }
    requireString(output.call_id, "output.call_id");
    if (!["completed", "failed", "blocked", "cancelled"].includes(output.status)) {
        throw new Error("output.status is invalid");
    }
    if (!["passed", "failed", "not_run", "review_required"].includes(output.verification_status)) {
        throw new Error("output.verification_status is invalid");
    }
    for (const field of [
        "produced_artifacts",
        "changed_refs",
        "verifier_evidence",
        "new_unknowns",
    ]) {
        for (const ref of output[field])
            requireRef(ref, `output.${field}[]`);
    }
    for (const field of [
        "input_ref",
        "output_ref",
        "session_ref",
        "events_ref",
        "metrics_ref",
        "savepoints_ref",
        "context_observations_ref",
        "context_projection_ref",
    ]) {
        requireRef(output[field], `output.${field}`);
    }
    requireNonNegativeInteger(output.duration_ms, "output.duration_ms");
    return output;
}
export function requireRef(value, field) {
    const ref = requireString(value, field);
    if (ref.startsWith("/") || ref.includes("\0") || ref.split(/[\\/]+/).includes("..")) {
        throw new Error(`${field} must be a workspace-relative ref`);
    }
    return ref;
}
function optionalRef(value, field) {
    if (value === undefined || value === null || value === "")
        return null;
    return requireRef(value, field);
}
function optionalSha256(value, field) {
    if (value === undefined || value === null || value === "")
        return null;
    return requireSha256(value, field);
}
function optionalString(value, field) {
    if (value === undefined || value === null || value === "")
        return "";
    return requireString(value, field);
}
function parsePiAgentCallSpec(value) {
    const data = requireObject(value, "call_spec");
    return {
        call_id: requireString(data.call_id, "call_spec.call_id"),
        mission_id: requireString(data.mission_id, "call_spec.mission_id"),
        iteration: requirePositiveInteger(data.iteration, "call_spec.iteration"),
        next_objective: requireString(data.next_objective, "call_spec.next_objective"),
        allowed_scope: requireRefList(data.allowed_scope, "call_spec.allowed_scope"),
        visible_refs: requireRefList(data.visible_refs, "call_spec.visible_refs"),
        expected_outputs: requireRefList(data.expected_outputs, "call_spec.expected_outputs"),
        exit_criteria: requireStringList(data.exit_criteria, "call_spec.exit_criteria"),
        stop_conditions: requireStringList(data.stop_conditions, "call_spec.stop_conditions"),
    };
}
function parsePiWorkerCall(value) {
    const data = requireObject(value, "piworker_call");
    const schemaVersion = requireString(data.schema_version, "piworker_call.schema_version");
    if (schemaVersion !== "piworker_call.v1") {
        throw new Error(`Unsupported piworker_call.schema_version: ${schemaVersion}`);
    }
    const role = requireString(data.role, "piworker_call.role");
    if (![
        "frontdesk_author_piworker",
        "executor_piworker",
        "judge_piworker",
        "repair_piworker",
        "revision_drafter_piworker",
    ].includes(role)) {
        throw new Error("piworker_call.role is invalid");
    }
    const call = {
        schema_version: "piworker_call.v1",
        call_id: requireString(data.call_id, "piworker_call.call_id"),
        role,
        contract_id: requireString(data.contract_id, "piworker_call.contract_id"),
        contract_hash: requireSha256(data.contract_hash, "piworker_call.contract_hash"),
        contract_ref: requireRef(data.contract_ref, "piworker_call.contract_ref"),
        objective: requireString(data.objective, "piworker_call.objective"),
        visible_refs: requireRefList(data.visible_refs ?? [], "piworker_call.visible_refs"),
        writable_refs: requireRefList(data.writable_refs ?? [], "piworker_call.writable_refs"),
        expected_output_refs: requireRefList(data.expected_output_refs ?? [], "piworker_call.expected_output_refs"),
        permission_manifest_ref: data.permission_manifest_ref === undefined || data.permission_manifest_ref === null
            ? null
            : requireRef(data.permission_manifest_ref, "piworker_call.permission_manifest_ref"),
        source_packet_ref: data.source_packet_ref === undefined || data.source_packet_ref === null
            ? null
            : requireRef(data.source_packet_ref, "piworker_call.source_packet_ref"),
        source_packet_hash: data.source_packet_hash === undefined || data.source_packet_hash === null
            ? null
            : requireSha256(data.source_packet_hash, "piworker_call.source_packet_hash"),
        evidence_refs: requireRefList(data.evidence_refs ?? [], "piworker_call.evidence_refs"),
        output_schema_ref: data.output_schema_ref === undefined || data.output_schema_ref === null
            ? null
            : requireRef(data.output_schema_ref, "piworker_call.output_schema_ref"),
        validation_policy_ref: data.validation_policy_ref === undefined || data.validation_policy_ref === null
            ? null
            : requireRef(data.validation_policy_ref, "piworker_call.validation_policy_ref"),
        runtime_budget: data.runtime_budget === undefined ? {} : requireObject(data.runtime_budget, "piworker_call.runtime_budget"),
        metadata: data.metadata === undefined ? {} : requireObject(data.metadata, "piworker_call.metadata"),
    };
    for (const ref of call.expected_output_refs) {
        if (!call.writable_refs.some((rootRef) => ref === rootRef || ref.startsWith(`${rootRef}/`))) {
            throw new Error("piworker_call expected output must be inside writable_refs");
        }
    }
    return call;
}
function parseRuntime(value) {
    const data = requireObject(value, "runtime");
    const model = data.model === undefined || data.model === null ? null : requireString(data.model, "runtime.model");
    const metadata = data.metadata === undefined ? {} : requireObject(data.metadata, "runtime.metadata");
    return {
        runtime_name: requireString(data.runtime_name, "runtime.runtime_name"),
        timeout_seconds: requirePositiveInteger(data.timeout_seconds, "runtime.timeout_seconds"),
        model,
        metadata,
    };
}
function parseExtensionGrants(value) {
    const items = requireArray(value, "permission_manifest.extension_grants").map((item) => parseExtensionGrant(item));
    requireUnique(items.map((item) => item.grant_id), "permission_manifest.extension_grants.grant_id");
    return items;
}
function parseExtensionLockEntries(value) {
    const items = requireArray(value, "extension_lock.extensions").map((item) => {
        const data = requireObject(item, "extension_lock_entry");
        const capability = requireString(data.capability, "extension_lock_entry.capability");
        if (!isExtensionCapability(capability)) {
            throw new Error("extension_lock_entry.capability is invalid");
        }
        const adapterMode = requireString(data.adapter_mode ?? "missionforge_provider", "extension_lock_entry.adapter_mode");
        if (!isExtensionAdapterMode(adapterMode)) {
            throw new Error("extension_lock_entry.adapter_mode is invalid");
        }
        const requiredEnv = requireStringList(data.required_env ?? [], "extension_lock_entry.required_env");
        for (const name of requiredEnv)
            requireEnvName(name, "extension_lock_entry.required_env[]");
        return {
            grant_id: requireString(data.grant_id, "extension_lock_entry.grant_id"),
            package: requireExtensionPackage(data.package, "extension_lock_entry.package"),
            name: requireString(data.name, "extension_lock_entry.name"),
            version: requireString(data.version, "extension_lock_entry.version"),
            capability,
            install_path: requireRef(data.install_path, "extension_lock_entry.install_path"),
            adapter_mode: adapterMode,
            requires_network: requireBoolean(data.requires_network ?? false, "extension_lock_entry.requires_network"),
            requires_bash: requireBoolean(data.requires_bash ?? false, "extension_lock_entry.requires_bash"),
            required_env: requiredEnv,
            resolved: data.resolved === undefined || data.resolved === null
                ? null
                : requireString(data.resolved, "extension_lock_entry.resolved"),
            integrity: data.integrity === undefined || data.integrity === null
                ? null
                : requireString(data.integrity, "extension_lock_entry.integrity"),
            package_hash: data.package_hash === undefined || data.package_hash === null
                ? null
                : requireSha256(data.package_hash, "extension_lock_entry.package_hash"),
            metadata: data.metadata === undefined ? {} : requireObject(data.metadata, "extension_lock_entry.metadata"),
        };
    });
    requireUnique(items.map((item) => item.grant_id), "extension_lock.extensions.grant_id");
    return items;
}
function parseExtensionLoadRecords(value, field) {
    const items = requireArray(value, field).map((item) => {
        const data = requireObject(item, "extension_load_record");
        const capability = requireString(data.capability, "extension_load_record.capability");
        if (!isExtensionCapability(capability)) {
            throw new Error("extension_load_record.capability is invalid");
        }
        const adapterMode = requireString(data.adapter_mode ?? "missionforge_provider", "extension_load_record.adapter_mode");
        if (!isExtensionAdapterMode(adapterMode)) {
            throw new Error("extension_load_record.adapter_mode is invalid");
        }
        const status = requireString(data.status, "extension_load_record.status");
        if (!["loaded", "loadable", "rejected"].includes(status)) {
            throw new Error("extension_load_record.status is invalid");
        }
        const networkPolicy = requireString(data.network_policy_at_load ?? "disabled", "extension_load_record.network_policy_at_load");
        if (!["disabled", "restricted", "enabled"].includes(networkPolicy)) {
            throw new Error("extension_load_record.network_policy_at_load is invalid");
        }
        return {
            grant_id: requireString(data.grant_id, "extension_load_record.grant_id"),
            package: requireExtensionPackage(data.package, "extension_load_record.package"),
            capability,
            status: status,
            adapter_mode: adapterMode,
            reason: data.reason === undefined || data.reason === null ? "" : requireString(data.reason, "extension_load_record.reason"),
            version: data.version === undefined || data.version === null
                ? null
                : requireString(data.version, "extension_load_record.version"),
            integrity: data.integrity === undefined || data.integrity === null
                ? null
                : requireString(data.integrity, "extension_load_record.integrity"),
            requires_network: requireBoolean(data.requires_network ?? false, "extension_load_record.requires_network"),
            network_policy_at_load: networkPolicy,
            tool_names: requireStringList(data.tool_names ?? [], "extension_load_record.tool_names"),
        };
    });
    requireUnique(items.map((item) => item.grant_id), `${field}.grant_id`);
    return items;
}
function parseRepair(value) {
    if (value === undefined || value === null) {
        return {
            mode: "none",
            verifier_failures: [],
            failed_constraints: [],
            previous_output_ref: null,
            repair_prompt: null,
        };
    }
    const data = requireObject(value, "repair");
    const mode = requireString(data.mode ?? "none", "repair.mode");
    if (mode !== "none" && mode !== "follow_up") {
        throw new Error("repair.mode must be none or follow_up");
    }
    const verifierFailures = requireStringList(data.verifier_failures ?? [], "repair.verifier_failures");
    const failedConstraints = requireStringList(data.failed_constraints ?? [], "repair.failed_constraints");
    const previousOutputRef = data.previous_output_ref === undefined || data.previous_output_ref === null
        ? null
        : requireRef(data.previous_output_ref, "repair.previous_output_ref");
    const repairPrompt = data.repair_prompt === undefined || data.repair_prompt === null
        ? null
        : requireString(data.repair_prompt, "repair.repair_prompt");
    if (mode === "follow_up") {
        if (verifierFailures.length === 0 && failedConstraints.length === 0) {
            throw new Error("repair.follow_up requires verifier_failures or failed_constraints");
        }
        if (!previousOutputRef) {
            throw new Error("repair.follow_up requires previous_output_ref");
        }
        if (!repairPrompt) {
            throw new Error("repair.follow_up requires repair_prompt");
        }
    }
    return {
        mode,
        verifier_failures: verifierFailures,
        failed_constraints: failedConstraints,
        previous_output_ref: previousOutputRef,
        repair_prompt: repairPrompt,
    };
}
function validateRuntimeAuthority(input) {
    const grant = input.capability_grant;
    const profile = input.sandbox_profile;
    const manifest = input.permission_manifest;
    if (grant.role !== input.piworker_call.role) {
        throw new Error("capability_grant.role must match piworker_call.role");
    }
    if (grant.contract_hash !== input.piworker_call.contract_hash) {
        throw new Error("capability_grant.contract_hash must match piworker_call.contract_hash");
    }
    if (grant.workspace_policy_ref !== manifest.workspace_policy_ref) {
        throw new Error("capability_grant.workspace_policy_ref must match permission_manifest.workspace_policy_ref");
    }
    if (grant.workspace_view_ref !== profile.workspace_root_ref) {
        throw new Error("capability_grant.workspace_view_ref must match sandbox_profile.workspace_root_ref");
    }
    if (grant.revoked_at !== null) {
        throw new Error("capability_grant must not be revoked");
    }
    if (Date.parse(grant.expires_at) <= Date.now()) {
        throw new Error("capability_grant must be active");
    }
    if (profile.mode === "unsupported") {
        throw new Error("sandbox_profile.mode must be supported");
    }
    requireSameStringSet(profile.readable_refs, manifest.readable_refs, "sandbox_profile.readable_refs");
    requireSameStringSet(profile.writable_refs, manifest.writable_refs, "sandbox_profile.writable_refs");
    requireSameStringSet(profile.denied_refs, manifest.denied_refs, "sandbox_profile.denied_refs");
    requireSameStringSet(profile.allowed_tools, manifest.allowed_tools, "sandbox_profile.allowed_tools");
    requireSameStringList(profile.command_allowlist, manifest.allowed_commands, "sandbox_profile.command_allowlist");
    requireSameStringList(profile.env_allowlist, manifest.env_allowlist, "sandbox_profile.env_allowlist");
    const networkEnabled = manifest.network_policy === "enabled";
    if (profile.network_enabled !== networkEnabled) {
        throw new Error("sandbox_profile.network_enabled must match permission_manifest.network_policy");
    }
}
function requireSameStringSet(actual, expected, field) {
    const actualSet = new Set(actual);
    const expectedSet = new Set(expected);
    if (actualSet.size !== expectedSet.size || [...actualSet].some((item) => !expectedSet.has(item))) {
        throw new Error(`${field} must match permission_manifest refs`);
    }
}
function requireSameStringList(actual, expected, field) {
    if (actual.length !== expected.length || actual.some((item, index) => item !== expected[index])) {
        throw new Error(`${field} must match permission_manifest`);
    }
}
function refIsUnder(ref, rootRef) {
    const safeRef = requireRef(ref, "ref");
    const safeRoot = requireRef(rootRef, "root_ref");
    return safeRef === safeRoot || safeRef.startsWith(`${safeRoot}/`);
}
function requireRefList(value, field) {
    return requireArray(value, field).map((item, index) => requireRef(item, `${field}[${index}]`));
}
function requireStringList(value, field) {
    return requireArray(value ?? [], field).map((item, index) => requireString(item, `${field}[${index}]`));
}
function requireArray(value, field) {
    if (!Array.isArray(value))
        throw new Error(`${field} must be an array`);
    return value;
}
function requireObject(value, field) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error(`${field} must be an object`);
    }
    return value;
}
function requireString(value, field) {
    if (typeof value !== "string" || value.length === 0) {
        throw new Error(`${field} must be a non-empty string`);
    }
    return value;
}
function requireSha256(value, field) {
    const text = requireString(value, field);
    if (!/^sha256:[0-9a-f]{64}$/.test(text)) {
        throw new Error(`${field} must be a sha256 hash`);
    }
    return text;
}
function requireIsoTimestamp(value, field) {
    const text = requireString(value, field);
    const timestamp = Date.parse(text);
    if (!Number.isFinite(timestamp)) {
        throw new Error(`${field} must be an ISO timestamp`);
    }
    return text;
}
function requireBoolean(value, field) {
    if (typeof value !== "boolean") {
        throw new Error(`${field} must be a boolean`);
    }
    return value;
}
function requireExtensionPackage(value, field) {
    const text = requireString(value, field);
    if (!text.startsWith("npm:") && !text.startsWith("local:")) {
        throw new Error(`${field} must start with npm: or local:`);
    }
    if (text.startsWith("local:")) {
        requireRef(text.slice("local:".length), field);
    }
    return text;
}
function requireEnvName(value, field) {
    const text = requireString(value, field);
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(text)) {
        throw new Error(`${field} must be an environment variable name`);
    }
    return text;
}
function requireUnique(values, field) {
    if (new Set(values).size !== values.length) {
        throw new Error(`${field} must be unique`);
    }
}
function isExtensionCapability(value) {
    return [
        "code_search",
        "lsp",
        "web",
        "mcp",
        "browser",
        "subagent",
        "memory",
        "preview",
        "workflow",
        "ui",
    ].includes(value);
}
function isExtensionAdapterMode(value) {
    return ["missionforge_provider", "untrusted_pi_extension"].includes(value);
}
function requirePositiveInteger(value, field) {
    const number = requireNonNegativeInteger(value, field);
    if (number < 1)
        throw new Error(`${field} must be at least 1`);
    return number;
}
function requireNonNegativeInteger(value, field) {
    if (!Number.isInteger(value) || typeof value !== "number" || value < 0) {
        throw new Error(`${field} must be a non-negative integer`);
    }
    return value;
}
function requireRatio(value, field) {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || value > 1) {
        throw new Error(`${field} must be a number in (0, 1]`);
    }
    return value;
}

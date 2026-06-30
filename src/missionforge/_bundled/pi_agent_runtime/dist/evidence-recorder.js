import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { RUNTIME_CONTEXT_CHECKPOINT_SCHEMA_VERSION } from "./contract.js";
import { appendJsonLine, prepareWorkspaceWritePath, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { redactJson, redactText } from "./redaction.js";
export class EvidenceRecorder {
    input;
    workspaceRoot;
    env;
    sequence = 0;
    startedAtMs = Date.now();
    toolStarts = new Map();
    toolGatewayDecisions = [];
    hasRecordedFirstTool = false;
    hasRecordedFirstArtifact = false;
    metrics = {
        turn_count: 0,
        tool_call_count: 0,
        total_tokens: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read_tokens: 0,
        cache_write_tokens: 0,
        input_cost_usd: 0,
        output_cost_usd: 0,
        cache_read_cost_usd: 0,
        cache_write_cost_usd: 0,
        provider_reported_cost_usd: 0,
        tool_error_count: 0,
        tool_latency_ms_total: 0,
        tool_latency_ms_by_name: {},
        command_count: 0,
        test_command_count: 0,
        command_failure_count: 0,
        time_to_first_tool_ms: 0,
        time_to_first_artifact_ms: 0,
        commands_run: [],
        tests_run: [],
    };
    constructor(input, workspaceRoot, env = process.env) {
        this.input = input;
        this.workspaceRoot = workspaceRoot;
        this.env = env;
    }
    async record(event) {
        this.updateMetrics(event);
        await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref), {
            schema_version: "missionforge.pi_agent_runtime_event.v1",
            event_id: `pi-agent-event-${String(++this.sequence).padStart(6, "0")}`,
            created_at: new Date().toISOString(),
            call_id: this.input.call_id,
            event_type: event.type,
            payload: redactJson(summarizeEvent(event), this.env),
        }, { workspaceRoot: this.workspaceRoot });
        if (event.type === "tool_execution_end" || event.type === "turn_end") {
            await this.recordFirstArtifactIfPresent();
        }
        if (event.type === "turn_end") {
            await this.writeSavepoint(event);
        }
    }
    async writeSession(messages) {
        const path = resolveWorkspaceRef(this.workspaceRoot, this.input.session_ref);
        const lines = messages.map((message, index) => JSON.stringify({
            schema_version: "missionforge.pi_agent_runtime_session_entry.v1",
            index,
            message: redactJson(summarizeMessage(message), this.env),
        }));
        await writeText(path, `${lines.join("\n")}${lines.length ? "\n" : ""}`, this.workspaceRoot);
    }
    recordToolGatewayDecision(decision) {
        this.toolGatewayDecisions.push({
            ...decision,
            env_names: decision.env_names ? [...decision.env_names] : undefined,
        });
    }
    async recordToolObservation(observation) {
        await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref), {
            schema_version: "missionforge.pi_agent_runtime_event.v1",
            event_id: `pi-agent-event-${String(++this.sequence).padStart(6, "0")}`,
            created_at: new Date().toISOString(),
            call_id: this.input.call_id,
            event_type: "tool_observation",
            payload: redactJson({
                schema_version: observation.schema_version,
                observation_id: observation.observation_id,
                tool_call_id: observation.tool_call_id,
                tool_name: observation.tool_name,
                status: observation.status,
                content_hash: observation.content_hash,
                content_bytes: observation.content_bytes,
                content_lines: observation.content_lines,
                inline_policy: observation.inline_policy,
                raw_ref: observation.raw_ref,
                source_ref: observation.source_ref,
                source_range: observation.source_range,
                source_hash: observation.source_hash,
            }, this.env),
        }, { workspaceRoot: this.workspaceRoot });
    }
    async writeMetrics(durationMs) {
        await this.flushToolGatewayDecisions();
        await this.recordFirstArtifactIfPresent();
        await writeJsonFile(resolveWorkspaceRef(this.workspaceRoot, this.input.metrics_ref), {
            schema_version: "missionforge.pi_agent_runtime_metrics.v1",
            call_id: this.input.call_id,
            duration_ms: durationMs,
            ...this.safeMetrics(),
        }, { workspaceRoot: this.workspaceRoot });
    }
    safeMetrics() {
        return {
            turn_count: this.metrics.turn_count,
            tool_call_count: this.metrics.tool_call_count,
            total_tokens: this.metrics.total_tokens,
            input_tokens: this.metrics.input_tokens,
            output_tokens: this.metrics.output_tokens,
            cache_read_tokens: this.metrics.cache_read_tokens,
            cache_write_tokens: this.metrics.cache_write_tokens,
            input_cost_usd: this.metrics.input_cost_usd,
            output_cost_usd: this.metrics.output_cost_usd,
            cache_read_cost_usd: this.metrics.cache_read_cost_usd,
            cache_write_cost_usd: this.metrics.cache_write_cost_usd,
            provider_reported_cost_usd: this.metrics.provider_reported_cost_usd,
            tool_error_count: this.metrics.tool_error_count,
            tool_latency_ms_total: this.metrics.tool_latency_ms_total,
            tool_latency_ms_by_name: safeNumericRecord(this.metrics.tool_latency_ms_by_name),
            command_count: this.metrics.command_count,
            test_command_count: this.metrics.test_command_count,
            command_failure_count: this.metrics.command_failure_count,
            time_to_first_tool_ms: this.metrics.time_to_first_tool_ms,
            time_to_first_artifact_ms: this.metrics.time_to_first_artifact_ms,
            commands_run: this.metrics.commands_run.map((command) => redactText(command, this.env)),
            tests_run: this.metrics.tests_run.map((command) => redactText(command, this.env)),
            stop_reason: this.metrics.stop_reason ? redactText(this.metrics.stop_reason, this.env) : undefined,
        };
    }
    contextCheckpointRef() {
        return `${this.input.attempt_dir_ref}/context/context_pressure_checkpoint.json`;
    }
    async writeContextCheckpoint(reason, diagnostics = {}) {
        const checkpointRef = this.contextCheckpointRef();
        await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref), {
            schema_version: "missionforge.pi_agent_runtime_event.v1",
            event_id: `pi-agent-event-${String(++this.sequence).padStart(6, "0")}`,
            created_at: new Date().toISOString(),
            call_id: this.input.call_id,
            event_type: "context_pressure_checkpoint",
            payload: redactJson({
                reason,
                turn_index: this.metrics.turn_count,
                savepoints_ref: this.input.savepoints_ref,
                context_observations_ref: this.input.context_observations_ref,
                context_projection_ref: this.input.context_projection_ref,
                checkpoint_refs: [checkpointRef],
                resume_boundary: "after_completed_turn",
            }, this.env),
        }, { workspaceRoot: this.workspaceRoot });
        await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.savepoints_ref), redactJson({
            schema_version: "missionforge.pi_agent_runtime_savepoint.v1",
            call_id: this.input.call_id,
            turn_index: this.metrics.turn_count,
            created_at: new Date().toISOString(),
            message_ref: `${this.input.session_ref}#checkpoint`,
            events_ref: this.input.events_ref,
            context_observations_ref: this.input.context_observations_ref,
            context_projection_ref: this.input.context_projection_ref,
            changed_refs: [],
            tool_call_count: this.metrics.tool_call_count,
            commands_run: this.metrics.commands_run.slice(),
            stop_reason: "context_checkpoint",
            token_count: this.metrics.total_tokens,
            resume_hint: {
                supported: true,
                boundary: "after_completed_turn",
                unsupported: [
                    "mid_tool_call",
                    "active_shell_process",
                    "partial_provider_stream",
                    "uncommitted_filesystem_mutations",
                ],
            },
            context_checkpoint: {
                applied: true,
                reason,
                checkpoint_ref: checkpointRef,
            },
        }, this.env), { workspaceRoot: this.workspaceRoot });
        await this.writeRuntimeContextCheckpoint(checkpointRef, reason, diagnostics);
        return checkpointRef;
    }
    async writeRuntimeContextCheckpoint(ref, reason, diagnostics) {
        const permissionManifestRef = this.input.piworker_call.permission_manifest_ref ?? this.input.capability_grant.permission_manifest_ref;
        const sources = await this.compactionSources(permissionManifestRef);
        await writeJsonFile(resolveWorkspaceRef(this.workspaceRoot, ref), {
            schema_version: RUNTIME_CONTEXT_CHECKPOINT_SCHEMA_VERSION,
            checkpoint_id: `${this.input.call_id}-context-checkpoint-${String(this.metrics.turn_count).padStart(4, "0")}`,
            call_id: this.input.call_id,
            role: this.input.piworker_call.role,
            kind: "runtime_context_checkpoint",
            reason: redactText(reason, this.env),
            turn_index: this.metrics.turn_count,
            sources,
            permission_manifest_ref: permissionManifestRef,
            created_by: "missionforge.pi_agent_runtime",
            metadata: compactMetadata({
                reason: redactText(reason, this.env),
                turn_index: this.metrics.turn_count,
                savepoints_ref: this.input.savepoints_ref,
                session_ref: this.input.session_ref,
                events_ref: this.input.events_ref,
                context_observations_ref: this.input.context_observations_ref,
                context_projection_ref: this.input.context_projection_ref,
                pressure_ratio: diagnostics.pressure_ratio,
                estimated_input_tokens: diagnostics.estimated_input_tokens,
                model_context_window: diagnostics.model_context_window,
                usable_input_budget: diagnostics.usable_input_budget ?? diagnostics.context_budget?.usable_input_budget,
                budget_pressure_ratio: diagnostics.budget_pressure_ratio ?? diagnostics.context_budget?.budget_pressure_ratio,
                soft_compact_ratio: diagnostics.soft_compact_ratio,
                hard_compact_ratio: diagnostics.hard_compact_ratio,
                cache_read_tokens: diagnostics.cache_read_tokens,
                cache_write_tokens: diagnostics.cache_write_tokens,
                recommended_action: diagnostics.recommended_action,
                resume_boundary: "after_completed_turn",
            }),
        }, { workspaceRoot: this.workspaceRoot });
    }
    async compactionSources(permissionManifestRef) {
        const candidates = [
            {
                source_id: "source-001",
                observation_id: "runtime-savepoints",
                ref: this.input.savepoints_ref,
                range_hint: `turn=${this.metrics.turn_count}`,
                source_kind: "savepoints",
            },
            {
                source_id: "source-002",
                observation_id: "context-projection",
                ref: this.input.context_projection_ref,
                range_hint: "latest",
                source_kind: "projection",
            },
            {
                source_id: "source-003",
                observation_id: "context-observations",
                ref: this.input.context_observations_ref,
                range_hint: "index",
                source_kind: "observations",
            },
            {
                source_id: "source-004",
                observation_id: "runtime-input",
                ref: this.input.input_ref,
                range_hint: "contract",
                source_kind: "runtime_input",
            },
        ];
        const sources = [];
        for (const candidate of candidates) {
            const path = resolveWorkspaceRef(this.workspaceRoot, candidate.ref);
            if (!(await fileExists(path)))
                continue;
            sources.push({
                source_id: candidate.source_id,
                observation_id: candidate.observation_id,
                ref: candidate.ref,
                content_hash: await hashFile(path),
                source_role: this.input.piworker_call.role,
                permission_manifest_ref: permissionManifestRef,
                range_hint: candidate.range_hint,
                metadata: { source_kind: candidate.source_kind },
            });
        }
        if (sources.length === 0) {
            throw new Error("runtime context checkpoint requires at least one refs-only source");
        }
        return sources;
    }
    async flushToolGatewayDecisions() {
        while (this.toolGatewayDecisions.length > 0) {
            const decision = this.toolGatewayDecisions.shift();
            if (!decision)
                continue;
            await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref), {
                schema_version: "missionforge.pi_agent_runtime_event.v1",
                event_id: `pi-agent-event-${String(++this.sequence).padStart(6, "0")}`,
                created_at: new Date().toISOString(),
                call_id: this.input.call_id,
                event_type: "tool_gateway_decision",
                payload: redactJson(decision, this.env),
            }, { workspaceRoot: this.workspaceRoot });
        }
    }
    updateMetrics(event) {
        if (event.type === "turn_start")
            this.metrics.turn_count += 1;
        if (event.type === "tool_execution_start") {
            this.metrics.tool_call_count += 1;
            if (!this.hasRecordedFirstTool) {
                this.hasRecordedFirstTool = true;
                this.metrics.time_to_first_tool_ms = elapsedMs(this.startedAtMs);
            }
            this.toolStarts.set(event.toolCallId, {
                toolName: event.toolName,
                startedAtMs: Date.now(),
            });
            if (event.toolName === "bash") {
                const command = typeof event.args?.command === "string" ? event.args.command : "";
                if (command) {
                    this.metrics.command_count += 1;
                    this.metrics.commands_run.push(command);
                    if (looksLikeTestCommand(command)) {
                        this.metrics.test_command_count += 1;
                        this.metrics.tests_run.push(command);
                    }
                }
            }
        }
        if (event.type === "tool_execution_end") {
            const started = this.toolStarts.get(event.toolCallId);
            const latencyMs = started ? elapsedMs(started.startedAtMs) : 0;
            this.toolStarts.delete(event.toolCallId);
            this.metrics.tool_latency_ms_total += latencyMs;
            const toolName = started?.toolName ?? event.toolName;
            this.metrics.tool_latency_ms_by_name[toolName] = (this.metrics.tool_latency_ms_by_name[toolName] ?? 0) + latencyMs;
            if (event.isError) {
                this.metrics.tool_error_count += 1;
                if (event.toolName === "bash")
                    this.metrics.command_failure_count += 1;
            }
        }
        if (event.type === "message_end" && event.message.role === "assistant") {
            const usage = event.message.usage;
            this.metrics.input_tokens += usage?.input ?? 0;
            this.metrics.output_tokens += usage?.output ?? 0;
            this.metrics.cache_read_tokens += usage?.cacheRead ?? 0;
            this.metrics.cache_write_tokens += usage?.cacheWrite ?? 0;
            this.metrics.total_tokens += usage?.totalTokens ?? 0;
            this.metrics.input_cost_usd += usage?.cost?.input ?? 0;
            this.metrics.output_cost_usd += usage?.cost?.output ?? 0;
            this.metrics.cache_read_cost_usd += usage?.cost?.cacheRead ?? 0;
            this.metrics.cache_write_cost_usd += usage?.cost?.cacheWrite ?? 0;
            this.metrics.provider_reported_cost_usd += usage?.cost?.total ?? 0;
            this.metrics.stop_reason = event.message.stopReason;
        }
    }
    async recordFirstArtifactIfPresent() {
        if (this.hasRecordedFirstArtifact)
            return;
        for (const ref of this.input.call_spec.expected_outputs) {
            if (await fileExists(resolveWorkspaceRef(this.workspaceRoot, ref))) {
                this.hasRecordedFirstArtifact = true;
                this.metrics.time_to_first_artifact_ms = elapsedMs(this.startedAtMs);
                return;
            }
        }
    }
    async writeSavepoint(event) {
        await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.savepoints_ref), redactJson({
            schema_version: "missionforge.pi_agent_runtime_savepoint.v1",
            call_id: this.input.call_id,
            turn_index: this.metrics.turn_count,
            created_at: new Date().toISOString(),
            message_ref: `${this.input.session_ref}#turn=${this.metrics.turn_count}`,
            events_ref: this.input.events_ref,
            context_observations_ref: this.input.context_observations_ref,
            context_projection_ref: this.input.context_projection_ref,
            changed_refs: [],
            tool_call_count: event.toolResults.length,
            commands_run: this.metrics.commands_run.slice(),
            stop_reason: event.message.role === "assistant" ? event.message.stopReason : undefined,
            token_count: this.metrics.total_tokens,
            resume_hint: {
                supported: true,
                boundary: "after_completed_turn",
                unsupported: [
                    "mid_tool_call",
                    "active_shell_process",
                    "partial_provider_stream",
                    "uncommitted_filesystem_mutations",
                ],
            },
        }, this.env), { workspaceRoot: this.workspaceRoot });
    }
}
function elapsedMs(startedAtMs) {
    return Math.max(0, Date.now() - startedAtMs);
}
function safeNumericRecord(values) {
    const result = {};
    for (const [key, value] of Object.entries(values)) {
        if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
            result[key] = value;
        }
    }
    return result;
}
function summarizeEvent(event) {
    switch (event.type) {
        case "agent_start":
        case "turn_start":
            return { type: event.type };
        case "agent_end":
            return {
                type: event.type,
                message_count: event.messages.length,
                messages: event.messages.map(summarizeMessage),
            };
        case "message_start":
        case "message_update":
        case "message_end":
            return { type: event.type, message: summarizeMessage(event.message) };
        case "tool_execution_start":
            return {
                type: event.type,
                toolCallId: event.toolCallId,
                toolName: event.toolName,
                args: summarizeToolArgs(event.toolName, event.args),
            };
        case "tool_execution_update":
            return {
                type: event.type,
                toolCallId: event.toolCallId,
                toolName: event.toolName,
                args: summarizeToolArgs(event.toolName, event.args),
                partialResult: summarizeToolExecutionResult(event.partialResult),
            };
        case "tool_execution_end":
            return {
                type: event.type,
                toolCallId: event.toolCallId,
                toolName: event.toolName,
                args: "args" in event ? summarizeToolArgs(event.toolName, event.args) : undefined,
                result: summarizeToolExecutionResult(event.result),
                isError: event.isError,
            };
        case "turn_end":
            return {
                type: event.type,
                message: summarizeMessage(event.message),
                toolResults: event.toolResults.map(summarizeToolResult),
            };
        default:
            return { type: event.type ?? "unknown" };
    }
}
function summarizeToolResult(message) {
    return {
        role: message.role,
        toolCallId: message.toolCallId,
        toolName: message.toolName,
        isError: message.isError,
        content: summarizeContentBlocks(message.content),
    };
}
function summarizeMessage(message) {
    const raw = message;
    if (!raw || typeof raw !== "object")
        return { type: typeof message };
    return {
        role: raw.role,
        api: raw.api,
        stopReason: raw.stopReason,
        errorMessage: raw.errorMessage ? redactText(String(raw.errorMessage)) : undefined,
        usage: raw.role === "assistant" ? summarizeUsage(raw.usage) : undefined,
        content: summarizeContentBlocks(raw.content),
    };
}
function summarizeUsage(usage) {
    if (!usage || typeof usage !== "object")
        return undefined;
    return {
        input: nonNegativeNumber(usage.input),
        output: nonNegativeNumber(usage.output),
        cacheRead: nonNegativeNumber(usage.cacheRead),
        cacheWrite: nonNegativeNumber(usage.cacheWrite),
        totalTokens: nonNegativeNumber(usage.totalTokens),
        cost: usage.cost && typeof usage.cost === "object"
            ? {
                input: nonNegativeNumber(usage.cost.input),
                output: nonNegativeNumber(usage.cost.output),
                cacheRead: nonNegativeNumber(usage.cost.cacheRead),
                cacheWrite: nonNegativeNumber(usage.cost.cacheWrite),
                total: nonNegativeNumber(usage.cost.total),
            }
            : undefined,
    };
}
function summarizeToolExecutionResult(result) {
    if (!result || typeof result !== "object")
        return { type: typeof result };
    return {
        content: summarizeContentBlocks(result.content),
        details: summarizeJsonShape(result.details),
        terminate: result.terminate,
    };
}
function summarizeToolArgs(toolName, args) {
    if (!args || typeof args !== "object")
        return { type: typeof args };
    if (toolName === "read") {
        return { path: safeString(args.path), offset: args.offset, limit: args.limit };
    }
    if (toolName === "write") {
        return { path: safeString(args.path), content: summarizeString(args.content) };
    }
    if (toolName === "edit") {
        return {
            path: safeString(args.path),
            edit_count: Array.isArray(args.edits) ? args.edits.length : undefined,
        };
    }
    if (toolName === "bash") {
        return {
            command: summarizeString(args.command),
            timeout: args.timeout,
        };
    }
    return summarizeJsonShape(args);
}
function summarizeContentBlocks(content) {
    if (!Array.isArray(content))
        return [];
    return content.map((block) => {
        if (!block || typeof block !== "object")
            return { type: typeof block };
        const value = block;
        if (value.type === "text")
            return { type: "text", text: summarizeString(value.text) };
        if (value.type === "thinking")
            return { type: "thinking", thinking: summarizeString(value.thinking) };
        if (value.type === "toolCall") {
            return {
                type: "toolCall",
                id: safeString(value.id),
                name: safeString(value.name),
                arguments: summarizeToolArgs(String(value.name ?? ""), value.arguments),
            };
        }
        if (value.type === "image")
            return { type: "image", mimeType: safeString(value.mimeType) };
        return { type: safeString(value.type) };
    });
}
function summarizeJsonShape(value) {
    if (value === null || value === undefined)
        return value;
    if (typeof value === "string")
        return summarizeString(value);
    if (typeof value === "number" || typeof value === "boolean")
        return { type: typeof value };
    if (Array.isArray(value))
        return { type: "array", length: value.length };
    if (typeof value === "object") {
        const entries = Object.entries(value);
        return {
            type: "object",
            keys: entries.map(([key]) => key),
        };
    }
    return { type: typeof value };
}
function summarizeString(value) {
    return { type: "string", length: typeof value === "string" ? value.length : 0 };
}
function nonNegativeNumber(value) {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}
function safeString(value) {
    return typeof value === "string" ? redactText(value) : undefined;
}
function looksLikeTestCommand(command) {
    return /\b(pytest|unittest|npm test|vitest|make test|go test|cargo test)\b/.test(command);
}
async function writeText(path, text, workspaceRoot) {
    const { mkdir, writeFile } = await import("node:fs/promises");
    const { dirname } = await import("node:path");
    const safePath = prepareWorkspaceWritePath(path, workspaceRoot);
    await mkdir(dirname(safePath), { recursive: true });
    await writeFile(safePath, text, "utf-8");
}
async function fileExists(path) {
    try {
        const { access } = await import("node:fs/promises");
        await access(path);
        return true;
    }
    catch {
        return false;
    }
}
async function hashFile(path) {
    const content = await readFile(path);
    return `sha256:${createHash("sha256").update(content).digest("hex")}`;
}
function compactMetadata(values) {
    const result = {};
    for (const [key, value] of Object.entries(values)) {
        if (value === undefined)
            continue;
        if (typeof value === "number" && !Number.isFinite(value))
            continue;
        result[key] = value;
    }
    return result;
}

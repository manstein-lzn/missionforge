import { runAgentLoop } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall, streamSimple } from "@earendil-works/pi-ai";
import { registerFauxProvider } from "@earendil-works/pi-ai";
import { createHash } from "node:crypto";
import { access } from "node:fs/promises";
import { readFile } from "node:fs/promises";
import type {
  AgentEvent,
  AgentMessage,
  AfterToolCallContext,
  ShouldStopAfterTurnContext,
} from "@earendil-works/pi-agent-core";
import type { Message } from "@earendil-works/pi-ai";

import { requireRef } from "./contract.js";
import type { RuntimeInput } from "./contract.js";
import { ToolObservationRecorder } from "./context-observations.js";
import { contextPressureExceeded, ContextProjector } from "./context-projector.js";
import type { ContextProjectionDiagnostics } from "./context-projector.js";
import { EvidenceRecorder } from "./evidence-recorder.js";
import { assertExtensionLoadReportAccepted, loadExtensionLock, writeExtensionLoadReport } from "./extensions.js";
import { loadExtensionTools } from "./extensions.js";
import { changedRefs, snapshotWorkspace } from "./filesystem-snapshot.js";
import { degradedLongMemoryDiagnostics, loadLongMemoryContext } from "./long-memory.js";
import type { LongMemoryContext } from "./long-memory.js";
import { readJsonFile, resolveWorkspaceRef } from "./paths.js";
import { ToolPermissionEnforcer } from "./permissions.js";
import { resolveProviderConfig } from "./provider-config.js";
import { buildRuntimeOutput, writeRuntimeOutput } from "./result-writer.js";
import { createMissionForgeTools, writeExpectedArtifact } from "./tools.js";

const DEFAULT_COMPLETION_RETRY_LIMIT = 2;

export async function runMissionForgePiAgent(input: RuntimeInput, workspaceRoot: string): Promise<void> {
  const provider = resolveProviderConfig();
  const maxTurns = effectiveMaxTurns(input, provider.maxTurns);
  const mainTurnLimit = mainTurnLimitWithCompletionReserve(
    maxTurns,
    input.call_spec.expected_outputs.length,
    DEFAULT_COMPLETION_RETRY_LIMIT,
  );
  const started = Date.now();
  const before = await snapshotWorkspace(workspaceRoot);
  const recorder = new EvidenceRecorder(input, workspaceRoot);
  const observations = new ToolObservationRecorder({ input, workspaceRoot });
  let longMemoryContext: LongMemoryContext = {
    packet: null,
    message: null,
    diagnostics: degradedLongMemoryDiagnostics("long_memory context not loaded"),
  };
  const projector = new ContextProjector({
    observations: () => observations.list(),
    currentTurnIndex: () => turnStartCount,
    contextWindow: () => provider.model.contextWindow ?? 128000,
    metrics: () => recorder.metrics,
    longMemory: () => longMemoryContext,
  });
  const failures: string[] = [];
  const workerClaims: string[] = [];
  let turnStartCount = 0;
  let cancelled = false;
  let checkpointWritten = false;
  let contextCheckpointRef: string | null = null;
  let cancellationReason: string | null = null;
  let latestProjectionDiagnostics: ContextProjectionDiagnostics | null = null;
  let unregisterFaux: (() => void) | undefined;
  let permissionBoundaryReady = false;

  try {
    longMemoryContext = await loadLongMemoryContext(input, workspaceRoot);
    const extensionLock = await loadExtensionLock(input, workspaceRoot);
    const extensionLoadReport = await writeExtensionLoadReport(input, workspaceRoot, extensionLock);
    assertExtensionLoadReportAccepted(extensionLoadReport);
    const { tools: extensionTools, report: loadedReport } = await loadExtensionTools(input, workspaceRoot, extensionLock);
    const tools = await createMissionForgeTools({
      workspaceRoot,
      permissionManifest: input.permission_manifest,
      sandboxProfile: input.sandbox_profile,
      extensionLock,
      extensionTools,
      callId: input.call_id,
      toolTimeoutSeconds: provider.toolTimeoutSeconds,
      knownFileRefs: runtimeKnownFileRefs(input),
      knownDirectoryRefs: runtimeKnownDirectoryRefs(input),
      contextSnapshot: {
        callId: input.call_id,
        workspaceRoot,
        permissionManifest: input.permission_manifest,
        contextObservationsRef: input.context_observations_ref,
        contextProjectionRef: input.context_projection_ref,
        observations: () => observations.list(),
        currentTurnIndex: () => turnStartCount,
        projectionDiagnostics: () => projector.diagnostics(input),
      },
      onToolGatewayDecision: (decision) => recorder.recordToolGatewayDecision(decision),
    });
    if (loadedReport.rejected_extensions.length > 0) {
      throw new Error(
        `extension load rejected: ${loadedReport.rejected_extensions.map((record) => `${record.grant_id}:${record.reason}`).join(", ")}`,
      );
    }
    permissionBoundaryReady = true;

    if (provider.mode === "faux") {
      const configuredContextWindow = provider.model.contextWindow;
      const faux = registerFauxProvider({
        api: "missionforge-faux",
        provider: "missionforge-faux",
        models: [{ id: "missionforge-faux", name: "MissionForge Faux" }],
      });
      unregisterFaux = faux.unregister;
      const fauxModel = faux.getModel();
      provider.model = { ...fauxModel, contextWindow: configuredContextWindow ?? fauxModel.contextWindow };
      const outputs = input.call_spec.expected_outputs;
      if (outputs.length === 0) throw new Error("PiWorker call requires at least one expected output");
      faux.setResponses([
        fauxAssistantMessage(
          outputs.map((outputRef, index) =>
            fauxToolCall("write", {
              path: outputRef,
              content: `pi-agent-runtime faux artifact for ${input.call_id} output ${index + 1}\n`,
            }),
          ),
          { stopReason: "toolUse" },
        ),
        fauxAssistantMessage(`Completed ${input.call_id}.`),
      ]);
    }

    const contextEngineText = await loadContextEngineProviderText(input, workspaceRoot);
    const systemPrompt = buildSystemPrompt(input, contextEngineText);
    const transcript: AgentMessage[] = [];
    const loopConfig = {
      model: provider.model,
      reasoning: provider.reasoning === "off" ? undefined : provider.reasoning,
      sessionId: input.call_id,
      convertToLlm: async (messages: AgentMessage[]): Promise<Message[]> => convertAgentMessagesToLlm(messages),
      transformContext: async (messages: AgentMessage[]) => {
        const projected = projector.project(
          await stripUnreplayableResponsesReasoning(messages),
          systemPrompt,
          provider.model,
          input,
        );
        latestProjectionDiagnostics = projector.diagnostics(input);
        return projected;
      },
      getApiKey: () => provider.apiKey,
      toolExecution: "parallel" as const,
      afterToolCall: async (context: AfterToolCallContext) => {
        await observations.recordAfterToolCall(context);
        const observation = observations.list().find((item) => item.tool_call_id === context.toolCall.id);
        if (observation) await recorder.recordToolObservation(observation);
        return undefined;
      },
      shouldStopAfterTurn: async (turnContext: ShouldStopAfterTurnContext) => {
        projector.project(
          await stripUnreplayableResponsesReasoning(turnContext.context.messages),
          systemPrompt,
          provider.model,
          input,
        );
        latestProjectionDiagnostics = projector.diagnostics(input);
        const checkpointRef = await maybeWriteContextCheckpoint({
          input,
          workspaceRoot,
          projector,
          recorder,
          diagnostics: latestProjectionDiagnostics,
          reason: checkpointReason(latestProjectionDiagnostics),
          alreadyWritten: () => checkpointWritten,
          markWritten: (ref) => {
            checkpointWritten = true;
            contextCheckpointRef = ref;
          },
          onFailure: (message) => pushFailures(failures, [message]),
        });
        if (input.call_spec.expected_outputs.length > 0) {
          const changedAfterTurn = await changedRefs(workspaceRoot, before);
          const missingOutputs = await collectMissingExpectedOutputRefs(input, workspaceRoot, changedAfterTurn);
          if (missingOutputs.length === 0) {
            return true;
          }
          if (turnStartCount >= mainTurnLimit) {
            return true;
          }
        }
        if (checkpointRef && contextPressureExceeded(latestProjectionDiagnostics)) {
          cancelled = true;
          cancellationReason =
            `context pressure ${latestProjectionDiagnostics.pressure_ratio.toFixed(4)} reached hard threshold ` +
            `${latestProjectionDiagnostics.hard_compact_ratio.toFixed(4)}`;
          return true;
        }
        return false;
      },
    };
    const recordEvent = async (event: AgentEvent) => {
      if (event.type === "turn_start") {
        turnStartCount += 1;
        observations.noteTurnStart();
        if (turnStartCount > maxTurns) {
          throw new Error(`pi-agent-runtime reached max turns: ${maxTurns}`);
        }
      }
      await recorder.record(event);
      if (
        event.type === "turn_end" &&
        provider.compactAfterTurns !== null &&
        turnStartCount >= provider.compactAfterTurns &&
        !checkpointWritten
      ) {
        checkpointWritten = true;
        latestProjectionDiagnostics = projector.diagnostics(input);
        await projector.writeDiagnostics(input, workspaceRoot);
        contextCheckpointRef = await recorder.writeContextCheckpoint(
          `turn_count >= ${provider.compactAfterTurns}`,
          latestProjectionDiagnostics,
        );
      }
      if (
        event.type === "turn_end" &&
        provider.cancelAfterTurns !== null &&
        turnStartCount >= provider.cancelAfterTurns
      ) {
        cancelled = true;
        throw new Error("pi-agent-runtime cancelled at a MissionForge safe point");
      }
    };
    const makeUserMessage = (text: string): AgentMessage => ({
      role: "user",
      content: [{ type: "text", text }],
      timestamp: Date.now(),
    });
    const runPrompt = async (prompt: string, currentMessages: AgentMessage[]): Promise<AgentMessage[]> =>
      runAgentLoopWithProviderRetry(
        {
          userMessages: [makeUserMessage(prompt)],
          currentMessages,
          systemPrompt,
          tools,
          loopConfig,
          recordEvent,
          maxRetries: provider.providerRetryLimit,
          retryDelayMs: provider.providerRetryDelayMs,
        },
      );

      transcript.push(...(await runPrompt(buildUserPrompt(input), [])));
    pushFailures(failures, collectAgentFailures(transcript));
    await promptForMissingExpectedOutputs({
      input,
      workspaceRoot,
      maxTurns,
      maxRetries: DEFAULT_COMPLETION_RETRY_LIMIT,
      currentTurnCount: () => turnStartCount,
      changedRefs: () => changedRefs(workspaceRoot, before),
      prompt: async (prompt) => {
        transcript.push(...(await runPrompt(prompt, transcript)));
        pushFailures(failures, collectAgentFailures(transcript));
      },
    });
    await recorder.writeSession(transcript);
    workerClaims.push(extractFinalText(transcript) ?? "");
  } catch (error) {
    failures.push(error instanceof Error ? error.message : String(error));
    if (provider.mode === "faux" && permissionBoundaryReady) {
      await fallbackFauxArtifact(input, workspaceRoot, failures);
    }
  } finally {
    unregisterFaux?.();
  }

  const durationMs = Date.now() - started;
  await observations.ensureIndex();
  await projector.writeDiagnostics(input, workspaceRoot);
  const changed = await changedRefs(workspaceRoot, before);
  await recorder.writeMetrics(durationMs);
  const missingOutputs = await collectMissingExpectedOutputRefs(input, workspaceRoot, changed);
  const cancellationShouldFail =
    cancelled &&
    (
      failures.length > 0 ||
      missingOutputs.length > 0
    );
  const artifactsAreCompleteAfterTransientFailure =
    !cancelled &&
    failures.length > 0 &&
    missingOutputs.length === 0 &&
    failures.every(isTransientProviderFailure);
  const output = await buildRuntimeOutput({
    input,
    workspaceRoot,
    changedRefs: changed,
    commandsRun: recorder.metrics.commands_run,
    testsRun: recorder.metrics.tests_run,
    failures,
    workerClaims: workerClaims.filter(Boolean),
    durationMs,
    metrics: recorder.safeMetrics() as unknown as Record<string, unknown>,
    statusOverride: cancellationShouldFail ? "cancelled" : artifactsAreCompleteAfterTransientFailure ? "completed" : undefined,
    recommendedNextSteps: cancellationShouldFail
      ? [
          cancellationReason
            ? `Run was cancelled at a MissionForge safe point: ${cancellationReason}.`
            : "Run was cancelled at a MissionForge safe point.",
          contextCheckpointRef
            ? `Resume with checkpoint_refs including ${contextCheckpointRef}.`
            : "Resume from the latest completed-turn savepoint.",
        ]
      : undefined,
  });
  await writeRuntimeOutput(workspaceRoot, input, output);
}

function convertAgentMessagesToLlm(messages: AgentMessage[]): Message[] {
  return messages.filter(
    (message): message is Message =>
      message.role === "user" || message.role === "assistant" || message.role === "toolResult",
  );
}

function collectAgentFailures(messages: readonly AgentMessage[]): string[] {
  const failures: string[] = [];
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    if (message.stopReason !== "error" && message.stopReason !== "aborted") continue;
    if (typeof message.errorMessage === "string" && message.errorMessage.trim()) {
      failures.push(message.errorMessage);
    } else {
      failures.push(message.stopReason);
    }
  }
  return failures;
}

function pushFailures(target: string[], candidates: string[]): void {
  for (const candidate of candidates) {
    if (!candidate || target.includes(candidate)) continue;
    target.push(candidate);
  }
}

export function isTransientProviderFailure(message: string): boolean {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("openai api error (429)") ||
    normalized.includes("openai api error (502)") ||
    normalized.includes("openai api error (503)") ||
    normalized.includes("openai api error (504)") ||
    normalized.includes("rate limit") ||
    normalized.includes("timeout") ||
    normalized.includes("timed out") ||
    normalized.includes("econnreset") ||
    normalized.includes("econnrefused") ||
    normalized.includes("etimedout") ||
    normalized.includes("socket hang up") ||
    normalized.includes("network error") ||
    normalized.includes("origin web server returned an invalid or incomplete response") ||
    normalized.includes("cloudflare")
  );
}

interface RunAgentLoopWithProviderRetryOptions {
  userMessages: AgentMessage[];
  currentMessages: AgentMessage[];
  systemPrompt: string;
  tools: unknown;
  loopConfig: unknown;
  recordEvent: (event: AgentEvent) => Promise<void>;
  maxRetries: number;
  retryDelayMs: number;
}

async function runAgentLoopWithProviderRetry(
  options: RunAgentLoopWithProviderRetryOptions,
): Promise<AgentMessage[]> {
  let attempt = 0;
  for (;;) {
    try {
      return await runAgentLoop(
        options.userMessages,
        { systemPrompt: options.systemPrompt, messages: options.currentMessages, tools: options.tools as any },
        options.loopConfig as any,
        options.recordEvent,
        undefined,
        streamSimple,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (attempt >= options.maxRetries || !isTransientProviderFailure(message)) throw error;
      attempt += 1;
      if (options.retryDelayMs > 0) {
        await sleep(options.retryDelayMs * attempt);
      }
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface MaybeWriteContextCheckpointOptions {
  input: RuntimeInput;
  workspaceRoot: string;
  projector: ContextProjector;
  recorder: EvidenceRecorder;
  diagnostics: ContextProjectionDiagnostics;
  reason: string;
  alreadyWritten: () => boolean;
  markWritten: (ref: string) => void;
  onFailure: (message: string) => void;
}

async function maybeWriteContextCheckpoint(options: MaybeWriteContextCheckpointOptions): Promise<string | null> {
  if (options.alreadyWritten()) return null;
  if (options.diagnostics.recommended_action === "continue") return null;
  try {
    await options.projector.writeDiagnostics(options.input, options.workspaceRoot);
    const checkpointRef = await options.recorder.writeContextCheckpoint(options.reason, options.diagnostics);
    options.markWritten(checkpointRef);
    return checkpointRef;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    options.onFailure(`runtime context checkpoint failed: ${message}`);
    return null;
  }
}

function checkpointReason(diagnostics: ContextProjectionDiagnostics): string {
  return [
    `context_pressure=${diagnostics.pressure_ratio.toFixed(4)}`,
    `estimated_input_tokens=${diagnostics.estimated_input_tokens}`,
    `usable_input_budget=${diagnostics.context_budget.usable_input_budget}`,
    `model_context_window=${diagnostics.model_context_window}`,
    `soft=${diagnostics.soft_compact_ratio}`,
    `hard=${diagnostics.hard_compact_ratio}`,
  ].join(" ");
}

function runtimeKnownFileRefs(input: RuntimeInput): string[] {
  return [
    input.input_ref,
    input.output_ref,
    input.session_ref,
    input.events_ref,
    input.metrics_ref,
    input.savepoints_ref,
    input.piworker_call.contract_ref,
    ...contextEngineKnownFileRefs(input),
    ...input.piworker_call.visible_refs,
    ...input.piworker_call.expected_output_refs,
    ...input.call_spec.visible_refs,
    ...input.call_spec.expected_outputs,
  ];
}

function contextEngineKnownFileRefs(input: RuntimeInput): string[] {
  const engine = input.context_engine;
  if (!engine?.enabled) return [];
  return [
    engine.context_view_ref,
    engine.context_compile_request_ref,
    engine.context_compile_result_ref,
    engine.context_baseline_ref,
    engine.context_source_snapshot_ref,
    engine.context_epoch_ref,
    engine.context_cache_layout_ref,
    engine.context_pressure_ref,
    engine.context_turn_safe_point_ref,
    engine.context_turn_boundary_ref,
  ].filter((ref): ref is string => typeof ref === "string" && ref.length > 0);
}

export async function loadContextEngineProviderText(input: RuntimeInput, workspaceRoot: string): Promise<string> {
  const engine = input.context_engine;
  if (!engine?.enabled) return "";
  if (!engine.context_view_ref || !engine.context_compile_result_ref) {
    throw new Error("context_engine enabled without required refs");
  }
  const enforcer = new ToolPermissionEnforcer(workspaceRoot, input.permission_manifest);
  for (const ref of contextEngineKnownFileRefs(input)) {
    enforcer.ensureReadRef(ref);
  }
  const view = requireJsonObject(
    await readJsonFile(enforcer.ensureReadPath(resolveWorkspaceRef(workspaceRoot, engine.context_view_ref))),
    "context_engine.context_view",
  );
  const compileResult = requireJsonObject(
    await readJsonFile(enforcer.ensureReadPath(resolveWorkspaceRef(workspaceRoot, engine.context_compile_result_ref))),
    "context_engine.context_compile_result",
  );
  const viewHash = requireStringField(view, "context_hash", "context_view.context_hash");
  const computedViewHash = stableJsonHash(contextViewContentForHash(view));
  if (computedViewHash !== viewHash) {
    throw new Error("context_engine context_view hash does not match content");
  }
  const resultHash = requireStringField(compileResult, "context_hash", "context_compile_result.context_hash");
  if (engine.context_hash && engine.context_hash !== viewHash) {
    throw new Error("context_engine context_hash does not match context_view");
  }
  if (resultHash !== viewHash) {
    throw new Error("context_engine compile result hash does not match context_view");
  }
  const resultViewRef = requireRef(compileResult.view_ref, "context_compile_result.view_ref");
  if (resultViewRef !== engine.context_view_ref) {
    throw new Error("context_engine compile result view_ref does not match context_view_ref");
  }
  return renderContextEngineProviderText(input, workspaceRoot, engine.context_view_ref, view, compileResult, enforcer);
}

async function renderContextEngineProviderText(
  input: RuntimeInput,
  workspaceRoot: string,
  viewRef: string,
  view: Record<string, unknown>,
  compileResult: Record<string, unknown>,
  enforcer: ToolPermissionEnforcer,
): Promise<string> {
  const engine = input.context_engine;
  const lines = [
    "[MissionForge ContextEngine compiled context]",
    "This refs-only context view is the provider-turn context authority for this call.",
    "Use admitted segment refs and body_ref handles through permitted tools when details are needed.",
    "Do not infer from omitted or denied refs; do not treat refs as semantic acceptance.",
    `context_view_ref: ${viewRef}`,
    `context_compile_result_ref: ${engine.context_compile_result_ref}`,
    `context_hash: ${requireStringField(view, "context_hash", "context_view.context_hash")}`,
    `context_compile_action: ${requireStringField(compileResult, "action", "context_compile_result.action")}`,
    `role: ${requireStringField(view, "role", "context_view.role")}`,
    `contract_ref: ${requireRef(view.contract_ref, "context_view.contract_ref")}`,
    `permission_manifest_ref: ${requireRef(view.permission_manifest_ref, "context_view.permission_manifest_ref")}`,
  ];
  for (const [bucketName, fieldName] of [
    ["stable_prefix", "stable_prefix"],
    ["semi_stable_context", "semi_stable_context"],
    ["volatile_tail", "volatile_tail"],
  ] as const) {
    lines.push(
      await renderContextSegmentBucket(
        workspaceRoot,
        enforcer,
        bucketName,
        requireArrayField(view, fieldName, `context_view.${fieldName}`),
      ),
    );
  }
  const omittedRefs = requireRefArrayField(compileResult, "omitted_refs", "context_compile_result.omitted_refs");
  const demotedRefs = requireRefArrayField(compileResult, "demoted_refs", "context_compile_result.demoted_refs");
  lines.push(`omitted_ref_count: ${omittedRefs.length}`);
  lines.push(`demoted_ref_count: ${demotedRefs.length}`);
  if (engine.context_cache_layout_ref) lines.push(`context_cache_layout_ref: ${engine.context_cache_layout_ref}`);
  if (engine.context_pressure_ref) lines.push(`context_pressure_ref: ${engine.context_pressure_ref}`);
  if (engine.context_epoch_ref) lines.push(`context_epoch_ref: ${engine.context_epoch_ref}`);
  return lines.join("\n");
}

async function renderContextSegmentBucket(
  workspaceRoot: string,
  enforcer: ToolPermissionEnforcer,
  bucketName: string,
  values: unknown[],
): Promise<string> {
  const lines = [`${bucketName}: count=${values.length}`];
  for (const item of values.slice(0, 20)) {
    const segment = requireJsonObject(item, `context_view.${bucketName}[]`);
    const refs = requireRefArrayField(segment, "source_refs", "context_segment.source_refs");
    for (const ref of refs) {
      enforcer.ensureReadRef(ref);
    }
    const bodyRef = optionalRefField(segment.body_ref, "context_segment.body_ref");
    const parts = [
      `id=${requireStringField(segment, "segment_id", "context_segment.segment_id")}`,
      `kind=${requireStringField(segment, "kind", "context_segment.kind")}`,
      `cache=${requireStringField(segment, "cache_policy", "context_segment.cache_policy")}`,
      `inline=${requireStringField(segment, "inline_policy", "context_segment.inline_policy")}`,
      `tokens=${requireNonNegativeNumberField(segment, "token_estimate", "context_segment.token_estimate")}`,
      `source_refs=${refs.join(",") || "<none>"}`,
    ];
    if (bodyRef) parts.push(`body_ref=${bodyRef}`);
    lines.push(`- ${parts.join(" ")}`);
    const boundedProjection = await boundedContextProjectionText(workspaceRoot, enforcer, segment, bodyRef);
    if (boundedProjection) lines.push(boundedProjection);
  }
  if (values.length > 20) lines.push(`- additional_segment_count=${values.length - 20}`);
  return lines.join("\n");
}

async function boundedContextProjectionText(
  workspaceRoot: string,
  enforcer: ToolPermissionEnforcer,
  segment: Record<string, unknown>,
  bodyRef: string | null,
): Promise<string> {
  if (!bodyRef) return "";
  const kind = requireStringField(segment, "kind", "context_segment.kind");
  const metadata = requireJsonObject(segment.metadata ?? {}, "context_segment.metadata");
  const sourceKind = typeof metadata.source_kind === "string" ? metadata.source_kind : "";
  const projectionLabel = projectionLabelForSegment(kind, sourceKind);
  if (!projectionLabel) return "";
  const path = enforcer.ensureReadPath(resolveWorkspaceRef(workspaceRoot, bodyRef));
  const content = await readFile(path);
  const expectedHash = compiledSegmentHash(segment, bodyRef);
  if (!expectedHash) {
    throw new Error(`context_engine ${projectionLabel} is missing compiled hash`);
  }
  const actualHash = `sha256:${createHash("sha256").update(content).digest("hex")}`;
  if (actualHash !== expectedHash) {
    throw new Error(`context_engine ${projectionLabel} hash does not match compiled context`);
  }
  const text = content.toString("utf-8");
  return [
    `  ${projectionLabel}:`,
    `  projection_ref: ${bodyRef}`,
    "  text:",
    ...boundedProjectionLines(text).map((line) => `    ${line}`),
  ].join("\n");
}

function projectionLabelForSegment(kind: string, sourceKind: string): string {
  if (kind === "artifact_preview" && sourceKind === "working_set") return "working_set_projection";
  if (kind === "tool_observation" && sourceKind === "tool_output_projection") return "tool_output_projection";
  return "";
}

function compiledSegmentHash(segment: Record<string, unknown>, ref: string): string {
  const sourceHashes = requireJsonObject(segment.source_hashes ?? {}, "context_segment.source_hashes");
  const value = sourceHashes[ref];
  if (typeof value !== "string" || !/^sha256:[0-9a-f]{64}$/.test(value)) {
    return "";
  }
  return value;
}

function contextViewContentForHash(view: Record<string, unknown>): Record<string, unknown> {
  const { context_hash: _contextHash, ...content } = view;
  return content;
}

function stableJsonHash(value: unknown): string {
  return `sha256:${createHash("sha256").update(stableJsonString(value)).digest("hex")}`;
}

function stableJsonString(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return ensureAsciiJsonString(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("stable_json value must not contain non-finite numbers");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map((item) => stableJsonString(item)).join(",")}]`;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJsonString(record[key])}`)
      .join(",")}}`;
  }
  throw new Error("stable_json value must be JSON-compatible");
}

function ensureAsciiJsonString(value: string): string {
  return JSON.stringify(value).replace(/[^\x00-\x7F]/g, (char) =>
    `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}

function boundedProjectionLines(text: string, maxChars = 4000, maxLines = 80): string[] {
  const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const truncated = normalized.length > maxChars ? normalized.slice(0, maxChars) + "\n[projection_truncated]" : normalized;
  return truncated.split("\n").slice(0, maxLines);
}

function requireJsonObject(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requireArrayField(record: Record<string, unknown>, key: string, field: string): unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  return value;
}

function requireRefArrayField(record: Record<string, unknown>, key: string, field: string): string[] {
  return requireArrayField(record, key, field).map((item, index) => requireRef(item, `${field}[${index}]`));
}

function requireStringField(record: Record<string, unknown>, key: string, field: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) throw new Error(`${field} must be a non-empty string`);
  return value;
}

function optionalRefField(value: unknown, field: string): string | null {
  if (value === undefined || value === null || value === "") return null;
  return requireRef(value, field);
}

function requireNonNegativeNumberField(record: Record<string, unknown>, key: string, field: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${field} must be a non-negative number`);
  }
  return value;
}

function runtimeKnownDirectoryRefs(input: RuntimeInput): string[] {
  return [
    input.attempt_dir_ref,
    ...input.piworker_call.writable_refs,
    ...input.call_spec.allowed_scope,
  ];
}

export async function stripUnreplayableResponsesReasoning(messages: any[]): Promise<any[]> {
  return messages.map((message) => {
    if (message?.role !== "assistant" || !Array.isArray(message.content)) return message;
    if (message.api !== "openai-responses") return message;
    const content = message.content.filter((block: any) => block?.type !== "thinking");
    return { ...message, content };
  });
}

export function mainTurnLimitWithCompletionReserve(
  maxTurns: number,
  expectedOutputCount: number,
  completionRetryLimit = DEFAULT_COMPLETION_RETRY_LIMIT,
): number {
  if (expectedOutputCount <= 0 || maxTurns <= 1 || completionRetryLimit <= 0) return maxTurns;
  const reserve = Math.min(completionRetryLimit, maxTurns - 1);
  return Math.max(1, maxTurns - reserve);
}

function buildSystemPrompt(input: RuntimeInput, contextEngineText = ""): string {
  const lines = [
    "You are MissionForge's dedicated PI Agent runtime worker.",
    "Act as a complete coding agent. Use the available tools only inside the declared permission manifest.",
    "MissionForge owns verification; your completion claims are evidence only.",
    "Do not call a tool that is not available in this runtime. If shell access is not provided, use read/write/edit only.",
    "Write only the declared expected or optional artifact refs. Do not create extra files.",
    "When a visible node spec describes exact JSON schemas, write those exact schema_version values, enum values, and required fields.",
    `Call id: ${input.call_id}`,
    `Mission: ${input.mission_id}`,
    `Objective: ${input.call_spec.next_objective}`,
    `Expected outputs: ${input.call_spec.expected_outputs.join(", ")}`,
    `Writable refs: ${input.permission_manifest.writable_refs.join(", ")}`,
    `Visible refs: ${input.call_spec.visible_refs.join(", ")}`,
    `Exit criteria: ${input.call_spec.exit_criteria.join("; ")}`,
    `Stop conditions: ${input.call_spec.stop_conditions.join("; ")}`,
  ];
  if (contextEngineText) {
    lines.push(contextEngineText);
  }
  if (input.repair.mode === "follow_up") {
    lines.push("This is a verifier-driven repair follow-up.");
    lines.push(`Failed constraints: ${input.repair.failed_constraints.join(", ") || "<none>"}`);
    lines.push(`Previous output: ${input.repair.previous_output_ref}`);
  }
  if (input.resume.mode === "follow_up") {
    lines.push("This is a MissionForge completed-turn resume follow-up.");
    lines.push(`Resume boundary: ${input.resume.boundary}`);
    lines.push(`Resume savepoint: ${input.resume.savepoint_ref}`);
    lines.push(`Resume session: ${input.resume.session_ref}`);
    lines.push(`Resume events: ${input.resume.events_ref}`);
    if (input.resume.checkpoint_refs.length > 0) {
      lines.push(`Resume context checkpoints: ${input.resume.checkpoint_refs.join(", ")}`);
    }
    if (input.resume.summary_artifact_refs.length > 0) {
      lines.push(`Resume semantic summary artifacts: ${input.resume.summary_artifact_refs.join(", ")}`);
    }
  }
  return lines.join("\n");
}

function buildUserPrompt(input: RuntimeInput): string {
  if (input.resume.mode === "follow_up") {
    return [
      "Resume this MissionForge PiWorker call from the completed-turn safe point below.",
      input.resume.resume_prompt ?? "Resume from the latest completed turn.",
      `Savepoint ref: ${input.resume.savepoint_ref}`,
      `Session ref: ${input.resume.session_ref}`,
      `Events ref: ${input.resume.events_ref}`,
      `Context checkpoint refs: ${input.resume.checkpoint_refs.join(", ") || "<none>"}`,
      `Semantic summary artifact refs: ${input.resume.summary_artifact_refs.join(", ") || "<none>"}`,
      `Write or update the expected outputs: ${input.call_spec.expected_outputs.join(", ")}`,
      "Do not claim completion as acceptance; MissionForge will verify after this attempt.",
      "Use only permitted tools and refs, then stop.",
    ].join("\n");
  }
  if (input.repair.mode === "follow_up") {
    return [
      "Repair this MissionForge PiWorker call using the verifier feedback below.",
      input.repair.repair_prompt ?? "Repair the expected outputs.",
      `Verifier failures: ${input.repair.verifier_failures.join("; ") || "<none>"}`,
      `Failed constraints: ${input.repair.failed_constraints.join(", ") || "<none>"}`,
      `Previous output ref: ${input.repair.previous_output_ref}`,
      `Write or update the expected outputs: ${input.call_spec.expected_outputs.join(", ")}`,
      "Use only permitted tools and refs, then stop.",
    ].join("\n");
  }
  return [
    "Complete this MissionForge PiWorker call.",
    `First read the visible refs: ${input.call_spec.visible_refs.join(", ") || "<none>"}`,
    `Write or update the expected outputs: ${input.call_spec.expected_outputs.join(", ")}`,
    "Treat those expected outputs as the durable completion boundary. If an expected output already exists as an input template, update it for this call before claiming completion.",
    "If the visible refs include a node spec, follow its schema_hints exactly before writing artifacts.",
    "Use permitted tools to inspect, edit, and write as needed. Do not use bash unless a bash tool is present and the exact command is allowed.",
  ].join("\n");
}

function effectiveMaxTurns(input: RuntimeInput, fallback: number): number {
  const value = input.piworker_call?.runtime_budget?.max_turns;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : fallback;
}

export interface MissingOutputRetryOptions {
  input: RuntimeInput;
  workspaceRoot: string;
  maxTurns: number;
  maxRetries: number;
  currentTurnCount: () => number;
  changedRefs?: () => Promise<string[]>;
  prompt: (prompt: string) => Promise<void>;
}

export interface MissingOutputRetryResult {
  missingOutputs: string[];
  retryCount: number;
}

export async function promptForMissingExpectedOutputs(
  options: MissingOutputRetryOptions,
): Promise<MissingOutputRetryResult> {
  let missingOutputs = await collectMissingExpectedOutputRefs(
    options.input,
    options.workspaceRoot,
    await options.changedRefs?.(),
  );
  let retryCount = 0;
  while (
    missingOutputs.length > 0 &&
    retryCount < options.maxRetries &&
    options.currentTurnCount() < options.maxTurns
  ) {
    retryCount += 1;
    await options.prompt(buildCompletionRetryPrompt(options.input, missingOutputs, retryCount));
    missingOutputs = await collectMissingExpectedOutputRefs(
      options.input,
      options.workspaceRoot,
      await options.changedRefs?.(),
    );
  }
  return { missingOutputs, retryCount };
}

export function buildCompletionRetryPrompt(input: RuntimeInput, missingOutputs: string[], retryCount: number): string {
  const lines = [
    `MissionForge verification pass ${retryCount} found missing expected output refs: ${missingOutputs.join(", ")}`,
    "Continue the same PiWorker call. Do not change the call_spec, packets, hard checks, evidence refs, or permission manifest.",
    `Visible refs to inspect: ${input.call_spec.visible_refs.join(", ") || "<none>"}`,
    `Writable refs: ${input.permission_manifest.writable_refs.join(", ")}`,
  ];
  for (const missingOutput of missingOutputs) {
    lines.push(`- ${missingOutput}: create or update this file now.`);
  }
  lines.push(
    "Write only the missing expected outputs listed above.",
    "Do not answer in text instead of writing artifacts. Use the available file tools to create or update the missing refs.",
  );
  if (input.piworker_call?.role === "judge_piworker") {
    lines.push(
      "As judge_piworker, write a complete judge report JSON object at the missing report ref using the visible judge context refs.",
    );
  }
  return lines.join("\n");
}

export async function missingExpectedOutputRefs(input: RuntimeInput, workspaceRoot: string): Promise<string[]> {
  return collectMissingExpectedOutputRefs(input, workspaceRoot, undefined);
}

async function collectMissingExpectedOutputRefs(
  input: RuntimeInput,
  workspaceRoot: string,
  changedRefsSnapshot: string[] | undefined,
): Promise<string[]> {
  const changed = changedRefsSnapshot ? new Set(changedRefsSnapshot) : null;
  const missing: string[] = [];
  for (const ref of input.call_spec.expected_outputs) {
    try {
      await access(resolveWorkspaceRef(workspaceRoot, ref));
      if (changed && !changed.has(ref)) missing.push(ref);
    } catch {
      missing.push(ref);
    }
  }
  return missing;
}

function extractFinalText(messages: readonly unknown[]): string | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index] as any;
    if (message?.role !== "assistant" || !Array.isArray(message.content)) continue;
    const text = message.content
      .filter((block: any) => block?.type === "text")
      .map((block: any) => block.text)
      .join("\n")
      .trim();
    if (text) return text;
  }
  return undefined;
}

async function fallbackFauxArtifact(input: RuntimeInput, workspaceRoot: string, failures: string[]): Promise<void> {
  const firstOutput = input.call_spec.expected_outputs[0];
  if (!firstOutput) return;
  try {
    await writeExpectedArtifact(
      workspaceRoot,
      firstOutput,
      `pi-agent-runtime fallback faux artifact for ${input.call_id}\n`,
      input.permission_manifest,
    );
  } catch (error) {
    failures.push(error instanceof Error ? error.message : String(error));
  }
}

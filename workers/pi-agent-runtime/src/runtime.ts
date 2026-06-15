import { runAgentLoop } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall, streamSimple } from "@earendil-works/pi-ai";
import { registerFauxProvider } from "@earendil-works/pi-ai";
import { access } from "node:fs/promises";
import type { AgentEvent, AgentMessage, AfterToolCallContext } from "@earendil-works/pi-agent-core";
import type { Message } from "@earendil-works/pi-ai";

import type { RuntimeInput } from "./contract.js";
import { ToolObservationRecorder } from "./context-observations.js";
import { ContextProjector } from "./context-projector.js";
import { EvidenceRecorder } from "./evidence-recorder.js";
import { assertExtensionLoadReportAccepted, loadExtensionLock, writeExtensionLoadReport } from "./extensions.js";
import { loadExtensionTools } from "./extensions.js";
import { changedRefs, snapshotWorkspace } from "./filesystem-snapshot.js";
import { resolveWorkspaceRef } from "./paths.js";
import { resolveProviderConfig } from "./provider-config.js";
import { buildRuntimeOutput, writeRuntimeOutput } from "./result-writer.js";
import { createMissionForgeTools, writeExpectedArtifact } from "./tools.js";

const DEFAULT_COMPLETION_RETRY_LIMIT = 2;

export async function runMissionForgePiAgent(input: RuntimeInput, workspaceRoot: string): Promise<void> {
  const provider = resolveProviderConfig();
  const started = Date.now();
  const before = await snapshotWorkspace(workspaceRoot);
  const recorder = new EvidenceRecorder(input, workspaceRoot);
  const observations = new ToolObservationRecorder({ input, workspaceRoot });
  const projector = new ContextProjector({
    observations: () => observations.list(),
    currentTurnIndex: () => turnStartCount,
  });
  const failures: string[] = [];
  const workerClaims: string[] = [];
  let turnStartCount = 0;
  let cancelled = false;
  let compactionWritten = false;
  let unregisterFaux: (() => void) | undefined;
  let permissionBoundaryReady = false;

  try {
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
      const faux = registerFauxProvider({
        api: "missionforge-faux",
        provider: "missionforge-faux",
        models: [{ id: "missionforge-faux", name: "MissionForge Faux" }],
      });
      unregisterFaux = faux.unregister;
      provider.model = faux.getModel();
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

    const systemPrompt = buildSystemPrompt(input);
    const transcript: AgentMessage[] = [];
    const loopConfig = {
      model: provider.model,
      reasoning: provider.reasoning === "off" ? undefined : provider.reasoning,
      sessionId: input.call_id,
      convertToLlm: async (messages: AgentMessage[]): Promise<Message[]> => convertAgentMessagesToLlm(messages),
      transformContext: async (messages: AgentMessage[]) =>
        projector.project(await stripUnreplayableResponsesReasoning(messages)),
      getApiKey: () => provider.apiKey,
      toolExecution: "parallel" as const,
      afterToolCall: async (context: AfterToolCallContext) => {
        await observations.recordAfterToolCall(context);
        const observation = observations.list().find((item) => item.tool_call_id === context.toolCall.id);
        if (observation) await recorder.recordToolObservation(observation);
        return undefined;
      },
      shouldStopAfterTurn: async () => {
        if (input.piworker_call.role !== "frontdesk_author_piworker") return false;
        if (input.call_spec.expected_outputs.length === 0) return false;
        return (await missingExpectedOutputRefs(input, workspaceRoot)).length === 0;
      },
    };
    const recordEvent = async (event: AgentEvent) => {
      if (event.type === "turn_start") {
        turnStartCount += 1;
        observations.noteTurnStart();
        if (turnStartCount > provider.maxTurns) {
          throw new Error(`pi-agent-runtime reached max turns: ${provider.maxTurns}`);
        }
      }
      await recorder.record(event);
      if (
        event.type === "turn_end" &&
        provider.compactAfterTurns !== null &&
        turnStartCount >= provider.compactAfterTurns &&
        !compactionWritten
      ) {
        compactionWritten = true;
        await recorder.writeCompactionMarker(`turn_count >= ${provider.compactAfterTurns}`);
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
      runAgentLoop(
        [makeUserMessage(prompt)],
        { systemPrompt, messages: currentMessages, tools },
        loopConfig,
        recordEvent,
        undefined,
        streamSimple,
      );

      transcript.push(...(await runPrompt(buildUserPrompt(input), [])));
    pushFailures(failures, collectAgentFailures(transcript));
    await promptForMissingExpectedOutputs({
      input,
      workspaceRoot,
      maxTurns: provider.maxTurns,
      maxRetries: DEFAULT_COMPLETION_RETRY_LIMIT,
      currentTurnCount: () => turnStartCount,
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
    statusOverride: cancelled ? "cancelled" : undefined,
    recommendedNextSteps: cancelled ? ["Run was cancelled at a MissionForge safe point."] : undefined,
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

function runtimeKnownFileRefs(input: RuntimeInput): string[] {
  return [
    input.input_ref,
    input.output_ref,
    input.session_ref,
    input.events_ref,
    input.metrics_ref,
    input.savepoints_ref,
    input.piworker_call.contract_ref,
    ...input.piworker_call.visible_refs,
    ...input.piworker_call.expected_output_refs,
    ...input.call_spec.visible_refs,
    ...input.call_spec.expected_outputs,
  ];
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

function buildSystemPrompt(input: RuntimeInput): string {
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
    if (input.resume.summary_artifact_refs.length > 0) {
      lines.push(`Resume summary artifacts: ${input.resume.summary_artifact_refs.join(", ")}`);
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
      `Summary artifact refs: ${input.resume.summary_artifact_refs.join(", ") || "<none>"}`,
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
    "If the visible refs include a node spec, follow its schema_hints exactly before writing artifacts.",
    "Use permitted tools to inspect, edit, and write as needed. Do not use bash unless a bash tool is present and the exact command is allowed.",
  ].join("\n");
}

export interface MissingOutputRetryOptions {
  input: RuntimeInput;
  workspaceRoot: string;
  maxTurns: number;
  maxRetries: number;
  currentTurnCount: () => number;
  prompt: (prompt: string) => Promise<void>;
}

export interface MissingOutputRetryResult {
  missingOutputs: string[];
  retryCount: number;
}

export async function promptForMissingExpectedOutputs(
  options: MissingOutputRetryOptions,
): Promise<MissingOutputRetryResult> {
  let missingOutputs = await missingExpectedOutputRefs(options.input, options.workspaceRoot);
  let retryCount = 0;
  while (
    missingOutputs.length > 0 &&
    retryCount < options.maxRetries &&
    options.currentTurnCount() < options.maxTurns
  ) {
    retryCount += 1;
    await options.prompt(buildCompletionRetryPrompt(options.input, missingOutputs, retryCount));
    missingOutputs = await missingExpectedOutputRefs(options.input, options.workspaceRoot);
  }
  return { missingOutputs, retryCount };
}

export function buildCompletionRetryPrompt(input: RuntimeInput, missingOutputs: string[], retryCount: number): string {
  const lines = [
    `MissionForge verification pass ${retryCount} found missing expected output refs: ${missingOutputs.join(", ")}`,
    "Continue the same PiWorker call. Do not change the call_spec, packets, hard checks, evidence refs, or permission manifest.",
    `Visible refs to inspect: ${input.call_spec.visible_refs.join(", ") || "<none>"}`,
    `Writable refs: ${input.permission_manifest.writable_refs.join(", ")}`,
    `Write only these missing expected outputs: ${missingOutputs.join(", ")}`,
    "Do not answer in text instead of writing artifacts. Use the available file tools to create or update the missing refs.",
  ];
  if (input.piworker_call?.role === "judge_piworker") {
    lines.push(
      "As judge_piworker, write a complete JudgeReport JSON object at the missing report ref using the judge node spec and JudgePacket.",
    );
  }
  return lines.join("\n");
}

export async function missingExpectedOutputRefs(input: RuntimeInput, workspaceRoot: string): Promise<string[]> {
  const missing: string[] = [];
  for (const ref of input.call_spec.expected_outputs) {
    try {
      await access(resolveWorkspaceRef(workspaceRoot, ref));
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

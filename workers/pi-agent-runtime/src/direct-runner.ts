import { mkdir, readFile } from "node:fs/promises";

import { Agent } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall, registerFauxProvider, streamSimple } from "@earendil-works/pi-ai";

import { DIRECT_OUTPUT_SCHEMA_VERSION, type DirectRuntimeInput, type DirectRuntimeOutput, validateDirectRuntimeOutput } from "./direct-contract.js";
import { DirectEvidenceRecorder } from "./direct-evidence-recorder.js";
import { changedRefs, snapshotWorkspace } from "./filesystem-snapshot.js";
import { prepareWorkspaceReadPath, prepareWorkspaceWritePath, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { deriveDirectPermissionManifest } from "./permissions.js";
import { resolveProviderConfig } from "./provider-config.js";
import { redactText } from "./redaction.js";
import { createMissionForgeTools } from "./tools.js";

export async function runDirectPiWorkerBenchmark(input: DirectRuntimeInput, workspaceRoot: string): Promise<void> {
  const provider = resolveProviderConfig();
  const started = Date.now();
  const toolWorkspaceRoot = prepareWorkspaceWritePath(resolveWorkspaceRef(workspaceRoot, input.workspace_ref), workspaceRoot);
  await mkdir(toolWorkspaceRoot, { recursive: true });
  const before = await snapshotWorkspace(toolWorkspaceRoot);
  const recorder = new DirectEvidenceRecorder(input, workspaceRoot);
  const failures: string[] = [];
  const workerClaims: string[] = [];
  let turnStartCount = 0;
  let cancelled = false;
  let unregisterFaux: (() => void) | undefined;
  let agent: Agent | undefined;

  try {
    const userText = await readFile(
      prepareWorkspaceReadPath(resolveWorkspaceRef(workspaceRoot, input.initial_user_text_ref), workspaceRoot),
      "utf-8",
    );
    const allowedSources = await readAllowedSourceRefs(input, workspaceRoot);
    if (provider.mode === "faux") {
      const faux = registerFauxProvider({
        api: "missionforge-direct-faux",
        provider: "missionforge-direct-faux",
        models: [{ id: "missionforge-direct-faux", name: "MissionForge Direct Faux" }],
      });
      unregisterFaux = faux.unregister;
      provider.model = faux.getModel();
      if (input.expected_output_refs.length === 0) {
        throw new Error("Direct PiWorker benchmark requires at least one expected output");
      }
      faux.setResponses([
        fauxAssistantMessage(
          input.expected_output_refs.map((outputRef, index) =>
            fauxToolCall("write", {
              path: outputRef,
              content: `direct piworker faux artifact for ${input.task_id} output ${index + 1}\n`,
            }),
          ),
          { stopReason: "toolUse" },
        ),
        fauxAssistantMessage(`Completed direct benchmark task ${input.task_id}.`),
      ]);
    }

    agent = new Agent({
      initialState: {
        systemPrompt: buildDirectSystemPrompt(input),
        model: provider.model,
        thinkingLevel: provider.reasoning,
        tools: await createMissionForgeTools({
          workspaceRoot: toolWorkspaceRoot,
          permissionManifest: deriveDirectPermissionManifest(input.task_id, input.expected_output_refs),
          toolTimeoutSeconds: provider.toolTimeoutSeconds,
          knownFileRefs: input.expected_output_refs,
          onToolGatewayDecision: (decision) => recorder.recordToolGatewayDecision(decision),
        }),
      },
      streamFn: streamSimple,
      getApiKey: () => provider.apiKey,
      transformContext: stripUnreplayableResponsesReasoning,
      toolExecution: "parallel",
    });
    agent.subscribe(async (event) => {
      if (event.type === "turn_start") {
        turnStartCount += 1;
        if (turnStartCount > provider.maxTurns) {
          throw new Error(`direct piworker benchmark reached max turns: ${provider.maxTurns}`);
        }
      }
      await recorder.record(event);
      if (
        event.type === "turn_end" &&
        provider.cancelAfterTurns !== null &&
        turnStartCount >= provider.cancelAfterTurns
      ) {
        cancelled = true;
        throw new Error("direct piworker benchmark cancelled at a safe point");
      }
    });
    await agent.prompt(buildDirectUserPrompt(input, userText, allowedSources));
    if (agent.state.errorMessage) {
      failures.push(agent.state.errorMessage);
    }
    workerClaims.push(extractFinalText(agent.state.messages) ?? "");
  } catch (error) {
    failures.push(redactText(error instanceof Error ? error.message : String(error)));
  } finally {
    unregisterFaux?.();
  }

  const durationMs = Date.now() - started;
  await recorder.writeSession(agent?.state.messages ?? []);
  await recorder.writeMetrics(durationMs);
  const changed = await changedRefs(toolWorkspaceRoot, before);
  const producedArtifacts = await existingExpectedOutputs(toolWorkspaceRoot, input.expected_output_refs);
  const missingOutputs = input.expected_output_refs.filter((ref) => !producedArtifacts.includes(ref));
  const status: DirectRuntimeOutput["status"] =
    cancelled ? "cancelled" : failures.length === 0 && missingOutputs.length === 0 ? "completed" : "failed";
  const output = validateDirectRuntimeOutput({
    schema_version: DIRECT_OUTPUT_SCHEMA_VERSION,
    benchmark_run_id: input.benchmark_run_id,
    task_id: input.task_id,
    seed: input.seed,
    status,
    workspace_ref: input.workspace_ref,
    produced_artifacts: producedArtifacts,
    changed_refs: changed,
    failures: [
      ...failures,
      ...missingOutputs.map((ref) => `expected output was not produced: ${ref}`),
    ],
    worker_claims: workerClaims.filter(Boolean).map(summarizeWorkerClaim),
    input_ref: input.input_ref,
    output_ref: input.output_ref,
    session_ref: input.session_ref,
    events_ref: input.events_ref,
    metrics_ref: input.metrics_ref,
    duration_ms: durationMs,
    metrics: recorder.safeMetrics() as unknown as Record<string, unknown>,
  });
  await writeDirectOutput(workspaceRoot, input, output);
}

export function buildDirectSystemPrompt(input: DirectRuntimeInput): string {
  const lines = [
    "You are a direct PiWorker coding agent in a benchmark trial.",
    "Use the available tools inside the current workspace permission manifest to satisfy the user's request.",
    "Write or update the requested output paths relative to the current workspace.",
    "Do not wait for external orchestration or acceptance feedback.",
    `Benchmark run: ${input.benchmark_run_id}`,
    `Task: ${input.task_id}`,
    `Seed: ${input.seed}`,
    `Expected outputs: ${input.expected_output_refs.join(", ")}`,
  ];
  if (input.allowed_source_refs.length) {
    lines.push(`Allowed source refs: ${input.allowed_source_refs.join(", ")}`);
  }
  return lines.join("\n");
}

export interface DirectAllowedSource {
  ref: string;
  content: string;
}

export function buildDirectFailureOutput(
  input: DirectRuntimeInput,
  failure: string,
  durationMs = 0,
): DirectRuntimeOutput {
  return validateDirectRuntimeOutput({
    schema_version: DIRECT_OUTPUT_SCHEMA_VERSION,
    benchmark_run_id: input.benchmark_run_id,
    task_id: input.task_id,
    seed: input.seed,
    status: "failed",
    workspace_ref: input.workspace_ref,
    produced_artifacts: [],
    changed_refs: [],
    failures: [redactText(failure)],
    worker_claims: [],
    input_ref: input.input_ref,
    output_ref: input.output_ref,
    session_ref: input.session_ref,
    events_ref: input.events_ref,
    metrics_ref: input.metrics_ref,
    duration_ms: durationMs,
    metrics: {
      duration_ms: durationMs,
    },
  });
}

export async function writeDirectOutput(
  workspaceRoot: string,
  input: DirectRuntimeInput,
  output: DirectRuntimeOutput,
): Promise<void> {
  await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.output_ref), validateDirectRuntimeOutput(output), {
    workspaceRoot,
  });
}

export async function stripUnreplayableResponsesReasoning(messages: any[]): Promise<any[]> {
  return messages.map((message) => {
    if (message?.role !== "assistant" || !Array.isArray(message.content)) return message;
    if (message.api !== "openai-responses") return message;
    const content = message.content.filter((block: any) => block?.type !== "thinking");
    return { ...message, content };
  });
}

export function buildDirectUserPrompt(
  input: DirectRuntimeInput,
  userText: string,
  allowedSources: DirectAllowedSource[] = [],
): string {
  const lines = [
    "User request:",
    userText.trim(),
    "",
  ];
  if (allowedSources.length) {
    lines.push(
      "Public source refs to inspect before writing:",
      "These refs are worker-visible public task and product requirements. They are not hidden acceptance checks.",
      "",
    );
    for (const source of allowedSources) {
      lines.push(`### ${source.ref}`, source.content.trim() || "(empty)", "");
    }
  }
  lines.push(
    "Output paths to write relative to the current workspace:",
    ...input.expected_output_refs.map((ref) => `- ${ref}`),
    "",
    "Use only permitted tools and refs inside the current workspace, then stop.",
  );
  return lines.join("\n");
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

async function existingExpectedOutputs(root: string, expectedRefs: string[]): Promise<string[]> {
  const result: string[] = [];
  for (const ref of expectedRefs) {
    try {
      if (await fileExists(prepareWorkspaceReadPath(resolveWorkspaceRef(root, ref), root))) {
        result.push(ref);
      }
    } catch {
      continue;
    }
  }
  return result;
}

async function readAllowedSourceRefs(input: DirectRuntimeInput, workspaceRoot: string): Promise<DirectAllowedSource[]> {
  const sources: DirectAllowedSource[] = [];
  for (const ref of input.allowed_source_refs) {
    const content = await readFile(
      prepareWorkspaceReadPath(resolveWorkspaceRef(workspaceRoot, ref), workspaceRoot),
      "utf-8",
    );
    sources.push({ ref, content });
  }
  return sources;
}

async function fileExists(path: string): Promise<boolean> {
  try {
    const { access } = await import("node:fs/promises");
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function summarizeWorkerClaim(value: string): string {
  const text = redactText(value).trim();
  return text ? `assistant_final_text_present:length=${text.length}` : "";
}

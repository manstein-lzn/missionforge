import { Agent } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall, streamSimple } from "@earendil-works/pi-ai";
import { registerFauxProvider } from "@earendil-works/pi-ai";

import type { RuntimeInput } from "./contract.js";
import { EvidenceRecorder } from "./evidence-recorder.js";
import { changedRefs, snapshotWorkspace } from "./filesystem-snapshot.js";
import { resolveProviderConfig } from "./provider-config.js";
import { buildRuntimeOutput, writeRuntimeOutput } from "./result-writer.js";
import { createMissionForgeTools, writeExpectedArtifact } from "./tools.js";

export async function runMissionForgePiAgent(input: RuntimeInput, workspaceRoot: string): Promise<void> {
  const provider = resolveProviderConfig();
  const started = Date.now();
  const before = await snapshotWorkspace(workspaceRoot);
  const recorder = new EvidenceRecorder(input, workspaceRoot);
  const failures: string[] = [];
  const workerClaims: string[] = [];
  let turnStartCount = 0;
  let cancelled = false;
  let compactionWritten = false;
  let unregisterFaux: (() => void) | undefined;

  try {
    if (provider.mode === "faux") {
      const faux = registerFauxProvider({
        api: "missionforge-faux",
        provider: "missionforge-faux",
        models: [{ id: "missionforge-faux", name: "MissionForge Faux" }],
      });
      unregisterFaux = faux.unregister;
      provider.model = faux.getModel();
      const outputs = input.contract.expected_outputs;
      if (outputs.length === 0) throw new Error("Work unit requires at least one expected output");
      faux.setResponses([
        fauxAssistantMessage(
          outputs.map((outputRef, index) =>
            fauxToolCall("write", {
              path: outputRef,
              content: `pi-agent-runtime faux artifact for ${input.work_unit_id} output ${index + 1}\n`,
            }),
          ),
          { stopReason: "toolUse" },
        ),
        fauxAssistantMessage(`Completed ${input.work_unit_id}.`),
      ]);
    }

    const agent = new Agent({
      initialState: {
        systemPrompt: buildSystemPrompt(input),
        model: provider.model,
        thinkingLevel: provider.reasoning,
        tools: createMissionForgeTools({
          workspaceRoot,
          toolTimeoutSeconds: provider.toolTimeoutSeconds,
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
    });
    await agent.prompt(buildUserPrompt(input));
    await recorder.writeSession(agent.state.messages);
    if (agent.state.errorMessage) {
      failures.push(agent.state.errorMessage);
    }
    workerClaims.push(extractFinalText(agent.state.messages) ?? "");
  } catch (error) {
    failures.push(error instanceof Error ? error.message : String(error));
    if (provider.mode === "faux") {
      await fallbackFauxArtifact(input, workspaceRoot, failures);
    }
  } finally {
    unregisterFaux?.();
  }

  const durationMs = Date.now() - started;
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
    "Act as a complete coding agent. Use the available tools freely inside the workspace.",
    "MissionForge owns verification; your completion claims are evidence only.",
    `Work unit: ${input.work_unit_id}`,
    `Mission: ${input.mission_id}`,
    `Objective: ${input.contract.next_objective}`,
    `Expected outputs: ${input.contract.expected_outputs.join(", ")}`,
    `Exit criteria: ${input.contract.exit_criteria.join("; ")}`,
    `Stop conditions: ${input.contract.stop_conditions.join("; ")}`,
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
  }
  return lines.join("\n");
}

function buildUserPrompt(input: RuntimeInput): string {
  if (input.resume.mode === "follow_up") {
    return [
      "Resume this MissionForge work unit from the completed-turn safe point below.",
      input.resume.resume_prompt ?? "Resume from the latest completed turn.",
      `Savepoint ref: ${input.resume.savepoint_ref}`,
      `Session ref: ${input.resume.session_ref}`,
      `Events ref: ${input.resume.events_ref}`,
      `Write or update the expected outputs: ${input.contract.expected_outputs.join(", ")}`,
      "Do not claim completion as acceptance; MissionForge will verify after this attempt.",
      "Use tools freely inside the workspace, then stop.",
    ].join("\n");
  }
  if (input.repair.mode === "follow_up") {
    return [
      "Repair this MissionForge work unit using the verifier feedback below.",
      input.repair.repair_prompt ?? "Repair the expected outputs.",
      `Verifier failures: ${input.repair.verifier_failures.join("; ") || "<none>"}`,
      `Failed constraints: ${input.repair.failed_constraints.join(", ") || "<none>"}`,
      `Previous output ref: ${input.repair.previous_output_ref}`,
      `Write or update the expected outputs: ${input.contract.expected_outputs.join(", ")}`,
      "Use tools freely inside the workspace, then stop.",
    ].join("\n");
  }
  return [
    "Complete this MissionForge work unit.",
    `Write or update the expected outputs: ${input.contract.expected_outputs.join(", ")}`,
    "Use tools to inspect, edit, run commands, and verify as needed.",
  ].join("\n");
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
  const firstOutput = input.contract.expected_outputs[0];
  if (!firstOutput) return;
  try {
    await writeExpectedArtifact(
      workspaceRoot,
      firstOutput,
      `pi-agent-runtime fallback faux artifact for ${input.work_unit_id}\n`,
    );
  } catch (error) {
    failures.push(error instanceof Error ? error.message : String(error));
  }
}

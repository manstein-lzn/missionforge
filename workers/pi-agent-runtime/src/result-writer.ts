import { access } from "node:fs/promises";

import type { RuntimeInput, RuntimeOutput } from "./contract.js";
import { OUTPUT_SCHEMA_VERSION, validateOutput } from "./contract.js";
import { resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { redactText } from "./redaction.js";

export interface BuildOutputOptions {
  input: RuntimeInput;
  workspaceRoot: string;
  changedRefs: string[];
  commandsRun: string[];
  testsRun: string[];
  failures: string[];
  workerClaims?: string[];
  durationMs: number;
  metrics: Record<string, unknown>;
  statusOverride?: RuntimeOutput["status"];
  recommendedNextSteps?: string[];
}

export async function buildRuntimeOutput(options: BuildOutputOptions): Promise<RuntimeOutput> {
  const producedArtifacts: string[] = [];
  const missingOutputs: string[] = [];
  for (const ref of options.input.contract.expected_outputs) {
    if (await fileExists(resolveWorkspaceRef(options.workspaceRoot, ref))) {
      producedArtifacts.push(ref);
    } else {
      missingOutputs.push(ref);
    }
  }

  const failures =
    options.statusOverride === "cancelled"
      ? [...options.failures]
      : [...options.failures, ...missingOutputs.map((ref) => `expected output was not produced: ${ref}`)];
  const status: RuntimeOutput["status"] = options.statusOverride ?? (failures.length === 0 ? "completed" : "failed");
  const output: RuntimeOutput = {
    schema_version: OUTPUT_SCHEMA_VERSION,
    work_unit_id: options.input.work_unit_id,
    status,
    produced_artifacts: producedArtifacts,
    changed_refs: dedupe([
      ...options.changedRefs,
      options.input.output_ref,
      options.input.session_ref,
      options.input.events_ref,
      options.input.metrics_ref,
      options.input.savepoints_ref,
    ]),
    commands_run: options.commandsRun.map((item) => redactText(item)),
    tests_run: options.testsRun.map((item) => redactText(item)),
    failures: failures.map((item) => redactText(item)),
    worker_claims: (options.workerClaims ?? []).map((item) => redactText(item)),
    verifier_evidence: [
      options.input.output_ref,
      options.input.events_ref,
      options.input.metrics_ref,
      options.input.savepoints_ref,
    ],
    new_unknowns: status === "completed" ? [] : missingOutputs,
    recommended_next_steps:
      options.recommendedNextSteps ?? (status === "completed" ? [] : ["Inspect pi-agent-runtime artifacts before retrying."]),
    verification_status: status === "completed" ? "not_run" : "failed",
    input_ref: options.input.input_ref,
    output_ref: options.input.output_ref,
    session_ref: options.input.session_ref,
    events_ref: options.input.events_ref,
    metrics_ref: options.input.metrics_ref,
    savepoints_ref: options.input.savepoints_ref,
    duration_ms: options.durationMs,
    metrics: options.metrics,
  };
  return validateOutput(output);
}

export async function writeRuntimeOutput(
  workspaceRoot: string,
  input: RuntimeInput,
  output: RuntimeOutput,
): Promise<void> {
  await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.output_ref), output);
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

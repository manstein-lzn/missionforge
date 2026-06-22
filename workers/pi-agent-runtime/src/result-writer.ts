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
  const changedRefs = options.changedRefs.filter((ref) => !isContextRawRef(options.input, ref));
  const changed = new Set(changedRefs);
  const producedArtifacts: string[] = [];
  const missingOutputs: string[] = [];
  const produced = new Set<string>();
  for (const ref of options.input.call_spec.expected_outputs) {
    if (changed.has(ref) && await fileExists(resolveWorkspaceRef(options.workspaceRoot, ref))) {
      producedArtifacts.push(ref);
      produced.add(ref);
    } else {
      missingOutputs.push(ref);
    }
  }
  for (const ref of changedRefs) {
    if (produced.has(ref)) continue;
    if (!options.input.call_spec.allowed_scope.includes(ref)) continue;
    if (!(await fileExists(resolveWorkspaceRef(options.workspaceRoot, ref)))) continue;
    producedArtifacts.push(ref);
    produced.add(ref);
  }

  const failures =
    options.statusOverride === "cancelled"
      ? [...options.failures]
      : [...options.failures, ...missingOutputs.map((ref) => `expected output was not produced: ${ref}`)];
  const status: RuntimeOutput["status"] = options.statusOverride ?? (failures.length === 0 ? "completed" : "failed");
  const verificationStatus: RuntimeOutput["verification_status"] =
    status === "completed" && failures.length === 0 ? "not_run" : "failed";
  const output: RuntimeOutput = {
    schema_version: OUTPUT_SCHEMA_VERSION,
    call_id: options.input.call_id,
    status,
    produced_artifacts: producedArtifacts,
    changed_refs: dedupe([
      ...changedRefs,
      options.input.output_ref,
      options.input.session_ref,
      options.input.events_ref,
      options.input.metrics_ref,
      options.input.savepoints_ref,
      options.input.context_observations_ref,
      options.input.context_projection_ref,
    ]),
    commands_run: options.commandsRun.map((item) => redactText(item)),
    tests_run: options.testsRun.map((item) => redactText(item)),
    failures: failures.map((item) => redactText(item)),
    worker_claims: (options.workerClaims ?? []).map(summarizeWorkerClaim),
    verifier_evidence: [
      options.input.output_ref,
      options.input.events_ref,
      options.input.metrics_ref,
      options.input.savepoints_ref,
      options.input.context_observations_ref,
      options.input.context_projection_ref,
    ],
    new_unknowns: status === "completed" ? [] : missingOutputs,
    recommended_next_steps:
      options.recommendedNextSteps ?? (status === "completed" ? [] : ["Inspect pi-agent-runtime artifacts before retrying."]),
    verification_status: verificationStatus,
    input_ref: options.input.input_ref,
    output_ref: options.input.output_ref,
    session_ref: options.input.session_ref,
    events_ref: options.input.events_ref,
    metrics_ref: options.input.metrics_ref,
    savepoints_ref: options.input.savepoints_ref,
    context_observations_ref: options.input.context_observations_ref,
    context_projection_ref: options.input.context_projection_ref,
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
  await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.output_ref), output, { workspaceRoot });
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

function isContextRawRef(input: RuntimeInput, ref: string): boolean {
  const rawDir = input.context_raw_dir_ref.replace(/\/+$/, "");
  return ref === rawDir || ref.startsWith(`${rawDir}/`);
}

function summarizeWorkerClaim(value: string): string {
  const text = redactText(value).trim();
  return text ? `assistant_final_text_present:length=${text.length}` : "";
}

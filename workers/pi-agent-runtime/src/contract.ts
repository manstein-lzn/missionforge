export const INPUT_SCHEMA_VERSION = "missionforge.pi_agent_runtime_input.v1";
export const OUTPUT_SCHEMA_VERSION = "missionforge.pi_agent_runtime_output.v1";

export type JsonObject = Record<string, unknown>;

export interface WorkUnitContract {
  work_unit_id: string;
  mission_id: string;
  iteration: number;
  next_objective: string;
  allowed_scope: string[];
  visible_refs: string[];
  expected_outputs: string[];
  exit_criteria: string[];
  stop_conditions: string[];
}

export interface RuntimeInput {
  schema_version: typeof INPUT_SCHEMA_VERSION;
  work_unit_id: string;
  mission_id: string;
  iteration: number;
  workspace_root: string;
  attempt_dir_ref: string;
  input_ref: string;
  output_ref: string;
  session_ref: string;
  events_ref: string;
  metrics_ref: string;
  savepoints_ref: string;
  contract: WorkUnitContract;
  runtime: {
    runtime_name: string;
    timeout_seconds: number;
    model?: string | null;
    metadata?: JsonObject;
  };
  repair: RepairInput;
  resume: ResumeInput;
}

export interface RepairInput {
  mode: "none" | "follow_up";
  verifier_failures: string[];
  failed_constraints: string[];
  previous_output_ref: string | null;
  repair_prompt: string | null;
}

export interface ResumeInput {
  mode: "none" | "follow_up";
  boundary: "after_completed_turn" | null;
  savepoint_ref: string | null;
  session_ref: string | null;
  events_ref: string | null;
  resume_prompt: string | null;
}

export interface RuntimeOutput {
  schema_version: typeof OUTPUT_SCHEMA_VERSION;
  work_unit_id: string;
  status: "completed" | "failed" | "blocked" | "cancelled";
  produced_artifacts: string[];
  changed_refs: string[];
  commands_run: string[];
  tests_run: string[];
  failures: string[];
  worker_claims: string[];
  verifier_evidence: string[];
  new_unknowns: string[];
  recommended_next_steps: string[];
  verification_status: "passed" | "failed" | "not_run" | "review_required";
  input_ref: string;
  output_ref: string;
  session_ref: string;
  events_ref: string;
  metrics_ref: string;
  savepoints_ref: string;
  duration_ms: number;
  metrics: JsonObject;
}

export function parseRuntimeInput(value: unknown): RuntimeInput {
  const data = requireObject(value, "input");
  const schemaVersion = requireString(data.schema_version, "schema_version");
  if (schemaVersion !== INPUT_SCHEMA_VERSION) {
    throw new Error(`Unsupported schema_version: ${schemaVersion}`);
  }

  const contract = parseWorkUnitContract(data.contract);
  const result: RuntimeInput = {
    schema_version: INPUT_SCHEMA_VERSION,
    work_unit_id: requireString(data.work_unit_id, "work_unit_id"),
    mission_id: requireString(data.mission_id, "mission_id"),
    iteration: requirePositiveInteger(data.iteration, "iteration"),
    workspace_root: requireString(data.workspace_root, "workspace_root"),
    attempt_dir_ref: requireRef(data.attempt_dir_ref, "attempt_dir_ref"),
    input_ref: requireRef(data.input_ref, "input_ref"),
    output_ref: requireRef(data.output_ref, "output_ref"),
    session_ref: requireRef(data.session_ref, "session_ref"),
    events_ref: requireRef(data.events_ref, "events_ref"),
    metrics_ref: requireRef(data.metrics_ref, "metrics_ref"),
    savepoints_ref: requireRef(data.savepoints_ref, "savepoints_ref"),
    contract,
    runtime: parseRuntime(data.runtime),
    repair: parseRepair(data.repair),
    resume: parseResume(data.resume),
  };

  if (result.work_unit_id !== contract.work_unit_id) {
    throw new Error("input.work_unit_id must match contract.work_unit_id");
  }
  if (result.mission_id !== contract.mission_id) {
    throw new Error("input.mission_id must match contract.mission_id");
  }
  return result;
}

function parseResume(value: unknown): ResumeInput {
  if (value === undefined || value === null) {
    return {
      mode: "none",
      boundary: null,
      savepoint_ref: null,
      session_ref: null,
      events_ref: null,
      resume_prompt: null,
    };
  }
  const data = requireObject(value, "resume");
  const mode = requireString(data.mode ?? "none", "resume.mode");
  if (mode !== "none" && mode !== "follow_up") {
    throw new Error("resume.mode must be none or follow_up");
  }
  const boundary =
    data.boundary === undefined || data.boundary === null
      ? null
      : requireString(data.boundary, "resume.boundary");
  if (boundary !== null && boundary !== "after_completed_turn") {
    throw new Error("resume.boundary must be after_completed_turn");
  }
  const savepointRef =
    data.savepoint_ref === undefined || data.savepoint_ref === null
      ? null
      : requireRef(data.savepoint_ref, "resume.savepoint_ref");
  const sessionRef =
    data.session_ref === undefined || data.session_ref === null
      ? null
      : requireRef(data.session_ref, "resume.session_ref");
  const eventsRef =
    data.events_ref === undefined || data.events_ref === null
      ? null
      : requireRef(data.events_ref, "resume.events_ref");
  const resumePrompt =
    data.resume_prompt === undefined || data.resume_prompt === null
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
    resume_prompt: resumePrompt,
  };
}

export function validateOutput(output: RuntimeOutput): RuntimeOutput {
  if (output.schema_version !== OUTPUT_SCHEMA_VERSION) {
    throw new Error("Unsupported output schema_version");
  }
  requireString(output.work_unit_id, "output.work_unit_id");
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
  ] as const) {
    for (const ref of output[field]) requireRef(ref, `output.${field}[]`);
  }
  for (const field of ["input_ref", "output_ref", "session_ref", "events_ref", "metrics_ref", "savepoints_ref"] as const) {
    requireRef(output[field], `output.${field}`);
  }
  requireNonNegativeInteger(output.duration_ms, "output.duration_ms");
  return output;
}

export function requireRef(value: unknown, field: string): string {
  const ref = requireString(value, field);
  if (ref.startsWith("/") || ref.includes("\0") || ref.split(/[\\/]+/).includes("..")) {
    throw new Error(`${field} must be a workspace-relative ref`);
  }
  return ref;
}

function parseWorkUnitContract(value: unknown): WorkUnitContract {
  const data = requireObject(value, "contract");
  return {
    work_unit_id: requireString(data.work_unit_id, "contract.work_unit_id"),
    mission_id: requireString(data.mission_id, "contract.mission_id"),
    iteration: requirePositiveInteger(data.iteration, "contract.iteration"),
    next_objective: requireString(data.next_objective, "contract.next_objective"),
    allowed_scope: requireRefList(data.allowed_scope, "contract.allowed_scope"),
    visible_refs: requireRefList(data.visible_refs, "contract.visible_refs"),
    expected_outputs: requireRefList(data.expected_outputs, "contract.expected_outputs"),
    exit_criteria: requireStringList(data.exit_criteria, "contract.exit_criteria"),
    stop_conditions: requireStringList(data.stop_conditions, "contract.stop_conditions"),
  };
}

function parseRuntime(value: unknown): RuntimeInput["runtime"] {
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

function parseRepair(value: unknown): RepairInput {
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
  const previousOutputRef =
    data.previous_output_ref === undefined || data.previous_output_ref === null
      ? null
      : requireRef(data.previous_output_ref, "repair.previous_output_ref");
  const repairPrompt =
    data.repair_prompt === undefined || data.repair_prompt === null
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

function requireRefList(value: unknown, field: string): string[] {
  return requireArray(value, field).map((item, index) => requireRef(item, `${field}[${index}]`));
}

function requireStringList(value: unknown, field: string): string[] {
  return requireArray(value ?? [], field).map((item, index) => requireString(item, `${field}[${index}]`));
}

function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  return value;
}

function requireObject(value: unknown, field: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as JsonObject;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

function requirePositiveInteger(value: unknown, field: string): number {
  const number = requireNonNegativeInteger(value, field);
  if (number < 1) throw new Error(`${field} must be at least 1`);
  return number;
}

function requireNonNegativeInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || typeof value !== "number" || value < 0) {
    throw new Error(`${field} must be a non-negative integer`);
  }
  return value;
}

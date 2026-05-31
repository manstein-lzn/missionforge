import type { AgentEvent, AgentMessage } from "@earendil-works/pi-agent-core";
import type { ToolResultMessage } from "@earendil-works/pi-ai";

import type { DirectRuntimeInput } from "./direct-contract.js";
import { appendJsonLine, prepareWorkspaceWritePath, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { redactText } from "./redaction.js";

export interface DirectRuntimeMetrics {
  turn_count: number;
  tool_call_count: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  input_cost_usd: number;
  output_cost_usd: number;
  cache_read_cost_usd: number;
  cache_write_cost_usd: number;
  provider_reported_cost_usd: number;
  tool_error_count: number;
  tool_latency_ms_total: number;
  tool_latency_ms_by_name: Record<string, number>;
  command_count: number;
  test_command_count: number;
  command_failure_count: number;
  time_to_first_tool_ms: number;
  time_to_first_artifact_ms: number;
  commands_run: string[];
  tests_run: string[];
  stop_reason?: string;
}

export class DirectEvidenceRecorder {
  private sequence = 0;
  private readonly startedAtMs = Date.now();
  private readonly toolStarts = new Map<string, { toolName: string; startedAtMs: number }>();
  private hasRecordedFirstTool = false;
  private hasRecordedFirstArtifact = false;
  readonly metrics: DirectRuntimeMetrics = {
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

  constructor(
    private readonly input: DirectRuntimeInput,
    private readonly workspaceRoot: string,
    private readonly env: NodeJS.ProcessEnv = process.env,
  ) {}

  async record(event: AgentEvent): Promise<void> {
    this.updateMetrics(event);
    await appendJsonLine(
      resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref),
      {
        schema_version: "missionforge.pi_agent_direct_event.v1",
        event_id: `pi-agent-direct-event-${String(++this.sequence).padStart(6, "0")}`,
        created_at: new Date().toISOString(),
        benchmark_run_id: this.input.benchmark_run_id,
        task_id: this.input.task_id,
        seed: this.input.seed,
        event_type: event.type,
        payload: summarizeEvent(event, this.env),
      },
      { workspaceRoot: this.workspaceRoot },
    );
    if (event.type === "tool_execution_end" || event.type === "turn_end") {
      await this.recordFirstArtifactIfPresent();
    }
  }

  async writeSession(messages: AgentMessage[]): Promise<void> {
    const lines = messages.map((message, index) =>
      JSON.stringify({
        schema_version: "missionforge.pi_agent_direct_session_entry.v1",
        index,
        message: summarizeMessage(message),
      }),
    );
    await writeText(
      resolveWorkspaceRef(this.workspaceRoot, this.input.session_ref),
      `${lines.join("\n")}${lines.length ? "\n" : ""}`,
      this.workspaceRoot,
    );
  }

  async writeMetrics(durationMs: number): Promise<void> {
    await this.recordFirstArtifactIfPresent();
    await writeJsonFile(
      resolveWorkspaceRef(this.workspaceRoot, this.input.metrics_ref),
      {
        schema_version: "missionforge.pi_agent_direct_metrics.v1",
        benchmark_run_id: this.input.benchmark_run_id,
        task_id: this.input.task_id,
        seed: this.input.seed,
        duration_ms: durationMs,
        ...this.safeMetrics(),
      },
      { workspaceRoot: this.workspaceRoot },
    );
  }

  safeMetrics(): DirectRuntimeMetrics {
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

  private updateMetrics(event: AgentEvent): void {
    if (event.type === "turn_start") this.metrics.turn_count += 1;
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
        if (event.toolName === "bash") this.metrics.command_failure_count += 1;
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

  private async recordFirstArtifactIfPresent(): Promise<void> {
    if (this.hasRecordedFirstArtifact) return;
    for (const ref of this.input.expected_output_refs) {
      if (await fileExists(resolveWorkspaceRef(this.workspaceRoot, joinRef(this.input.workspace_ref, ref)))) {
        this.hasRecordedFirstArtifact = true;
        this.metrics.time_to_first_artifact_ms = elapsedMs(this.startedAtMs);
        return;
      }
    }
  }
}

function summarizeEvent(event: AgentEvent, env: NodeJS.ProcessEnv): unknown {
  switch (event.type) {
    case "message_start":
    case "message_update":
    case "message_end":
      return { type: event.type, message: summarizeMessage(event.message) };
    case "tool_execution_start":
      return {
        type: event.type,
        toolCallId: event.toolCallId,
        toolName: event.toolName,
        args: summarizeToolArgs(event.args, env),
      };
    case "tool_execution_end":
      return summarizeToolResult(event as unknown as ToolResultMessage);
    case "turn_end":
      return {
        type: event.type,
        message: summarizeMessage(event.message),
        toolResults: event.toolResults.map(summarizeToolResult),
      };
    default:
      return { type: (event as { type?: string }).type ?? "unknown" };
  }
}

function summarizeMessage(message: AgentMessage): unknown {
  const item = message as any;
  return {
    role: item.role,
    stopReason: item.role === "assistant" ? item.stopReason : undefined,
    usage: item.role === "assistant" ? summarizeUsage(item.usage) : undefined,
    content_summary: summarizeContent(item.content),
  };
}

function summarizeToolResult(message: ToolResultMessage): unknown {
  const item = message as any;
  return {
    role: item.role,
    toolCallId: item.toolCallId,
    toolName: item.toolName,
    isError: item.isError,
    content_summary: summarizeContent(item.content),
  };
}

function summarizeUsage(usage: any): unknown {
  if (!usage || typeof usage !== "object") return undefined;
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

function summarizeContent(content: unknown): unknown[] {
  if (!Array.isArray(content)) return [];
  return content.map((block) => {
    if (!block || typeof block !== "object") return { type: typeof block };
    const item = block as Record<string, unknown>;
    const type = typeof item.type === "string" ? item.type : "unknown";
    if (type === "toolUse") {
      return {
        type,
        id: typeof item.id === "string" ? item.id : undefined,
        name: typeof item.name === "string" ? item.name : undefined,
        input_keys: item.input && typeof item.input === "object" && !Array.isArray(item.input)
          ? Object.keys(item.input as Record<string, unknown>).sort()
          : [],
      };
    }
    return {
      type,
      text_char_count: typeof item.text === "string" ? item.text.length : undefined,
      thinking_char_count: typeof item.thinking === "string" ? item.thinking.length : undefined,
    };
  });
}

function summarizeToolArgs(args: unknown, env: NodeJS.ProcessEnv): unknown {
  if (!args || typeof args !== "object" || Array.isArray(args)) return {};
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(args)) {
    if (key === "command" && typeof value === "string") {
      result[key] = redactText(value, env);
    } else if (typeof value === "string" && /^(path|file|cwd|pattern|glob)$/i.test(key)) {
      result[key] = redactText(value, env);
    } else {
      result[key] = summarizeArgumentValue(value);
    }
  }
  return result;
}

function summarizeArgumentValue(value: unknown): unknown {
  if (typeof value === "string") return { string_char_count: value.length };
  if (Array.isArray(value)) return { array_length: value.length };
  if (value && typeof value === "object") return { keys: Object.keys(value as Record<string, unknown>).sort() };
  if (typeof value === "number" || typeof value === "boolean") return value;
  return null;
}

function elapsedMs(startedAtMs: number): number {
  return Math.max(0, Date.now() - startedAtMs);
}

function safeNumericRecord(values: Record<string, number>): Record<string, number> {
  const result: Record<string, number> = {};
  for (const [key, value] of Object.entries(values)) {
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      result[key] = value;
    }
  }
  return result;
}

function nonNegativeNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

function looksLikeTestCommand(command: string): boolean {
  return /\b(pytest|unittest|npm test|vitest|make test|go test|cargo test)\b/.test(command);
}

function joinRef(prefix: string, ref: string): string {
  return prefix ? `${prefix.replace(/\/+$/, "")}/${ref.replace(/^\/+/, "")}` : ref;
}

async function writeText(path: string, text: string, workspaceRoot: string): Promise<void> {
  const { mkdir, writeFile } = await import("node:fs/promises");
  const { dirname } = await import("node:path");
  const safePath = prepareWorkspaceWritePath(path, workspaceRoot);
  await mkdir(dirname(safePath), { recursive: true });
  await writeFile(safePath, text, "utf-8");
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

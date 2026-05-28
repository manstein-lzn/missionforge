import type { AgentEvent, AgentMessage } from "@earendil-works/pi-agent-core";
import type { ToolResultMessage } from "@earendil-works/pi-ai";

import type { RuntimeInput } from "./contract.js";
import { appendJsonLine, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { redactJson } from "./redaction.js";

export interface RuntimeMetrics {
  turn_count: number;
  tool_call_count: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  commands_run: string[];
  tests_run: string[];
  stop_reason?: string;
}

export class EvidenceRecorder {
  private sequence = 0;
  readonly metrics: RuntimeMetrics = {
    turn_count: 0,
    tool_call_count: 0,
    total_tokens: 0,
    input_tokens: 0,
    output_tokens: 0,
    commands_run: [],
    tests_run: [],
  };

  constructor(
    private readonly input: RuntimeInput,
    private readonly workspaceRoot: string,
    private readonly env: NodeJS.ProcessEnv = process.env,
  ) {}

  async record(event: AgentEvent): Promise<void> {
    this.updateMetrics(event);
    await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref), {
      schema_version: "missionforge.pi_agent_runtime_event.v1",
      event_id: `pi-agent-event-${String(++this.sequence).padStart(6, "0")}`,
      created_at: new Date().toISOString(),
      work_unit_id: this.input.work_unit_id,
      event_type: event.type,
      payload: redactJson(summarizeEvent(event), this.env),
    });
    if (event.type === "turn_end") {
      await this.writeSavepoint(event);
    }
  }

  async writeSession(messages: AgentMessage[]): Promise<void> {
    const path = resolveWorkspaceRef(this.workspaceRoot, this.input.session_ref);
    const lines = messages.map((message, index) =>
      JSON.stringify({
        schema_version: "missionforge.pi_agent_runtime_session_entry.v1",
        index,
        message: redactJson(summarizeMessage(message), this.env),
      }),
    );
    await writeText(path, `${lines.join("\n")}${lines.length ? "\n" : ""}`);
  }

  async writeMetrics(durationMs: number): Promise<void> {
    await writeJsonFile(resolveWorkspaceRef(this.workspaceRoot, this.input.metrics_ref), {
      schema_version: "missionforge.pi_agent_runtime_metrics.v1",
      work_unit_id: this.input.work_unit_id,
      duration_ms: durationMs,
      ...this.metrics,
    });
  }

  async writeCompactionMarker(reason: string): Promise<void> {
    await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.events_ref), {
      schema_version: "missionforge.pi_agent_runtime_event.v1",
      event_id: `pi-agent-event-${String(++this.sequence).padStart(6, "0")}`,
      created_at: new Date().toISOString(),
      work_unit_id: this.input.work_unit_id,
      event_type: "compaction",
      payload: redactJson({
        reason,
        turn_index: this.metrics.turn_count,
        savepoints_ref: this.input.savepoints_ref,
        resume_boundary: "after_completed_turn",
      }, this.env),
    });
    await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.savepoints_ref), redactJson({
      schema_version: "missionforge.pi_agent_runtime_savepoint.v1",
      work_unit_id: this.input.work_unit_id,
      turn_index: this.metrics.turn_count,
      created_at: new Date().toISOString(),
      message_ref: `${this.input.session_ref}#compact`,
      events_ref: this.input.events_ref,
      changed_refs: [],
      tool_call_count: this.metrics.tool_call_count,
      commands_run: this.metrics.commands_run.slice(),
      stop_reason: "compacted",
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
      compaction: {
        applied: true,
        reason,
      },
    }, this.env));
  }

  private updateMetrics(event: AgentEvent): void {
    if (event.type === "turn_start") this.metrics.turn_count += 1;
    if (event.type === "tool_execution_start") {
      this.metrics.tool_call_count += 1;
      if (event.toolName === "bash") {
        const command = typeof event.args?.command === "string" ? event.args.command : "";
        if (command) {
          this.metrics.commands_run.push(command);
          if (looksLikeTestCommand(command)) this.metrics.tests_run.push(command);
        }
      }
    }
    if (event.type === "message_end" && event.message.role === "assistant") {
      const usage = event.message.usage;
      this.metrics.input_tokens += usage?.input ?? 0;
      this.metrics.output_tokens += usage?.output ?? 0;
      this.metrics.total_tokens += usage?.totalTokens ?? 0;
      this.metrics.stop_reason = event.message.stopReason;
    }
  }

  private async writeSavepoint(event: Extract<AgentEvent, { type: "turn_end" }>): Promise<void> {
    await appendJsonLine(resolveWorkspaceRef(this.workspaceRoot, this.input.savepoints_ref), redactJson({
      schema_version: "missionforge.pi_agent_runtime_savepoint.v1",
      work_unit_id: this.input.work_unit_id,
      turn_index: this.metrics.turn_count,
      created_at: new Date().toISOString(),
      message_ref: `${this.input.session_ref}#turn=${this.metrics.turn_count}`,
      events_ref: this.input.events_ref,
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
    }, this.env));
  }
}

function summarizeEvent(event: AgentEvent): unknown {
  switch (event.type) {
    case "message_start":
    case "message_update":
    case "message_end":
      return { ...event, message: summarizeMessage(event.message) };
    case "turn_end":
      return {
        type: event.type,
        message: summarizeMessage(event.message),
        toolResults: event.toolResults.map(summarizeToolResult),
      };
    default:
      return event;
  }
}

function summarizeToolResult(message: ToolResultMessage): unknown {
  return {
    role: message.role,
    toolCallId: message.toolCallId,
    toolName: message.toolName,
    isError: message.isError,
    content: message.content.map((block) => (block.type === "text" ? { ...block, text: truncate(block.text) } : block)),
  };
}

function summarizeMessage(message: AgentMessage): unknown {
  if (message.role !== "assistant") return message;
  return {
    ...message,
    content: message.content.map((block) => {
      if (block.type === "text") return { ...block, text: truncate(block.text) };
      if (block.type === "thinking") return { ...block, thinking: truncate(block.thinking) };
      return block;
    }),
  };
}

function truncate(value: string, limit = 4000): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}\n[truncated]`;
}

function looksLikeTestCommand(command: string): boolean {
  return /\b(pytest|unittest|npm test|vitest|make test|go test|cargo test)\b/.test(command);
}

async function writeText(path: string, text: string): Promise<void> {
  const { mkdir, writeFile } = await import("node:fs/promises");
  const { dirname } = await import("node:path");
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, text, "utf-8");
}

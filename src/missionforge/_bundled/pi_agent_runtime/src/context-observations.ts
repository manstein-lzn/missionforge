import { createHash } from "node:crypto";
import { access, copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, relative, resolve } from "node:path";

import type { AfterToolCallContext } from "@earendil-works/pi-agent-core";

import type { RuntimeInput } from "./contract.js";
import { appendJsonLine, prepareWorkspaceReadPath, resolveWorkspaceRef } from "./paths.js";
import { absolutePathToWorkspaceRef, ToolPermissionEnforcer } from "./permissions.js";

export const TOOL_OBSERVATION_SCHEMA_VERSION = "missionforge.pi_agent_tool_observation.v1";

export type ToolObservationInlinePolicy = "keep" | "demote_after_turn" | "ref_only";
export type ToolObservationStatus = "ok" | "error";

export interface SourceRange {
  offset?: number;
  limit?: number;
}

export interface ToolObservation {
  schema_version: typeof TOOL_OBSERVATION_SCHEMA_VERSION;
  observation_id: string;
  call_id: string;
  turn_index: number;
  tool_call_id: string;
  tool_name: string;
  status: ToolObservationStatus;
  created_at: string;
  content_hash: string;
  content_bytes: number;
  content_lines: number;
  inline_policy: ToolObservationInlinePolicy;
  raw_ref?: string;
  source_ref?: string;
  source_range?: SourceRange;
  source_hash?: string;
  source_bytes?: number;
}

export interface ToolObservationRecorderOptions {
  input: RuntimeInput;
  workspaceRoot: string;
  env?: NodeJS.ProcessEnv;
}

export class ToolObservationRecorder {
  private sequence = 0;
  private turnIndex = 0;
  private readonly observations: ToolObservation[] = [];
  private readonly workspaceRoot: string;
  private readonly input: RuntimeInput;
  private readonly env: NodeJS.ProcessEnv;

  constructor(options: ToolObservationRecorderOptions) {
    this.input = options.input;
    this.workspaceRoot = options.workspaceRoot;
    this.env = options.env ?? process.env;
  }

  noteTurnStart(): void {
    this.turnIndex += 1;
  }

  list(): ToolObservation[] {
    return this.observations.map((observation) => ({ ...observation }));
  }

  async recordAfterToolCall(context: AfterToolCallContext): Promise<void> {
    const text = extractText(context.result.content);
    const stats = textStats(text);
    const largeObservationBytes = this.input.context_projection_config.large_observation_bytes;
    const observation: ToolObservation = {
      schema_version: TOOL_OBSERVATION_SCHEMA_VERSION,
      observation_id: `tool-observation-${String(++this.sequence).padStart(6, "0")}`,
      call_id: this.input.call_id,
      turn_index: this.turnIndex,
      tool_call_id: context.toolCall.id,
      tool_name: context.toolCall.name,
      status: context.isError ? "error" : "ok",
      created_at: new Date().toISOString(),
      content_hash: hashText(text),
      content_bytes: stats.bytes,
      content_lines: stats.lines,
      inline_policy: inlinePolicy(context.toolCall.name, stats.bytes, context.isError, largeObservationBytes),
    };

    if (context.toolCall.name === "bash") {
      const raw = await this.writeBashRawRef(context, text, stats.bytes, largeObservationBytes);
      if (raw) {
        observation.raw_ref = raw.raw_ref;
        observation.content_hash = raw.content_hash;
        observation.content_bytes = raw.content_bytes;
        observation.content_lines = raw.content_lines;
      }
    }

    if (context.toolCall.name === "read") {
      const source = await this.readSourceMetadata(context);
      if (source) {
        observation.source_ref = source.source_ref;
        observation.source_range = source.source_range;
        observation.source_hash = source.source_hash;
        observation.source_bytes = source.source_bytes;
      } else if (stats.bytes >= largeObservationBytes) {
        observation.raw_ref = await this.writeRawText(context.toolCall.id, "read", text);
      }
    }

    this.observations.push(observation);
    await appendJsonLine(
      resolveWorkspaceRef(this.workspaceRoot, this.input.context_observations_ref),
      observation,
      { workspaceRoot: this.workspaceRoot },
    );
  }

  async ensureIndex(): Promise<void> {
    const path = resolveWorkspaceRef(this.workspaceRoot, this.input.context_observations_ref);
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, "", { encoding: "utf-8", flag: "a" });
  }

  async eventPayloadFor(toolCallId: string): Promise<Record<string, unknown> | undefined> {
    const observation = this.observations.find((item) => item.tool_call_id === toolCallId);
    if (!observation) return undefined;
    return {
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
    };
  }

  private async writeBashRawRef(
    context: AfterToolCallContext,
    text: string,
    contentBytes: number,
    largeObservationBytes: number,
  ): Promise<RawCapture | undefined> {
    const fullOutputPath = detailString(context.result.details, "fullOutputPath");
    if (fullOutputPath) {
      try {
        const safeFullOutputPath = resolvePiBashTempPath(fullOutputPath);
        await access(safeFullOutputPath);
        const rawRef = this.rawRef(context.toolCall.id, "bash", basename(safeFullOutputPath) || "output.log");
        const target = resolveWorkspaceRef(this.workspaceRoot, rawRef);
        await mkdir(dirname(target), { recursive: true });
        await copyFile(safeFullOutputPath, target);
        return await rawCapture(rawRef, target);
      } catch {
        // Fall through to text capture when the Pi temp file is unavailable or unsafe.
      }
    }
    if (contentBytes < largeObservationBytes) return undefined;
    const rawRef = await this.writeRawText(context.toolCall.id, "bash", text);
    return rawCapture(rawRef, resolveWorkspaceRef(this.workspaceRoot, rawRef));
  }

  private async writeRawText(toolCallId: string, toolName: string, text: string): Promise<string> {
    const rawRef = this.rawRef(toolCallId, toolName, "output.txt");
    const target = resolveWorkspaceRef(this.workspaceRoot, rawRef);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, text, "utf-8");
    return rawRef;
  }

  private rawRef(toolCallId: string, toolName: string, filename: string): string {
    const safeToolCallId = toolCallId.replace(/[^a-zA-Z0-9_.-]/g, "_");
    const safeToolName = toolName.replace(/[^a-zA-Z0-9_.-]/g, "_");
    const safeFilename = filename.replace(/[^a-zA-Z0-9_.-]/g, "_") || "output.txt";
    return `${this.input.context_raw_dir_ref}/${String(this.sequence).padStart(6, "0")}-${safeToolName}-${safeToolCallId}-${safeFilename}`;
  }

  private async readSourceMetadata(context: AfterToolCallContext): Promise<{
    source_ref: string;
    source_range: SourceRange;
    source_hash: string;
    source_bytes: number;
  } | undefined> {
    if (!context.args || typeof context.args !== "object" || Array.isArray(context.args)) return undefined;
    const path = (context.args as Record<string, unknown>).path;
    if (typeof path !== "string" || path.length === 0) return undefined;
    try {
      const absolutePath = resolve(this.workspaceRoot, path);
      const safePath = new ToolPermissionEnforcer(this.workspaceRoot, this.input.permission_manifest).ensureReadPath(
        absolutePath,
      );
      const sourceRef = absolutePathToWorkspaceRef(this.workspaceRoot, safePath);
      const sourceContent = await readFile(prepareWorkspaceReadPath(safePath, this.workspaceRoot));
      return {
        source_ref: sourceRef,
        source_range: {
          offset: positiveNumber((context.args as Record<string, unknown>).offset),
          limit: positiveNumber((context.args as Record<string, unknown>).limit),
        },
        source_hash: hashBuffer(sourceContent),
        source_bytes: sourceContent.byteLength,
      };
    } catch {
      return undefined;
    }
  }
}

function inlinePolicy(
  toolName: string,
  contentBytes: number,
  isError: boolean,
  largeObservationBytes: number,
): ToolObservationInlinePolicy {
  if (toolName === "read" || toolName === "bash") {
    return contentBytes >= largeObservationBytes ? "demote_after_turn" : "keep";
  }
  if (isError) return "keep";
  return "keep";
}

function extractText(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content
    .map((block) => {
      if (!block || typeof block !== "object") return "";
      const value = block as Record<string, unknown>;
      return value.type === "text" && typeof value.text === "string" ? value.text : "";
    })
    .filter(Boolean)
    .join("\n");
}

function textStats(text: string): { bytes: number; lines: number } {
  const bytes = Buffer.byteLength(text, "utf-8");
  if (text.length === 0) return { bytes, lines: 0 };
  const lines = text.endsWith("\n") ? text.split("\n").length - 1 : text.split("\n").length;
  return { bytes, lines };
}

function hashText(text: string): string {
  return `sha256:${createHash("sha256").update(text).digest("hex")}`;
}

function hashBuffer(value: Buffer): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function detailString(details: unknown, key: string): string | undefined {
  if (!details || typeof details !== "object" || Array.isArray(details)) return undefined;
  const value = (details as Record<string, unknown>)[key];
  return typeof value === "string" && value ? value : undefined;
}

function positiveNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : undefined;
}

function resolvePiBashTempPath(path: string): string {
  const resolved = resolve(path);
  const root = resolve(tmpdir());
  const rel = relative(root, resolved);
  if (rel.startsWith("..") || rel === "" || rel.includes("..")) {
    throw new Error("bash fullOutputPath is outside the system temp directory");
  }
  const name = basename(resolved);
  if (!/^pi-bash-[a-f0-9]+\.log$/i.test(name)) {
    throw new Error("bash fullOutputPath is not a Pi bash temp output");
  }
  return resolved;
}

interface RawCapture {
  raw_ref: string;
  content_hash: string;
  content_bytes: number;
  content_lines: number;
}

async function rawCapture(rawRef: string, path: string): Promise<RawCapture> {
  const content = await readFile(path);
  const text = content.toString("utf-8");
  const stats = textStats(text);
  return {
    raw_ref: rawRef,
    content_hash: hashBuffer(content),
    content_bytes: stats.bytes,
    content_lines: stats.lines,
  };
}

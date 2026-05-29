import type { Model } from "@earendil-works/pi-ai";

export type ProviderMode = "faux" | "live";

export interface RuntimeProviderConfig {
  mode: ProviderMode;
  model: Model<any>;
  apiKey?: string;
  reasoning: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
  maxTurns: number;
  toolTimeoutSeconds: number;
  cancelAfterTurns: number | null;
  compactAfterTurns: number | null;
}

export function resolveProviderConfig(env: NodeJS.ProcessEnv = process.env): RuntimeProviderConfig {
  const mode = normalizeMode(env.MISSIONFORGE_PI_AGENT_PROVIDER ?? "faux");
  const reasoning = normalizeReasoning(env.MISSIONFORGE_PI_AGENT_REASONING ?? "off");
  const maxTurns = positiveInt(env.MISSIONFORGE_PI_AGENT_MAX_TURNS, 12);
  const toolTimeoutSeconds = positiveInt(env.MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS, 60);
  const cancelAfterTurns = optionalPositiveInt(env.MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS);
  const compactAfterTurns = optionalPositiveInt(env.MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS);
  if (mode === "faux") {
    return {
      mode,
      reasoning,
      maxTurns,
      toolTimeoutSeconds,
      cancelAfterTurns,
      compactAfterTurns,
      model: {
        id: "missionforge-faux",
        name: "MissionForge Faux",
        api: "unknown",
        provider: "missionforge-faux",
        baseUrl: "",
        reasoning: false,
        input: [],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 128000,
        maxTokens: 4096,
      } satisfies Model<any>,
    };
  }

  const modelId = required(env.MISSIONFORGE_PI_AGENT_MODEL, "MISSIONFORGE_PI_AGENT_MODEL");
  const baseUrl = required(env.MISSIONFORGE_PI_AGENT_BASE_URL, "MISSIONFORGE_PI_AGENT_BASE_URL");
  const apiKey = required(env.MISSIONFORGE_PI_AGENT_API_KEY, "MISSIONFORGE_PI_AGENT_API_KEY");
  return {
    mode,
    apiKey,
    reasoning,
    maxTurns,
    toolTimeoutSeconds,
    cancelAfterTurns,
    compactAfterTurns,
    model: {
      id: modelId,
      name: modelId,
      api: "openai-responses",
      provider: "missionforge-live",
      baseUrl,
      reasoning: reasoning !== "off",
      input: ["text", "image"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128000,
      maxTokens: 4096,
      compat: {
        sendSessionIdHeader: false,
        supportsLongCacheRetention: false,
      },
    } satisfies Model<any>,
  };
}

function normalizeMode(value: string): ProviderMode {
  const normalized = value.trim().toLowerCase();
  if (normalized === "faux" || normalized === "live") return normalized;
  throw new Error("MISSIONFORGE_PI_AGENT_PROVIDER must be faux or live");
}

function normalizeReasoning(value: string): RuntimeProviderConfig["reasoning"] {
  const normalized = value.trim().toLowerCase();
  if (["off", "minimal", "low", "medium", "high", "xhigh"].includes(normalized)) {
    return normalized as RuntimeProviderConfig["reasoning"];
  }
  throw new Error("MISSIONFORGE_PI_AGENT_REASONING is invalid");
}

function positiveInt(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) throw new Error(`Invalid positive integer: ${value}`);
  return parsed;
}

function optionalPositiveInt(value: string | undefined): number | null {
  if (!value) return null;
  return positiveInt(value, 1);
}

function required(value: string | undefined, name: string): string {
  if (!value) throw new Error(`${name} is required`);
  return value;
}

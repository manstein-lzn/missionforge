export function resolveProviderConfig(env = process.env) {
    const mode = normalizeMode(env.MISSIONFORGE_PI_AGENT_PROVIDER ?? "faux");
    const reasoning = normalizeReasoning(env.MISSIONFORGE_PI_AGENT_REASONING ?? "off");
    const maxTurns = positiveInt(env.MISSIONFORGE_PI_AGENT_MAX_TURNS, 500);
    const providerRetryLimit = nonNegativeInt(env.MISSIONFORGE_PI_AGENT_PROVIDER_RETRY_LIMIT, mode === "live" ? 2 : 0);
    const providerRetryDelayMs = nonNegativeInt(env.MISSIONFORGE_PI_AGENT_PROVIDER_RETRY_DELAY_MS, 1000);
    const toolTimeoutSeconds = positiveInt(env.MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS, 60);
    const cancelAfterTurns = optionalPositiveInt(env.MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS);
    const compactAfterTurns = optionalPositiveInt(env.MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS);
    const contextWindow = positiveInt(env.MISSIONFORGE_PI_AGENT_CONTEXT_WINDOW, 128000);
    if (mode === "faux") {
        return {
            mode,
            reasoning,
            maxTurns,
            providerRetryLimit,
            providerRetryDelayMs,
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
                contextWindow,
                maxTokens: 4096,
            },
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
        providerRetryLimit,
        providerRetryDelayMs,
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
            contextWindow,
            maxTokens: 4096,
            compat: {
                sendSessionIdHeader: false,
                supportsLongCacheRetention: false,
            },
        },
    };
}
function normalizeMode(value) {
    const normalized = value.trim().toLowerCase();
    if (normalized === "faux" || normalized === "live")
        return normalized;
    throw new Error("MISSIONFORGE_PI_AGENT_PROVIDER must be faux or live");
}
function normalizeReasoning(value) {
    const normalized = value.trim().toLowerCase();
    if (["off", "minimal", "low", "medium", "high", "xhigh"].includes(normalized)) {
        return normalized;
    }
    throw new Error("MISSIONFORGE_PI_AGENT_REASONING is invalid");
}
function positiveInt(value, fallback) {
    if (!value)
        return fallback;
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 1)
        throw new Error(`Invalid positive integer: ${value}`);
    return parsed;
}
function nonNegativeInt(value, fallback) {
    if (!value)
        return fallback;
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 0)
        throw new Error(`Invalid non-negative integer: ${value}`);
    return parsed;
}
function optionalPositiveInt(value) {
    if (!value)
        return null;
    return positiveInt(value, 1);
}
function required(value, name) {
    if (!value)
        throw new Error(`${name} is required`);
    return value;
}

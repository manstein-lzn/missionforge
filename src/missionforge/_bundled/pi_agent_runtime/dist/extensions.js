import { EXTENSION_LOAD_REPORT_SCHEMA_VERSION, parseExtensionLock, } from "./contract.js";
import { readJsonFile, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import { AuthStorage, createEventBus, createExtensionRuntime, ExtensionRunner, ModelRegistry, SessionManager, wrapRegisteredTools, } from "@earendil-works/pi-coding-agent";
import { loadExtensions } from "../node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/index.js";
export async function loadExtensionLock(input, workspaceRoot) {
    if (!input.extension_lock_ref)
        return null;
    return parseExtensionLock(await readJsonFile(resolveWorkspaceRef(workspaceRoot, input.extension_lock_ref)));
}
export async function writeExtensionLoadReport(input, workspaceRoot, extensionLock) {
    const report = extensionLoadReportFromLock(input, extensionLock);
    await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.extension_load_report_ref), report, { workspaceRoot });
    return report;
}
export async function loadExtensionTools(input, workspaceRoot, extensionLock) {
    const permissionManifest = input.permission_manifest;
    const extensionGrants = permissionManifest.extension_grants ?? [];
    const report = extensionLoadReportFromLock(input, extensionLock);
    if (extensionGrants.length === 0 || extensionLock === null) {
        return { tools: [], report };
    }
    const loadableByGrantId = new Map(report.loaded_extensions.map((record) => [record.grant_id, record]));
    const toolEntries = extensionLock.extensions.filter((entry) => loadableByGrantId.has(entry.grant_id));
    const loadResult = await loadExtensions(toolEntries.map((entry) => entry.install_path), workspaceRoot, createEventBus());
    const runtime = loadResult.runtime ?? createExtensionRuntime();
    const authStorage = AuthStorage.inMemory();
    const modelRegistry = ModelRegistry.inMemory(authStorage);
    const sessionManager = SessionManager.inMemory(workspaceRoot);
    const runner = new ExtensionRunner(loadResult.extensions, runtime, workspaceRoot, sessionManager, modelRegistry);
    runner.bindCore({
        sendMessage: () => undefined,
        sendUserMessage: () => undefined,
        appendEntry: () => undefined,
        setSessionName: () => undefined,
        getSessionName: () => undefined,
        setLabel: () => undefined,
        getActiveTools: () => [],
        getAllTools: () => [],
        setActiveTools: () => undefined,
        refreshTools: () => undefined,
        getCommands: () => [],
        setModel: async () => false,
        getThinkingLevel: () => "off",
        setThinkingLevel: () => undefined,
    }, {
        getModel: () => undefined,
        isIdle: () => true,
        getSignal: () => undefined,
        abort: () => undefined,
        hasPendingMessages: () => false,
        shutdown: () => undefined,
        getContextUsage: () => undefined,
        compact: () => undefined,
        getSystemPrompt: () => "",
    });
    const wrappedTools = wrapRegisteredTools(runner.getAllRegisteredTools(), runner);
    const loadedExtensionsByPath = new Map(loadResult.extensions.map((extension) => [extension.path, extension]));
    const errorsByPath = new Map(loadResult.errors.map((error) => [error.path, error.error]));
    const loaded = [];
    const rejected = [...report.rejected_extensions];
    for (const entry of extensionLock.extensions) {
        const accepted = loadableByGrantId.get(entry.grant_id);
        if (!accepted)
            continue;
        const loadError = errorsByPath.get(entry.install_path);
        const loadedExtension = loadedExtensionsByPath.get(entry.install_path);
        if (!loadedExtension || loadError) {
            rejected.push({
                ...accepted,
                status: "rejected",
                reason: loadError ? `load_error:${loadError}` : "load_failed",
                tool_names: [],
            });
            continue;
        }
        loaded.push({
            ...accepted,
            status: "loaded",
            tool_names: Array.from(loadedExtension.tools.keys()),
        });
    }
    const finalReport = {
        ...report,
        loaded_extensions: loaded,
        rejected_extensions: rejected,
    };
    await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.extension_load_report_ref), finalReport, {
        workspaceRoot,
    });
    return { tools: wrappedTools, report: finalReport };
}
export function extensionLoadReportFromLock(input, extensionLock) {
    const manifest = input.permission_manifest;
    const extensionGrants = manifest.extension_grants ?? [];
    if (extensionGrants.length === 0) {
        return emptyExtensionLoadReport(input);
    }
    if (!extensionLock) {
        return {
            ...emptyExtensionLoadReport(input),
            rejected_extensions: extensionGrants.map((grant) => rejectedRecord(grant, manifest, "missing_extension_lock")),
        };
    }
    const lockedByGrantId = new Map(extensionLock.extensions.map((entry) => [entry.grant_id, entry]));
    const manifestGrantIds = new Set(extensionGrants.map((grant) => grant.grant_id));
    const loaded = [];
    const rejected = [];
    for (const entry of extensionLock.extensions) {
        if (!manifestGrantIds.has(entry.grant_id)) {
            rejected.push(rejectedRecordFromLockEntry(entry, manifest, "extra_lock_entry"));
        }
    }
    for (const grant of extensionGrants) {
        const entry = lockedByGrantId.get(grant.grant_id);
        if (!entry) {
            rejected.push(rejectedRecord(grant, manifest, "missing_lock_entry"));
            continue;
        }
        const reason = grantLockMismatch(grant, entry, manifest);
        if (reason) {
            rejected.push(rejectedRecord(grant, manifest, reason, entry));
            continue;
        }
        loaded.push({
            grant_id: grant.grant_id,
            package: grant.package,
            capability: grant.capability,
            status: "loaded",
            adapter_mode: grant.adapter_mode,
            reason: "extension lock matched; provider loading is delegated to runtime adapters",
            version: entry.version,
            integrity: entry.integrity,
            requires_network: grant.requires_network,
            network_policy_at_load: manifest.network_policy,
            tool_names: [],
        });
    }
    return {
        ...emptyExtensionLoadReport(input),
        loaded_extensions: loaded,
        rejected_extensions: rejected,
    };
}
export function assertExtensionLoadReportAccepted(report) {
    if (report.rejected_extensions.length > 0) {
        const reasons = report.rejected_extensions.map((record) => `${record.grant_id}:${record.reason}`).join(", ");
        throw new Error(`declared extensions were rejected: ${reasons}`);
    }
}
function emptyExtensionLoadReport(input) {
    return {
        schema_version: EXTENSION_LOAD_REPORT_SCHEMA_VERSION,
        call_id: input.call_id,
        extension_lock_ref: input.extension_lock_ref,
        permission_manifest_ref: input.piworker_call.permission_manifest_ref,
        loaded_extensions: [],
        rejected_extensions: [],
    };
}
function rejectedRecordFromLockEntry(entry, manifest, reason) {
    return {
        grant_id: entry.grant_id,
        package: entry.package,
        capability: entry.capability,
        status: "rejected",
        adapter_mode: entry.adapter_mode,
        reason,
        version: entry.version,
        integrity: entry.integrity,
        requires_network: entry.requires_network,
        network_policy_at_load: manifest.network_policy,
        tool_names: [],
    };
}
function grantLockMismatch(grant, entry, manifest) {
    if (grant.package !== entry.package)
        return "package_mismatch";
    if (grant.capability !== entry.capability)
        return "capability_mismatch";
    if (grant.adapter_mode !== entry.adapter_mode)
        return "adapter_mode_mismatch";
    if (grant.requires_network !== entry.requires_network)
        return "requires_network_mismatch";
    if (grant.requires_bash !== entry.requires_bash)
        return "requires_bash_mismatch";
    if (!sameStringSet(grant.required_env, entry.required_env))
        return "required_env_mismatch";
    if (grant.requires_network && manifest.network_policy === "disabled")
        return "network_policy_disabled";
    if (grant.required_env.some((name) => !manifest.env_allowlist.includes(name)))
        return "required_env_not_allowed";
    if (grant.integrity !== null && entry.integrity !== grant.integrity)
        return "integrity_mismatch";
    return "";
}
function rejectedRecord(grant, manifest, reason, entry) {
    return {
        grant_id: grant.grant_id,
        package: grant.package,
        capability: grant.capability,
        status: "rejected",
        adapter_mode: grant.adapter_mode,
        reason,
        version: entry?.version ?? null,
        integrity: entry?.integrity ?? grant.integrity,
        requires_network: grant.requires_network,
        network_policy_at_load: manifest.network_policy,
        tool_names: [],
    };
}
function sameStringSet(left, right) {
    if (left.length !== right.length)
        return false;
    const rightSet = new Set(right);
    return left.every((item) => rightSet.has(item));
}

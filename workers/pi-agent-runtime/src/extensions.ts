import type {
  ExtensionGrant,
  ExtensionLoadRecord,
  ExtensionLoadReport,
  ExtensionLock,
  ExtensionLockEntry,
  PermissionManifest,
  RuntimeInput,
} from "./contract.js";
import {
  EXTENSION_LOAD_REPORT_SCHEMA_VERSION,
  parseExtensionLock,
} from "./contract.js";
import { readJsonFile, resolveWorkspaceRef, writeJsonFile } from "./paths.js";
import {
  AuthStorage,
  createEventBus,
  createExtensionRuntime,
  ExtensionRunner,
  ModelRegistry,
  SessionManager,
  wrapRegisteredTools,
} from "@earendil-works/pi-coding-agent";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { loadExtensions } from "../node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/index.js";

export async function loadExtensionLock(input: RuntimeInput, workspaceRoot: string): Promise<ExtensionLock | null> {
  if (!input.extension_lock_ref) return null;
  return parseExtensionLock(await readJsonFile(resolveWorkspaceRef(workspaceRoot, input.extension_lock_ref)));
}

export async function writeExtensionLoadReport(
  input: RuntimeInput,
  workspaceRoot: string,
  extensionLock: ExtensionLock | null,
): Promise<ExtensionLoadReport> {
  const report = extensionLoadReportFromLock(input, extensionLock);
  await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.extension_load_report_ref), report, { workspaceRoot });
  return report;
}

export async function loadExtensionTools(
  input: RuntimeInput,
  workspaceRoot: string,
  extensionLock: ExtensionLock | null,
): Promise<{ tools: AgentTool<any>[]; report: ExtensionLoadReport }> {
  const permissionManifest = input.permission_manifest;
  const extensionGrants = permissionManifest.extension_grants ?? [];
  const report = extensionLoadReportFromLock(input, extensionLock);
  if (extensionGrants.length === 0 || extensionLock === null) {
    return { tools: [], report };
  }
  const loadableByGrantId = new Map(report.loaded_extensions.map((record) => [record.grant_id, record]));
  const toolEntries = extensionLock.extensions.filter((entry) => loadableByGrantId.has(entry.grant_id));
  const loadResult = await loadExtensions(
    toolEntries.map((entry) => entry.install_path),
    workspaceRoot,
    createEventBus(),
  );
  const runtime = loadResult.runtime ?? createExtensionRuntime();
  const authStorage = AuthStorage.inMemory();
  const modelRegistry = ModelRegistry.inMemory(authStorage);
  const sessionManager = SessionManager.inMemory(workspaceRoot);
  const runner = new ExtensionRunner(loadResult.extensions, runtime, workspaceRoot, sessionManager, modelRegistry);
  runner.bindCore(
    {
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
      getThinkingLevel: () => "off" as any,
      setThinkingLevel: () => undefined,
    },
    {
      getModel: () => undefined,
      isIdle: () => true,
      getSignal: () => undefined,
      abort: () => undefined,
      hasPendingMessages: () => false,
      shutdown: () => undefined,
      getContextUsage: () => undefined,
      compact: () => undefined,
      getSystemPrompt: () => "",
    },
  );
  const wrappedTools = wrapRegisteredTools(runner.getAllRegisteredTools(), runner);
  const loadedExtensionsByPath = new Map(loadResult.extensions.map((extension) => [extension.path, extension]));
  const errorsByPath = new Map(loadResult.errors.map((error) => [error.path, error.error]));
  const loaded: ExtensionLoadRecord[] = [];
  const rejected: ExtensionLoadRecord[] = [...report.rejected_extensions];
  for (const entry of extensionLock.extensions) {
    const accepted = loadableByGrantId.get(entry.grant_id);
    if (!accepted) continue;
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
  const finalReport: ExtensionLoadReport = {
    ...report,
    loaded_extensions: loaded,
    rejected_extensions: rejected,
  };
  await writeJsonFile(resolveWorkspaceRef(workspaceRoot, input.extension_load_report_ref), finalReport, {
    workspaceRoot,
  });
  return { tools: wrappedTools, report: finalReport };
}

export function extensionLoadReportFromLock(
  input: RuntimeInput,
  extensionLock: ExtensionLock | null,
): ExtensionLoadReport {
  const manifest = input.permission_manifest;
  const extensionGrants = manifest.extension_grants ?? [];
  if (extensionGrants.length === 0) {
    return emptyExtensionLoadReport(input);
  }
  if (!extensionLock) {
    return {
      ...emptyExtensionLoadReport(input),
      rejected_extensions: extensionGrants.map((grant) =>
        rejectedRecord(grant, manifest, "missing_extension_lock"),
      ),
    };
  }
  const lockedByGrantId = new Map(extensionLock.extensions.map((entry) => [entry.grant_id, entry]));
  const manifestGrantIds = new Set(extensionGrants.map((grant) => grant.grant_id));
  const loaded: ExtensionLoadRecord[] = [];
  const rejected: ExtensionLoadRecord[] = [];
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

export function assertExtensionLoadReportAccepted(report: ExtensionLoadReport): void {
  if (report.rejected_extensions.length > 0) {
    const reasons = report.rejected_extensions.map((record) => `${record.grant_id}:${record.reason}`).join(", ");
    throw new Error(`declared extensions were rejected: ${reasons}`);
  }
}

function emptyExtensionLoadReport(input: RuntimeInput): ExtensionLoadReport {
  return {
    schema_version: EXTENSION_LOAD_REPORT_SCHEMA_VERSION,
    call_id: input.call_id,
    extension_lock_ref: input.extension_lock_ref,
    permission_manifest_ref: input.piworker_call.permission_manifest_ref,
    loaded_extensions: [],
    rejected_extensions: [],
  };
}

function rejectedRecordFromLockEntry(
  entry: ExtensionLockEntry,
  manifest: PermissionManifest,
  reason: string,
): ExtensionLoadRecord {
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

function grantLockMismatch(
  grant: ExtensionGrant,
  entry: ExtensionLockEntry,
  manifest: PermissionManifest,
): string {
  if (grant.package !== entry.package) return "package_mismatch";
  if (grant.capability !== entry.capability) return "capability_mismatch";
  if (grant.adapter_mode !== entry.adapter_mode) return "adapter_mode_mismatch";
  if (grant.requires_network !== entry.requires_network) return "requires_network_mismatch";
  if (grant.requires_bash !== entry.requires_bash) return "requires_bash_mismatch";
  if (!sameStringSet(grant.required_env, entry.required_env)) return "required_env_mismatch";
  if (grant.requires_network && manifest.network_policy === "disabled") return "network_policy_disabled";
  if (grant.required_env.some((name) => !manifest.env_allowlist.includes(name))) return "required_env_not_allowed";
  if (grant.integrity !== null && entry.integrity !== grant.integrity) return "integrity_mismatch";
  return "";
}

function rejectedRecord(
  grant: ExtensionGrant,
  manifest: PermissionManifest,
  reason: string,
  entry?: ExtensionLockEntry,
): ExtensionLoadRecord {
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

function sameStringSet(left: readonly string[], right: readonly string[]): boolean {
  if (left.length !== right.length) return false;
  const rightSet = new Set(right);
  return left.every((item) => rightSet.has(item));
}

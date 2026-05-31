import { lstatSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";

import type { PermissionManifest, WorkUnitContract } from "./contract.js";
import { PERMISSION_MANIFEST_SCHEMA_VERSION, requireRef } from "./contract.js";

export const SUPPORTED_HARD_POLICIES = new Set([
  "filesystem_ref_roots",
  "bash_exact_command_allowlist",
  "env_allowlist",
]);

export class ToolPermissionEnforcer {
  readonly workspaceRoot: string;
  readonly manifest: PermissionManifest;

  constructor(workspaceRoot: string, manifest: PermissionManifest) {
    this.workspaceRoot = realpathSync(resolve(workspaceRoot));
    this.manifest = manifest;
    assertSupportedHardPolicies(manifest);
  }

  ensureReadPath(path: string): string {
    const resolved = guardWorkspacePath(this.workspaceRoot, path);
    const ref = absolutePathToWorkspaceRef(this.workspaceRoot, resolved);
    this.ensureReadRef(ref);
    assertNoSymlinkSegments(this.workspaceRoot, resolved, { allowMissingLeaf: false });
    return resolved;
  }

  ensureWritePath(path: string): string {
    const resolved = guardWorkspacePath(this.workspaceRoot, path);
    const ref = absolutePathToWorkspaceRef(this.workspaceRoot, resolved);
    this.ensureWriteRef(ref);
    assertNoSymlinkSegments(this.workspaceRoot, resolved, { allowMissingLeaf: true });
    return resolved;
  }

  ensureWriteContainerPath(path: string): string {
    const resolved = guardWorkspacePath(this.workspaceRoot, path);
    const ref = absolutePathToWorkspaceRef(this.workspaceRoot, resolved);
    if (ref === "") return resolved;
    ensureRefCanContainWrite(ref, this.manifest.writable_refs, this.manifest.denied_refs);
    assertNoSymlinkSegments(this.workspaceRoot, resolved, { allowMissingLeaf: true });
    return resolved;
  }

  ensureReadRef(ref: string): string {
    return ensureRefAllowed("read", normalizeWorkspaceRef(ref, "permission.read_ref"), this.manifest.readable_refs, this.manifest.denied_refs);
  }

  ensureWriteRef(ref: string): string {
    return ensureRefAllowed("write", normalizeWorkspaceRef(ref, "permission.write_ref"), this.manifest.writable_refs, this.manifest.denied_refs);
  }

  ensureCommand(command: string): string {
    if (typeof command !== "string" || command.length === 0) {
      throw new Error("permission.command must be a non-empty string");
    }
    if (!this.manifest.allowed_commands.includes(command)) {
      throw new Error(`permission denied for command: command is not in allowed_commands: ${command}`);
    }
    return command;
  }

  filterEnv(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
    return filterEnvByAllowlist(env, this.manifest.env_allowlist);
  }
}

export function derivePermissionManifestFromContract(contract: WorkUnitContract): PermissionManifest {
  const readableRefs = uniqueRefs([
    ...contract.visible_refs,
    ...contract.allowed_scope,
    ...contract.expected_outputs.map(parentRef),
  ]);
  return {
    manifest_id: `${contract.work_unit_id}-pi-runtime-permissions`,
    workspace_policy_ref: null,
    readable_refs: readableRefs,
    writable_refs: uniqueRefs(contract.allowed_scope),
    denied_refs: [],
    allowed_commands: [],
    network_policy: "disabled",
    env_allowlist: [],
    secret_ref: null,
    unsupported_hard_policies: [],
    schema_version: PERMISSION_MANIFEST_SCHEMA_VERSION,
  };
}

export function deriveDirectPermissionManifest(
  taskId: string,
  expectedOutputRefs: string[],
): PermissionManifest {
  const outputRoots = uniqueRefs(expectedOutputRefs.map(parentRef));
  return {
    manifest_id: `${taskId}-direct-piworker-permissions`,
    workspace_policy_ref: null,
    readable_refs: outputRoots,
    writable_refs: outputRoots,
    denied_refs: [],
    allowed_commands: [],
    network_policy: "disabled",
    env_allowlist: [],
    secret_ref: null,
    unsupported_hard_policies: [],
    schema_version: PERMISSION_MANIFEST_SCHEMA_VERSION,
  };
}

export function assertSupportedHardPolicies(manifest: PermissionManifest): void {
  const unsupported = manifest.unsupported_hard_policies.filter(
    (name) => !SUPPORTED_HARD_POLICIES.has(name),
  );
  if (manifest.network_policy === "restricted") {
    unsupported.push("network_restricted_policy");
  }
  if (unsupported.length > 0) {
    throw new Error(`unsupported hard permission policies: ${unsupported.join(", ")}`);
  }
}

export function filterEnvByAllowlist(
  env: NodeJS.ProcessEnv,
  allowlist: readonly string[],
): NodeJS.ProcessEnv {
  const allowed = new Set(allowlist);
  const result: NodeJS.ProcessEnv = {};
  for (const name of allowed) {
    if (Object.hasOwn(env, name) && env[name] !== undefined) {
      result[name] = env[name];
    }
  }
  return result;
}

export function guardWorkspacePath(workspaceRoot: string, path: string): string {
  const root = resolve(workspaceRoot);
  const resolved = resolve(path);
  const rel = relative(root, resolved);
  if (rel === "" || (!rel.startsWith("..") && !isAbsolute(rel))) return resolved;
  throw new Error(`Path escapes MissionForge workspace: ${path}`);
}

export function assertNoSymlinkSegments(
  workspaceRoot: string,
  path: string,
  options: { allowMissingLeaf: boolean },
): void {
  const root = realpathSync(resolve(workspaceRoot));
  const resolved = guardWorkspacePath(root, path);
  const rel = relative(root, resolved);
  if (rel === "") return;
  const parts = rel.split(sep).filter(Boolean);
  let current = root;
  for (let index = 0; index < parts.length; index += 1) {
    current = resolve(current, parts[index]);
    try {
      const stat = lstatSync(current);
      if (stat.isSymbolicLink()) {
        throw new Error(`Path crosses symlink inside MissionForge workspace: ${current}`);
      }
    } catch (error) {
      if (isMissingPathError(error) && options.allowMissingLeaf) {
        return;
      }
      throw error;
    }
  }
}

export function absolutePathToWorkspaceRef(workspaceRoot: string, absolutePath: string): string {
  const root = resolve(workspaceRoot);
  const resolved = guardWorkspacePath(root, absolutePath);
  const rel = relative(root, resolved);
  return rel.split(sep).join("/");
}

export function refIsUnder(ref: string, rootRef: string): boolean {
  const safeRef = normalizeWorkspaceRef(ref, "permission.ref");
  const safeRoot = requireRef(rootRef, "permission.root_ref");
  return safeRef === safeRoot || safeRef.startsWith(`${safeRoot}/`);
}

function ensureRefAllowed(
  operation: "read" | "write",
  ref: string,
  allowedRoots: readonly string[],
  deniedRoots: readonly string[],
): string {
  const deniedRoot = firstMatchingRoot(ref, deniedRoots);
  if (deniedRoot !== null) {
    throw new Error(`permission denied for ${ref}: ref is denied by ${deniedRoot}`);
  }
  const allowedRoot = firstMatchingRoot(ref, allowedRoots);
  if (allowedRoot !== null) return ref;
  throw new Error(`permission denied for ${ref || "<workspace-root>"}: ${operation} ref is outside allowed roots`);
}

function ensureRefCanContainWrite(
  ref: string,
  writableRoots: readonly string[],
  deniedRoots: readonly string[],
): string {
  const deniedRoot = firstMatchingRoot(ref, deniedRoots);
  if (deniedRoot !== null) {
    throw new Error(`permission denied for ${ref}: ref is denied by ${deniedRoot}`);
  }
  if (firstMatchingRoot(ref, writableRoots) !== null) return ref;
  for (const writableRoot of writableRoots) {
    if (refIsUnder(writableRoot, ref)) return ref;
  }
  throw new Error(`permission denied for ${ref}: write container is outside writable roots`);
}

function firstMatchingRoot(ref: string, roots: readonly string[]): string | null {
  for (const root of roots) {
    if (refIsUnder(ref, root)) return root;
  }
  return null;
}

function normalizeWorkspaceRef(ref: string, field: string): string {
  if (typeof ref !== "string") throw new Error(`${field} must be a string`);
  if (ref === "") return ref;
  return requireRef(ref, field);
}

function isMissingPathError(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT");
}

function uniqueRefs(refs: string[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const ref of refs) {
    const safeRef = requireRef(ref, "permission.ref");
    if (seen.has(safeRef)) continue;
    result.push(safeRef);
    seen.add(safeRef);
  }
  return result;
}

function parentRef(ref: string): string {
  const safeRef = requireRef(ref, "permission.ref");
  const parts = safeRef.split("/");
  if (parts.length === 1) return safeRef;
  return parts.slice(0, -1).join("/");
}

import { lstatSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { PERMISSION_MANIFEST_SCHEMA_VERSION, requireRef } from "./contract.js";
export const SUPPORTED_HARD_POLICIES = new Set([
    "filesystem_ref_roots",
    "bash_exact_command_allowlist",
    "env_allowlist",
]);
export class ToolPermissionEnforcer {
    workspaceRoot;
    manifest;
    constructor(workspaceRoot, manifest) {
        this.workspaceRoot = realpathSync(resolve(workspaceRoot));
        this.manifest = manifest;
        assertSupportedHardPolicies(manifest);
    }
    ensureReadPath(path) {
        const resolved = guardWorkspacePath(this.workspaceRoot, path);
        const ref = absolutePathToWorkspaceRef(this.workspaceRoot, resolved);
        this.ensureReadRef(ref);
        assertNoSymlinkSegments(this.workspaceRoot, resolved, { allowMissingLeaf: false });
        return resolved;
    }
    ensureWritePath(path) {
        const resolved = guardWorkspacePath(this.workspaceRoot, path);
        const ref = absolutePathToWorkspaceRef(this.workspaceRoot, resolved);
        this.ensureWriteRef(ref);
        assertNoSymlinkSegments(this.workspaceRoot, resolved, { allowMissingLeaf: true });
        return resolved;
    }
    ensureWriteContainerPath(path) {
        const resolved = guardWorkspacePath(this.workspaceRoot, path);
        const ref = absolutePathToWorkspaceRef(this.workspaceRoot, resolved);
        if (ref === "")
            return resolved;
        ensureRefCanContainWrite(ref, this.manifest.writable_refs, this.manifest.denied_refs);
        assertNoSymlinkSegments(this.workspaceRoot, resolved, { allowMissingLeaf: true });
        return resolved;
    }
    ensureReadRef(ref) {
        return ensureRefAllowed("read", normalizeWorkspaceRef(ref, "permission.read_ref"), this.manifest.readable_refs, this.manifest.denied_refs);
    }
    ensureWriteRef(ref) {
        return ensureRefAllowed("write", normalizeWorkspaceRef(ref, "permission.write_ref"), this.manifest.writable_refs, this.manifest.denied_refs);
    }
    ensureCommand(command) {
        if (typeof command !== "string" || command.length === 0) {
            throw new Error("permission.command must be a non-empty string");
        }
        if (!this.manifest.allowed_commands.includes(command)) {
            throw new Error(`permission denied for command: command is not in allowed_commands: ${command}`);
        }
        return command;
    }
    ensureTool(toolName) {
        if (typeof toolName !== "string" || toolName.length === 0) {
            throw new Error("permission.tool_name must be a non-empty string");
        }
        if (this.manifest.allowed_tools.includes(toolName))
            return toolName;
        const alias = toolName === "read_text" || toolName === "read_json"
            ? "read"
            : toolName === "write_text" || toolName === "write_json"
                ? "write"
                : toolName;
        if (this.manifest.allowed_tools.includes(alias))
            return toolName;
        throw new Error(`permission denied for tool: tool is not in allowed_tools: ${toolName}`);
    }
    filterEnv(env = process.env) {
        return filterEnvByAllowlist(env, this.manifest.env_allowlist);
    }
}
export function derivePermissionManifestFromCallSpec(call_spec) {
    const readableRefs = uniqueRefs([
        ...call_spec.visible_refs,
        ...call_spec.allowed_scope,
        ...call_spec.expected_outputs.map(parentRef),
    ]);
    return {
        manifest_id: `${call_spec.call_id}-pi-runtime-permissions`,
        workspace_policy_ref: null,
        readable_refs: readableRefs,
        writable_refs: uniqueRefs(call_spec.allowed_scope),
        denied_refs: [],
        allowed_tools: ["read", "write", "edit"],
        allowed_commands: [],
        network_policy: "disabled",
        env_allowlist: [],
        secret_ref: null,
        unsupported_hard_policies: [],
        extension_grants: [],
        schema_version: PERMISSION_MANIFEST_SCHEMA_VERSION,
    };
}
export function assertSupportedHardPolicies(manifest) {
    const unsupported = manifest.unsupported_hard_policies.filter((name) => !SUPPORTED_HARD_POLICIES.has(name));
    if (manifest.network_policy === "restricted") {
        unsupported.push("network_restricted_policy");
    }
    if (unsupported.length > 0) {
        throw new Error(`unsupported hard permission policies: ${unsupported.join(", ")}`);
    }
}
export function filterEnvByAllowlist(env, allowlist) {
    const allowed = new Set(allowlist);
    const result = {};
    for (const name of allowed) {
        if (Object.hasOwn(env, name) && env[name] !== undefined) {
            result[name] = env[name];
        }
    }
    return result;
}
export function guardWorkspacePath(workspaceRoot, path) {
    const root = resolve(workspaceRoot);
    const resolved = resolve(path);
    const rel = relative(root, resolved);
    if (rel === "" || (!rel.startsWith("..") && !isAbsolute(rel)))
        return resolved;
    throw new Error(`Path escapes MissionForge workspace: ${path}`);
}
export function assertNoSymlinkSegments(workspaceRoot, path, options) {
    const root = realpathSync(resolve(workspaceRoot));
    const resolved = guardWorkspacePath(root, path);
    const rel = relative(root, resolved);
    if (rel === "")
        return;
    const parts = rel.split(sep).filter(Boolean);
    let current = root;
    for (let index = 0; index < parts.length; index += 1) {
        current = resolve(current, parts[index]);
        try {
            const stat = lstatSync(current);
            if (stat.isSymbolicLink()) {
                throw new Error(`Path crosses symlink inside MissionForge workspace: ${current}`);
            }
        }
        catch (error) {
            if (isMissingPathError(error) && options.allowMissingLeaf) {
                return;
            }
            throw error;
        }
    }
}
export function absolutePathToWorkspaceRef(workspaceRoot, absolutePath) {
    const root = resolve(workspaceRoot);
    const resolved = guardWorkspacePath(root, absolutePath);
    const rel = relative(root, resolved);
    return rel.split(sep).join("/");
}
export function refIsUnder(ref, rootRef) {
    const safeRef = normalizeWorkspaceRef(ref, "permission.ref");
    const safeRoot = requireRef(rootRef, "permission.root_ref");
    return safeRef === safeRoot || safeRef.startsWith(`${safeRoot}/`);
}
function ensureRefAllowed(operation, ref, allowedRoots, deniedRoots) {
    const deniedRoot = firstMatchingRoot(ref, deniedRoots);
    if (deniedRoot !== null) {
        throw new Error(`permission denied for ${ref}: ref is denied by ${deniedRoot}`);
    }
    const allowedRoot = firstMatchingRoot(ref, allowedRoots);
    if (allowedRoot !== null)
        return ref;
    throw new Error(`permission denied for ${ref || "<workspace-root>"}: ${operation} ref is outside allowed roots`);
}
function ensureRefCanContainWrite(ref, writableRoots, deniedRoots) {
    const deniedRoot = firstMatchingRoot(ref, deniedRoots);
    if (deniedRoot !== null) {
        throw new Error(`permission denied for ${ref}: ref is denied by ${deniedRoot}`);
    }
    if (firstMatchingRoot(ref, writableRoots) !== null)
        return ref;
    for (const writableRoot of writableRoots) {
        if (refIsUnder(writableRoot, ref))
            return ref;
    }
    throw new Error(`permission denied for ${ref}: write container is outside writable roots`);
}
function firstMatchingRoot(ref, roots) {
    for (const root of roots) {
        if (refIsUnder(ref, root))
            return root;
    }
    return null;
}
function normalizeWorkspaceRef(ref, field) {
    if (typeof ref !== "string")
        throw new Error(`${field} must be a string`);
    if (ref === "")
        return ref;
    return requireRef(ref, field);
}
function isMissingPathError(error) {
    return Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT");
}
function uniqueRefs(refs) {
    const result = [];
    const seen = new Set();
    for (const ref of refs) {
        const safeRef = requireRef(ref, "permission.ref");
        if (seen.has(safeRef))
            continue;
        result.push(safeRef);
        seen.add(safeRef);
    }
    return result;
}
function parentRef(ref) {
    const safeRef = requireRef(ref, "permission.ref");
    const parts = safeRef.split("/");
    if (parts.length === 1)
        return safeRef;
    return parts.slice(0, -1).join("/");
}

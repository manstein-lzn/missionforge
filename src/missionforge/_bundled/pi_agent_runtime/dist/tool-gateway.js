import { createHash } from "node:crypto";
import { absolutePathToWorkspaceRef, guardWorkspacePath, ToolPermissionEnforcer, } from "./permissions.js";
export const TOOL_GATEWAY_DECISION_SCHEMA_VERSION = "missionforge.pi_agent_tool_gateway_decision.v1";
export class ToolGateway {
    options;
    enforcer;
    decisions = [];
    sequence = 0;
    constructor(options) {
        this.options = options;
        this.enforcer = new ToolPermissionEnforcer(options.workspaceRoot, options.permissionManifest);
    }
    authorizeTool(toolName) {
        try {
            const allowedTool = this.enforcer.ensureTool(toolName);
            this.record({
                tool_name: allowedTool,
                operation: "tool",
                status: "allowed",
            });
            return allowedTool;
        }
        catch (error) {
            this.record({
                tool_name: toolName,
                operation: "tool",
                status: "denied",
                reason: safeReason(error),
            });
            throw error;
        }
    }
    authorizeReadPath(toolName, absolutePath) {
        this.authorizeTool(toolName);
        return this.authorizePath("read_path", toolName, absolutePath, () => this.enforcer.ensureReadPath(absolutePath));
    }
    authorizeWritePath(toolName, absolutePath) {
        this.authorizeTool(toolName);
        return this.authorizePath("write_path", toolName, absolutePath, () => this.enforcer.ensureWritePath(absolutePath));
    }
    authorizeReadWritePath(toolName, absolutePath) {
        this.authorizeTool(toolName);
        return this.authorizePath("read_write_path", toolName, absolutePath, () => {
            this.enforcer.ensureReadPath(absolutePath);
            return this.enforcer.ensureWritePath(absolutePath);
        });
    }
    authorizeWriteContainerPath(toolName, absolutePath) {
        this.authorizeTool(toolName);
        return this.authorizePath("write_container", toolName, absolutePath, () => this.enforcer.ensureWriteContainerPath(absolutePath));
    }
    authorizeCommand(command) {
        this.authorizeTool("bash");
        const commandHash = hashText(command);
        try {
            const allowedCommand = this.enforcer.ensureCommand(command);
            this.record({
                tool_name: "bash",
                operation: "bash_command",
                status: "allowed",
                command_hash: commandHash,
            });
            return allowedCommand;
        }
        catch (error) {
            this.record({
                tool_name: "bash",
                operation: "bash_command",
                status: "denied",
                command_hash: commandHash,
                reason: safeReason(error),
            });
            throw error;
        }
    }
    authorizeCwd(path) {
        this.authorizeTool("bash");
        const ref = this.refForPath(path);
        try {
            const safePath = guardWorkspacePath(this.options.workspaceRoot, path);
            this.record({
                tool_name: "bash",
                operation: "bash_cwd",
                status: "allowed",
                cwd_ref: ref ?? this.refForPath(safePath),
            });
            return safePath;
        }
        catch (error) {
            this.record({
                tool_name: "bash",
                operation: "bash_cwd",
                status: "denied",
                cwd_ref: ref,
                reason: safeReason(error),
            });
            throw error;
        }
    }
    filterEnv(env = process.env) {
        this.authorizeTool("bash");
        const result = this.enforcer.filterEnv(env);
        this.record({
            tool_name: "bash",
            operation: "env",
            status: "allowed",
            env_names: Object.keys(result).sort(),
        });
        return result;
    }
    getDecisions() {
        return this.decisions.map((decision) => ({ ...decision }));
    }
    authorizePath(operation, toolName, absolutePath, authorize) {
        const ref = this.refForPath(absolutePath);
        try {
            const safePath = authorize();
            this.record({
                tool_name: toolName,
                operation,
                status: "allowed",
                ref: ref ?? this.refForPath(safePath),
            });
            return safePath;
        }
        catch (error) {
            this.record({
                tool_name: toolName,
                operation,
                status: "denied",
                ref,
                reason: safeReason(error),
            });
            throw error;
        }
    }
    record(decision) {
        const item = {
            schema_version: TOOL_GATEWAY_DECISION_SCHEMA_VERSION,
            decision_id: `tool-gateway-decision-${String(++this.sequence).padStart(6, "0")}`,
            created_at: new Date().toISOString(),
            manifest_id: this.options.permissionManifest.manifest_id,
            ...decision,
        };
        this.decisions.push(item);
        this.options.onDecision?.({ ...item });
    }
    refForPath(path) {
        try {
            const safePath = guardWorkspacePath(this.options.workspaceRoot, path);
            return absolutePathToWorkspaceRef(this.options.workspaceRoot, safePath);
        }
        catch {
            return undefined;
        }
    }
}
function hashText(value) {
    return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}
function safeReason(error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("allowed_commands"))
        return "command_not_allowlisted";
    if (message.includes("allowed_tools"))
        return "tool_not_allowlisted";
    if (message.includes("ref is denied"))
        return "ref_denied";
    if (message.includes("write container is outside writable roots"))
        return "container_outside_writable_roots";
    if (message.includes("outside allowed roots"))
        return "ref_outside_allowed_roots";
    if (message.includes("outside writable roots"))
        return "ref_outside_writable_roots";
    if (message.includes("Path escapes MissionForge workspace"))
        return "path_escapes_workspace";
    if (message.includes("symlink"))
        return "path_crosses_symlink";
    return "authorization_failed";
}

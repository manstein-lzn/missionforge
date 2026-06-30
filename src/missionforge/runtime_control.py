"""Runtime capability grants and sandbox execution boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from datetime import datetime, timezone

from .contracts import (
    ContractValidationError,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .permissions import PermissionEnforcer, WriteGate
from .task_contract import PermissionManifest, WorkspacePolicy


RUNTIME_CAPABILITY_GRANT_SCHEMA_VERSION = "runtime_capability_grant.v1"
SANDBOX_PROFILE_SCHEMA_VERSION = "sandbox_profile.v1"
TOOL_GATEWAY_REQUEST_SCHEMA_VERSION = "tool_gateway_request.v1"
TOOL_GATEWAY_RESULT_SCHEMA_VERSION = "tool_gateway_result.v1"


class SandboxMode(StrEnum):
    """Sandbox isolation profile families."""

    BUBBLEWRAP = "bubblewrap"
    NSJAIL = "nsjail"
    SUBPROCESS = "subprocess"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CapabilityGrant:
    """Short-lived runtime authority for one agent role."""

    grant_id: str
    role: str
    contract_hash: str
    workspace_policy_ref: str
    permission_manifest_ref: str
    workspace_view_ref: str
    sandbox_profile_ref: str
    issued_by: str
    issued_at: str
    expires_at: str
    parent_grant_ref: str | None = None
    revoked_at: str | None = None
    schema_version: str = RUNTIME_CAPABILITY_GRANT_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)
    grant_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "grant_hash", stable_json_hash(self._content_dict()))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityGrant":
        data = require_mapping(payload, "capability_grant")
        grant = cls(
            grant_id=require_non_empty_str(data.get("grant_id"), "capability_grant.grant_id"),
            role=require_non_empty_str(data.get("role"), "capability_grant.role"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "capability_grant.contract_hash"),
            workspace_policy_ref=validate_ref(data.get("workspace_policy_ref"), "capability_grant.workspace_policy_ref"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "capability_grant.permission_manifest_ref",
            ),
            workspace_view_ref=validate_ref(data.get("workspace_view_ref"), "capability_grant.workspace_view_ref"),
            sandbox_profile_ref=validate_ref(data.get("sandbox_profile_ref"), "capability_grant.sandbox_profile_ref"),
            issued_by=require_non_empty_str(data.get("issued_by"), "capability_grant.issued_by"),
            issued_at=require_non_empty_str(data.get("issued_at"), "capability_grant.issued_at"),
            expires_at=require_non_empty_str(data.get("expires_at"), "capability_grant.expires_at"),
            parent_grant_ref=_optional_ref(data.get("parent_grant_ref"), "capability_grant.parent_grant_ref"),
            revoked_at=_optional_timestamp(data.get("revoked_at"), "capability_grant.revoked_at"),
            schema_version=require_non_empty_str(
                data.get("schema_version", RUNTIME_CAPABILITY_GRANT_SCHEMA_VERSION),
                "capability_grant.schema_version",
            ),
            metadata=_safe_mapping(data.get("metadata", {}), "capability_grant.metadata"),
        )
        return grant

    def validate(self) -> None:
        _require_schema(self.schema_version, RUNTIME_CAPABILITY_GRANT_SCHEMA_VERSION, "capability_grant.schema_version")
        require_non_empty_str(self.grant_id, "capability_grant.grant_id")
        require_non_empty_str(self.role, "capability_grant.role")
        require_non_empty_str(self.contract_hash, "capability_grant.contract_hash")
        validate_ref(self.workspace_policy_ref, "capability_grant.workspace_policy_ref")
        validate_ref(self.permission_manifest_ref, "capability_grant.permission_manifest_ref")
        validate_ref(self.workspace_view_ref, "capability_grant.workspace_view_ref")
        validate_ref(self.sandbox_profile_ref, "capability_grant.sandbox_profile_ref")
        require_non_empty_str(self.issued_by, "capability_grant.issued_by")
        _require_timestamp(self.issued_at, "capability_grant.issued_at")
        _require_timestamp(self.expires_at, "capability_grant.expires_at")
        if self.parent_grant_ref is not None:
            validate_ref(self.parent_grant_ref, "capability_grant.parent_grant_ref")
        if self.revoked_at is not None:
            _require_timestamp(self.revoked_at, "capability_grant.revoked_at")
        _safe_mapping(self.metadata, "capability_grant.metadata")

    def is_active(self, *, now: str | None = None) -> bool:
        if self.revoked_at is not None:
            return False
        current = _parse_timestamp(now) if now is not None else datetime.now(timezone.utc)
        return current < _parse_timestamp(self.expires_at)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self._content_dict()
        payload["grant_hash"] = self.grant_hash
        return payload

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "grant_id": self.grant_id,
            "role": self.role,
            "contract_hash": self.contract_hash,
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "workspace_view_ref": self.workspace_view_ref,
            "sandbox_profile_ref": self.sandbox_profile_ref,
            "issued_by": self.issued_by,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "parent_grant_ref": self.parent_grant_ref,
            "revoked_at": self.revoked_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SandboxProfile:
    """Declarative execution profile for one sandboxed agent."""

    profile_id: str
    mode: SandboxMode
    workspace_root_ref: str
    readable_refs: list[str] = field(default_factory=list)
    writable_refs: list[str] = field(default_factory=list)
    denied_refs: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=lambda: ["read", "write", "edit"])
    network_enabled: bool = False
    env_allowlist: list[str] = field(default_factory=list)
    command_allowlist: list[str] = field(default_factory=list)
    resource_budget: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SANDBOX_PROFILE_SCHEMA_VERSION
    profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "profile_hash", stable_json_hash(self._content_dict()))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SandboxProfile":
        data = require_mapping(payload, "sandbox_profile")
        profile = cls(
            profile_id=require_non_empty_str(data.get("profile_id"), "sandbox_profile.profile_id"),
            mode=_require_sandbox_mode(data.get("mode"), "sandbox_profile.mode"),
            workspace_root_ref=validate_ref(data.get("workspace_root_ref"), "sandbox_profile.workspace_root_ref"),
            readable_refs=_ref_list(data.get("readable_refs", []), "sandbox_profile.readable_refs"),
            writable_refs=_ref_list(data.get("writable_refs", []), "sandbox_profile.writable_refs"),
            denied_refs=_ref_list(data.get("denied_refs", []), "sandbox_profile.denied_refs"),
            allowed_tools=require_str_list(
                data.get("allowed_tools", ["read", "write", "edit"]),
                "sandbox_profile.allowed_tools",
            ),
            network_enabled=bool(data.get("network_enabled", False)),
            env_allowlist=require_str_list(data.get("env_allowlist", []), "sandbox_profile.env_allowlist"),
            command_allowlist=require_str_list(
                data.get("command_allowlist", []),
                "sandbox_profile.command_allowlist",
            ),
            resource_budget=_safe_mapping(data.get("resource_budget", {}), "sandbox_profile.resource_budget"),
            schema_version=require_non_empty_str(
                data.get("schema_version", SANDBOX_PROFILE_SCHEMA_VERSION),
                "sandbox_profile.schema_version",
            ),
        )
        return profile

    def validate(self) -> None:
        _require_schema(self.schema_version, SANDBOX_PROFILE_SCHEMA_VERSION, "sandbox_profile.schema_version")
        require_non_empty_str(self.profile_id, "sandbox_profile.profile_id")
        if not isinstance(self.mode, SandboxMode):
            raise ContractValidationError(
                f"sandbox_profile.mode must be one of {sorted(item.value for item in SandboxMode)}"
            )
        validate_ref(self.workspace_root_ref, "sandbox_profile.workspace_root_ref")
        _validate_unique_refs(self.readable_refs, "sandbox_profile.readable_refs")
        _validate_unique_refs(self.writable_refs, "sandbox_profile.writable_refs")
        _validate_unique_refs(self.denied_refs, "sandbox_profile.denied_refs")
        _validate_unique_strings(self.allowed_tools, "sandbox_profile.allowed_tools")
        require_str_list(self.env_allowlist, "sandbox_profile.env_allowlist")
        require_str_list(self.command_allowlist, "sandbox_profile.command_allowlist")
        _safe_mapping(self.resource_budget, "sandbox_profile.resource_budget")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self._content_dict()
        payload["profile_hash"] = self.profile_hash
        return payload

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "mode": self.mode.value,
            "workspace_root_ref": self.workspace_root_ref,
            "readable_refs": list(self.readable_refs),
            "writable_refs": list(self.writable_refs),
            "denied_refs": list(self.denied_refs),
            "allowed_tools": list(self.allowed_tools),
            "network_enabled": self.network_enabled,
            "env_allowlist": list(self.env_allowlist),
            "command_allowlist": list(self.command_allowlist),
            "resource_budget": dict(self.resource_budget),
        }


@dataclass(frozen=True)
class ToolGatewayRequest:
    """One tool execution request routed through the runtime control plane."""

    request_id: str
    grant: CapabilityGrant
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    cwd_ref: str | None = None
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = TOOL_GATEWAY_REQUEST_SCHEMA_VERSION

    def validate(self) -> None:
        require_non_empty_str(self.request_id, "tool_gateway_request.request_id")
        if not isinstance(self.grant, CapabilityGrant):
            raise ContractValidationError("tool_gateway_request.grant must be a CapabilityGrant")
        self.grant.validate()
        require_non_empty_str(self.tool_name, "tool_gateway_request.tool_name")
        _safe_mapping(self.args, "tool_gateway_request.args")
        if self.cwd_ref is not None:
            validate_ref(self.cwd_ref, "tool_gateway_request.cwd_ref")
        _ref_list(self.input_refs, "tool_gateway_request.input_refs")
        _ref_list(self.output_refs, "tool_gateway_request.output_refs")
        _ref_list(self.evidence_refs, "tool_gateway_request.evidence_refs")
        _require_schema(self.schema_version, TOOL_GATEWAY_REQUEST_SCHEMA_VERSION, "tool_gateway_request.schema_version")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "grant": self.grant.to_dict(),
            "tool_name": self.tool_name,
            "args": ensure_json_value(self.args, "tool_gateway_request.args"),
            "cwd_ref": self.cwd_ref,
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ToolGatewayResult:
    """Refs-first result of a tool gateway decision."""

    request_id: str
    allowed: bool
    decision: str
    sandbox_ref: str | None = None
    reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    unsupported_policy_names: list[str] = field(default_factory=list)
    schema_version: str = TOOL_GATEWAY_RESULT_SCHEMA_VERSION

    def validate(self) -> None:
        require_non_empty_str(self.request_id, "tool_gateway_result.request_id")
        if not isinstance(self.allowed, bool):
            raise ContractValidationError("tool_gateway_result.allowed must be a boolean")
        require_non_empty_str(self.decision, "tool_gateway_result.decision")
        if self.sandbox_ref is not None:
            validate_ref(self.sandbox_ref, "tool_gateway_result.sandbox_ref")
        if self.reason:
            require_non_empty_str(self.reason, "tool_gateway_result.reason")
        _ref_list(self.evidence_refs, "tool_gateway_result.evidence_refs")
        require_str_list(self.unsupported_policy_names, "tool_gateway_result.unsupported_policy_names")
        _require_schema(self.schema_version, TOOL_GATEWAY_RESULT_SCHEMA_VERSION, "tool_gateway_result.schema_version")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "allowed": self.allowed,
            "decision": self.decision,
            "sandbox_ref": self.sandbox_ref,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "unsupported_policy_names": list(self.unsupported_policy_names),
        }


class SandboxRunner(Protocol):
    """Sandbox execution boundary for one tool or agent call."""

    runner_id: str

    def run(
        self,
        request: ToolGatewayRequest,
        *,
        workspace: Path,
        sandbox_profile: SandboxProfile,
    ) -> ToolGatewayResult:
        ...


@dataclass(frozen=True)
class HostSandboxRunner:
    """Minimal runner placeholder that enforces control-plane validation only."""

    runner_id: str = "host-sandbox-runner"

    def run(
        self,
        request: ToolGatewayRequest,
        *,
        workspace: Path,
        sandbox_profile: SandboxProfile,
    ) -> ToolGatewayResult:
        request.validate()
        sandbox_profile.validate()
        if not request.grant.is_active():
            return ToolGatewayResult(
                request_id=request.request_id,
                allowed=False,
                decision="grant_inactive",
                sandbox_ref=None,
                reason="grant is expired or revoked",
            )
        if request.cwd_ref is not None and not _is_under(request.cwd_ref, sandbox_profile.workspace_root_ref):
            return ToolGatewayResult(
                request_id=request.request_id,
                allowed=False,
                decision="cwd_denied",
                sandbox_ref=None,
                reason="cwd is outside the sandbox workspace root",
            )
        enforcer = PermissionEnforcer(
            PermissionManifest.from_dict(
                {
                    "manifest_id": request.grant.permission_manifest_ref.replace("/", "-"),
                    "workspace_policy_ref": request.grant.workspace_policy_ref,
                    "readable_refs": list(sandbox_profile.readable_refs),
                    "writable_refs": list(sandbox_profile.writable_refs),
                    "denied_refs": list(sandbox_profile.denied_refs),
                    "allowed_tools": list(sandbox_profile.allowed_tools),
                    "allowed_commands": list(sandbox_profile.command_allowlist),
                    "network_policy": "enabled" if sandbox_profile.network_enabled else "disabled",
                    "env_allowlist": list(sandbox_profile.env_allowlist),
                }
            )
        )
        tool_decision = enforcer.check_tool(request.tool_name)
        if not tool_decision.allowed:
            return ToolGatewayResult(
                request_id=request.request_id,
                allowed=False,
                decision="tool_denied",
                sandbox_ref=None,
                reason=tool_decision.reason,
                evidence_refs=list(request.evidence_refs),
            )
        if request.tool_name in {"read", "read_text", "read_json"}:
            for ref in request.input_refs:
                decision = enforcer.check_read(ref)
                if not decision.allowed:
                    return ToolGatewayResult(
                        request_id=request.request_id,
                        allowed=False,
                        decision="read_denied",
                        sandbox_ref=None,
                        reason=decision.reason,
                        evidence_refs=list(request.evidence_refs),
                    )
        elif request.tool_name in {"write", "write_text", "write_json", "edit"}:
            write_gate = WriteGate(
                PermissionManifest.from_dict(
                    {
                        "manifest_id": request.grant.permission_manifest_ref.replace("/", "-"),
                        "workspace_policy_ref": request.grant.workspace_policy_ref,
                        "readable_refs": list(sandbox_profile.readable_refs),
                        "writable_refs": list(sandbox_profile.writable_refs),
                        "denied_refs": list(sandbox_profile.denied_refs),
                        "allowed_tools": list(sandbox_profile.allowed_tools),
                        "allowed_commands": list(sandbox_profile.command_allowlist),
                        "network_policy": "enabled" if sandbox_profile.network_enabled else "disabled",
                        "env_allowlist": list(sandbox_profile.env_allowlist),
                    }
                )
            )
            for ref in request.output_refs:
                decision = write_gate.check(ref, writer_role=request.grant.role)
                if not decision.allowed:
                    return ToolGatewayResult(
                        request_id=request.request_id,
                        allowed=False,
                        decision="write_denied",
                        sandbox_ref=None,
                        reason=decision.reason,
                        evidence_refs=list(request.evidence_refs),
                    )
        elif request.tool_name == "bash":
            command = str(request.args.get("command", ""))
            command_decision = enforcer.check_command(command)
            if not command_decision.allowed:
                return ToolGatewayResult(
                    request_id=request.request_id,
                    allowed=False,
                    decision="command_denied",
                    sandbox_ref=None,
                    reason=command_decision.reason,
                )
            network_requested = bool(request.args.get("network", False))
            network_decision = enforcer.check_network(requested=network_requested)
            if not network_decision.allowed:
                return ToolGatewayResult(
                    request_id=request.request_id,
                    allowed=False,
                    decision="network_denied",
                    sandbox_ref=None,
                    reason=network_decision.reason,
                    unsupported_policy_names=list(network_decision.unsupported_policy_names),
                )
        else:
            return ToolGatewayResult(
                request_id=request.request_id,
                allowed=False,
                decision="unsupported_tool",
                sandbox_ref=None,
                reason="tool is not supported by the control plane",
            )
        return ToolGatewayResult(
            request_id=request.request_id,
            allowed=True,
            decision="allowed",
            sandbox_ref=request.grant.workspace_view_ref,
            reason="sandbox request passed control-plane checks",
        )


@dataclass(frozen=True)
class ToolGateway:
    """Single routing point for runtime tool requests."""

    runner: SandboxRunner

    def dispatch(
        self,
        request: ToolGatewayRequest,
        *,
        workspace: Path,
        sandbox_profile: SandboxProfile,
    ) -> ToolGatewayResult:
        request.validate()
        sandbox_profile.validate()
        if request.grant.workspace_view_ref != sandbox_profile.workspace_root_ref:
            raise ContractValidationError("capability grant workspace view must match sandbox profile root")
        result = self.runner.run(request, workspace=workspace, sandbox_profile=sandbox_profile)
        result.validate()
        return result


def create_sandbox_profile_from_workspace(
    profile_id: str,
    *,
    workspace_policy: WorkspacePolicy,
    permission_manifest: PermissionManifest,
    mode: SandboxMode = SandboxMode.SUBPROCESS,
    network_enabled: bool | None = None,
) -> SandboxProfile:
    """Create a small sandbox profile from core permission objects."""

    workspace_policy.validate()
    permission_manifest.validate()
    return SandboxProfile(
        profile_id=profile_id,
        mode=mode,
        workspace_root_ref=workspace_policy.workspace_root_ref,
        readable_refs=list(permission_manifest.readable_refs or workspace_policy.input_refs),
        writable_refs=list(permission_manifest.writable_refs or workspace_policy.artifact_root_refs),
        denied_refs=sorted({*workspace_policy.denied_refs, *permission_manifest.denied_refs}),
        allowed_tools=list(permission_manifest.allowed_tools),
        network_enabled=permission_manifest.network_policy.value == "enabled" if network_enabled is None else network_enabled,
        env_allowlist=list(permission_manifest.env_allowlist),
        command_allowlist=list(permission_manifest.allowed_commands),
        resource_budget={},
    )


def create_capability_grant(
    *,
    grant_id: str,
    role: str,
    contract_hash: str,
    workspace_policy_ref: str,
    permission_manifest_ref: str,
    workspace_view_ref: str,
    sandbox_profile_ref: str,
    issued_by: str,
    expires_at: str,
    issued_at: str | None = None,
    parent_grant_ref: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CapabilityGrant:
    """Create a grant with a UTC ISO timestamp default for issued_at."""

    return CapabilityGrant(
        grant_id=grant_id,
        role=role,
        contract_hash=contract_hash,
        workspace_policy_ref=workspace_policy_ref,
        permission_manifest_ref=permission_manifest_ref,
        workspace_view_ref=workspace_view_ref,
        sandbox_profile_ref=sandbox_profile_ref,
        issued_by=issued_by,
        issued_at=issued_at or datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
        parent_grant_ref=parent_grant_ref,
        metadata=dict(metadata or {}),
    )


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")


def _require_timestamp(value: str, field_name: str) -> str:
    timestamp = require_non_empty_str(value, field_name)
    _parse_timestamp(timestamp)
    return timestamp


def _optional_timestamp(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_timestamp(value, field_name)


def _parse_timestamp(value: str) -> datetime:
    timestamp = require_non_empty_str(value, "timestamp")
    normalized = timestamp.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractValidationError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_sandbox_mode(value: Any, field_name: str) -> SandboxMode:
    if isinstance(value, SandboxMode):
        return value
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be one of {sorted(item.value for item in SandboxMode)}")
    try:
        return SandboxMode(value)
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be one of {sorted(item.value for item in SandboxMode)}") from exc


def _safe_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    data = require_mapping(value, field_name)
    return ensure_json_value(data, field_name)


def _ref_list(value: Any, field_name: str) -> list[str]:
    refs = require_str_list(value, field_name)
    for ref in refs:
        validate_ref(ref, f"{field_name}[]")
    return refs


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return validate_ref(value, field_name)


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _validate_unique_strings(values: list[str], field_name: str) -> None:
    items = require_str_list(values, field_name)
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")


def _is_under(ref: str, scope: str) -> bool:
    safe_ref = validate_ref(ref, "runtime_control.ref")
    safe_scope = validate_ref(scope, "runtime_control.scope")
    return safe_ref == safe_scope or safe_ref.startswith(f"{safe_scope}/")

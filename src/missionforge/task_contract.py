"""Minimal agentic task contract contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_bool,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


TASK_CONTRACT_SCHEMA_VERSION = "task_contract.v1"
TASK_CONTRACT_REVISION_SCHEMA_VERSION = "task_contract_revision.v1"
WORKSPACE_POLICY_SCHEMA_VERSION = "workspace_policy.v1"
PERMISSION_MANIFEST_SCHEMA_VERSION = "permission_manifest.v1"
DEFAULT_ALLOWED_TOOLS = ["read", "write", "edit"]


class NetworkPolicy(StrEnum):
    """Network authority declared for a PiWorker invocation."""

    DISABLED = "disabled"
    RESTRICTED = "restricted"
    ENABLED = "enabled"


class ExtensionCapability(StrEnum):
    """Coarse capability bucket declared for a runtime extension."""

    CODE_SEARCH = "code_search"
    LSP = "lsp"
    WEB = "web"
    MCP = "mcp"
    BROWSER = "browser"
    SUBAGENT = "subagent"
    MEMORY = "memory"
    PREVIEW = "preview"
    WORKFLOW = "workflow"
    UI = "ui"


class ExtensionAdapterMode(StrEnum):
    """How MissionForge expects the runtime to load an extension package."""

    MISSIONFORGE_PROVIDER = "missionforge_provider"
    UNTRUSTED_PI_EXTENSION = "untrusted_pi_extension"


@dataclass(frozen=True)
class ProgressStreamGrant:
    """Frozen declaration that a role may write user-visible progress events."""

    stream_id: str
    stream_ref: str
    audience: str = "user"
    renderer: str = "plain"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProgressStreamGrant":
        data = require_mapping(payload, "progress_stream_grant")
        grant = cls(
            stream_id=require_non_empty_str(data.get("stream_id"), "progress_stream_grant.stream_id"),
            stream_ref=validate_ref(data.get("stream_ref"), "progress_stream_grant.stream_ref"),
            audience=require_non_empty_str(data.get("audience", "user"), "progress_stream_grant.audience"),
            renderer=require_non_empty_str(data.get("renderer", "plain"), "progress_stream_grant.renderer"),
        )
        grant.validate()
        return grant

    def validate(self) -> None:
        require_non_empty_str(self.stream_id, "progress_stream_grant.stream_id")
        validate_ref(self.stream_ref, "progress_stream_grant.stream_ref")
        require_non_empty_str(self.audience, "progress_stream_grant.audience")
        require_non_empty_str(self.renderer, "progress_stream_grant.renderer")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "stream_id": self.stream_id,
            "stream_ref": self.stream_ref,
            "audience": self.audience,
            "renderer": self.renderer,
        }


@dataclass(frozen=True)
class ContractClause:
    """Small reusable clause for outputs, constraints, criteria, and risks."""

    clause_id: str
    text: str
    refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContractClause":
        data = require_mapping(payload, "contract_clause")
        clause = cls(
            clause_id=require_non_empty_str(data.get("clause_id"), "contract_clause.clause_id"),
            text=require_non_empty_str(data.get("text"), "contract_clause.text"),
            refs=_ref_list(data.get("refs", []), "contract_clause.refs"),
            metadata=_safe_mapping(data.get("metadata", {}), "contract_clause.metadata"),
        )
        clause.validate()
        return clause

    def validate(self) -> None:
        require_non_empty_str(self.clause_id, "contract_clause.clause_id")
        require_non_empty_str(self.text, "contract_clause.text")
        _ref_list(self.refs, "contract_clause.refs")
        _safe_mapping(self.metadata, "contract_clause.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "clause_id": self.clause_id,
            "text": self.text,
            "refs": list(self.refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ExtensionGrant:
    """Frozen declaration that an extension package may be mounted for a role."""

    grant_id: str
    package: str
    version_spec: str
    capability: ExtensionCapability
    config_ref: str | None = None
    requires_network: bool = False
    requires_bash: bool = False
    required_env: list[str] = field(default_factory=list)
    sandbox_profile_ref: str | None = None
    adapter_mode: ExtensionAdapterMode = ExtensionAdapterMode.MISSIONFORGE_PROVIDER
    integrity: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExtensionGrant":
        data = require_mapping(payload, "extension_grant")
        integrity = data.get("integrity")
        if integrity is not None:
            integrity = require_non_empty_str(integrity, "extension_grant.integrity")
        grant = cls(
            grant_id=require_non_empty_str(data.get("grant_id"), "extension_grant.grant_id"),
            package=_validate_extension_package(data.get("package"), "extension_grant.package"),
            version_spec=require_non_empty_str(data.get("version_spec"), "extension_grant.version_spec"),
            capability=require_enum(
                data.get("capability"),
                ExtensionCapability,
                "extension_grant.capability",
            ),
            config_ref=_optional_ref(data.get("config_ref"), "extension_grant.config_ref"),
            requires_network=require_bool(
                data.get("requires_network", False),
                "extension_grant.requires_network",
            ),
            requires_bash=require_bool(
                data.get("requires_bash", False),
                "extension_grant.requires_bash",
            ),
            required_env=require_str_list(data.get("required_env", []), "extension_grant.required_env"),
            sandbox_profile_ref=_optional_ref(
                data.get("sandbox_profile_ref"),
                "extension_grant.sandbox_profile_ref",
            ),
            adapter_mode=require_enum(
                data.get("adapter_mode", ExtensionAdapterMode.MISSIONFORGE_PROVIDER.value),
                ExtensionAdapterMode,
                "extension_grant.adapter_mode",
            ),
            integrity=integrity,
            metadata=_safe_mapping(data.get("metadata", {}), "extension_grant.metadata"),
        )
        grant.validate()
        return grant

    def validate(self) -> None:
        require_non_empty_str(self.grant_id, "extension_grant.grant_id")
        _validate_extension_package(self.package, "extension_grant.package")
        require_non_empty_str(self.version_spec, "extension_grant.version_spec")
        require_enum(self.capability, ExtensionCapability, "extension_grant.capability")
        _optional_ref(self.config_ref, "extension_grant.config_ref")
        require_bool(self.requires_network, "extension_grant.requires_network")
        require_bool(self.requires_bash, "extension_grant.requires_bash")
        _validate_unique_strings(self.required_env, "extension_grant.required_env")
        for name in self.required_env:
            _validate_env_name(name, "extension_grant.required_env[]")
        _optional_ref(self.sandbox_profile_ref, "extension_grant.sandbox_profile_ref")
        require_enum(self.adapter_mode, ExtensionAdapterMode, "extension_grant.adapter_mode")
        if self.integrity is not None:
            require_non_empty_str(self.integrity, "extension_grant.integrity")
        _safe_mapping(self.metadata, "extension_grant.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "grant_id": self.grant_id,
            "package": self.package,
            "version_spec": self.version_spec,
            "capability": self.capability.value,
            "config_ref": self.config_ref,
            "requires_network": self.requires_network,
            "requires_bash": self.requires_bash,
            "required_env": list(self.required_env),
            "sandbox_profile_ref": self.sandbox_profile_ref,
            "adapter_mode": self.adapter_mode.value,
            "integrity": self.integrity,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class WorkspacePolicy:
    """Declared workspace layout for a task run."""

    policy_id: str
    workspace_root_ref: str
    input_refs: list[str] = field(default_factory=list)
    artifact_root_refs: list[str] = field(default_factory=list)
    scratch_root_refs: list[str] = field(default_factory=list)
    denied_refs: list[str] = field(default_factory=list)
    schema_version: str = WORKSPACE_POLICY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkspacePolicy":
        data = require_mapping(payload, "workspace_policy")
        policy = cls(
            policy_id=require_non_empty_str(data.get("policy_id"), "workspace_policy.policy_id"),
            workspace_root_ref=validate_ref(
                data.get("workspace_root_ref", "runs/current"),
                "workspace_policy.workspace_root_ref",
            ),
            input_refs=_ref_list(
                data.get("input_refs", data.get("readable_roots", [])),
                "workspace_policy.input_refs",
            ),
            artifact_root_refs=_ref_list(
                data.get("artifact_root_refs", data.get("artifact_roots", [])),
                "workspace_policy.artifact_root_refs",
            ),
            scratch_root_refs=_ref_list(
                data.get("scratch_root_refs", []),
                "workspace_policy.scratch_root_refs",
            ),
            denied_refs=_ref_list(
                data.get("denied_refs", data.get("denied_paths", [])),
                "workspace_policy.denied_refs",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", WORKSPACE_POLICY_SCHEMA_VERSION),
                "workspace_policy.schema_version",
            ),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        _require_schema(self.schema_version, WORKSPACE_POLICY_SCHEMA_VERSION, "workspace_policy.schema_version")
        require_non_empty_str(self.policy_id, "workspace_policy.policy_id")
        validate_ref(self.workspace_root_ref, "workspace_policy.workspace_root_ref")
        _validate_unique_refs(self.input_refs, "workspace_policy.input_refs")
        _validate_unique_refs(self.artifact_root_refs, "workspace_policy.artifact_root_refs")
        _validate_unique_refs(self.scratch_root_refs, "workspace_policy.scratch_root_refs")
        _validate_unique_refs(self.denied_refs, "workspace_policy.denied_refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "policy_id": self.policy_id,
            "schema_version": self.schema_version,
            "workspace_root_ref": self.workspace_root_ref,
            "input_refs": list(self.input_refs),
            "artifact_root_refs": list(self.artifact_root_refs),
            "scratch_root_refs": list(self.scratch_root_refs),
            "denied_refs": list(self.denied_refs),
        }


@dataclass(frozen=True)
class PermissionManifest:
    """Declared permission envelope for a PiWorker role."""

    manifest_id: str
    workspace_policy_ref: str | None = None
    readable_refs: list[str] = field(default_factory=list)
    writable_refs: list[str] = field(default_factory=list)
    denied_refs: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    allowed_commands: list[str] = field(default_factory=list)
    network_policy: NetworkPolicy = NetworkPolicy.DISABLED
    env_allowlist: list[str] = field(default_factory=list)
    secret_ref: str | None = None
    unsupported_hard_policies: list[str] = field(default_factory=list)
    extension_grants: list[ExtensionGrant] = field(default_factory=list)
    progress_streams: list[ProgressStreamGrant] = field(default_factory=list)
    schema_version: str = PERMISSION_MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PermissionManifest":
        data = require_mapping(payload, "permission_manifest")
        secret_ref = data.get("secret_ref")
        if secret_ref is not None:
            secret_ref = validate_ref(secret_ref, "permission_manifest.secret_ref")
        manifest = cls(
            manifest_id=require_non_empty_str(data.get("manifest_id"), "permission_manifest.manifest_id"),
            workspace_policy_ref=_optional_ref(
                data.get("workspace_policy_ref"),
                "permission_manifest.workspace_policy_ref",
            ),
            readable_refs=_ref_list(
                data.get("readable_refs", data.get("readable_roots", [])),
                "permission_manifest.readable_refs",
            ),
            writable_refs=_ref_list(
                data.get("writable_refs", data.get("writable_roots", [])),
                "permission_manifest.writable_refs",
            ),
            denied_refs=_ref_list(
                data.get("denied_refs", data.get("denied_paths", [])),
                "permission_manifest.denied_refs",
            ),
            allowed_tools=require_str_list(
                data.get("allowed_tools", DEFAULT_ALLOWED_TOOLS),
                "permission_manifest.allowed_tools",
            ),
            allowed_commands=require_str_list(
                data.get("allowed_commands", data.get("executable_commands", [])),
                "permission_manifest.allowed_commands",
            ),
            network_policy=require_enum(
                data.get("network_policy", NetworkPolicy.DISABLED.value),
                NetworkPolicy,
                "permission_manifest.network_policy",
            ),
            env_allowlist=require_str_list(
                data.get("env_allowlist", data.get("environment_allowlist", [])),
                "permission_manifest.env_allowlist",
            ),
            secret_ref=secret_ref,
            unsupported_hard_policies=require_str_list(
                data.get("unsupported_hard_policies", []),
                "permission_manifest.unsupported_hard_policies",
            ),
            extension_grants=_extension_grants_from_dicts(
                data.get("extension_grants", []),
                "permission_manifest.extension_grants",
            ),
            progress_streams=_progress_streams_from_dicts(
                data.get("progress_streams", []),
                "permission_manifest.progress_streams",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", PERMISSION_MANIFEST_SCHEMA_VERSION),
                "permission_manifest.schema_version",
            ),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        _require_schema(self.schema_version, PERMISSION_MANIFEST_SCHEMA_VERSION, "permission_manifest.schema_version")
        require_non_empty_str(self.manifest_id, "permission_manifest.manifest_id")
        _optional_ref(self.workspace_policy_ref, "permission_manifest.workspace_policy_ref")
        _validate_unique_refs(self.readable_refs, "permission_manifest.readable_refs")
        _validate_unique_refs(self.writable_refs, "permission_manifest.writable_refs")
        _validate_unique_refs(self.denied_refs, "permission_manifest.denied_refs")
        _validate_unique_strings(self.allowed_tools, "permission_manifest.allowed_tools")
        require_str_list(self.allowed_commands, "permission_manifest.allowed_commands")
        require_enum(self.network_policy, NetworkPolicy, "permission_manifest.network_policy")
        require_str_list(self.env_allowlist, "permission_manifest.env_allowlist")
        if self.secret_ref is not None:
            validate_ref(self.secret_ref, "permission_manifest.secret_ref")
        require_str_list(self.unsupported_hard_policies, "permission_manifest.unsupported_hard_policies")
        _validate_extension_grants(self.extension_grants, "permission_manifest.extension_grants")
        _validate_progress_streams(self.progress_streams, "permission_manifest.progress_streams")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "manifest_id": self.manifest_id,
            "schema_version": self.schema_version,
            "workspace_policy_ref": self.workspace_policy_ref,
            "readable_refs": list(self.readable_refs),
            "writable_refs": list(self.writable_refs),
            "denied_refs": list(self.denied_refs),
            "allowed_tools": list(self.allowed_tools),
            "allowed_commands": list(self.allowed_commands),
            "network_policy": self.network_policy.value,
            "env_allowlist": list(self.env_allowlist),
            "secret_ref": self.secret_ref,
            "unsupported_hard_policies": list(self.unsupported_hard_policies),
            "extension_grants": [grant.to_dict() for grant in self.extension_grants],
            "progress_streams": [stream.to_dict() for stream in self.progress_streams],
        }


@dataclass(frozen=True)
class TaskContract:
    """Frozen task obligation compiled by Product Integration."""

    contract_id: str
    product_id: str
    objective: str
    required_outputs: list[ContractClause]
    semantic_acceptance: list[ContractClause]
    hard_constraints: list[ContractClause] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    users_or_audience: list[str] = field(default_factory=list)
    non_goals: list[ContractClause] = field(default_factory=list)
    assumptions: list[ContractClause] = field(default_factory=list)
    risk_notes: list[ContractClause] = field(default_factory=list)
    workspace_policy_ref: str = "contract/workspace_policy.json"
    permission_manifest_ref: str = "contract/permission_manifest.json"
    judge_rubric_ref: str = "contract/judge_rubric.json"
    revision_policy: str | dict[str, Any] = "explicit_revision_required"
    source_refs: list[str] = field(default_factory=list)
    product_contract_refs: list[str] = field(default_factory=list)
    created_by: str = "product.integration"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = TASK_CONTRACT_SCHEMA_VERSION
    contract_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "contract_hash", stable_json_hash(self._content_dict()))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskContract":
        data = require_mapping(payload, "task_contract")
        contract_hash = data.get("contract_hash")
        contract = cls(
            contract_id=require_non_empty_str(data.get("contract_id"), "task_contract.contract_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", TASK_CONTRACT_SCHEMA_VERSION),
                "task_contract.schema_version",
            ),
            product_id=require_non_empty_str(data.get("product_id"), "task_contract.product_id"),
            objective=require_non_empty_str(data.get("objective"), "task_contract.objective"),
            background=_string_or_str_list(data.get("background", []), "task_contract.background"),
            users_or_audience=require_str_list(
                data.get("users_or_audience", []),
                "task_contract.users_or_audience",
            ),
            non_goals=_clauses_or_strings(data.get("non_goals", []), "task_contract.non_goals", "non-goal"),
            assumptions=_clauses_or_strings(data.get("assumptions", []), "task_contract.assumptions", "assumption"),
            required_outputs=_output_clauses_from_dicts(
                data.get("required_outputs", []),
                "task_contract.required_outputs",
            ),
            hard_constraints=_constraint_clauses_from_dicts(
                data.get("hard_constraints", []),
                "task_contract.hard_constraints",
            ),
            semantic_acceptance=_acceptance_clauses_from_dicts(
                data.get("semantic_acceptance", []),
                "task_contract.semantic_acceptance",
            ),
            risk_notes=_clauses_or_strings(data.get("risk_notes", []), "task_contract.risk_notes", "risk"),
            workspace_policy_ref=validate_ref(
                data.get("workspace_policy_ref", "contract/workspace_policy.json"),
                "task_contract.workspace_policy_ref",
            ),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref", "contract/permission_manifest.json"),
                "task_contract.permission_manifest_ref",
            ),
            judge_rubric_ref=validate_ref(
                data.get("judge_rubric_ref", "contract/judge_rubric.json"),
                "task_contract.judge_rubric_ref",
            ),
            revision_policy=_revision_policy(data.get("revision_policy", "explicit_revision_required")),
            source_refs=_ref_list(data.get("source_refs", []), "task_contract.source_refs"),
            product_contract_refs=_ref_list(
                data.get("product_contract_refs", []),
                "task_contract.product_contract_refs",
            ),
            created_by=require_non_empty_str(data.get("created_by", "product.integration"), "task_contract.created_by"),
            created_at=_optional_str(data.get("created_at", ""), "task_contract.created_at"),
            metadata=_safe_mapping(data.get("metadata", {}), "task_contract.metadata"),
        )
        if contract_hash is not None and contract_hash != contract.contract_hash:
            raise ContractValidationError("task_contract.contract_hash does not match contract content")
        return contract

    def validate(self) -> None:
        _require_schema(self.schema_version, TASK_CONTRACT_SCHEMA_VERSION, "task_contract.schema_version")
        require_non_empty_str(self.contract_id, "task_contract.contract_id")
        require_non_empty_str(self.product_id, "task_contract.product_id")
        require_non_empty_str(self.objective, "task_contract.objective")
        require_str_list(self.background, "task_contract.background")
        require_str_list(self.users_or_audience, "task_contract.users_or_audience")
        _validate_clause_list(self.non_goals, "task_contract.non_goals")
        _validate_clause_list(self.assumptions, "task_contract.assumptions")
        _validate_clause_list(self.required_outputs, "task_contract.required_outputs")
        _validate_clause_list(self.hard_constraints, "task_contract.hard_constraints")
        _validate_clause_list(self.semantic_acceptance, "task_contract.semantic_acceptance")
        _validate_clause_list(self.risk_notes, "task_contract.risk_notes")
        if not self.required_outputs:
            raise ContractValidationError("task_contract.required_outputs must not be empty")
        if not self.semantic_acceptance:
            raise ContractValidationError("task_contract.semantic_acceptance must not be empty")
        validate_ref(self.workspace_policy_ref, "task_contract.workspace_policy_ref")
        validate_ref(self.permission_manifest_ref, "task_contract.permission_manifest_ref")
        validate_ref(self.judge_rubric_ref, "task_contract.judge_rubric_ref")
        _revision_policy(self.revision_policy)
        _validate_unique_refs(self.source_refs, "task_contract.source_refs")
        _validate_unique_refs(self.product_contract_refs, "task_contract.product_contract_refs")
        require_non_empty_str(self.created_by, "task_contract.created_by")
        _optional_str(self.created_at, "task_contract.created_at")
        _safe_mapping(self.metadata, "task_contract.metadata")

    def freeze(self) -> dict[str, Any]:
        """Return the frozen contract payload including the derived hash."""

        return self.to_dict()

    def compute_hash(self) -> str:
        """Return the stable hash for the current contract content."""

        return stable_json_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        if self.compute_hash() != self.contract_hash:
            raise ContractValidationError("task_contract content changed after freeze")
        payload = self._content_dict()
        payload["contract_hash"] = self.contract_hash
        return payload

    def _content_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "objective": self.objective,
            "background": list(self.background),
            "users_or_audience": list(self.users_or_audience),
            "non_goals": [item.to_dict() for item in self.non_goals],
            "assumptions": [item.to_dict() for item in self.assumptions],
            "required_outputs": [item.to_dict() for item in self.required_outputs],
            "hard_constraints": [item.to_dict() for item in self.hard_constraints],
            "semantic_acceptance": [item.to_dict() for item in self.semantic_acceptance],
            "risk_notes": [item.to_dict() for item in self.risk_notes],
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "judge_rubric_ref": self.judge_rubric_ref,
            "revision_policy": _revision_policy(self.revision_policy),
            "source_refs": list(self.source_refs),
            "product_contract_refs": list(self.product_contract_refs),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TaskContractRevision:
    """Explicit record for changing a frozen task contract."""

    revision_id: str
    previous_contract_ref: str
    previous_contract_hash: str
    revised_contract_ref: str
    revised_contract_hash: str
    reason: str
    requested_by: str
    approved_by: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = TASK_CONTRACT_REVISION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskContractRevision":
        data = require_mapping(payload, "task_contract_revision")
        approved_by = data.get("approved_by")
        if approved_by is not None:
            approved_by = require_non_empty_str(approved_by, "task_contract_revision.approved_by")
        revision = cls(
            revision_id=require_non_empty_str(data.get("revision_id"), "task_contract_revision.revision_id"),
            previous_contract_ref=validate_ref(
                data.get("previous_contract_ref"),
                "task_contract_revision.previous_contract_ref",
            ),
            previous_contract_hash=require_non_empty_str(
                data.get("previous_contract_hash"),
                "task_contract_revision.previous_contract_hash",
            ),
            revised_contract_ref=validate_ref(
                data.get("revised_contract_ref"),
                "task_contract_revision.revised_contract_ref",
            ),
            revised_contract_hash=require_non_empty_str(
                data.get("revised_contract_hash"),
                "task_contract_revision.revised_contract_hash",
            ),
            reason=require_non_empty_str(data.get("reason"), "task_contract_revision.reason"),
            requested_by=require_non_empty_str(data.get("requested_by"), "task_contract_revision.requested_by"),
            approved_by=approved_by,
            evidence_refs=_ref_list(data.get("evidence_refs", []), "task_contract_revision.evidence_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", TASK_CONTRACT_REVISION_SCHEMA_VERSION),
                "task_contract_revision.schema_version",
            ),
        )
        revision.validate()
        return revision

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            TASK_CONTRACT_REVISION_SCHEMA_VERSION,
            "task_contract_revision.schema_version",
        )
        require_non_empty_str(self.revision_id, "task_contract_revision.revision_id")
        validate_ref(self.previous_contract_ref, "task_contract_revision.previous_contract_ref")
        _validate_hash(self.previous_contract_hash, "task_contract_revision.previous_contract_hash")
        validate_ref(self.revised_contract_ref, "task_contract_revision.revised_contract_ref")
        _validate_hash(self.revised_contract_hash, "task_contract_revision.revised_contract_hash")
        if self.previous_contract_hash == self.revised_contract_hash:
            raise ContractValidationError("task_contract_revision must change the contract hash")
        require_non_empty_str(self.reason, "task_contract_revision.reason")
        require_non_empty_str(self.requested_by, "task_contract_revision.requested_by")
        if self.approved_by is not None:
            require_non_empty_str(self.approved_by, "task_contract_revision.approved_by")
        _validate_unique_refs(self.evidence_refs, "task_contract_revision.evidence_refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "revision_id": self.revision_id,
            "schema_version": self.schema_version,
            "previous_contract_ref": self.previous_contract_ref,
            "previous_contract_hash": self.previous_contract_hash,
            "revised_contract_ref": self.revised_contract_ref,
            "revised_contract_hash": self.revised_contract_hash,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "approved_by": self.approved_by,
            "evidence_refs": list(self.evidence_refs),
        }


def _clauses_from_dicts(value: Any, field_name: str) -> list[ContractClause]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    clauses = [ContractClause.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]
    _validate_clause_list(clauses, field_name)
    return clauses


def _extension_grants_from_dicts(value: Any, field_name: str) -> list[ExtensionGrant]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    grants = [ExtensionGrant.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]
    _validate_extension_grants(grants, field_name)
    return grants


def _progress_streams_from_dicts(value: Any, field_name: str) -> list[ProgressStreamGrant]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    streams = [ProgressStreamGrant.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]
    _validate_progress_streams(streams, field_name)
    return streams


def _output_clauses_from_dicts(value: Any, field_name: str) -> list[ContractClause]:
    return _mapped_clauses(
        value,
        field_name,
        id_key="output_id",
        text_key="description",
        refs_key="artifact_refs",
    )


def _constraint_clauses_from_dicts(value: Any, field_name: str) -> list[ContractClause]:
    return _mapped_clauses(
        value,
        field_name,
        id_key="constraint_id",
        text_key="statement",
        refs_key="source_refs",
    )


def _acceptance_clauses_from_dicts(value: Any, field_name: str) -> list[ContractClause]:
    return _mapped_clauses(
        value,
        field_name,
        id_key="criterion_id",
        text_key="statement",
        refs_key="evidence_refs",
    )


def _mapped_clauses(value: Any, field_name: str, *, id_key: str, text_key: str, refs_key: str) -> list[ContractClause]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    clauses: list[ContractClause] = []
    for item in value:
        data = require_mapping(item, f"{field_name}[]")
        if "clause_id" in data:
            clauses.append(ContractClause.from_dict(data))
            continue
        clauses.append(
            ContractClause(
                clause_id=require_non_empty_str(data.get(id_key), f"{field_name}.{id_key}"),
                text=require_non_empty_str(data.get(text_key), f"{field_name}.{text_key}"),
                refs=_ref_list(data.get(refs_key, []), f"{field_name}.{refs_key}"),
                metadata=_safe_mapping(data.get("metadata", {}), f"{field_name}.metadata"),
            )
        )
    _validate_clause_list(clauses, field_name)
    return clauses


def _clauses_or_strings(value: Any, field_name: str, id_prefix: str) -> list[ContractClause]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    clauses: list[ContractClause] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            clauses.append(
                ContractClause(
                    clause_id=f"{id_prefix}-{index:03d}",
                    text=require_non_empty_str(item, f"{field_name}[]"),
                )
            )
            continue
        clauses.append(ContractClause.from_dict(require_mapping(item, f"{field_name}[]")))
    _validate_clause_list(clauses, field_name)
    return clauses


def _validate_clause_list(clauses: list[ContractClause], field_name: str) -> None:
    seen: set[str] = set()
    for clause in clauses:
        clause.validate()
        if clause.clause_id in seen:
            raise ContractValidationError(f"duplicate {field_name} clause_id: {clause.clause_id}")
        seen.add(clause.clause_id)


def _validate_extension_grants(grants: list[ExtensionGrant], field_name: str) -> None:
    if not isinstance(grants, list):
        raise ContractValidationError(f"{field_name} must be a list")
    seen: set[str] = set()
    for grant in grants:
        if not isinstance(grant, ExtensionGrant):
            raise ContractValidationError(f"{field_name}[] must be an ExtensionGrant")
        grant.validate()
        if grant.grant_id in seen:
            raise ContractValidationError(f"duplicate {field_name} grant_id: {grant.grant_id}")
        seen.add(grant.grant_id)


def _validate_progress_streams(streams: list[ProgressStreamGrant], field_name: str) -> None:
    if not isinstance(streams, list):
        raise ContractValidationError(f"{field_name} must be a list")
    seen: set[str] = set()
    for stream in streams:
        if not isinstance(stream, ProgressStreamGrant):
            raise ContractValidationError(f"{field_name}[] must be a ProgressStreamGrant")
        stream.validate()
        if stream.stream_id in seen:
            raise ContractValidationError(f"duplicate {field_name} stream_id: {stream.stream_id}")
        seen.add(stream.stream_id)


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _validate_unique_strings(values: list[str], field_name: str) -> None:
    items = require_str_list(values, field_name)
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")


def _safe_mapping(value: Any, field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(value, field_name), field_name))


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _validate_extension_package(value: Any, field_name: str) -> str:
    package = require_non_empty_str(value, field_name)
    allowed_prefixes = ("npm:", "local:")
    if not package.startswith(allowed_prefixes):
        raise ContractValidationError(f"{field_name} must start with one of {allowed_prefixes}")
    if any(ord(char) < 32 or ord(char) == 127 for char in package):
        raise ContractValidationError(f"{field_name} must not contain control characters")
    if package.startswith("local:"):
        validate_ref(package[len("local:"):], field_name)
    return package


def _validate_env_name(value: Any, field_name: str) -> str:
    name = require_non_empty_str(value, field_name)
    if not (name[0].isalpha() or name[0] == "_"):
        raise ContractValidationError(f"{field_name} must be an environment variable name")
    if not all(char.isalnum() or char == "_" for char in name):
        raise ContractValidationError(f"{field_name} must be an environment variable name")
    return name


def _revision_policy(value: Any) -> str | dict[str, Any]:
    if isinstance(value, str):
        return require_non_empty_str(value, "task_contract.revision_policy")
    return _safe_mapping(value, "task_contract.revision_policy")


def _optional_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be a string")
    return value


def _string_or_str_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        return [require_non_empty_str(value, field_name)]
    return require_str_list(value, field_name)


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix):]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")

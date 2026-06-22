"""Kernel API data contracts.

These contracts are a product-neutral facade over the existing MissionForge
core. They describe Step/Flow composition without replacing TaskContract,
PermissionManifest, PiWorkerCall, or the tool gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from ..piworker_call import PiWorkerCallRole
from ..task_contract import ExtensionAdapterMode, ExtensionCapability


class KernelValidationError(ContractValidationError):
    """Raised when a kernel Step/Flow declaration is invalid."""


class ArtifactRole(StrEnum):
    """Product-neutral artifact handling role."""

    INPUT = "input"
    OUTPUT = "output"
    DECISION = "decision"
    STATE = "state"
    PROJECTION = "projection"
    LEDGER = "ledger"


class StepStatus(StrEnum):
    """Refs-first status for one kernel step boundary."""

    SKIPPED = "skipped"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class FlowLedgerEventKind(StrEnum):
    """Product-neutral flow ledger event kinds."""

    STARTED = "started"
    STEP_STARTED = "step_started"
    STEP_RECORDED = "step_recorded"
    ROUTED = "routed"
    PROJECTIONS_RECORDED = "projections_recorded"
    STOPPED = "stopped"


@dataclass(frozen=True)
class Artifact:
    """Declaration for one product-visible or runtime-visible artifact."""

    ref: str
    role: ArtifactRole = ArtifactRole.OUTPUT
    owner: str = "piworker"
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Artifact":
        data = _refs_only_mapping(payload, "kernel_artifact")
        artifact = cls(
            ref=validate_ref(data.get("ref"), "kernel_artifact.ref"),
            role=require_enum(data.get("role", ArtifactRole.OUTPUT.value), ArtifactRole, "kernel_artifact.role"),
            owner=require_non_empty_str(data.get("owner", "piworker"), "kernel_artifact.owner"),
            required=_bool(data.get("required", True), "kernel_artifact.required"),
            metadata=_metadata(data.get("metadata", {}), "kernel_artifact.metadata"),
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        validate_ref(self.ref, "kernel_artifact.ref")
        require_enum(self.role, ArtifactRole, "kernel_artifact.role")
        owner = require_non_empty_str(self.owner, "kernel_artifact.owner")
        if owner not in {"piworker", "runtime", "product"}:
            raise KernelValidationError("kernel_artifact.owner must be piworker, runtime, or product")
        if self.role in {ArtifactRole.PROJECTION, ArtifactRole.LEDGER} and owner != "runtime":
            raise KernelValidationError("projection and ledger artifacts must be runtime-owned")
        _bool(self.required, "kernel_artifact.required")
        _metadata(self.metadata, "kernel_artifact.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "ref": self.ref,
            "role": self.role.value,
            "owner": self.owner,
            "required": self.required,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Toolset:
    """Declaration for an extension-backed tool group."""

    id: str
    package: str
    tools: list[str] = field(default_factory=list)
    capability: ExtensionCapability = ExtensionCapability.WEB
    version_spec: str = "0.1.0"
    network: bool = False
    bash: bool = False
    required_env: list[str] = field(default_factory=list)
    adapter_mode: ExtensionAdapterMode = ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION
    config_ref: str | None = None
    integrity: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Toolset":
        data = _refs_only_mapping(payload, "kernel_toolset")
        toolset = cls(
            id=_safe_id(data.get("id"), "kernel_toolset.id"),
            package=require_non_empty_str(data.get("package"), "kernel_toolset.package"),
            tools=require_str_list(data.get("tools", []), "kernel_toolset.tools"),
            capability=require_enum(
                data.get("capability", ExtensionCapability.WEB.value),
                ExtensionCapability,
                "kernel_toolset.capability",
            ),
            version_spec=require_non_empty_str(data.get("version_spec", "0.1.0"), "kernel_toolset.version_spec"),
            network=_bool(data.get("network", False), "kernel_toolset.network"),
            bash=_bool(data.get("bash", False), "kernel_toolset.bash"),
            required_env=require_str_list(data.get("required_env", []), "kernel_toolset.required_env"),
            adapter_mode=require_enum(
                data.get("adapter_mode", ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION.value),
                ExtensionAdapterMode,
                "kernel_toolset.adapter_mode",
            ),
            config_ref=_optional_ref(data.get("config_ref"), "kernel_toolset.config_ref"),
            integrity=_optional_non_empty_str(data.get("integrity"), "kernel_toolset.integrity"),
            metadata=_metadata(data.get("metadata", {}), "kernel_toolset.metadata"),
        )
        toolset.validate()
        return toolset

    def validate(self) -> None:
        _safe_id(self.id, "kernel_toolset.id")
        require_non_empty_str(self.package, "kernel_toolset.package")
        _unique_non_empty_strings(self.tools, "kernel_toolset.tools")
        require_enum(self.capability, ExtensionCapability, "kernel_toolset.capability")
        require_non_empty_str(self.version_spec, "kernel_toolset.version_spec")
        _bool(self.network, "kernel_toolset.network")
        _bool(self.bash, "kernel_toolset.bash")
        _unique_non_empty_strings(self.required_env, "kernel_toolset.required_env")
        require_enum(self.adapter_mode, ExtensionAdapterMode, "kernel_toolset.adapter_mode")
        _optional_ref(self.config_ref, "kernel_toolset.config_ref")
        _optional_non_empty_str(self.integrity, "kernel_toolset.integrity")
        _metadata(self.metadata, "kernel_toolset.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "package": self.package,
            "tools": list(self.tools),
            "capability": self.capability.value,
            "version_spec": self.version_spec,
            "network": self.network,
            "bash": self.bash,
            "required_env": list(self.required_env),
            "adapter_mode": self.adapter_mode.value,
            "config_ref": self.config_ref,
            "integrity": self.integrity,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Projection:
    """Runtime-owned mechanical artifact declaration."""

    output: str
    from_: list[str]
    projector: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Projection":
        data = _refs_only_mapping(payload, "kernel_projection")
        projection = cls(
            output=validate_ref(data.get("output"), "kernel_projection.output"),
            from_=_ref_list(data.get("from", data.get("from_", [])), "kernel_projection.from"),
            projector=_safe_id(data.get("projector"), "kernel_projection.projector"),
            metadata=_metadata(data.get("metadata", {}), "kernel_projection.metadata"),
        )
        projection.validate()
        return projection

    def validate(self) -> None:
        validate_ref(self.output, "kernel_projection.output")
        if not self.from_:
            raise KernelValidationError("kernel_projection.from must not be empty")
        _unique_refs(self.from_, "kernel_projection.from")
        _safe_id(self.projector, "kernel_projection.projector")
        _metadata(self.metadata, "kernel_projection.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "output": self.output,
            "from": list(self.from_),
            "projector": self.projector,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProjectionRecord:
    """Refs-first record for one runtime-owned projection."""

    output_ref: str
    projector: str
    source_refs: list[str]
    source_hashes: Mapping[str, str]
    output_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectionRecord":
        data = _refs_only_mapping(payload, "kernel_projection_record")
        record = cls(
            output_ref=validate_ref(data.get("output_ref"), "kernel_projection_record.output_ref"),
            projector=_safe_id(data.get("projector"), "kernel_projection_record.projector"),
            source_refs=_ref_list(data.get("source_refs", []), "kernel_projection_record.source_refs"),
            source_hashes=_hash_mapping(data.get("source_hashes", {}), "kernel_projection_record.source_hashes"),
            output_hash=_hash(data.get("output_hash"), "kernel_projection_record.output_hash"),
            metadata=_metadata(data.get("metadata", {}), "kernel_projection_record.metadata"),
        )
        record.validate()
        return record

    def validate(self) -> None:
        validate_ref(self.output_ref, "kernel_projection_record.output_ref")
        _safe_id(self.projector, "kernel_projection_record.projector")
        _unique_refs(self.source_refs, "kernel_projection_record.source_refs")
        if not self.source_refs:
            raise KernelValidationError("kernel_projection_record.source_refs must not be empty")
        _hash_mapping(self.source_hashes, "kernel_projection_record.source_hashes")
        _hash(self.output_hash, "kernel_projection_record.output_hash")
        _metadata(self.metadata, "kernel_projection_record.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "output_ref": self.output_ref,
            "projector": self.projector,
            "source_refs": list(self.source_refs),
            "source_hashes": dict(self.source_hashes),
            "output_hash": self.output_hash,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FailurePolicy:
    """Bounded retry and exhausted-status declaration."""

    retries: int = 0
    on_exhausted: StepStatus = StepStatus.FAILED

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FailurePolicy":
        data = _refs_only_mapping(payload, "kernel_failure_policy")
        policy = cls(
            retries=require_int_at_least(data.get("retries", 0), "kernel_failure_policy.retries", 0),
            on_exhausted=require_enum(
                data.get("on_exhausted", StepStatus.FAILED.value),
                StepStatus,
                "kernel_failure_policy.on_exhausted",
            ),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        require_int_at_least(self.retries, "kernel_failure_policy.retries", 0)
        status = require_enum(self.on_exhausted, StepStatus, "kernel_failure_policy.on_exhausted")
        if status in {StepStatus.SKIPPED, StepStatus.COMPLETED}:
            raise KernelValidationError("kernel_failure_policy.on_exhausted must be failed or blocked")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "retries": self.retries,
            "on_exhausted": self.on_exhausted.value,
        }


@dataclass(frozen=True)
class Step:
    """One white-box PiWorker work unit."""

    id: str
    brief: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    read: list[str] = field(default_factory=list)
    write: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=lambda: ["read", "write"])
    role: PiWorkerCallRole = PiWorkerCallRole.EXECUTOR
    route_on: str | None = None
    route_fields: list[str] = field(default_factory=list)
    runtime_budget: Mapping[str, Any] = field(default_factory=dict)
    command_allowlist: list[str] = field(default_factory=list)
    env_allowlist: list[str] = field(default_factory=list)
    network: bool = False
    failure: FailurePolicy = field(default_factory=FailurePolicy)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Step":
        data = _refs_only_mapping(payload, "kernel_step")
        failure_payload = data.get("failure", {})
        failure = failure_payload if isinstance(failure_payload, FailurePolicy) else FailurePolicy.from_dict(failure_payload)
        step = cls(
            id=_safe_id(data.get("id"), "kernel_step.id"),
            brief=require_non_empty_str(data.get("brief"), "kernel_step.brief"),
            inputs=_ref_list(data.get("inputs", []), "kernel_step.inputs"),
            outputs=_ref_list(data.get("outputs", []), "kernel_step.outputs"),
            read=_ref_list(data.get("read", []), "kernel_step.read"),
            write=_ref_list(data.get("write", []), "kernel_step.write"),
            tools=require_str_list(data.get("tools", ["read", "write"]), "kernel_step.tools"),
            role=require_enum(data.get("role", PiWorkerCallRole.EXECUTOR.value), PiWorkerCallRole, "kernel_step.role"),
            route_on=_optional_ref(data.get("route_on"), "kernel_step.route_on"),
            route_fields=require_str_list(data.get("route_fields", []), "kernel_step.route_fields"),
            runtime_budget=_runtime_budget(data.get("runtime_budget", {}), "kernel_step.runtime_budget"),
            command_allowlist=require_str_list(data.get("command_allowlist", []), "kernel_step.command_allowlist"),
            env_allowlist=require_str_list(data.get("env_allowlist", []), "kernel_step.env_allowlist"),
            network=_bool(data.get("network", False), "kernel_step.network"),
            failure=failure,
            metadata=_metadata(data.get("metadata", {}), "kernel_step.metadata"),
        )
        step.validate()
        return step

    def validate(self) -> None:
        _safe_id(self.id, "kernel_step.id")
        require_non_empty_str(self.brief, "kernel_step.brief")
        _unique_refs(self.inputs, "kernel_step.inputs")
        _unique_refs(self.outputs, "kernel_step.outputs")
        if not self.outputs:
            raise KernelValidationError("kernel_step.outputs must not be empty")
        _unique_refs(self.read, "kernel_step.read")
        _unique_refs(self.write, "kernel_step.write")
        if not self.read:
            raise KernelValidationError("kernel_step.read must not be empty")
        if not self.write:
            raise KernelValidationError("kernel_step.write must not be empty")
        _unique_non_empty_strings(self.tools, "kernel_step.tools")
        require_enum(self.role, PiWorkerCallRole, "kernel_step.role")
        _optional_ref(self.route_on, "kernel_step.route_on")
        if self.route_on is not None and self.route_on not in self.outputs:
            raise KernelValidationError("kernel_step.route_on must be one of kernel_step.outputs")
        _unique_non_empty_strings(self.route_fields, "kernel_step.route_fields")
        _runtime_budget(self.runtime_budget, "kernel_step.runtime_budget")
        _unique_non_empty_strings(self.command_allowlist, "kernel_step.command_allowlist")
        _unique_non_empty_strings(self.env_allowlist, "kernel_step.env_allowlist")
        _bool(self.network, "kernel_step.network")
        if "bash" in self.tools and not self.command_allowlist:
            raise KernelValidationError("kernel_step using bash requires command_allowlist")
        self.failure.validate()
        _metadata(self.metadata, "kernel_step.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "brief": self.brief,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "read": list(self.read),
            "write": list(self.write),
            "tools": list(self.tools),
            "role": self.role.value,
            "route_on": self.route_on,
            "route_fields": list(self.route_fields),
            "runtime_budget": dict(self.runtime_budget),
            "command_allowlist": list(self.command_allowlist),
            "env_allowlist": list(self.env_allowlist),
            "network": self.network,
            "failure": self.failure.to_dict(),
            "metadata": dict(self.metadata),
        }

    @property
    def spec_hash(self) -> str:
        return stable_json_hash(self.to_dict())


@dataclass(frozen=True)
class FlowStop:
    """Terminal route target."""

    status: str

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FlowStop":
        data = _refs_only_mapping(payload, "kernel_flow_stop")
        stop = cls(status=_safe_id(data.get("status"), "kernel_flow_stop.status"))
        stop.validate()
        return stop

    def validate(self) -> None:
        _safe_id(self.status, "kernel_flow_stop.status")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"status": self.status}


@dataclass(frozen=True)
class Flow:
    """Step composition and route declaration."""

    id: str
    steps: list[Step]
    routes: Mapping[str, str | FlowStop] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    toolsets: list[Toolset] = field(default_factory=list)
    projections: list[Projection] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @staticmethod
    def stop(status: str) -> FlowStop:
        return FlowStop(status=_safe_id(status, "kernel_flow_stop.status"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Flow":
        data = _refs_only_mapping(payload, "kernel_flow")
        routes = require_mapping(data.get("routes", {}), "kernel_flow.routes")
        flow = cls(
            id=_safe_id(data.get("id"), "kernel_flow.id"),
            steps=[Step.from_dict(item) for item in _mapping_list(data.get("steps", []), "kernel_flow.steps")],
            routes={
                require_non_empty_str(key, "kernel_flow.routes.key"): _route_target(value)
                for key, value in routes.items()
            },
            artifacts=[Artifact.from_dict(item) for item in _mapping_list(data.get("artifacts", []), "kernel_flow.artifacts")],
            toolsets=[Toolset.from_dict(item) for item in _mapping_list(data.get("toolsets", []), "kernel_flow.toolsets")],
            projections=[
                Projection.from_dict(item) for item in _mapping_list(data.get("projections", []), "kernel_flow.projections")
            ],
            metadata=_metadata(data.get("metadata", {}), "kernel_flow.metadata"),
        )
        flow.validate()
        return flow

    def validate(self) -> None:
        _safe_id(self.id, "kernel_flow.id")
        if not self.steps:
            raise KernelValidationError("kernel_flow.steps must not be empty")
        step_ids = _unique_ids([step.id for step in self.steps], "kernel_flow.steps[].id")
        step_by_id = {step.id: step for step in self.steps}
        artifact_by_ref = {artifact.ref: artifact for artifact in self.artifacts}
        step_output_refs = {ref for step in self.steps for ref in step.outputs}
        _unique_ids([toolset.id for toolset in self.toolsets], "kernel_flow.toolsets[].id")
        _unique_refs([artifact.ref for artifact in self.artifacts], "kernel_flow.artifacts[].ref")
        _unique_refs([projection.output for projection in self.projections], "kernel_flow.projections[].output")
        for step in self.steps:
            step.validate()
        for projection in self.projections:
            projection.validate()
            if projection.output in step_output_refs:
                raise KernelValidationError(f"kernel_flow projection output conflicts with step output: {projection.output}")
            artifact = artifact_by_ref.get(projection.output)
            if artifact is None:
                raise KernelValidationError(f"kernel_flow projection output artifact must be declared: {projection.output}")
            if artifact.owner != "runtime" or artifact.role != ArtifactRole.PROJECTION:
                raise KernelValidationError("kernel_flow projection output artifact must be runtime-owned projection")
        for route_key, target in self.routes.items():
            source_step, _value = _route_key(route_key)
            if source_step not in step_ids:
                raise KernelValidationError(f"kernel_flow route source step is unknown: {source_step}")
            source = step_by_id[source_step]
            if source.route_on is None:
                raise KernelValidationError(f"kernel_flow route source step must declare route_on: {source_step}")
            if not source.route_fields:
                raise KernelValidationError(f"kernel_flow route source step must declare route_fields: {source_step}")
            route_artifact = artifact_by_ref.get(source.route_on)
            if route_artifact is None:
                raise KernelValidationError(f"kernel_flow route_on artifact must be declared: {source.route_on}")
            if route_artifact.owner != "piworker" or route_artifact.role != ArtifactRole.DECISION:
                raise KernelValidationError("kernel_flow route_on artifact must be piworker-owned decision artifact")
            if isinstance(target, FlowStop):
                target.validate()
                if target.status == "accepted" and source.role != PiWorkerCallRole.JUDGE:
                    raise KernelValidationError("kernel_flow accepted stop must be routed from a judge step")
                if target.status == "accepted" and not _judge_accepts_prior_non_judge_output(source, self.steps):
                    raise KernelValidationError("kernel_flow accepted stop must be based on a prior non-judge step output")
            else:
                target_id = _safe_id(target, "kernel_flow.routes.target")
                if target_id not in step_ids:
                    raise KernelValidationError(f"kernel_flow route target step is unknown: {target_id}")
        _metadata(self.metadata, "kernel_flow.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "steps": [step.to_dict() for step in self.steps],
            "routes": {key: _route_target_to_dict(value) for key, value in self.routes.items()},
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "toolsets": [toolset.to_dict() for toolset in self.toolsets],
            "projections": [projection.to_dict() for projection in self.projections],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StepRecord:
    """Refs-first record for one step boundary."""

    step_id: str
    step_spec_hash: str
    contract_ref: str
    contract_hash: str
    input_refs: list[str]
    output_refs: list[str]
    status: StepStatus
    permission_manifest_ref: str
    permission_manifest_hash: str | None = None
    extension_lock_ref: str | None = None
    extension_lock_hash: str | None = None
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    output_hashes: Mapping[str, str] = field(default_factory=dict)
    piworker_call_ref: str | None = None
    piworker_call_result_ref: str | None = None
    execution_report_ref: str | None = None
    metric_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StepRecord":
        data = _refs_only_mapping(payload, "kernel_step_record")
        record = cls(
            step_id=_safe_id(data.get("step_id"), "kernel_step_record.step_id"),
            step_spec_hash=_hash(data.get("step_spec_hash"), "kernel_step_record.step_spec_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "kernel_step_record.contract_ref"),
            contract_hash=_hash(data.get("contract_hash"), "kernel_step_record.contract_hash"),
            input_refs=_ref_list(data.get("input_refs", []), "kernel_step_record.input_refs"),
            output_refs=_ref_list(data.get("output_refs", []), "kernel_step_record.output_refs"),
            input_hashes=_hash_mapping(data.get("input_hashes", {}), "kernel_step_record.input_hashes"),
            output_hashes=_hash_mapping(data.get("output_hashes", {}), "kernel_step_record.output_hashes"),
            status=require_enum(data.get("status"), StepStatus, "kernel_step_record.status"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "kernel_step_record.permission_manifest_ref",
            ),
            permission_manifest_hash=_optional_hash(
                data.get("permission_manifest_hash"),
                "kernel_step_record.permission_manifest_hash",
            ),
            extension_lock_ref=_optional_ref(data.get("extension_lock_ref"), "kernel_step_record.extension_lock_ref"),
            extension_lock_hash=_optional_hash(
                data.get("extension_lock_hash"),
                "kernel_step_record.extension_lock_hash",
            ),
            piworker_call_ref=_optional_ref(data.get("piworker_call_ref"), "kernel_step_record.piworker_call_ref"),
            piworker_call_result_ref=_optional_ref(
                data.get("piworker_call_result_ref"),
                "kernel_step_record.piworker_call_result_ref",
            ),
            execution_report_ref=_optional_ref(
                data.get("execution_report_ref"),
                "kernel_step_record.execution_report_ref",
            ),
            metric_refs=_ref_list(data.get("metric_refs", []), "kernel_step_record.metric_refs"),
            failure_refs=_ref_list(data.get("failure_refs", []), "kernel_step_record.failure_refs"),
            metadata=_metadata(data.get("metadata", {}), "kernel_step_record.metadata"),
        )
        record.validate()
        return record

    def validate(self) -> None:
        _safe_id(self.step_id, "kernel_step_record.step_id")
        _hash(self.step_spec_hash, "kernel_step_record.step_spec_hash")
        validate_ref(self.contract_ref, "kernel_step_record.contract_ref")
        _hash(self.contract_hash, "kernel_step_record.contract_hash")
        _unique_refs(self.input_refs, "kernel_step_record.input_refs")
        _unique_refs(self.output_refs, "kernel_step_record.output_refs")
        _hash_mapping(self.input_hashes, "kernel_step_record.input_hashes")
        _hash_mapping(self.output_hashes, "kernel_step_record.output_hashes")
        require_enum(self.status, StepStatus, "kernel_step_record.status")
        validate_ref(self.permission_manifest_ref, "kernel_step_record.permission_manifest_ref")
        _optional_hash(self.permission_manifest_hash, "kernel_step_record.permission_manifest_hash")
        _optional_ref(self.extension_lock_ref, "kernel_step_record.extension_lock_ref")
        _optional_hash(self.extension_lock_hash, "kernel_step_record.extension_lock_hash")
        _optional_ref(self.piworker_call_ref, "kernel_step_record.piworker_call_ref")
        _optional_ref(self.piworker_call_result_ref, "kernel_step_record.piworker_call_result_ref")
        _optional_ref(self.execution_report_ref, "kernel_step_record.execution_report_ref")
        _unique_refs(self.metric_refs, "kernel_step_record.metric_refs")
        _unique_refs(self.failure_refs, "kernel_step_record.failure_refs")
        _metadata(self.metadata, "kernel_step_record.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "step_id": self.step_id,
            "step_spec_hash": self.step_spec_hash,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "input_hashes": dict(self.input_hashes),
            "output_hashes": dict(self.output_hashes),
            "status": self.status.value,
            "permission_manifest_ref": self.permission_manifest_ref,
            "permission_manifest_hash": self.permission_manifest_hash,
            "extension_lock_ref": self.extension_lock_ref,
            "extension_lock_hash": self.extension_lock_hash,
            "piworker_call_ref": self.piworker_call_ref,
            "piworker_call_result_ref": self.piworker_call_result_ref,
            "execution_report_ref": self.execution_report_ref,
            "metric_refs": list(self.metric_refs),
            "failure_refs": list(self.failure_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FlowResult:
    """Refs-first record for one Flow run."""

    flow_id: str
    run_id: str
    contract_ref: str
    contract_hash: str
    status: str
    step_record_refs: list[str] = field(default_factory=list)
    final_artifact_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    ledger_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FlowResult":
        data = _refs_only_mapping(payload, "kernel_flow_result")
        result = cls(
            flow_id=_safe_id(data.get("flow_id"), "kernel_flow_result.flow_id"),
            run_id=_safe_id(data.get("run_id"), "kernel_flow_result.run_id"),
            contract_ref=validate_ref(data.get("contract_ref"), "kernel_flow_result.contract_ref"),
            contract_hash=_hash(data.get("contract_hash"), "kernel_flow_result.contract_hash"),
            status=_safe_id(data.get("status"), "kernel_flow_result.status"),
            step_record_refs=_ref_list(data.get("step_record_refs", []), "kernel_flow_result.step_record_refs"),
            final_artifact_refs=_ref_list(
                data.get("final_artifact_refs", []),
                "kernel_flow_result.final_artifact_refs",
            ),
            decision_refs=_ref_list(data.get("decision_refs", []), "kernel_flow_result.decision_refs"),
            ledger_refs=_ref_list(data.get("ledger_refs", []), "kernel_flow_result.ledger_refs"),
            metadata=_metadata(data.get("metadata", {}), "kernel_flow_result.metadata"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        _safe_id(self.flow_id, "kernel_flow_result.flow_id")
        _safe_id(self.run_id, "kernel_flow_result.run_id")
        validate_ref(self.contract_ref, "kernel_flow_result.contract_ref")
        _hash(self.contract_hash, "kernel_flow_result.contract_hash")
        _safe_id(self.status, "kernel_flow_result.status")
        _unique_refs(self.step_record_refs, "kernel_flow_result.step_record_refs")
        _unique_refs(self.final_artifact_refs, "kernel_flow_result.final_artifact_refs")
        _unique_refs(self.decision_refs, "kernel_flow_result.decision_refs")
        _unique_refs(self.ledger_refs, "kernel_flow_result.ledger_refs")
        _metadata(self.metadata, "kernel_flow_result.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "flow_id": self.flow_id,
            "run_id": self.run_id,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "status": self.status,
            "step_record_refs": list(self.step_record_refs),
            "final_artifact_refs": list(self.final_artifact_refs),
            "decision_refs": list(self.decision_refs),
            "ledger_refs": list(self.ledger_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FlowLedgerEvent:
    """Refs-first event for one Kernel Flow execution trace."""

    event_id: str
    flow_id: str
    run_id: str
    kind: FlowLedgerEventKind
    step_id: str | None = None
    status: str | None = None
    step_record_ref: str | None = None
    decision_ref: str | None = None
    route_value: str | None = None
    route_target: str | None = None
    stop_reason: str | None = None
    refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FlowLedgerEvent":
        data = _refs_only_mapping(payload, "kernel_flow_ledger_event")
        event = cls(
            event_id=_safe_id(data.get("event_id"), "kernel_flow_ledger_event.event_id"),
            flow_id=_safe_id(data.get("flow_id"), "kernel_flow_ledger_event.flow_id"),
            run_id=_safe_id(data.get("run_id"), "kernel_flow_ledger_event.run_id"),
            kind=require_enum(
                data.get("kind"),
                FlowLedgerEventKind,
                "kernel_flow_ledger_event.kind",
            ),
            step_id=_optional_safe_id(data.get("step_id"), "kernel_flow_ledger_event.step_id"),
            status=_optional_safe_id(data.get("status"), "kernel_flow_ledger_event.status"),
            step_record_ref=_optional_ref(
                data.get("step_record_ref"),
                "kernel_flow_ledger_event.step_record_ref",
            ),
            decision_ref=_optional_ref(data.get("decision_ref"), "kernel_flow_ledger_event.decision_ref"),
            route_value=_optional_safe_id(data.get("route_value"), "kernel_flow_ledger_event.route_value"),
            route_target=_optional_safe_id(data.get("route_target"), "kernel_flow_ledger_event.route_target"),
            stop_reason=_optional_safe_id(data.get("stop_reason"), "kernel_flow_ledger_event.stop_reason"),
            refs=_ref_list(data.get("refs", []), "kernel_flow_ledger_event.refs"),
            metadata=_metadata(data.get("metadata", {}), "kernel_flow_ledger_event.metadata"),
        )
        event.validate()
        return event

    def validate(self) -> None:
        _safe_id(self.event_id, "kernel_flow_ledger_event.event_id")
        _safe_id(self.flow_id, "kernel_flow_ledger_event.flow_id")
        _safe_id(self.run_id, "kernel_flow_ledger_event.run_id")
        require_enum(self.kind, FlowLedgerEventKind, "kernel_flow_ledger_event.kind")
        _optional_safe_id(self.step_id, "kernel_flow_ledger_event.step_id")
        _optional_safe_id(self.status, "kernel_flow_ledger_event.status")
        _optional_ref(self.step_record_ref, "kernel_flow_ledger_event.step_record_ref")
        _optional_ref(self.decision_ref, "kernel_flow_ledger_event.decision_ref")
        _optional_safe_id(self.route_value, "kernel_flow_ledger_event.route_value")
        _optional_safe_id(self.route_target, "kernel_flow_ledger_event.route_target")
        _optional_safe_id(self.stop_reason, "kernel_flow_ledger_event.stop_reason")
        _unique_refs(self.refs, "kernel_flow_ledger_event.refs")
        _metadata(self.metadata, "kernel_flow_ledger_event.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "event_id": self.event_id,
            "flow_id": self.flow_id,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "step_id": self.step_id,
            "status": self.status,
            "step_record_ref": self.step_record_ref,
            "decision_ref": self.decision_ref,
            "route_value": self.route_value,
            "route_target": self.route_target,
            "stop_reason": self.stop_reason,
            "refs": list(self.refs),
            "metadata": dict(self.metadata),
        }


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _mapping_list(value: Any, field_name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise KernelValidationError(f"{field_name} must be a list")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise KernelValidationError(f"{field_name}[{index}] must be a mapping")
        result.append(item)
    return result


def _judge_accepts_prior_non_judge_output(source: Step, steps: list[Step]) -> bool:
    prior_non_judge_outputs: set[str] = set()
    for step in steps:
        if step.id == source.id:
            break
        if step.role != PiWorkerCallRole.JUDGE:
            prior_non_judge_outputs.update(step.outputs)
    return bool(prior_non_judge_outputs.intersection(source.inputs))


def _safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise KernelValidationError(f"{field_name} must be a single safe id segment")
    validate_ref(text, field_name)
    return text


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return validate_ref(value, field_name)


def _optional_safe_id(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return _safe_id(value, field_name)


def _optional_non_empty_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _unique_refs(values: list[str], field_name: str) -> list[str]:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise KernelValidationError(f"{field_name} must not contain duplicates")
    return refs


def _unique_non_empty_strings(values: list[str], field_name: str) -> list[str]:
    items = require_str_list(values, field_name)
    if len(items) != len(set(items)):
        raise KernelValidationError(f"{field_name} must not contain duplicates")
    return items


def _unique_ids(values: list[str], field_name: str) -> set[str]:
    ids = [_safe_id(value, field_name) for value in values]
    if len(ids) != len(set(ids)):
        raise KernelValidationError(f"{field_name} must not contain duplicates")
    return set(ids)


def _bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise KernelValidationError(f"{field_name} must be a boolean")
    return value


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _runtime_budget(value: Any, field_name: str) -> dict[str, int]:
    data = _refs_only_mapping(require_mapping(value, field_name), field_name)
    allowed = {"max_turns", "timeout_seconds", "max_tool_calls", "max_output_refs"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise KernelValidationError(f"{field_name} contains unknown fields: {unknown}")
    return {key: require_int_at_least(item, f"{field_name}.{key}", 1) for key, item in data.items()}


def _hash(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if not text.startswith("sha256:") or len(text) <= len("sha256:"):
        raise KernelValidationError(f"{field_name} must be a sha256 hash")
    return text


def _optional_hash(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return _hash(value, field_name)


def _hash_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = _refs_only_mapping(require_mapping(value, field_name), field_name)
    result: dict[str, str] = {}
    for key, item in data.items():
        result[validate_ref(key, f"{field_name}.key")] = _hash(item, f"{field_name}.{key}")
    return result


def _route_key(value: str) -> tuple[str, str]:
    text = require_non_empty_str(value, "kernel_flow.routes.key")
    parts = text.split(".", 1)
    if len(parts) != 2:
        raise KernelValidationError("kernel_flow route keys must be '<step_id>.<value>'")
    return _safe_id(parts[0], "kernel_flow.routes.source_step"), _safe_id(
        parts[1],
        "kernel_flow.routes.value",
    )


def _route_target(value: Any) -> str | FlowStop:
    if isinstance(value, FlowStop):
        value.validate()
        return value
    if isinstance(value, Mapping):
        return FlowStop.from_dict(value)
    return _safe_id(value, "kernel_flow.routes.target")


def _route_target_to_dict(value: str | FlowStop) -> str | dict[str, Any]:
    if isinstance(value, FlowStop):
        return value.to_dict()
    return _safe_id(value, "kernel_flow.routes.target")

"""MissionForge programmer kernel API.

The package root intentionally exposes only the small, orthogonal surface a
programmer needs to embed bounded PiWorker/LLM calls in ordinary Python
systems. Higher-level flows, FrontDesk authoring, repair/revision controllers,
stores, profiles, and adapter internals remain available from their explicit
modules.
"""

from .agentic_ledger import FinalPackage, replay_decision_ledger
from .contracts import (
    ContractValidationError,
    MissionForgeError,
    Ref,
    assert_refs_only_payload,
    stable_json_hash,
    validate_ref,
)
from .context_summary import (
    ContextSummaryArtifact,
    ContextSummaryKind,
    ContextSummarySource,
)
from .evidence import ArtifactRef, EvidenceRef
from .evidence_store import EvidenceLedger, EvidenceRecord, FileEvidenceStore, InMemoryEvidenceStore
from .extensions import (
    ExtensionCompileReport,
    ExtensionLoadRecord,
    ExtensionLoadReport,
    ExtensionLock,
    ExtensionLockEntry,
    compile_extension_lock,
    extension_load_report_from_lock,
    read_extension_lock,
    verify_extension_lock,
    write_extension_lock,
)
from .runtime_control import (
    CapabilityGrant,
    HostSandboxRunner,
    SandboxMode,
    SandboxProfile,
    ToolGateway,
    ToolGatewayRequest,
    ToolGatewayResult,
    create_capability_grant,
    create_sandbox_profile_from_workspace,
)
from .piworker_call import (
    PiWorkerCall,
    PiWorkerCallResult,
    PiWorkerCallResultStatus,
    PiWorkerCallRole,
)
from .piworker_runtime import (
    PiWorkerCallAdapter,
    TaskContractFlowPreset,
    create_default_piworker_adapter,
    create_default_task_contract_flow,
    run_piworker_call,
)
from .product_integration import (
    ProductCompileStatus,
    ProductIntegration,
    ProductTaskContractCompileResult,
    TaskContractProductIntegration,
)
from .task_contract import (
    ContractClause,
    ExtensionAdapterMode,
    ExtensionCapability,
    ExtensionGrant,
    NetworkPolicy,
    PermissionManifest,
    TaskContract,
    TaskContractRevision,
    WorkspacePolicy,
)
from .task_projection import (
    JudgeRubric,
    WorkerBrief,
    build_judge_rubric,
    build_worker_brief,
    project_judge_rubric,
    project_worker_brief,
)

__all__ = [
    "ArtifactRef",
    "ContractClause",
    "ContractValidationError",
    "ContextSummaryArtifact",
    "ContextSummaryKind",
    "ContextSummarySource",
    "EvidenceLedger",
    "EvidenceRecord",
    "EvidenceRef",
    "ExtensionAdapterMode",
    "ExtensionCapability",
    "ExtensionCompileReport",
    "ExtensionGrant",
    "ExtensionLoadRecord",
    "ExtensionLoadReport",
    "ExtensionLock",
    "ExtensionLockEntry",
    "FileEvidenceStore",
    "FinalPackage",
    "CapabilityGrant",
    "HostSandboxRunner",
    "InMemoryEvidenceStore",
    "JudgeRubric",
    "MissionForgeError",
    "NetworkPolicy",
    "PermissionManifest",
    "SandboxMode",
    "SandboxProfile",
    "PiWorkerCall",
    "PiWorkerCallAdapter",
    "PiWorkerCallResult",
    "PiWorkerCallResultStatus",
    "PiWorkerCallRole",
    "ProductCompileStatus",
    "ProductIntegration",
    "ProductTaskContractCompileResult",
    "Ref",
    "ToolGateway",
    "ToolGatewayRequest",
    "ToolGatewayResult",
    "TaskContract",
    "TaskContractFlowPreset",
    "TaskContractProductIntegration",
    "TaskContractRevision",
    "WorkerBrief",
    "WorkspacePolicy",
    "assert_refs_only_payload",
    "build_judge_rubric",
    "build_worker_brief",
    "compile_extension_lock",
    "create_capability_grant",
    "create_default_piworker_adapter",
    "create_default_task_contract_flow",
    "create_sandbox_profile_from_workspace",
    "project_judge_rubric",
    "project_worker_brief",
    "read_extension_lock",
    "replay_decision_ledger",
    "run_piworker_call",
    "stable_json_hash",
    "validate_ref",
    "verify_extension_lock",
    "write_extension_lock",
    "extension_load_report_from_lock",
]

"""SkillFoundry compiler for the simplified TaskContract path."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from missionforge.task_contract import ContractClause, NetworkPolicy, PermissionManifest, TaskContract, WorkspacePolicy

from .product_contract import (
    ProductAcceptanceMatrix,
    SkillFoundryRequest,
    SkillProductContract,
)
from .workspace import read_json_ref, resolve_workspace_ref, write_json_ref


SKILLFOUNDRY_TASK_CONTRACT_REF = "contract/task_contract.json"
SKILLFOUNDRY_WORKSPACE_POLICY_REF = "policy/workspace_policy.json"
SKILLFOUNDRY_PERMISSION_MANIFEST_REF = "policy/permission_manifest.json"
SKILLFOUNDRY_JUDGE_RUBRIC_REF = "projections/judge_rubric.json"
SKILLFOUNDRY_HARD_CHECK_RESULT_REF = "reports/skillfoundry_hard_checks.json"
SKILLFOUNDRY_TASK_COMPILE_REPORT_REF = "product_contract/task_contract_compile_report.json"
TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION = "missionforge_skillfoundry.task_contract_compile_result.v1"


@dataclass(frozen=True)
class SkillFoundryTaskContractCompileResult:
    """Refs emitted by compiling a SkillFoundry request into TaskContract form."""

    bundle_id: str
    run_workspace_ref: str
    task_contract_ref: str
    workspace_policy_ref: str
    permission_manifest_ref: str
    product_request_ref: str
    product_contract_ref: str
    acceptance_matrix_ref: str
    compile_report_ref: str
    hard_check_refs: list[str] = field(default_factory=lambda: [SKILLFOUNDRY_HARD_CHECK_RESULT_REF])
    contract_hash: str = ""
    schema_version: str = TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundryTaskContractCompileResult":
        data = require_mapping(payload, "skillfoundry_task_contract_compile_result")
        result = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION),
                "skillfoundry_task_contract_compile_result.schema_version",
            ),
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skillfoundry_task_contract_compile_result.bundle_id"),
            run_workspace_ref=validate_ref(
                data.get("run_workspace_ref"),
                "skillfoundry_task_contract_compile_result.run_workspace_ref",
            ),
            task_contract_ref=validate_ref(
                data.get("task_contract_ref"),
                "skillfoundry_task_contract_compile_result.task_contract_ref",
            ),
            workspace_policy_ref=validate_ref(
                data.get("workspace_policy_ref"),
                "skillfoundry_task_contract_compile_result.workspace_policy_ref",
            ),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "skillfoundry_task_contract_compile_result.permission_manifest_ref",
            ),
            product_request_ref=validate_ref(
                data.get("product_request_ref"),
                "skillfoundry_task_contract_compile_result.product_request_ref",
            ),
            product_contract_ref=validate_ref(
                data.get("product_contract_ref"),
                "skillfoundry_task_contract_compile_result.product_contract_ref",
            ),
            acceptance_matrix_ref=validate_ref(
                data.get("acceptance_matrix_ref"),
                "skillfoundry_task_contract_compile_result.acceptance_matrix_ref",
            ),
            compile_report_ref=validate_ref(
                data.get("compile_report_ref"),
                "skillfoundry_task_contract_compile_result.compile_report_ref",
            ),
            hard_check_refs=[
                validate_ref(ref, "skillfoundry_task_contract_compile_result.hard_check_refs[]")
                for ref in require_str_list(data.get("hard_check_refs", []), "skillfoundry_task_contract_compile_result.hard_check_refs")
            ],
            contract_hash=require_non_empty_str(
                data.get("contract_hash"),
                "skillfoundry_task_contract_compile_result.contract_hash",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("skillfoundry_task_contract_compile_result.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "skillfoundry_task_contract_compile_result.bundle_id")
        validate_ref(self.run_workspace_ref, "skillfoundry_task_contract_compile_result.run_workspace_ref")
        validate_ref(self.task_contract_ref, "skillfoundry_task_contract_compile_result.task_contract_ref")
        validate_ref(self.workspace_policy_ref, "skillfoundry_task_contract_compile_result.workspace_policy_ref")
        validate_ref(self.permission_manifest_ref, "skillfoundry_task_contract_compile_result.permission_manifest_ref")
        validate_ref(self.product_request_ref, "skillfoundry_task_contract_compile_result.product_request_ref")
        validate_ref(self.product_contract_ref, "skillfoundry_task_contract_compile_result.product_contract_ref")
        validate_ref(self.acceptance_matrix_ref, "skillfoundry_task_contract_compile_result.acceptance_matrix_ref")
        validate_ref(self.compile_report_ref, "skillfoundry_task_contract_compile_result.compile_report_ref")
        for field_name, ref in (
            ("task_contract_ref", self.task_contract_ref),
            ("workspace_policy_ref", self.workspace_policy_ref),
            ("permission_manifest_ref", self.permission_manifest_ref),
            ("product_request_ref", self.product_request_ref),
            ("product_contract_ref", self.product_contract_ref),
            ("acceptance_matrix_ref", self.acceptance_matrix_ref),
            ("compile_report_ref", self.compile_report_ref),
        ):
            _validate_ref_under_run_workspace(
                ref,
                self.run_workspace_ref,
                f"skillfoundry_task_contract_compile_result.{field_name}",
            )
        for ref in self.hard_check_refs:
            validate_ref(ref, "skillfoundry_task_contract_compile_result.hard_check_refs[]")
        require_non_empty_str(self.contract_hash, "skillfoundry_task_contract_compile_result.contract_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "skillfoundry_task_contract_compile_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "run_workspace_ref": self.run_workspace_ref,
            "task_contract_ref": self.task_contract_ref,
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "product_request_ref": self.product_request_ref,
            "product_contract_ref": self.product_contract_ref,
            "acceptance_matrix_ref": self.acceptance_matrix_ref,
            "compile_report_ref": self.compile_report_ref,
            "hard_check_refs": list(self.hard_check_refs),
            "contract_hash": self.contract_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def compile_skillfoundry_task_contract(
    request: SkillFoundryRequest,
    *,
    workspace: str | Path = ".",
    request_ref: str = "product_contract/skillfoundry_request.json",
) -> SkillFoundryTaskContractCompileResult:
    """Compile a SkillFoundry request into the new TaskContract runtime shape."""

    request.validate()
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)

    product_contract = SkillProductContract.from_request(request, request_ref=request_ref)
    matrix = ProductAcceptanceMatrix.for_profile(
        bundle_id=request.bundle_id,
        profile=product_contract.bundle_profile,
        risk_domains=list(product_contract.risk_domains),
    )
    run_workspace_ref = f"runs/{request.bundle_id}"
    materialized_source_refs, unavailable_source_refs = _mirror_existing_source_refs(
        root,
        run_workspace_ref,
        request.source_refs,
    )
    workspace_policy = _workspace_policy_for_product(
        request,
        product_contract,
        run_workspace_ref=run_workspace_ref,
        source_refs=materialized_source_refs,
    )
    permission_manifest = _permission_manifest_for_product(
        request,
        product_contract,
        source_refs=materialized_source_refs,
    )
    task_contract = _task_contract_for_product(
        request,
        product_contract,
        matrix,
        workspace_policy=workspace_policy,
        permission_manifest=permission_manifest,
        request_ref=request_ref,
        product_contract_ref="product_contract/skill_product_contract.json",
        source_refs=materialized_source_refs,
    )

    product_contract_ref = _run_ref(run_workspace_ref, "product_contract/skill_product_contract.json")
    acceptance_matrix_ref = _run_ref(run_workspace_ref, product_contract.matrix_ref)
    product_request_ref = _run_ref(run_workspace_ref, request_ref)
    task_contract_ref = _run_ref(run_workspace_ref, SKILLFOUNDRY_TASK_CONTRACT_REF)
    workspace_policy_ref = _run_ref(run_workspace_ref, SKILLFOUNDRY_WORKSPACE_POLICY_REF)
    permission_manifest_ref = _run_ref(run_workspace_ref, SKILLFOUNDRY_PERMISSION_MANIFEST_REF)
    compile_report_ref = _run_ref(run_workspace_ref, SKILLFOUNDRY_TASK_COMPILE_REPORT_REF)

    write_json_ref(root, product_request_ref, request.to_dict())
    write_json_ref(root, product_contract_ref, product_contract.to_dict())
    write_json_ref(root, acceptance_matrix_ref, matrix.to_dict())
    write_json_ref(root, task_contract_ref, task_contract.to_dict())
    write_json_ref(root, workspace_policy_ref, workspace_policy.to_dict())
    write_json_ref(root, permission_manifest_ref, permission_manifest.to_dict())

    result = SkillFoundryTaskContractCompileResult(
        bundle_id=request.bundle_id,
        run_workspace_ref=run_workspace_ref,
        task_contract_ref=task_contract_ref,
        workspace_policy_ref=workspace_policy_ref,
        permission_manifest_ref=permission_manifest_ref,
        product_request_ref=product_request_ref,
        product_contract_ref=product_contract_ref,
        acceptance_matrix_ref=acceptance_matrix_ref,
        compile_report_ref=compile_report_ref,
        hard_check_refs=[SKILLFOUNDRY_HARD_CHECK_RESULT_REF],
        contract_hash=task_contract.contract_hash,
    )
    write_json_ref(
        root,
        compile_report_ref,
        {
            "bundle_id": request.bundle_id,
            "task_contract_ref": result.task_contract_ref,
            "workspace_policy_ref": result.workspace_policy_ref,
            "permission_manifest_ref": result.permission_manifest_ref,
            "product_request_ref": result.product_request_ref,
            "product_contract_ref": result.product_contract_ref,
            "acceptance_matrix_ref": result.acceptance_matrix_ref,
            "contract_hash": result.contract_hash,
            "hard_check_refs": list(result.hard_check_refs),
            "materialized_source_refs": list(materialized_source_refs),
            "unavailable_source_refs": list(unavailable_source_refs),
        },
    )
    result.validate()
    return result


def load_skillfoundry_task_contract(
    workspace: str | Path,
    result: SkillFoundryTaskContractCompileResult,
) -> tuple[TaskContract, WorkspacePolicy, PermissionManifest]:
    """Load compiled TaskContract, WorkspacePolicy, and PermissionManifest refs."""

    result.validate()
    task_contract = TaskContract.from_dict(read_json_ref(workspace, result.task_contract_ref, "task_contract"))
    workspace_policy = WorkspacePolicy.from_dict(
        read_json_ref(workspace, result.workspace_policy_ref, "workspace_policy")
    )
    permission_manifest = PermissionManifest.from_dict(
        read_json_ref(workspace, result.permission_manifest_ref, "permission_manifest")
    )
    return task_contract, workspace_policy, permission_manifest


def _task_contract_for_product(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
    matrix: ProductAcceptanceMatrix,
    *,
    workspace_policy: WorkspacePolicy,
    permission_manifest: PermissionManifest,
    request_ref: str,
    product_contract_ref: str,
    source_refs: list[str],
) -> TaskContract:
    admitted_source_refs = _unique_refs([request_ref, product_contract_ref, product_contract.matrix_ref, *source_refs])
    task_contract = TaskContract(
        contract_id=f"skillfoundry-{request.bundle_id}-task-contract",
        product_id="skillfoundry",
        objective=f"Build SkillFoundry {product_contract.bundle_profile.value} bundle {request.bundle_id}.",
        background=[
            "Compiled by the external SkillFoundry product integration.",
            "Executor produces package artifacts; independent judge applies the SkillFoundry product rubric.",
        ],
        users_or_audience=[request.target_user],
        required_outputs=[
            ContractClause(
                clause_id=f"sf-output-{index:03d}",
                text=f"Produce SkillFoundry package artifact {ref}.",
                refs=[ref],
                metadata={"bundle_id": request.bundle_id},
            )
            for index, ref in enumerate(product_contract.target_package_refs, start=1)
        ],
        hard_constraints=[
            ContractClause(
                clause_id="sf-hard-source-boundary",
                text="Use only sanitized SkillFoundry request and admitted source refs for task facts.",
                refs=admitted_source_refs,
            ),
            ContractClause(
                clause_id="sf-hard-output-root",
                text="Write SkillFoundry package artifacts only under declared package output roots.",
                refs=[SKILLFOUNDRY_PERMISSION_MANIFEST_REF],
            ),
            ContractClause(
                clause_id="sf-hard-no-raw-context",
                text="Package artifacts must not expose raw prompts, transcripts, provider payloads, credentials, or secrets.",
                refs=[product_contract.matrix_ref],
            ),
        ],
        semantic_acceptance=[
            ContractClause(
                clause_id=f"sf-accept-{item.check_id.lower().replace('_', '-')}",
                text=item.purpose,
                refs=[product_contract.matrix_ref, SKILLFOUNDRY_HARD_CHECK_RESULT_REF],
                metadata={"check_id": item.check_id, "evaluator": item.evaluator},
            )
            for item in matrix.items
        ],
        non_goals=[
            ContractClause(clause_id=f"sf-nongoal-{index:03d}", text=text)
            for index, text in enumerate(request.must_not, start=1)
        ],
        assumptions=[
            ContractClause(clause_id="sf-assumption-sanitized-inputs", text="Input refs are sanitized product artifacts.")
        ],
        risk_notes=[
            ContractClause(clause_id=f"sf-risk-{index:03d}", text=risk.value)
            for index, risk in enumerate(product_contract.risk_domains, start=1)
        ],
        workspace_policy_ref=SKILLFOUNDRY_WORKSPACE_POLICY_REF,
        permission_manifest_ref=SKILLFOUNDRY_PERMISSION_MANIFEST_REF,
        judge_rubric_ref=SKILLFOUNDRY_JUDGE_RUBRIC_REF,
        revision_policy={"mode": "explicit_revision_required", "product_id": "skillfoundry"},
        source_refs=admitted_source_refs,
        product_contract_refs=[product_contract_ref, product_contract.matrix_ref],
        created_by="missionforge_skillfoundry.task_contract_compiler",
        metadata={
            "bundle_id": request.bundle_id,
            "bundle_profile": product_contract.bundle_profile.value,
            "workspace_policy_id": workspace_policy.policy_id,
            "permission_manifest_id": permission_manifest.manifest_id,
        },
    )
    task_contract.validate()
    return task_contract


def _workspace_policy_for_product(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
    *,
    run_workspace_ref: str,
    source_refs: list[str],
) -> WorkspacePolicy:
    input_refs = _unique_refs([_root_ref(ref) for ref in ["product_contract", *source_refs]])
    return WorkspacePolicy(
        policy_id=f"skillfoundry-{request.bundle_id}-workspace",
        workspace_root_ref=run_workspace_ref,
        input_refs=input_refs,
        artifact_root_refs=list(product_contract.allowed_write_scopes),
        scratch_root_refs=["scratch"],
        denied_refs=["secrets"],
    )


def _permission_manifest_for_product(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
    *,
    source_refs: list[str],
) -> PermissionManifest:
    readable_refs = _unique_refs(
        [
            "contract",
            "policy",
            "product_contract",
            "projections",
            *(_root_ref(ref) for ref in source_refs),
        ]
    )
    writable_refs = _unique_refs([*product_contract.allowed_write_scopes, "attempts", "reports", "ledgers"])
    return PermissionManifest(
        manifest_id=f"skillfoundry-{request.bundle_id}-permissions",
        workspace_policy_ref=SKILLFOUNDRY_WORKSPACE_POLICY_REF,
        readable_refs=readable_refs,
        writable_refs=writable_refs,
        denied_refs=["secrets"],
        allowed_commands=[],
        network_policy=NetworkPolicy.DISABLED,
    )


def _run_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"


def _validate_ref_under_run_workspace(ref: str, run_workspace_ref: str, field_name: str) -> None:
    safe_ref = validate_ref(ref, field_name)
    safe_root = validate_ref(run_workspace_ref, "skillfoundry_task_contract_compile_result.run_workspace_ref")
    if safe_ref != safe_root and not safe_ref.startswith(f"{safe_root}/"):
        raise ContractValidationError(f"{field_name} must be under run_workspace_ref")


def _mirror_existing_source_refs(root: Path, run_workspace_ref: str, source_refs: list[str]) -> tuple[list[str], list[str]]:
    materialized_refs: list[str] = []
    unavailable_refs: list[str] = []
    for ref in source_refs:
        source_path = resolve_workspace_ref(root, ref)
        if not source_path.exists() or not source_path.is_file():
            unavailable_refs.append(validate_ref(ref, "skillfoundry_source_ref"))
            continue
        target_path = resolve_workspace_ref(root, _run_ref(run_workspace_ref, ref))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())
        materialized_refs.append(validate_ref(ref, "skillfoundry_source_ref"))
    return _unique_refs(materialized_refs), _unique_refs(unavailable_refs)


def _root_ref(ref: str) -> str:
    return validate_ref(ref, "skillfoundry_ref").split("/", 1)[0]


def _unique_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "skillfoundry_ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result

"""Role-specific projections derived from a TaskContract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import ContractValidationError, require_mapping, require_non_empty_str, require_str_list, validate_ref
from .task_contract import ContractClause, PermissionManifest, TaskContract, WorkspacePolicy


WORKER_BRIEF_SCHEMA_VERSION = "worker_brief.v1"
JUDGE_RUBRIC_SCHEMA_VERSION = "judge_rubric.v1"
JUDGE_DECISION_OPTIONS = ("accepted", "repair", "revision_required", "rejected")


@dataclass(frozen=True)
class WorkerBrief:
    """Execution-facing view of a frozen TaskContract."""

    brief_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    objective: str
    required_outputs: list[ContractClause]
    hard_constraints: list[ContractClause]
    schema_version: str = WORKER_BRIEF_SCHEMA_VERSION
    background: list[str] = field(default_factory=list)
    non_goals: list[ContractClause] = field(default_factory=list)
    assumptions: list[ContractClause] = field(default_factory=list)
    allowed_input_refs: list[str] = field(default_factory=list)
    writable_refs: list[str] = field(default_factory=list)
    expected_artifact_root_refs: list[str] = field(default_factory=list)
    workspace_policy_ref: str | None = None
    permission_manifest_ref: str | None = None
    completion_report_ref: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkerBrief":
        data = require_mapping(payload, "worker_brief")
        brief = cls(
            brief_id=require_non_empty_str(data.get("brief_id"), "worker_brief.brief_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "worker_brief.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "worker_brief.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "worker_brief.contract_ref"),
            objective=require_non_empty_str(data.get("objective"), "worker_brief.objective"),
            required_outputs=_clauses_from_dicts(data.get("required_outputs", []), "worker_brief.required_outputs"),
            hard_constraints=_clauses_from_dicts(data.get("hard_constraints", []), "worker_brief.hard_constraints"),
            schema_version=require_non_empty_str(
                data.get("schema_version", WORKER_BRIEF_SCHEMA_VERSION),
                "worker_brief.schema_version",
            ),
            background=require_str_list(data.get("background", []), "worker_brief.background"),
            non_goals=_clauses_from_dicts(data.get("non_goals", []), "worker_brief.non_goals"),
            assumptions=_clauses_from_dicts(data.get("assumptions", []), "worker_brief.assumptions"),
            allowed_input_refs=_ref_list(data.get("allowed_input_refs", []), "worker_brief.allowed_input_refs"),
            writable_refs=_ref_list(data.get("writable_refs", []), "worker_brief.writable_refs"),
            expected_artifact_root_refs=_ref_list(
                data.get("expected_artifact_root_refs", []),
                "worker_brief.expected_artifact_root_refs",
            ),
            workspace_policy_ref=_optional_ref(data.get("workspace_policy_ref"), "worker_brief.workspace_policy_ref"),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "worker_brief.permission_manifest_ref",
            ),
            completion_report_ref=_optional_ref(
                data.get("completion_report_ref"),
                "worker_brief.completion_report_ref",
            ),
        )
        brief.validate()
        return brief

    def validate(self) -> None:
        _require_schema(self.schema_version, WORKER_BRIEF_SCHEMA_VERSION, "worker_brief.schema_version")
        require_non_empty_str(self.brief_id, "worker_brief.brief_id")
        require_non_empty_str(self.contract_id, "worker_brief.contract_id")
        require_non_empty_str(self.contract_hash, "worker_brief.contract_hash")
        validate_ref(self.contract_ref, "worker_brief.contract_ref")
        require_non_empty_str(self.objective, "worker_brief.objective")
        _validate_clause_list(self.required_outputs, "worker_brief.required_outputs")
        if not self.required_outputs:
            raise ContractValidationError("worker_brief.required_outputs must not be empty")
        _validate_clause_list(self.hard_constraints, "worker_brief.hard_constraints")
        require_str_list(self.background, "worker_brief.background")
        _validate_clause_list(self.non_goals, "worker_brief.non_goals")
        _validate_clause_list(self.assumptions, "worker_brief.assumptions")
        _validate_unique_refs(self.allowed_input_refs, "worker_brief.allowed_input_refs")
        _validate_unique_refs(self.writable_refs, "worker_brief.writable_refs")
        _validate_unique_refs(self.expected_artifact_root_refs, "worker_brief.expected_artifact_root_refs")
        _optional_ref(self.workspace_policy_ref, "worker_brief.workspace_policy_ref")
        _optional_ref(self.permission_manifest_ref, "worker_brief.permission_manifest_ref")
        _optional_ref(self.completion_report_ref, "worker_brief.completion_report_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "brief_id": self.brief_id,
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "objective": self.objective,
            "background": list(self.background),
            "non_goals": [item.to_dict() for item in self.non_goals],
            "assumptions": [item.to_dict() for item in self.assumptions],
            "required_outputs": [item.to_dict() for item in self.required_outputs],
            "hard_constraints": [item.to_dict() for item in self.hard_constraints],
            "allowed_input_refs": list(self.allowed_input_refs),
            "writable_refs": list(self.writable_refs),
            "expected_artifact_root_refs": list(self.expected_artifact_root_refs),
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "completion_report_ref": self.completion_report_ref,
        }


@dataclass(frozen=True)
class JudgeRubric:
    """Acceptance-facing view of a frozen TaskContract."""

    rubric_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    objective: str
    required_outputs: list[ContractClause]
    hard_constraints: list[ContractClause]
    semantic_acceptance: list[ContractClause]
    schema_version: str = JUDGE_RUBRIC_SCHEMA_VERSION
    non_goals: list[ContractClause] = field(default_factory=list)
    risk_notes: list[ContractClause] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    hard_check_refs: list[str] = field(default_factory=list)
    decision_options: tuple[str, ...] = JUDGE_DECISION_OPTIONS
    workspace_policy_ref: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JudgeRubric":
        data = require_mapping(payload, "judge_rubric")
        rubric = cls(
            rubric_id=require_non_empty_str(data.get("rubric_id"), "judge_rubric.rubric_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "judge_rubric.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "judge_rubric.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "judge_rubric.contract_ref"),
            objective=require_non_empty_str(data.get("objective"), "judge_rubric.objective"),
            required_outputs=_clauses_from_dicts(data.get("required_outputs", []), "judge_rubric.required_outputs"),
            hard_constraints=_clauses_from_dicts(data.get("hard_constraints", []), "judge_rubric.hard_constraints"),
            semantic_acceptance=_clauses_from_dicts(
                data.get("semantic_acceptance", []),
                "judge_rubric.semantic_acceptance",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", JUDGE_RUBRIC_SCHEMA_VERSION),
                "judge_rubric.schema_version",
            ),
            non_goals=_clauses_from_dicts(data.get("non_goals", []), "judge_rubric.non_goals"),
            risk_notes=_clauses_from_dicts(data.get("risk_notes", []), "judge_rubric.risk_notes"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "judge_rubric.evidence_refs"),
            hard_check_refs=_ref_list(data.get("hard_check_refs", []), "judge_rubric.hard_check_refs"),
            decision_options=tuple(
                require_str_list(
                    data.get("decision_options", list(JUDGE_DECISION_OPTIONS)),
                    "judge_rubric.decision_options",
                )
            ),
            workspace_policy_ref=_optional_ref(data.get("workspace_policy_ref"), "judge_rubric.workspace_policy_ref"),
        )
        rubric.validate()
        return rubric

    def validate(self) -> None:
        _require_schema(self.schema_version, JUDGE_RUBRIC_SCHEMA_VERSION, "judge_rubric.schema_version")
        require_non_empty_str(self.rubric_id, "judge_rubric.rubric_id")
        require_non_empty_str(self.contract_id, "judge_rubric.contract_id")
        require_non_empty_str(self.contract_hash, "judge_rubric.contract_hash")
        validate_ref(self.contract_ref, "judge_rubric.contract_ref")
        require_non_empty_str(self.objective, "judge_rubric.objective")
        _validate_clause_list(self.required_outputs, "judge_rubric.required_outputs")
        if not self.required_outputs:
            raise ContractValidationError("judge_rubric.required_outputs must not be empty")
        _validate_clause_list(self.hard_constraints, "judge_rubric.hard_constraints")
        _validate_clause_list(self.semantic_acceptance, "judge_rubric.semantic_acceptance")
        if not self.semantic_acceptance:
            raise ContractValidationError("judge_rubric.semantic_acceptance must not be empty")
        _validate_clause_list(self.non_goals, "judge_rubric.non_goals")
        _validate_clause_list(self.risk_notes, "judge_rubric.risk_notes")
        _validate_unique_refs(self.evidence_refs, "judge_rubric.evidence_refs")
        _validate_unique_refs(self.hard_check_refs, "judge_rubric.hard_check_refs")
        if tuple(self.decision_options) != JUDGE_DECISION_OPTIONS:
            raise ContractValidationError("judge_rubric.decision_options must use the fixed judge decisions")
        _optional_ref(self.workspace_policy_ref, "judge_rubric.workspace_policy_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "rubric_id": self.rubric_id,
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "objective": self.objective,
            "non_goals": [item.to_dict() for item in self.non_goals],
            "required_outputs": [item.to_dict() for item in self.required_outputs],
            "hard_constraints": [item.to_dict() for item in self.hard_constraints],
            "semantic_acceptance": [item.to_dict() for item in self.semantic_acceptance],
            "risk_notes": [item.to_dict() for item in self.risk_notes],
            "evidence_refs": list(self.evidence_refs),
            "hard_check_refs": list(self.hard_check_refs),
            "decision_options": list(self.decision_options),
            "workspace_policy_ref": self.workspace_policy_ref,
        }


def project_worker_brief(
    contract: TaskContract,
    workspace_policy: WorkspacePolicy,
    permission_manifest: PermissionManifest,
    *,
    brief_id: str,
    contract_ref: str,
    completion_report_ref: str | None = None,
) -> WorkerBrief:
    """Project a contract into the executor-facing brief."""

    _assert_contract_not_drifted(contract)
    workspace_policy.validate()
    permission_manifest.validate()
    brief = WorkerBrief(
        brief_id=brief_id,
        contract_id=contract.contract_id,
        contract_hash=contract.contract_hash,
        contract_ref=validate_ref(contract_ref, "contract_ref"),
        objective=contract.objective,
        background=list(contract.background),
        non_goals=_copy_clauses(contract.non_goals),
        assumptions=_copy_clauses(contract.assumptions),
        required_outputs=_copy_clauses(contract.required_outputs),
        hard_constraints=_copy_clauses(contract.hard_constraints),
        allowed_input_refs=_unique_refs([*workspace_policy.input_refs, *contract.source_refs]),
        writable_refs=list(permission_manifest.writable_refs),
        expected_artifact_root_refs=list(workspace_policy.artifact_root_refs),
        workspace_policy_ref=contract.workspace_policy_ref,
        permission_manifest_ref=contract.permission_manifest_ref,
        completion_report_ref=completion_report_ref,
    )
    _validate_read_authority(brief.allowed_input_refs, permission_manifest.readable_refs)
    brief.validate()
    return brief


def project_judge_rubric(
    contract: TaskContract,
    workspace_policy: WorkspacePolicy,
    *,
    rubric_id: str,
    contract_ref: str,
    evidence_refs: list[str] | None = None,
    hard_check_refs: list[str] | None = None,
) -> JudgeRubric:
    """Project a contract into the judge-facing rubric."""

    _assert_contract_not_drifted(contract)
    workspace_policy.validate()
    rubric = JudgeRubric(
        rubric_id=rubric_id,
        contract_id=contract.contract_id,
        contract_hash=contract.contract_hash,
        contract_ref=validate_ref(contract_ref, "contract_ref"),
        objective=contract.objective,
        non_goals=_copy_clauses(contract.non_goals),
        required_outputs=_copy_clauses(contract.required_outputs),
        hard_constraints=_copy_clauses(contract.hard_constraints),
        semantic_acceptance=_copy_clauses(contract.semantic_acceptance),
        risk_notes=_copy_clauses(contract.risk_notes),
        evidence_refs=_unique_refs(evidence_refs or []),
        hard_check_refs=_unique_refs(hard_check_refs or []),
        workspace_policy_ref=contract.workspace_policy_ref,
    )
    rubric.validate()
    return rubric


def build_worker_brief(
    contract: TaskContract,
    *,
    brief_id: str | None = None,
    contract_ref: str = "contract/task_contract.json",
) -> WorkerBrief:
    """Build a minimal executor brief when full workspace policy is not needed."""

    workspace_policy = WorkspacePolicy(
        policy_id=f"{contract.contract_id}-workspace",
        workspace_root_ref="runs/current",
        input_refs=list(contract.source_refs),
        artifact_root_refs=[],
        scratch_root_refs=[],
        denied_refs=[],
    )
    permission_manifest = PermissionManifest(
        manifest_id=f"{contract.contract_id}-permissions",
        readable_refs=list(contract.source_refs),
        writable_refs=[],
        denied_refs=[],
    )
    return project_worker_brief(
        contract,
        workspace_policy,
        permission_manifest,
        brief_id=brief_id or f"{contract.contract_id}-worker-brief",
        contract_ref=contract_ref,
    )


def build_judge_rubric(
    contract: TaskContract,
    *,
    rubric_id: str | None = None,
    contract_ref: str = "contract/task_contract.json",
) -> JudgeRubric:
    """Build a minimal judge rubric when full workspace policy is not needed."""

    workspace_policy = WorkspacePolicy(
        policy_id=f"{contract.contract_id}-workspace",
        workspace_root_ref="runs/current",
        input_refs=list(contract.source_refs),
        artifact_root_refs=[],
        scratch_root_refs=[],
        denied_refs=[],
    )
    return project_judge_rubric(
        contract,
        workspace_policy,
        rubric_id=rubric_id or f"{contract.contract_id}-judge-rubric",
        contract_ref=contract_ref,
    )


def _clauses_from_dicts(value: Any, field_name: str) -> list[ContractClause]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    clauses = [ContractClause.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]
    _validate_clause_list(clauses, field_name)
    return clauses


def _assert_contract_not_drifted(contract: TaskContract) -> None:
    contract.to_dict()


def _copy_clauses(clauses: list[ContractClause]) -> list[ContractClause]:
    return [ContractClause.from_dict(clause.to_dict()) for clause in clauses]


def _validate_clause_list(clauses: list[ContractClause], field_name: str) -> None:
    seen: set[str] = set()
    for clause in clauses:
        clause.validate()
        if clause.clause_id in seen:
            raise ContractValidationError(f"duplicate {field_name} clause_id: {clause.clause_id}")
        seen.add(clause.clause_id)


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _unique_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        ref = validate_ref(value, "ref")
        if ref not in result:
            result.append(ref)
    return result


def _validate_read_authority(visible_refs: list[str], readable_refs: list[str]) -> None:
    readable = _unique_refs(readable_refs)
    for ref in visible_refs:
        if not any(_ref_is_under(ref, readable_ref) for readable_ref in readable):
            raise ContractValidationError(f"worker_brief.allowed_input_refs includes unreadable ref: {ref}")


def _ref_is_under(ref: str, root_ref: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_root = validate_ref(root_ref, "root_ref")
    return safe_ref == safe_root or safe_ref.startswith(f"{safe_root}/")


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")

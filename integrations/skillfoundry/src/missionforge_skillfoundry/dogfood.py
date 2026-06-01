"""Opt-in SkillFoundry live dogfood harness."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Mapping

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig
from missionforge.contracts import (
    ContractValidationError,
    VerificationStatus,
    assert_refs_only_payload,
    require_bool,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)

from .product_contract import PROMPT_ONLY_REQUIRED_PACKAGE_REFS, RegistryStatus, SkillFoundryRequest
from .product_grade_gate import PRODUCT_GRADE_REPORT_REF, ProductGradeReport
from .reports import PRODUCT_REPORT_REF, SkillFoundryProductReport
from .runtime import run_skillfoundry_bundle_build
from .validators import BUNDLE_VALIDATION_REPORT_REF, BundleValidationReport
from .workspace import read_json_ref, ref_exists, write_json_ref


DOGFOOD_REPORT_SCHEMA_VERSION = "missionforge_skillfoundry.live_dogfood_report.v1"
DOGFOOD_REPORT_REF = "reports/skillfoundry_live_dogfood_report.json"
DOGFOOD_OPT_IN_ENV = "MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD"
DOGFOOD_TIMEOUT_ENV = "MISSIONFORGE_SKILLFOUNDRY_LIVE_TIMEOUT_SECONDS"
DOGFOOD_OUTCOME_CATEGORIES = {
    "product_contract",
    "worker_execution",
    "verifier",
    "product_grade",
    "registry",
    "completed",
}
DOGFOOD_RUN_STATUSES = {"completed", "classified_failure"}


@dataclass(frozen=True)
class SkillFoundryDogfoodReport:
    """Refs-only read model for one live dogfood run."""

    bundle_id: str
    outcome_category: str
    run_status: str
    live_enabled: bool
    request_ref: str = ""
    product_report_ref: str = ""
    product_grade_report_ref: str = ""
    bundle_validation_report_ref: str = ""
    registry_decision_ref: str = ""
    package_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    issue_codes: list[str] = field(default_factory=list)
    exception_type: str = ""
    boundary_flags: dict[str, bool] = field(
        default_factory=lambda: {
            "user_input_material_excluded": True,
            "dialog_material_excluded": True,
            "provider_wire_material_excluded": True,
            "provider_auth_material_excluded": True,
            "worker_self_report_is_acceptance": False,
        }
    )
    schema_version: str = DOGFOOD_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundryDogfoodReport":
        data = require_mapping(payload, "skillfoundry_dogfood_report")
        report = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skillfoundry_dogfood_report.bundle_id"),
            outcome_category=require_non_empty_str(
                data.get("outcome_category"),
                "skillfoundry_dogfood_report.outcome_category",
            ),
            run_status=require_non_empty_str(data.get("run_status"), "skillfoundry_dogfood_report.run_status"),
            live_enabled=require_bool(data.get("live_enabled"), "skillfoundry_dogfood_report.live_enabled"),
            request_ref=data.get("request_ref", ""),
            product_report_ref=data.get("product_report_ref", ""),
            product_grade_report_ref=data.get("product_grade_report_ref", ""),
            bundle_validation_report_ref=data.get("bundle_validation_report_ref", ""),
            registry_decision_ref=data.get("registry_decision_ref", ""),
            package_refs=require_str_list(data.get("package_refs", []), "skillfoundry_dogfood_report.package_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "skillfoundry_dogfood_report.evidence_refs"),
            issue_codes=require_str_list(data.get("issue_codes", []), "skillfoundry_dogfood_report.issue_codes"),
            exception_type=data.get("exception_type", ""),
            boundary_flags=require_mapping(
                data.get("boundary_flags", {}),
                "skillfoundry_dogfood_report.boundary_flags",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", DOGFOOD_REPORT_SCHEMA_VERSION),
                "skillfoundry_dogfood_report.schema_version",
            ),
        )
        report.validate()
        return report

    @property
    def report_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    def validate(self) -> None:
        if self.schema_version != DOGFOOD_REPORT_SCHEMA_VERSION:
            raise ContractValidationError("skillfoundry_dogfood_report.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "skillfoundry_dogfood_report.bundle_id")
        if self.outcome_category not in DOGFOOD_OUTCOME_CATEGORIES:
            raise ContractValidationError("skillfoundry_dogfood_report.outcome_category is unsupported")
        if self.run_status not in DOGFOOD_RUN_STATUSES:
            raise ContractValidationError("skillfoundry_dogfood_report.run_status is unsupported")
        if self.run_status == "completed" and self.outcome_category != "completed":
            raise ContractValidationError("completed dogfood run must use completed outcome_category")
        if not isinstance(self.live_enabled, bool):
            raise ContractValidationError("skillfoundry_dogfood_report.live_enabled must be boolean")
        for field_name in (
            "request_ref",
            "product_report_ref",
            "product_grade_report_ref",
            "bundle_validation_report_ref",
            "registry_decision_ref",
        ):
            value = getattr(self, field_name)
            if value:
                validate_ref(value, f"skillfoundry_dogfood_report.{field_name}")
        for ref in self.package_refs:
            validate_ref(ref, "skillfoundry_dogfood_report.package_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "skillfoundry_dogfood_report.evidence_refs[]")
        require_str_list(self.issue_codes, "skillfoundry_dogfood_report.issue_codes")
        if self.exception_type:
            require_non_empty_str(self.exception_type, "skillfoundry_dogfood_report.exception_type")
        for key, value in self.boundary_flags.items():
            require_non_empty_str(key, "skillfoundry_dogfood_report.boundary_flags.key")
            if not isinstance(value, bool):
                raise ContractValidationError("skillfoundry_dogfood_report.boundary_flags values must be boolean")
        assert_refs_only_payload(self.to_dict_without_hash(), "skillfoundry_dogfood_report")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "outcome_category": self.outcome_category,
            "run_status": self.run_status,
            "live_enabled": self.live_enabled,
            "request_ref": self.request_ref,
            "product_report_ref": self.product_report_ref,
            "product_grade_report_ref": self.product_grade_report_ref,
            "bundle_validation_report_ref": self.bundle_validation_report_ref,
            "registry_decision_ref": self.registry_decision_ref,
            "package_refs": list(self.package_refs),
            "evidence_refs": list(self.evidence_refs),
            "issue_codes": list(self.issue_codes),
            "exception_type": self.exception_type,
            "boundary_flags": dict(self.boundary_flags),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["report_hash"] = self.report_hash
        return payload


def run_skillfoundry_live_dogfood(
    request: SkillFoundryRequest,
    *,
    workspace: str | Path = ".",
    require_opt_in: bool = True,
    environ: Mapping[str, str] | None = None,
    timeout_seconds: int | None = None,
    build_runner: Any | None = None,
    report_ref: str = DOGFOOD_REPORT_REF,
) -> SkillFoundryDogfoodReport:
    """Run one explicit live PI Agent dogfood attempt and classify the outcome."""

    env = dict(os.environ if environ is None else environ)
    live_enabled = env.get(DOGFOOD_OPT_IN_ENV) == "1"
    if require_opt_in and not live_enabled:
        raise ContractValidationError(f"set {DOGFOOD_OPT_IN_ENV}=1 to run SkillFoundry live dogfood")
    request.validate()
    timeout = timeout_seconds if timeout_seconds is not None else int(env.get(DOGFOOD_TIMEOUT_ENV, "300"))
    pi_agent_config = PiAgentRuntimeConfig(
        timeout_seconds=timeout,
        provider_mode="live",
        provider_config_source="codex_current",
        metadata={"phase": "skillfoundry_live_dogfood", "bundle_id": request.bundle_id},
    )
    runner = build_runner or run_skillfoundry_bundle_build
    try:
        product_report = runner(
            request,
            workspace=workspace,
            max_attempts=1,
            pi_agent_config=pi_agent_config,
            allow_candidate_registration=True,
        )
        if not isinstance(product_report, SkillFoundryProductReport):
            raise ContractValidationError("SkillFoundry dogfood runner returned an unsupported product report")
        report = _report_from_product_report(
            workspace=workspace,
            request=request,
            product_report=product_report,
            live_enabled=live_enabled,
        )
    except Exception as exc:
        report = _report_from_exception(
            workspace=workspace,
            request=request,
            live_enabled=live_enabled,
            exc=exc,
        )
    write_json_ref(workspace, report_ref, report.to_dict())
    return report


def _report_from_product_report(
    *,
    workspace: str | Path,
    request: SkillFoundryRequest,
    product_report: SkillFoundryProductReport,
    live_enabled: bool,
) -> SkillFoundryDogfoodReport:
    outcome, issue_codes = _classify_product_report(workspace, product_report)
    return SkillFoundryDogfoodReport(
        bundle_id=request.bundle_id,
        outcome_category=outcome,
        run_status="completed" if outcome == "completed" else "classified_failure",
        live_enabled=live_enabled,
        request_ref=product_report.request_ref,
        product_report_ref=PRODUCT_REPORT_REF,
        product_grade_report_ref=product_report.product_grade_report_ref,
        bundle_validation_report_ref=BUNDLE_VALIDATION_REPORT_REF,
        registry_decision_ref=product_report.registry_decision_ref,
        package_refs=list(product_report.package_refs),
        evidence_refs=list(product_report.verifier_refs),
        issue_codes=issue_codes,
    )


def _report_from_exception(
    *,
    workspace: str | Path,
    request: SkillFoundryRequest,
    live_enabled: bool,
    exc: Exception,
) -> SkillFoundryDogfoodReport:
    outcome, issue_codes, refs = _classify_workspace_after_exception(workspace)
    issue_codes = [*issue_codes, _exception_issue_code(exc)]
    return SkillFoundryDogfoodReport(
        bundle_id=request.bundle_id,
        outcome_category=outcome,
        run_status="classified_failure",
        live_enabled=live_enabled,
        request_ref=refs.get("request_ref", ""),
        product_report_ref=refs.get("product_report_ref", ""),
        product_grade_report_ref=refs.get("product_grade_report_ref", ""),
        bundle_validation_report_ref=refs.get("bundle_validation_report_ref", ""),
        registry_decision_ref=refs.get("registry_decision_ref", ""),
        package_refs=refs.get("package_refs", []),
        evidence_refs=refs.get("evidence_refs", []),
        issue_codes=_dedupe(issue_codes),
        exception_type=type(exc).__name__,
    )


def _classify_product_report(
    workspace: str | Path,
    product_report: SkillFoundryProductReport,
) -> tuple[str, list[str]]:
    if product_report.final_status == RegistryStatus.PRODUCT_GRADE_REGISTERED.value:
        return "completed", ["product_grade_registered"]
    grade_report = _load_product_grade_report(workspace)
    if grade_report is None:
        return "registry", ["missing_product_grade_report"]
    return _classify_product_grade_report(workspace, grade_report)


def _classify_product_grade_report(
    workspace: str | Path,
    grade_report: ProductGradeReport,
) -> tuple[str, list[str]]:
    if grade_report.product_grade:
        return "registry", ["product_gate_passed_without_product_grade_registration"]
    if grade_report.verifier_status != VerificationStatus.COMPLETED_VERIFIED.value:
        if _missing_required_package_refs(workspace):
            return "worker_execution", ["missing_expected_package_refs", f"verifier_status:{grade_report.verifier_status}"]
        return "verifier", [f"verifier_status:{grade_report.verifier_status}"]
    if grade_report.findings:
        return "product_grade", [finding.finding_id for finding in grade_report.findings]
    return "product_grade", ["product_gate_failed_without_structured_findings"]


def _classify_workspace_after_exception(workspace: str | Path) -> tuple[str, list[str], dict[str, Any]]:
    refs: dict[str, Any] = {}
    if ref_exists(workspace, "product_contract/skillfoundry_request.json"):
        refs["request_ref"] = "product_contract/skillfoundry_request.json"
    if ref_exists(workspace, PRODUCT_REPORT_REF):
        refs["product_report_ref"] = PRODUCT_REPORT_REF
        try:
            product_report = SkillFoundryProductReport.from_dict(read_json_ref(workspace, PRODUCT_REPORT_REF, "product_report"))
            refs["registry_decision_ref"] = product_report.registry_decision_ref
            refs["package_refs"] = list(product_report.package_refs)
            refs["evidence_refs"] = list(product_report.verifier_refs)
            outcome, issue_codes = _classify_product_report(workspace, product_report)
            return outcome, issue_codes, refs
        except ContractValidationError:
            return "registry", ["invalid_product_report"], refs
    if ref_exists(workspace, PRODUCT_GRADE_REPORT_REF):
        refs["product_grade_report_ref"] = PRODUCT_GRADE_REPORT_REF
        try:
            grade_report = _load_product_grade_report(workspace)
            if grade_report is not None:
                refs["package_refs"] = list(grade_report.package_refs)
                refs["evidence_refs"] = list(grade_report.verifier_refs)
                outcome, issue_codes = _classify_product_grade_report(workspace, grade_report)
                return outcome, issue_codes, refs
        except ContractValidationError:
            return "product_grade", ["invalid_product_grade_report"], refs
    if ref_exists(workspace, BUNDLE_VALIDATION_REPORT_REF):
        refs["bundle_validation_report_ref"] = BUNDLE_VALIDATION_REPORT_REF
        try:
            bundle_report = BundleValidationReport.from_dict(
                read_json_ref(workspace, BUNDLE_VALIDATION_REPORT_REF, "bundle_validation_report")
            )
            refs["package_refs"] = list(bundle_report.package_refs)
            if _missing_required_package_refs(workspace):
                return "worker_execution", ["missing_expected_package_refs"], refs
            return "product_grade", ["bundle_validation_completed_without_product_grade_report"], refs
        except ContractValidationError:
            return "product_grade", ["invalid_bundle_validation_report"], refs
    if _missing_required_package_refs(workspace) and ref_exists(workspace, f"missions"):
        return "worker_execution", ["missing_expected_package_refs"], refs
    if ref_exists(workspace, "product_contract/skill_product_contract.json"):
        return "worker_execution", ["build_interrupted_after_product_contract"], refs
    return "product_contract", ["product_contract_not_written"], refs


def _load_product_grade_report(workspace: str | Path) -> ProductGradeReport | None:
    if not ref_exists(workspace, PRODUCT_GRADE_REPORT_REF):
        return None
    return ProductGradeReport.from_dict(read_json_ref(workspace, PRODUCT_GRADE_REPORT_REF, "product_grade_report"))


def _missing_required_package_refs(workspace: str | Path) -> bool:
    return any(not ref_exists(workspace, ref) for ref in PROMPT_ONLY_REQUIRED_PACKAGE_REFS)


def _exception_issue_code(exc: Exception) -> str:
    if isinstance(exc, ContractValidationError):
        return "contract_validation_error"
    return "runtime_exception"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result

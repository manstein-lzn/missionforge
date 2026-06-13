"""SkillFoundry product-grade gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

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
from missionforge.runtime_results import MissionResult

from .product_contract import (
    ACCEPTANCE_COVERAGE_REPORT_REF,
    AcceptanceCoverageReport,
    AcceptanceCoverageRoute,
    RegistryStatus,
    SkillProductContract,
)
from .validators import BundleValidationReport
from .workspace import package_fingerprint, read_json_ref, ref_exists, write_json_ref


PRODUCT_GRADE_REPORT_SCHEMA_VERSION = "missionforge_skillfoundry.product_grade_report.v1"
PRODUCT_REPAIR_PACKET_SCHEMA_VERSION = "missionforge_skillfoundry.product_repair_packet.v1"
PRODUCT_GRADE_REPORT_REF = "qa/product_grade_report.json"
PRODUCT_REPAIR_PACKET_REF = "qa/product_repair_packet.json"
PRODUCT_GRADE_OUTCOME_CATEGORIES = {
    "mission_verifier_failed",
    "product_grade_failed_after_covered_verification",
    "coverage_miss",
    "product_grade_registered",
    "candidate_registered",
}


@dataclass(frozen=True)
class ProductGradeFinding:
    """One product-grade finding."""

    finding_id: str
    severity: str
    message: str
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductGradeFinding":
        data = require_mapping(payload, "product_grade_finding")
        finding = cls(
            finding_id=require_non_empty_str(data.get("finding_id"), "product_grade_finding.finding_id"),
            severity=require_non_empty_str(data.get("severity"), "product_grade_finding.severity"),
            message=require_non_empty_str(data.get("message"), "product_grade_finding.message"),
            source_refs=require_str_list(data.get("source_refs", []), "product_grade_finding.source_refs"),
        )
        finding.validate()
        return finding

    def validate(self) -> None:
        require_non_empty_str(self.finding_id, "product_grade_finding.finding_id")
        if self.severity not in {"blocking", "major", "minor"}:
            raise ContractValidationError("product_grade_finding.severity must be blocking, major, or minor")
        require_non_empty_str(self.message, "product_grade_finding.message")
        for ref in self.source_refs:
            validate_ref(ref, "product_grade_finding.source_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "message": self.message,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class ProductRepairPacket:
    """Structured repair guidance for product-grade failures."""

    bundle_id: str
    repair_items: list[ProductGradeFinding]
    source_refs: list[str] = field(default_factory=list)
    schema_version: str = PRODUCT_REPAIR_PACKET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductRepairPacket":
        data = require_mapping(payload, "product_repair_packet")
        packet = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "product_repair_packet.bundle_id"),
            repair_items=[
                ProductGradeFinding.from_dict(require_mapping(item, "product_repair_packet.repair_items[]"))
                for item in data.get("repair_items", [])
            ],
            source_refs=require_str_list(data.get("source_refs", []), "product_repair_packet.source_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_REPAIR_PACKET_SCHEMA_VERSION),
                "product_repair_packet.schema_version",
            ),
        )
        packet.validate()
        return packet

    def validate(self) -> None:
        if self.schema_version != PRODUCT_REPAIR_PACKET_SCHEMA_VERSION:
            raise ContractValidationError("product_repair_packet.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "product_repair_packet.bundle_id")
        for item in self.repair_items:
            item.validate()
            if item.severity not in {"blocking", "major"}:
                raise ContractValidationError("product_repair_packet only accepts blocking or major findings")
        for ref in self.source_refs:
            validate_ref(ref, "product_repair_packet.source_refs[]")
        assert_refs_only_payload(self.to_dict_without_validation(), "product_repair_packet")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "repair_items": [item.to_dict() for item in self.repair_items],
            "source_refs": list(self.source_refs),
            "trust_boundaries": {
                "user_input_material_policy": "excluded",
                "dialog_material_policy": "excluded",
                "worker_self_report_is_acceptance": False,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ProductGradeReport:
    """Product-grade decision report."""

    bundle_id: str
    package_refs: list[str]
    package_hash: str
    verifier_status: str
    verifier_refs: list[str]
    bundle_validation_report_ref: str
    product_grade: bool
    recommended_registry_status: RegistryStatus
    findings: list[ProductGradeFinding] = field(default_factory=list)
    outcome_category: str = "candidate_registered"
    repair_packet_ref: str = ""
    schema_version: str = PRODUCT_GRADE_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductGradeReport":
        data = require_mapping(payload, "product_grade_report")
        report = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "product_grade_report.bundle_id"),
            package_refs=require_str_list(data.get("package_refs", []), "product_grade_report.package_refs"),
            package_hash=require_non_empty_str(data.get("package_hash"), "product_grade_report.package_hash"),
            verifier_status=require_non_empty_str(data.get("verifier_status"), "product_grade_report.verifier_status"),
            verifier_refs=require_str_list(data.get("verifier_refs", []), "product_grade_report.verifier_refs"),
            bundle_validation_report_ref=validate_ref(
                data.get("bundle_validation_report_ref"),
                "product_grade_report.bundle_validation_report_ref",
            ),
            product_grade=require_bool(data.get("product_grade"), "product_grade_report.product_grade"),
            recommended_registry_status=RegistryStatus(
                require_non_empty_str(
                    data.get("recommended_registry_status"),
                    "product_grade_report.recommended_registry_status",
                )
            ),
            findings=[
                ProductGradeFinding.from_dict(require_mapping(item, "product_grade_report.findings[]"))
                for item in data.get("findings", [])
            ],
            outcome_category=require_non_empty_str(
                data.get("outcome_category", "candidate_registered"),
                "product_grade_report.outcome_category",
            ),
            repair_packet_ref=data.get("repair_packet_ref", ""),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_GRADE_REPORT_SCHEMA_VERSION),
                "product_grade_report.schema_version",
            ),
        )
        report.validate()
        return report

    @property
    def report_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    def validate(self) -> None:
        if self.schema_version != PRODUCT_GRADE_REPORT_SCHEMA_VERSION:
            raise ContractValidationError("product_grade_report.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "product_grade_report.bundle_id")
        for ref in self.package_refs:
            validate_ref(ref, "product_grade_report.package_refs[]")
        if not self.package_hash.startswith("sha256:"):
            raise ContractValidationError("product_grade_report.package_hash must be sha256")
        require_non_empty_str(self.verifier_status, "product_grade_report.verifier_status")
        for ref in self.verifier_refs:
            validate_ref(ref, "product_grade_report.verifier_refs[]")
        validate_ref(self.bundle_validation_report_ref, "product_grade_report.bundle_validation_report_ref")
        if not isinstance(self.product_grade, bool):
            raise ContractValidationError("product_grade_report.product_grade must be a boolean")
        if self.product_grade and self.findings:
            raise ContractValidationError("product-grade report cannot pass with findings")
        if self.outcome_category not in PRODUCT_GRADE_OUTCOME_CATEGORIES:
            raise ContractValidationError("product_grade_report.outcome_category is unsupported")
        if self.product_grade and self.outcome_category != "product_grade_registered":
            raise ContractValidationError("product-grade pass must use product_grade_registered outcome")
        if self.product_grade and self.recommended_registry_status != RegistryStatus.PRODUCT_GRADE_REGISTERED:
            raise ContractValidationError("product-grade pass must recommend product_grade_registered")
        if not self.product_grade and self.recommended_registry_status == RegistryStatus.PRODUCT_GRADE_REGISTERED:
            raise ContractValidationError("product-grade failure cannot recommend product_grade_registered")
        if self.repair_packet_ref:
            validate_ref(self.repair_packet_ref, "product_grade_report.repair_packet_ref")
        for finding in self.findings:
            finding.validate()
        assert_refs_only_payload(self.to_dict_without_hash(), "product_grade_report")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "package_refs": list(self.package_refs),
            "package_hash": self.package_hash,
            "verifier_status": self.verifier_status,
            "verifier_refs": list(self.verifier_refs),
            "bundle_validation_report_ref": self.bundle_validation_report_ref,
            "product_grade": self.product_grade,
            "recommended_registry_status": self.recommended_registry_status.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "outcome_category": self.outcome_category,
            "repair_packet_ref": self.repair_packet_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["report_hash"] = self.report_hash
        return payload


def evaluate_product_grade(
    *,
    workspace: str | Path = ".",
    bundle_id: str,
    mission_result: MissionResult,
    bundle_validation_report_ref: str = "qa/skill_bundle_validation_report.json",
    report_ref: str = PRODUCT_GRADE_REPORT_REF,
    repair_packet_ref: str = PRODUCT_REPAIR_PACKET_REF,
) -> ProductGradeReport:
    bundle_report = BundleValidationReport.from_dict(
        read_json_ref(workspace, bundle_validation_report_ref, "bundle_validation_report")
    )
    coverage_report = _read_acceptance_coverage_report(workspace)
    findings: list[ProductGradeFinding] = []
    if mission_result.status != VerificationStatus.COMPLETED_VERIFIED.value:
        findings.append(
            ProductGradeFinding(
                finding_id="SF-PG-VERIFIER-NOT-CLOSED",
                severity="blocking",
                message=f"MissionForge verifier status is {mission_result.status}",
                source_refs=list(mission_result.evidence_refs),
            )
        )
    for check in bundle_report.blocking_failures:
        finding_id = f"bundle_validator:{check.check_id}"
        if mission_result.status == VerificationStatus.COMPLETED_VERIFIED.value and _is_mission_ir_covered(
            coverage_report,
            check.check_id,
        ):
            finding_id = f"coverage_miss:{check.check_id}"
        findings.append(
            ProductGradeFinding(
                finding_id=finding_id,
                severity="blocking",
                message=check.message,
                source_refs=list(check.evidence_refs),
            )
        )
    product_contract = _read_product_contract(workspace)
    if product_contract is not None:
        missing_package_refs = sorted(set(product_contract.target_package_refs) - set(bundle_report.package_refs))
        if missing_package_refs:
            findings.append(
                ProductGradeFinding(
                    finding_id="SF-PG-PACKAGE-REFS-MISMATCH",
                    severity="blocking",
                    message=f"Package refs do not satisfy product contract targets: {missing_package_refs}",
                    source_refs=[
                        "product_contract/skill_product_contract.json",
                        bundle_validation_report_ref,
                    ],
                )
            )
    product_grade = not findings
    package_hash = package_fingerprint(workspace, bundle_report.package_refs)
    recommended = RegistryStatus.PRODUCT_GRADE_REGISTERED if product_grade else RegistryStatus.CANDIDATE_REGISTERED
    outcome_category = _outcome_category(
        product_grade=product_grade,
        mission_status=mission_result.status,
        findings=findings,
    )
    written_repair_ref = ""
    if findings:
        packet = ProductRepairPacket(
            bundle_id=bundle_id,
            repair_items=[finding for finding in findings if finding.severity in {"blocking", "major"}],
            source_refs=[bundle_validation_report_ref, *mission_result.evidence_refs],
        )
        write_json_ref(workspace, repair_packet_ref, packet.to_dict())
        written_repair_ref = repair_packet_ref
    report = ProductGradeReport(
        bundle_id=bundle_id,
        package_refs=list(bundle_report.package_refs),
        package_hash=package_hash,
        verifier_status=mission_result.status,
        verifier_refs=list(mission_result.evidence_refs),
        bundle_validation_report_ref=bundle_validation_report_ref,
        product_grade=product_grade,
        recommended_registry_status=recommended,
        findings=findings,
        outcome_category=outcome_category,
        repair_packet_ref=written_repair_ref,
    )
    write_json_ref(workspace, report_ref, report.to_dict())
    return report


def _read_product_contract(workspace: str | Path) -> SkillProductContract | None:
    try:
        return SkillProductContract.from_dict(
            read_json_ref(workspace, "product_contract/skill_product_contract.json", "skill_product_contract")
        )
    except ContractValidationError as exc:
        if "ref does not exist" in str(exc):
            return None
        raise


def _read_acceptance_coverage_report(workspace: str | Path) -> AcceptanceCoverageReport | None:
    if not ref_exists(workspace, ACCEPTANCE_COVERAGE_REPORT_REF):
        return None
    return AcceptanceCoverageReport.from_dict(
        read_json_ref(workspace, ACCEPTANCE_COVERAGE_REPORT_REF, "acceptance_coverage_report")
    )


def _is_mission_ir_covered(report: AcceptanceCoverageReport | None, check_id: str) -> bool:
    if report is None:
        return False
    for item in report.items:
        if item.check_id == check_id:
            return item.covered and item.coverage_route in {
                AcceptanceCoverageRoute.MISSION_IR_VALIDATOR,
                AcceptanceCoverageRoute.MISSION_IR_MANUAL_GATE,
                AcceptanceCoverageRoute.MISSION_IR_PROFILE,
            }
    return False


def _outcome_category(
    *,
    product_grade: bool,
    mission_status: str,
    findings: list[ProductGradeFinding],
) -> str:
    if product_grade:
        return "product_grade_registered"
    if mission_status != VerificationStatus.COMPLETED_VERIFIED.value:
        return "mission_verifier_failed"
    if any(finding.finding_id.startswith("coverage_miss:") for finding in findings):
        return "coverage_miss"
    if findings:
        return "product_grade_failed_after_covered_verification"
    return "candidate_registered"

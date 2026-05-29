"""Refs-only SkillFoundry product report."""

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
    stable_json_hash,
    validate_ref,
)

from .registry import RegistryEntry
from .workspace import write_json_ref


PRODUCT_REPORT_SCHEMA_VERSION = "missionforge_skillfoundry.product_report.v1"
PRODUCT_REPORT_REF = "reports/skillfoundry_product_report.json"


@dataclass(frozen=True)
class SkillFoundryProductReport:
    """Product-facing refs-only read model."""

    bundle_id: str
    request_ref: str
    product_contract_ref: str
    mission_ref: str
    mission_run_id: str
    verifier_refs: list[str]
    product_grade_report_ref: str
    registry_decision_ref: str
    package_refs: list[str]
    final_status: str
    product_grade_outcome_category: str = ""
    trust_boundary_flags: dict[str, bool] = field(
        default_factory=lambda: {
            "user_input_material_excluded": True,
            "dialog_material_excluded": True,
            "worker_self_report_is_acceptance": False,
        }
    )
    schema_version: str = PRODUCT_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundryProductReport":
        data = require_mapping(payload, "skillfoundry_product_report")
        report = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skillfoundry_product_report.bundle_id"),
            request_ref=validate_ref(data.get("request_ref"), "skillfoundry_product_report.request_ref"),
            product_contract_ref=validate_ref(
                data.get("product_contract_ref"),
                "skillfoundry_product_report.product_contract_ref",
            ),
            mission_ref=validate_ref(data.get("mission_ref"), "skillfoundry_product_report.mission_ref"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "skillfoundry_product_report.mission_run_id"),
            verifier_refs=require_str_list(data.get("verifier_refs", []), "skillfoundry_product_report.verifier_refs"),
            product_grade_report_ref=validate_ref(
                data.get("product_grade_report_ref"),
                "skillfoundry_product_report.product_grade_report_ref",
            ),
            registry_decision_ref=validate_ref(
                data.get("registry_decision_ref"),
                "skillfoundry_product_report.registry_decision_ref",
            ),
            package_refs=require_str_list(data.get("package_refs", []), "skillfoundry_product_report.package_refs"),
            final_status=require_non_empty_str(data.get("final_status"), "skillfoundry_product_report.final_status"),
            product_grade_outcome_category=require_non_empty_str(
                data.get("product_grade_outcome_category", data.get("final_status")),
                "skillfoundry_product_report.product_grade_outcome_category",
            ),
            trust_boundary_flags=require_mapping(
                data.get("trust_boundary_flags", {}),
                "skillfoundry_product_report.trust_boundary_flags",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_REPORT_SCHEMA_VERSION),
                "skillfoundry_product_report.schema_version",
            ),
        )
        report.validate()
        return report

    @property
    def report_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    def validate(self) -> None:
        if self.schema_version != PRODUCT_REPORT_SCHEMA_VERSION:
            raise ContractValidationError("skillfoundry_product_report.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "skillfoundry_product_report.bundle_id")
        validate_ref(self.request_ref, "skillfoundry_product_report.request_ref")
        validate_ref(self.product_contract_ref, "skillfoundry_product_report.product_contract_ref")
        validate_ref(self.mission_ref, "skillfoundry_product_report.mission_ref")
        require_non_empty_str(self.mission_run_id, "skillfoundry_product_report.mission_run_id")
        for ref in self.verifier_refs:
            validate_ref(ref, "skillfoundry_product_report.verifier_refs[]")
        validate_ref(self.product_grade_report_ref, "skillfoundry_product_report.product_grade_report_ref")
        validate_ref(self.registry_decision_ref, "skillfoundry_product_report.registry_decision_ref")
        for ref in self.package_refs:
            validate_ref(ref, "skillfoundry_product_report.package_refs[]")
        require_non_empty_str(self.final_status, "skillfoundry_product_report.final_status")
        require_non_empty_str(
            self.product_grade_outcome_category,
            "skillfoundry_product_report.product_grade_outcome_category",
        )
        for key, value in self.trust_boundary_flags.items():
            require_non_empty_str(key, "skillfoundry_product_report.trust_boundary_flags.key")
            if not isinstance(value, bool):
                raise ContractValidationError("skillfoundry_product_report.trust_boundary_flags values must be boolean")
        assert_refs_only_payload(self.to_dict_without_hash(), "skillfoundry_product_report")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "request_ref": self.request_ref,
            "product_contract_ref": self.product_contract_ref,
            "mission_ref": self.mission_ref,
            "mission_run_id": self.mission_run_id,
            "verifier_refs": list(self.verifier_refs),
            "product_grade_report_ref": self.product_grade_report_ref,
            "registry_decision_ref": self.registry_decision_ref,
            "package_refs": list(self.package_refs),
            "final_status": self.final_status,
            "product_grade_outcome_category": self.product_grade_outcome_category,
            "trust_boundary_flags": dict(self.trust_boundary_flags),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["report_hash"] = self.report_hash
        return payload


def write_product_report(
    *,
    workspace: str | Path = ".",
    bundle_id: str,
    request_ref: str,
    product_contract_ref: str,
    mission_ref: str,
    mission_run_id: str,
    verifier_refs: list[str],
    product_grade_report_ref: str,
    registry_entry: RegistryEntry,
    package_refs: list[str],
    product_grade_outcome_category: str = "",
    report_ref: str = PRODUCT_REPORT_REF,
) -> SkillFoundryProductReport:
    report = SkillFoundryProductReport(
        bundle_id=bundle_id,
        request_ref=request_ref,
        product_contract_ref=product_contract_ref,
        mission_ref=mission_ref,
        mission_run_id=mission_run_id,
        verifier_refs=verifier_refs,
        product_grade_report_ref=product_grade_report_ref,
        registry_decision_ref=registry_entry.registry_decision_ref,
        package_refs=package_refs,
        final_status=registry_entry.status.value,
        product_grade_outcome_category=product_grade_outcome_category or registry_entry.status.value,
    )
    write_json_ref(workspace, report_ref, report.to_dict())
    return report

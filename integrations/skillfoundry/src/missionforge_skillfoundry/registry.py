"""Local SkillFoundry product registry."""

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

from .product_contract import RegistryStatus
from .product_grade_gate import ProductGradeReport
from .workspace import read_json_ref, write_json_ref


REGISTRY_SCHEMA_VERSION = "missionforge_skillfoundry.registry.v1"
REGISTRY_REF = "registry/skillfoundry_registry.json"


@dataclass(frozen=True)
class RegistryEntry:
    """One SkillFoundry registry entry."""

    entry_id: str
    bundle_id: str
    status: RegistryStatus
    package_hash: str
    package_refs: list[str]
    product_grade_report_ref: str
    registry_decision_ref: str = REGISTRY_REF
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegistryEntry":
        data = require_mapping(payload, "registry_entry")
        entry = cls(
            entry_id=require_non_empty_str(data.get("entry_id"), "registry_entry.entry_id"),
            bundle_id=require_non_empty_str(data.get("bundle_id"), "registry_entry.bundle_id"),
            status=RegistryStatus(require_non_empty_str(data.get("status"), "registry_entry.status")),
            package_hash=require_non_empty_str(data.get("package_hash"), "registry_entry.package_hash"),
            package_refs=require_str_list(data.get("package_refs", []), "registry_entry.package_refs"),
            product_grade_report_ref=validate_ref(
                data.get("product_grade_report_ref"),
                "registry_entry.product_grade_report_ref",
            ),
            registry_decision_ref=validate_ref(
                data.get("registry_decision_ref", REGISTRY_REF),
                "registry_entry.registry_decision_ref",
            ),
            metadata=require_mapping(data.get("metadata", {}), "registry_entry.metadata"),
        )
        entry.validate()
        return entry

    @property
    def entry_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    def validate(self) -> None:
        require_non_empty_str(self.entry_id, "registry_entry.entry_id")
        require_non_empty_str(self.bundle_id, "registry_entry.bundle_id")
        if self.status == RegistryStatus.PRODUCT_GRADE_REGISTERED and not self.product_grade_report_ref:
            raise ContractValidationError("product_grade_registered requires product_grade_report_ref")
        if not self.package_hash.startswith("sha256:"):
            raise ContractValidationError("registry_entry.package_hash must be sha256")
        for ref in self.package_refs:
            validate_ref(ref, "registry_entry.package_refs[]")
        validate_ref(self.product_grade_report_ref, "registry_entry.product_grade_report_ref")
        validate_ref(self.registry_decision_ref, "registry_entry.registry_decision_ref")
        assert_refs_only_payload(self.to_dict_without_hash(), "registry_entry")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "bundle_id": self.bundle_id,
            "status": self.status.value,
            "package_hash": self.package_hash,
            "package_refs": list(self.package_refs),
            "product_grade_report_ref": self.product_grade_report_ref,
            "registry_decision_ref": self.registry_decision_ref,
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["entry_hash"] = self.entry_hash
        return payload


@dataclass(frozen=True)
class SkillFoundryRegistry:
    """Refs-only local registry payload."""

    entries: list[RegistryEntry] = field(default_factory=list)
    schema_version: str = REGISTRY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundryRegistry":
        data = require_mapping(payload, "skillfoundry_registry")
        registry = cls(
            entries=[
                RegistryEntry.from_dict(require_mapping(item, "skillfoundry_registry.entries[]"))
                for item in data.get("entries", [])
            ],
            schema_version=require_non_empty_str(
                data.get("schema_version", REGISTRY_SCHEMA_VERSION),
                "skillfoundry_registry.schema_version",
            ),
        )
        registry.validate()
        return registry

    def validate(self) -> None:
        if self.schema_version != REGISTRY_SCHEMA_VERSION:
            raise ContractValidationError("skillfoundry_registry.schema_version is unsupported")
        seen: set[str] = set()
        for entry in self.entries:
            entry.validate()
            if entry.entry_id in seen:
                raise ContractValidationError(f"duplicate registry entry_id: {entry.entry_id}")
            seen.add(entry.entry_id)
        assert_refs_only_payload(self.to_dict_without_validation(), "skillfoundry_registry")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def register_skill_bundle(
    *,
    workspace: str | Path = ".",
    product_grade_report_ref: str = "qa/product_grade_report.json",
    registry_ref: str = REGISTRY_REF,
    allow_candidate: bool = True,
) -> RegistryEntry:
    report = ProductGradeReport.from_dict(read_json_ref(workspace, product_grade_report_ref, "product_grade_report"))
    status = report.recommended_registry_status
    if status == RegistryStatus.PRODUCT_GRADE_REGISTERED and not report.product_grade:
        raise ContractValidationError("cannot product-grade register a failed ProductGradeGate report")
    if status == RegistryStatus.CANDIDATE_REGISTERED and not allow_candidate:
        raise ContractValidationError("candidate registration is disabled")
    existing = _load_registry(workspace, registry_ref)
    entry = RegistryEntry(
        entry_id=f"{report.bundle_id}-{status.value}",
        bundle_id=report.bundle_id,
        status=status,
        package_hash=report.package_hash,
        package_refs=list(report.package_refs),
        product_grade_report_ref=product_grade_report_ref,
        registry_decision_ref=registry_ref,
        metadata={"product_grade": report.product_grade},
    )
    entries = [item for item in existing.entries if item.entry_id != entry.entry_id]
    entries.append(entry)
    registry = SkillFoundryRegistry(entries=entries)
    write_json_ref(workspace, registry_ref, registry.to_dict())
    return entry


def _load_registry(workspace: str | Path, registry_ref: str) -> SkillFoundryRegistry:
    try:
        return SkillFoundryRegistry.from_dict(read_json_ref(workspace, registry_ref, "skillfoundry_registry"))
    except ContractValidationError as exc:
        if "ref does not exist" not in str(exc):
            raise
        return SkillFoundryRegistry()

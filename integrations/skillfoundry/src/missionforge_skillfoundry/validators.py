"""Prompt-only SkillFoundry bundle validators."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
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

from .product_contract import BundleProfile, ProductAcceptanceMatrix, SkillBundleManifest, SkillProductContract
from .workspace import read_json_ref, read_text_ref, ref_exists, write_json_ref


BUNDLE_VALIDATION_REPORT_SCHEMA_VERSION = "missionforge_skillfoundry.bundle_validation_report.v1"
BUNDLE_VALIDATION_REPORT_REF = "qa/skill_bundle_validation_report.json"
RAW_CONTEXT_MARKERS = [
    "raw_prompt",
    "raw transcript",
    "raw_transcript",
    "conversation.jsonl",
    "provider payload",
    "provider_payload",
    "chat transcript",
]
SELF_GRADE_MARKERS = [
    "product_grade_registered",
    "product-grade registered",
    "product grade registered",
    "product_grade: true",
    "product grade: true",
]


@dataclass(frozen=True)
class BundleValidationCheck:
    """One SkillFoundry bundle validation check."""

    check_id: str
    passed: bool
    message: str
    evidence_refs: list[str] = field(default_factory=list)
    blocking: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BundleValidationCheck":
        data = require_mapping(payload, "bundle_validation_check")
        check = cls(
            check_id=require_non_empty_str(data.get("check_id"), "bundle_validation_check.check_id"),
            passed=bool(data.get("passed")),
            message=require_non_empty_str(data.get("message"), "bundle_validation_check.message"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "bundle_validation_check.evidence_refs"),
            blocking=bool(data.get("blocking", True)),
        )
        check.validate()
        return check

    def validate(self) -> None:
        require_non_empty_str(self.check_id, "bundle_validation_check.check_id")
        if not isinstance(self.passed, bool):
            raise ContractValidationError("bundle_validation_check.passed must be a boolean")
        require_non_empty_str(self.message, "bundle_validation_check.message")
        for ref in self.evidence_refs:
            validate_ref(ref, "bundle_validation_check.evidence_refs[]")
        if not isinstance(self.blocking, bool):
            raise ContractValidationError("bundle_validation_check.blocking must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class BundleValidationReport:
    """Refs-only prompt-only bundle validation report."""

    bundle_id: str
    package_refs: list[str]
    checks: list[BundleValidationCheck]
    matrix_ref: str = "product_contract/product_acceptance_matrix.json"
    schema_version: str = BUNDLE_VALIDATION_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BundleValidationReport":
        data = require_mapping(payload, "bundle_validation_report")
        report = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "bundle_validation_report.bundle_id"),
            package_refs=require_str_list(data.get("package_refs", []), "bundle_validation_report.package_refs"),
            checks=[
                BundleValidationCheck.from_dict(require_mapping(item, "bundle_validation_report.checks[]"))
                for item in data.get("checks", [])
            ],
            matrix_ref=validate_ref(
                data.get("matrix_ref", "product_contract/product_acceptance_matrix.json"),
                "bundle_validation_report.matrix_ref",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", BUNDLE_VALIDATION_REPORT_SCHEMA_VERSION),
                "bundle_validation_report.schema_version",
            ),
        )
        report.validate()
        return report

    @property
    def passed(self) -> bool:
        return all(check.passed or not check.blocking for check in self.checks)

    @property
    def blocking_failures(self) -> list[BundleValidationCheck]:
        return [check for check in self.checks if check.blocking and not check.passed]

    @property
    def report_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_validation())

    def validate(self) -> None:
        if self.schema_version != BUNDLE_VALIDATION_REPORT_SCHEMA_VERSION:
            raise ContractValidationError("bundle_validation_report.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "bundle_validation_report.bundle_id")
        for ref in self.package_refs:
            validate_ref(ref, "bundle_validation_report.package_refs[]")
        for check in self.checks:
            check.validate()
        if not self.checks:
            raise ContractValidationError("bundle_validation_report.checks must not be empty")
        validate_ref(self.matrix_ref, "bundle_validation_report.matrix_ref")
        assert_refs_only_payload(self.to_dict_without_validation(), "bundle_validation_report")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "package_refs": list(self.package_refs),
            "matrix_ref": self.matrix_ref,
            "checks": [check.to_dict() for check in self.checks],
            "passed": self.passed,
            "blocking_failure_count": len(self.blocking_failures),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_validation()
        payload["report_hash"] = self.report_hash
        return payload


def validate_skill_bundle(
    *,
    workspace: str | Path = ".",
    bundle_id: str,
    matrix_ref: str = "product_contract/product_acceptance_matrix.json",
    report_ref: str = BUNDLE_VALIDATION_REPORT_REF,
) -> BundleValidationReport:
    matrix = ProductAcceptanceMatrix.from_dict(read_json_ref(workspace, matrix_ref, "product_acceptance_matrix"))
    if matrix.bundle_profile == BundleProfile.PROMPT_ONLY:
        report = _validate_prompt_only_bundle(workspace=workspace, bundle_id=bundle_id, matrix=matrix, matrix_ref=matrix_ref)
    elif matrix.bundle_profile == BundleProfile.CODE_RUNTIME:
        report = _validate_code_runtime_bundle(workspace=workspace, bundle_id=bundle_id, matrix=matrix, matrix_ref=matrix_ref)
    else:
        raise ContractValidationError(f"bundle validators do not implement profile: {matrix.bundle_profile.value}")
    write_json_ref(workspace, report_ref, report.to_dict())
    return report


def _validate_prompt_only_bundle(
    *,
    workspace: str | Path,
    bundle_id: str,
    matrix: ProductAcceptanceMatrix,
    matrix_ref: str,
) -> BundleValidationReport:
    checks: list[BundleValidationCheck] = []
    package_refs = ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"]

    skill_exists = ref_exists(workspace, "package/SKILL.md")
    checks.append(_check("SF-PROMPT-SKILL-EXISTS", skill_exists, "package/SKILL.md exists", ["package/SKILL.md"] if skill_exists else []))

    manifest_exists = ref_exists(workspace, "package/skillfoundry.bundle.json")
    checks.append(
        _check(
            "SF-PROMPT-MANIFEST-EXISTS",
            manifest_exists,
            "package/skillfoundry.bundle.json exists",
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    manifest: SkillBundleManifest | None = None
    manifest_schema_passed = False
    manifest_message = "manifest is missing"
    if manifest_exists:
        try:
            manifest = SkillBundleManifest.from_dict(read_json_ref(workspace, "package/skillfoundry.bundle.json", "skill_bundle_manifest"))
            manifest_schema_passed = manifest.bundle_id == bundle_id
            manifest_message = "manifest schema valid" if manifest_schema_passed else "manifest bundle_id does not match request"
        except Exception as exc:
            manifest_message = f"manifest schema invalid: {exc}"
    checks.append(
        _check(
            "SF-PROMPT-MANIFEST-SCHEMA",
            manifest_schema_passed,
            manifest_message,
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )
    entrypoint_passed = manifest is not None and manifest.entrypoint == "SKILL.md"
    checks.append(
        _check(
            "SF-PROMPT-ENTRYPOINT",
            entrypoint_passed,
            "manifest entrypoint points to SKILL.md" if entrypoint_passed else "manifest entrypoint must be SKILL.md",
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    readme_exists = ref_exists(workspace, "package/README.md")
    checks.append(_check("SF-PROMPT-README-EXISTS", readme_exists, "package/README.md exists", ["package/README.md"] if readme_exists else []))

    refs_safe_passed = manifest is not None
    checks.append(
        _check(
            "SF-PROMPT-REFS-SAFE",
            refs_safe_passed,
            "manifest refs are safe package refs" if refs_safe_passed else "manifest refs are invalid or unavailable",
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    marker_text = _package_text(workspace, package_refs)
    raw_marker = _first_marker(marker_text, RAW_CONTEXT_MARKERS)
    checks.append(
        _check(
            "SF-PROMPT-NO-RAW-CONTEXT",
            raw_marker is None,
            "package does not expose raw context markers" if raw_marker is None else f"package exposes raw context marker: {raw_marker}",
            [ref for ref in package_refs if ref_exists(workspace, ref)],
        )
    )

    self_grade_marker = _first_marker(marker_text, SELF_GRADE_MARKERS)
    checks.append(
        _check(
            "SF-PROMPT-NO-SELF-GRADE",
            self_grade_marker is None,
            "package does not claim product-grade approval" if self_grade_marker is None else f"package self-claims product grade: {self_grade_marker}",
            [ref for ref in package_refs if ref_exists(workspace, ref)],
        )
    )

    checks.append(
        _check(
            "SF-PROMPT-VERIFICATION",
            True,
            "external verifier and ProductGradeGate refs are required outside package content",
            [matrix_ref],
        )
    )

    _ensure_matrix_covered(matrix, checks)
    report = BundleValidationReport(
        bundle_id=bundle_id,
        package_refs=[ref for ref in package_refs if ref_exists(workspace, ref)],
        checks=checks,
        matrix_ref=matrix_ref,
    )
    return report


def _validate_code_runtime_bundle(
    *,
    workspace: str | Path,
    bundle_id: str,
    matrix: ProductAcceptanceMatrix,
    matrix_ref: str,
) -> BundleValidationReport:
    checks: list[BundleValidationCheck] = []
    contract = _read_product_contract(workspace)
    package_refs = list(
        contract.target_package_refs
        if contract is not None and contract.bundle_profile == BundleProfile.CODE_RUNTIME
        else ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"]
    )

    skill_exists = ref_exists(workspace, "package/SKILL.md")
    checks.append(_check("SF-CODE-SKILL-EXISTS", skill_exists, "package/SKILL.md exists", ["package/SKILL.md"] if skill_exists else []))

    manifest_exists = ref_exists(workspace, "package/skillfoundry.bundle.json")
    checks.append(
        _check(
            "SF-CODE-MANIFEST-EXISTS",
            manifest_exists,
            "package/skillfoundry.bundle.json exists",
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    manifest: SkillBundleManifest | None = None
    manifest_schema_passed = False
    manifest_message = "manifest is missing"
    if manifest_exists:
        try:
            manifest = SkillBundleManifest.from_dict(read_json_ref(workspace, "package/skillfoundry.bundle.json", "skill_bundle_manifest"))
            manifest_schema_passed = manifest.bundle_id == bundle_id and manifest.bundle_profile == BundleProfile.CODE_RUNTIME
            manifest_message = "manifest schema valid" if manifest_schema_passed else "manifest bundle_id or profile does not match request"
            package_refs = _dedupe_refs([*package_refs, *manifest.runtime_assets, *manifest.data_assets, *manifest.references])
        except Exception as exc:
            manifest_message = f"manifest schema invalid: {exc}"
    checks.append(
        _check(
            "SF-CODE-MANIFEST-SCHEMA",
            manifest_schema_passed,
            manifest_message,
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    entrypoint_passed = manifest is not None and manifest.entrypoint == "SKILL.md"
    checks.append(
        _check(
            "SF-CODE-ENTRYPOINT",
            entrypoint_passed,
            "manifest entrypoint points to SKILL.md" if entrypoint_passed else "manifest entrypoint must be SKILL.md",
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    readme_exists = ref_exists(workspace, "package/README.md")
    checks.append(_check("SF-CODE-README-EXISTS", readme_exists, "package/README.md exists", ["package/README.md"] if readme_exists else []))

    runtime_assets = list(manifest.runtime_assets if manifest is not None else [])
    runtime_assets_declared = bool(runtime_assets) and any(
        ref.startswith("package/scripts/") or ref.startswith("package/bin/") for ref in runtime_assets
    )
    checks.append(
        _check(
            "SF-CODE-RUNTIME-ASSETS-DECLARED",
            runtime_assets_declared,
            "manifest declares package-local runtime assets" if runtime_assets_declared else "manifest must declare scripts or bin runtime assets",
            ["package/skillfoundry.bundle.json"] if manifest_exists else [],
        )
    )

    missing_runtime_assets = [ref for ref in runtime_assets if not ref_exists(workspace, ref)]
    runtime_assets_exist = bool(runtime_assets) and not missing_runtime_assets
    checks.append(
        _check(
            "SF-CODE-RUNTIME-ASSETS-EXIST",
            runtime_assets_exist,
            "declared runtime assets exist" if runtime_assets_exist else f"missing runtime assets: {missing_runtime_assets}",
            [ref for ref in runtime_assets if ref_exists(workspace, ref)],
        )
    )

    script_refs = [ref for ref in runtime_assets if ref.startswith("package/scripts/") and ref.endswith(".py")]
    script_failures = [ref for ref in script_refs if not _script_exposes_help(workspace, ref)]
    scripts_runnable = bool(script_refs) and not script_failures
    checks.append(
        _check(
            "SF-CODE-SCRIPTS-RUNNABLE",
            scripts_runnable,
            "helper scripts expose local --help entrypoints" if scripts_runnable else f"helper scripts missing --help entrypoint: {script_failures or script_refs}",
            [ref for ref in script_refs if ref_exists(workspace, ref)],
        )
    )

    schema_refs = list(manifest.data_assets if manifest is not None else [])
    schema_failures = [ref for ref in schema_refs if ref.startswith("package/schemas/") and not _json_ref_parses(workspace, ref)]
    schema_refs_expected = [ref for ref in schema_refs if ref.startswith("package/schemas/")]
    schemas_valid = bool(schema_refs_expected) and not schema_failures
    checks.append(
        _check(
            "SF-CODE-SCHEMAS-VALID",
            schemas_valid,
            "declared schemas parse as JSON" if schemas_valid else f"schema refs missing or invalid: {schema_failures or schema_refs_expected}",
            [ref for ref in schema_refs_expected if ref_exists(workspace, ref)],
        )
    )

    marker_text = _package_text(workspace, package_refs)
    raw_marker = _first_marker(marker_text, RAW_CONTEXT_MARKERS)
    checks.append(
        _check(
            "SF-CODE-NO-RAW-CONTEXT",
            raw_marker is None,
            "package does not expose raw context markers" if raw_marker is None else f"package exposes raw context marker: {raw_marker}",
            [ref for ref in package_refs if ref_exists(workspace, ref)],
        )
    )

    self_grade_marker = _first_marker(marker_text, SELF_GRADE_MARKERS)
    checks.append(
        _check(
            "SF-CODE-NO-SELF-GRADE",
            self_grade_marker is None,
            "package does not claim product-grade approval" if self_grade_marker is None else f"package self-claims product grade: {self_grade_marker}",
            [ref for ref in package_refs if ref_exists(workspace, ref)],
        )
    )

    checks.append(
        _check(
            "SF-CODE-VERIFICATION",
            True,
            "external verifier and ProductGradeGate refs are required outside package content",
            [matrix_ref],
        )
    )

    _ensure_matrix_covered(matrix, checks)
    return BundleValidationReport(
        bundle_id=bundle_id,
        package_refs=[ref for ref in package_refs if ref_exists(workspace, ref)],
        checks=checks,
        matrix_ref=matrix_ref,
    )


def _check(check_id: str, passed: bool, message: str, evidence_refs: list[str]) -> BundleValidationCheck:
    return BundleValidationCheck(
        check_id=check_id,
        passed=passed,
        message=message,
        evidence_refs=evidence_refs,
        blocking=True,
    )


def _package_text(workspace: str | Path, refs: list[str]) -> str:
    chunks: list[str] = []
    for ref in refs:
        if ref_exists(workspace, ref):
            try:
                chunks.append(read_text_ref(workspace, ref))
            except UnicodeDecodeError:
                continue
    return "\n".join(chunks).lower()


def _first_marker(text: str, markers: list[str]) -> str | None:
    for marker in markers:
        if marker.lower() in text:
            return marker
    return None


def _ensure_matrix_covered(matrix: ProductAcceptanceMatrix, checks: list[BundleValidationCheck]) -> None:
    check_ids = {check.check_id for check in checks}
    missing = [item.check_id for item in matrix.items if item.check_id not in check_ids]
    if missing:
        raise ContractValidationError(f"bundle validators do not cover acceptance matrix checks: {missing}")


def _read_product_contract(workspace: str | Path) -> SkillProductContract | None:
    try:
        return SkillProductContract.from_dict(
            read_json_ref(workspace, "product_contract/skill_product_contract.json", "skill_product_contract")
        )
    except ContractValidationError as exc:
        if "ref does not exist" in str(exc):
            return None
        raise


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "package_refs[]")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def _script_exposes_help(workspace: str | Path, ref: str) -> bool:
    if not ref_exists(workspace, ref):
        return False
    try:
        text = read_text_ref(workspace, ref)
    except UnicodeDecodeError:
        return False
    lowered = text.lower()
    has_help = "--help" in lowered or "argparse" in lowered
    has_entrypoint = "def main" in lowered or "__name__" in lowered
    return has_help and has_entrypoint


def _json_ref_parses(workspace: str | Path, ref: str) -> bool:
    if not ref_exists(workspace, ref):
        return False
    try:
        json.loads(read_text_ref(workspace, ref))
    except (ContractValidationError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return True

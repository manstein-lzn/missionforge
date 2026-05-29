"""SkillFoundry product contracts on top of MissionForge."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any, Mapping

from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


REQUEST_SCHEMA_VERSION = "missionforge_skillfoundry.request.v1"
PRODUCT_CONTRACT_SCHEMA_VERSION = "missionforge_skillfoundry.product_contract.v1"
ACCEPTANCE_MATRIX_SCHEMA_VERSION = "missionforge_skillfoundry.product_acceptance_matrix.v1"
BUNDLE_MANIFEST_SCHEMA_VERSION = "skillfoundry.bundle.v1"
PROMPT_ONLY_REQUIRED_PACKAGE_REFS = [
    "package/SKILL.md",
    "package/skillfoundry.bundle.json",
    "package/README.md",
]
CODE_RUNTIME_BASE_PACKAGE_REFS = [
    "package/SKILL.md",
    "package/skillfoundry.bundle.json",
    "package/README.md",
]
CODE_RUNTIME_REQUIRED_PACKAGE_REFS = [
    *CODE_RUNTIME_BASE_PACKAGE_REFS,
    "package/scripts/skill_runtime.py",
    "package/schemas/runtime.schema.json",
]
PROMPT_ONLY_MANIFEST_REQUIRED_KEYS = [
    "schema_version",
    "bundle_id",
    "bundle_profile",
    "entrypoint",
    "capability_surface",
    "runtime_assets",
    "data_assets",
    "references",
    "environment",
    "permissions",
    "verification",
    "distribution",
]
PROMPT_ONLY_CHECKS = [
    (
        "SF-PROMPT-SKILL-EXISTS",
        "package/SKILL.md exists",
    ),
    (
        "SF-PROMPT-MANIFEST-EXISTS",
        "package/skillfoundry.bundle.json exists",
    ),
    (
        "SF-PROMPT-MANIFEST-SCHEMA",
        "manifest has required fields",
    ),
    (
        "SF-PROMPT-ENTRYPOINT",
        "manifest entrypoint is SKILL.md inside package",
    ),
    (
        "SF-PROMPT-README-EXISTS",
        "package/README.md exists",
    ),
    (
        "SF-PROMPT-REFS-SAFE",
        "manifest refs are workspace-relative package refs",
    ),
    (
        "SF-PROMPT-NO-RAW-CONTEXT",
        "package does not expose raw prompt or transcript markers",
    ),
    (
        "SF-PROMPT-NO-SELF-GRADE",
        "package does not claim its own product-grade approval",
    ),
    (
        "SF-PROMPT-VERIFICATION",
        "verifier and product gate refs are recorded externally",
    ),
]
CODE_RUNTIME_CHECKS = [
    (
        "SF-CODE-SKILL-EXISTS",
        "package/SKILL.md exists",
    ),
    (
        "SF-CODE-MANIFEST-EXISTS",
        "package/skillfoundry.bundle.json exists",
    ),
    (
        "SF-CODE-MANIFEST-SCHEMA",
        "manifest has required code-runtime fields",
    ),
    (
        "SF-CODE-ENTRYPOINT",
        "manifest entrypoint is SKILL.md inside package",
    ),
    (
        "SF-CODE-README-EXISTS",
        "package/README.md exists",
    ),
    (
        "SF-CODE-RUNTIME-ASSETS-DECLARED",
        "manifest declares script or binary runtime assets",
    ),
    (
        "SF-CODE-RUNTIME-ASSETS-EXIST",
        "declared runtime assets exist inside package",
    ),
    (
        "SF-CODE-SCRIPTS-RUNNABLE",
        "declared helper scripts expose a runnable Python entrypoint",
    ),
    (
        "SF-CODE-SCHEMAS-VALID",
        "declared schema artifacts parse as JSON",
    ),
    (
        "SF-CODE-NO-RAW-CONTEXT",
        "package does not expose raw prompt or transcript markers",
    ),
    (
        "SF-CODE-NO-SELF-GRADE",
        "package does not claim its own product-grade approval",
    ),
    (
        "SF-CODE-VERIFICATION",
        "verifier and product gate refs are recorded externally",
    ),
]
PROFILE_REQUIRED_PACKAGE_REFS = {
    "prompt_only": PROMPT_ONLY_REQUIRED_PACKAGE_REFS,
    "code_runtime": CODE_RUNTIME_BASE_PACKAGE_REFS,
}
PROFILE_ACCEPTANCE_CHECKS = {
    "prompt_only": PROMPT_ONLY_CHECKS,
    "code_runtime": CODE_RUNTIME_CHECKS,
}
PACKAGE_REF_PATTERN = re.compile(r"package/[A-Za-z0-9._@=+,-]+(?:/[A-Za-z0-9._@=+,-]+)*")
FORBIDDEN_REQUEST_FIELDS = {
    "conversation",
    "messages",
    "prompt",
    "raw_prompt",
    "raw_text",
    "raw_transcript",
    "transcript",
}


class BundleProfile(StrEnum):
    """SkillFoundry bundle profile vocabulary."""

    PROMPT_ONLY = "prompt_only"
    SCRIPT_TOOL = "script_tool"
    CODE_RUNTIME = "code_runtime"
    KNOWLEDGE_RUNTIME = "knowledge_runtime"
    MCP_RUNTIME = "mcp_runtime"
    SERVICE_RUNTIME = "service_runtime"
    FULL_RUNTIME_BUNDLE = "full_runtime_bundle"


IMPLEMENTED_BUNDLE_PROFILES = {
    BundleProfile.PROMPT_ONLY,
    BundleProfile.CODE_RUNTIME,
}


class RiskDomain(StrEnum):
    """Product risk domains that drive SkillFoundry acceptance defaults."""

    PRIVACY_SENSITIVE_INPUT = "privacy_sensitive_input"
    FILESYSTEM_WRITE = "filesystem_write"
    STRUCTURED_DATA_VALIDATION = "structured_data_validation"
    EXTERNAL_DOCUMENT_INGESTION = "external_document_ingestion"
    DOMAIN_KNOWLEDGE_RELIABILITY = "domain_knowledge_reliability"
    NETWORK_BOUNDARY = "network_boundary"
    RUNTIME_EXECUTION = "runtime_execution"
    LONG_RUNNING_SERVICE = "long_running_service"
    DISTRIBUTION_PACKAGE = "distribution_package"


class RegistryStatus(StrEnum):
    """SkillFoundry registry status vocabulary."""

    GENERATED = "generated"
    VERIFIED = "verified"
    CANDIDATE_REGISTERED = "candidate_registered"
    PRODUCT_GRADE_REGISTERED = "product_grade_registered"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class SkillFoundryRequest:
    """User-facing product request or sanitized FrontDesk output."""

    request_id: str
    bundle_id: str
    desired_capability: str
    target_user: str = "codex_user"
    triggers: list[str] = field(default_factory=list)
    non_triggers: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    must: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    privacy_boundaries: list[str] = field(default_factory=list)
    distribution_boundaries: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    desired_bundle_profile: BundleProfile = BundleProfile.PROMPT_ONLY
    schema_version: str = REQUEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundryRequest":
        data = _strict_mapping(
            payload,
            "skillfoundry_request",
            {
                "schema_version",
                "request_id",
                "bundle_id",
                "desired_capability",
                "target_user",
                "triggers",
                "non_triggers",
                "expected_outputs",
                "must",
                "must_not",
                "privacy_boundaries",
                "distribution_boundaries",
                "source_refs",
                "desired_bundle_profile",
            },
        )
        request = cls(
            request_id=require_non_empty_str(data.get("request_id"), "skillfoundry_request.request_id"),
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skillfoundry_request.bundle_id"),
            desired_capability=require_non_empty_str(
                data.get("desired_capability"),
                "skillfoundry_request.desired_capability",
            ),
            target_user=require_non_empty_str(data.get("target_user", "codex_user"), "skillfoundry_request.target_user"),
            triggers=require_str_list(data.get("triggers", []), "skillfoundry_request.triggers"),
            non_triggers=require_str_list(data.get("non_triggers", []), "skillfoundry_request.non_triggers"),
            expected_outputs=require_str_list(data.get("expected_outputs", []), "skillfoundry_request.expected_outputs"),
            must=require_str_list(data.get("must", []), "skillfoundry_request.must"),
            must_not=require_str_list(data.get("must_not", []), "skillfoundry_request.must_not"),
            privacy_boundaries=require_str_list(
                data.get("privacy_boundaries", []),
                "skillfoundry_request.privacy_boundaries",
            ),
            distribution_boundaries=require_str_list(
                data.get("distribution_boundaries", []),
                "skillfoundry_request.distribution_boundaries",
            ),
            source_refs=require_str_list(data.get("source_refs", []), "skillfoundry_request.source_refs"),
            desired_bundle_profile=_bundle_profile(
                data.get("desired_bundle_profile", BundleProfile.PROMPT_ONLY.value),
                "skillfoundry_request.desired_bundle_profile",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", REQUEST_SCHEMA_VERSION),
                "skillfoundry_request.schema_version",
            ),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if self.schema_version != REQUEST_SCHEMA_VERSION:
            raise ContractValidationError("skillfoundry_request.schema_version is unsupported")
        require_non_empty_str(self.request_id, "skillfoundry_request.request_id")
        require_non_empty_str(self.bundle_id, "skillfoundry_request.bundle_id")
        require_non_empty_str(self.desired_capability, "skillfoundry_request.desired_capability")
        require_non_empty_str(self.target_user, "skillfoundry_request.target_user")
        for ref in self.source_refs:
            validate_ref(ref, "skillfoundry_request.source_refs[]")
        _bundle_profile(self.desired_bundle_profile, "skillfoundry_request.desired_bundle_profile")
        _reject_raw_fields(self.to_dict_without_validation(), "skillfoundry_request")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "bundle_id": self.bundle_id,
            "desired_capability": self.desired_capability,
            "target_user": self.target_user,
            "triggers": list(self.triggers),
            "non_triggers": list(self.non_triggers),
            "expected_outputs": list(self.expected_outputs),
            "must": list(self.must),
            "must_not": list(self.must_not),
            "privacy_boundaries": list(self.privacy_boundaries),
            "distribution_boundaries": list(self.distribution_boundaries),
            "source_refs": list(self.source_refs),
            "desired_bundle_profile": self.desired_bundle_profile.value,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ProductAcceptanceItem:
    """One ProductAcceptanceMatrix item."""

    check_id: str
    purpose: str
    blocking: bool = True
    evaluator: str = "missionforge_skillfoundry.prompt_only"
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductAcceptanceItem":
        data = _strict_mapping(
            payload,
            "product_acceptance_item",
            {"check_id", "purpose", "blocking", "evaluator", "evidence_refs"},
        )
        item = cls(
            check_id=require_non_empty_str(data.get("check_id"), "product_acceptance_item.check_id"),
            purpose=require_non_empty_str(data.get("purpose"), "product_acceptance_item.purpose"),
            blocking=bool(data.get("blocking", True)),
            evaluator=require_non_empty_str(
                data.get("evaluator", "missionforge_skillfoundry.prompt_only"),
                "product_acceptance_item.evaluator",
            ),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "product_acceptance_item.evidence_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.check_id, "product_acceptance_item.check_id")
        require_non_empty_str(self.purpose, "product_acceptance_item.purpose")
        if not isinstance(self.blocking, bool):
            raise ContractValidationError("product_acceptance_item.blocking must be a boolean")
        require_non_empty_str(self.evaluator, "product_acceptance_item.evaluator")
        for ref in self.evidence_refs:
            validate_ref(ref, "product_acceptance_item.evidence_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "check_id": self.check_id,
            "purpose": self.purpose,
            "blocking": self.blocking,
            "evaluator": self.evaluator,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ProductAcceptanceMatrix:
    """SkillFoundry product-grade acceptance matrix."""

    matrix_id: str
    bundle_id: str
    bundle_profile: BundleProfile
    risk_domains: list[RiskDomain] = field(default_factory=list)
    items: list[ProductAcceptanceItem] = field(default_factory=list)
    schema_version: str = ACCEPTANCE_MATRIX_SCHEMA_VERSION

    @classmethod
    def for_prompt_only(
        cls,
        *,
        bundle_id: str,
        matrix_id: str | None = None,
        risk_domains: list[RiskDomain] | None = None,
    ) -> "ProductAcceptanceMatrix":
        matrix = cls(
            matrix_id=matrix_id or f"{bundle_id}-prompt-only-matrix",
            bundle_id=bundle_id,
            bundle_profile=BundleProfile.PROMPT_ONLY,
            risk_domains=list(risk_domains or []),
            items=[ProductAcceptanceItem(check_id=check_id, purpose=purpose) for check_id, purpose in PROMPT_ONLY_CHECKS],
        )
        matrix.validate()
        return matrix

    @classmethod
    def for_code_runtime(
        cls,
        *,
        bundle_id: str,
        matrix_id: str | None = None,
        risk_domains: list[RiskDomain] | None = None,
    ) -> "ProductAcceptanceMatrix":
        matrix = cls.for_profile(
            bundle_id=bundle_id,
            profile=BundleProfile.CODE_RUNTIME,
            matrix_id=matrix_id,
            risk_domains=risk_domains,
        )
        matrix.validate()
        return matrix

    @classmethod
    def for_profile(
        cls,
        *,
        bundle_id: str,
        profile: BundleProfile,
        matrix_id: str | None = None,
        risk_domains: list[RiskDomain] | None = None,
    ) -> "ProductAcceptanceMatrix":
        safe_profile = _implemented_bundle_profile(profile, "product_acceptance_matrix.bundle_profile")
        matrix = cls(
            matrix_id=matrix_id or f"{bundle_id}-{safe_profile.value.replace('_', '-')}-matrix",
            bundle_id=bundle_id,
            bundle_profile=safe_profile,
            risk_domains=list(risk_domains or []),
            items=[
                ProductAcceptanceItem(
                    check_id=check_id,
                    purpose=purpose,
                    evaluator=f"missionforge_skillfoundry.{safe_profile.value}",
                )
                for check_id, purpose in acceptance_checks_for_profile(safe_profile)
            ],
        )
        matrix.validate()
        return matrix

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductAcceptanceMatrix":
        data = _strict_mapping(
            payload,
            "product_acceptance_matrix",
            {"schema_version", "matrix_id", "bundle_id", "bundle_profile", "risk_domains", "items"},
        )
        matrix = cls(
            matrix_id=require_non_empty_str(data.get("matrix_id"), "product_acceptance_matrix.matrix_id"),
            bundle_id=require_non_empty_str(data.get("bundle_id"), "product_acceptance_matrix.bundle_id"),
            bundle_profile=_bundle_profile(data.get("bundle_profile"), "product_acceptance_matrix.bundle_profile"),
            risk_domains=[
                _risk_domain(item, "product_acceptance_matrix.risk_domains[]")
                for item in data.get("risk_domains", [])
            ],
            items=[
                ProductAcceptanceItem.from_dict(require_mapping(item, "product_acceptance_matrix.items[]"))
                for item in data.get("items", [])
            ],
            schema_version=require_non_empty_str(
                data.get("schema_version", ACCEPTANCE_MATRIX_SCHEMA_VERSION),
                "product_acceptance_matrix.schema_version",
            ),
        )
        matrix.validate()
        return matrix

    @property
    def matrix_hash(self) -> str:
        return stable_json_hash(self.to_dict())

    def validate(self) -> None:
        if self.schema_version != ACCEPTANCE_MATRIX_SCHEMA_VERSION:
            raise ContractValidationError("product_acceptance_matrix.schema_version is unsupported")
        require_non_empty_str(self.matrix_id, "product_acceptance_matrix.matrix_id")
        require_non_empty_str(self.bundle_id, "product_acceptance_matrix.bundle_id")
        _bundle_profile(self.bundle_profile, "product_acceptance_matrix.bundle_profile")
        seen: set[str] = set()
        for item in self.items:
            item.validate()
            if item.check_id in seen:
                raise ContractValidationError(f"duplicate product acceptance check_id: {item.check_id}")
            seen.add(item.check_id)
        if not self.items:
            raise ContractValidationError("product_acceptance_matrix.items must not be empty")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return assert_refs_only_payload(
            {
                "schema_version": self.schema_version,
                "matrix_id": self.matrix_id,
                "bundle_id": self.bundle_id,
                "bundle_profile": self.bundle_profile.value,
                "risk_domains": [item.value for item in self.risk_domains],
                "items": [item.to_dict() for item in self.items],
            },
            "product_acceptance_matrix",
        )


@dataclass(frozen=True)
class SkillBundleManifest:
    """Machine-readable SkillFoundry bundle manifest."""

    bundle_id: str
    bundle_profile: BundleProfile
    entrypoint: str = "SKILL.md"
    capability_surface: dict[str, Any] = field(default_factory=lambda: {"codex_skill": {"entry_ref": "package/SKILL.md"}})
    runtime_assets: list[str] = field(default_factory=list)
    data_assets: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    distribution: dict[str, Any] = field(default_factory=dict)
    schema_version: str = BUNDLE_MANIFEST_SCHEMA_VERSION

    @classmethod
    def prompt_only(cls, bundle_id: str, *, references: list[str] | None = None) -> "SkillBundleManifest":
        manifest = cls(
            bundle_id=bundle_id,
            bundle_profile=BundleProfile.PROMPT_ONLY,
            references=list(references or []),
            verification={
                "matrix_ref": "product_contract/product_acceptance_matrix.json",
                "product_grade_ref": "qa/product_grade_report.json",
            },
            distribution={"status": "local"},
        )
        manifest.validate()
        return manifest

    @classmethod
    def code_runtime(
        cls,
        bundle_id: str,
        *,
        runtime_assets: list[str] | None = None,
        data_assets: list[str] | None = None,
        references: list[str] | None = None,
        command_health_check: list[str] | None = None,
    ) -> "SkillBundleManifest":
        resolved_runtime_assets = list(
            runtime_assets if runtime_assets is not None else ["package/scripts/skill_runtime.py"]
        )
        resolved_health_check = list(
            command_health_check or _default_code_runtime_health_check(resolved_runtime_assets)
        )
        manifest = cls(
            bundle_id=bundle_id,
            bundle_profile=BundleProfile.CODE_RUNTIME,
            capability_surface=capability_surface_for_profile(BundleProfile.CODE_RUNTIME),
            runtime_assets=resolved_runtime_assets,
            data_assets=list(data_assets if data_assets is not None else ["package/schemas/runtime.schema.json"]),
            references=list(references or []),
            environment={
                "runtime": "python3",
                "health_check": resolved_health_check,
            },
            permissions={
                "network": False,
                "filesystem_write_refs": ["package"],
                "external_process": True,
            },
            verification={
                "matrix_ref": "product_contract/product_acceptance_matrix.json",
                "product_grade_ref": "qa/product_grade_report.json",
                "command_health_check": resolved_health_check,
            },
            distribution={"status": "local"},
        )
        manifest.validate()
        return manifest

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillBundleManifest":
        data = _strict_mapping(
            payload,
            "skill_bundle_manifest",
            {
                "schema_version",
                "bundle_id",
                "bundle_profile",
                "entrypoint",
                "capability_surface",
                "runtime_assets",
                "data_assets",
                "references",
                "environment",
                "permissions",
                "verification",
                "distribution",
            },
        )
        manifest = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skill_bundle_manifest.bundle_id"),
            bundle_profile=_bundle_profile(data.get("bundle_profile"), "skill_bundle_manifest.bundle_profile"),
            entrypoint=validate_ref(data.get("entrypoint", "SKILL.md"), "skill_bundle_manifest.entrypoint"),
            capability_surface=require_mapping(
                data.get("capability_surface", {}),
                "skill_bundle_manifest.capability_surface",
            ),
            runtime_assets=require_str_list(data.get("runtime_assets", []), "skill_bundle_manifest.runtime_assets"),
            data_assets=require_str_list(data.get("data_assets", []), "skill_bundle_manifest.data_assets"),
            references=require_str_list(data.get("references", []), "skill_bundle_manifest.references"),
            environment=require_mapping(data.get("environment", {}), "skill_bundle_manifest.environment"),
            permissions=require_mapping(data.get("permissions", {}), "skill_bundle_manifest.permissions"),
            verification=require_mapping(data.get("verification", {}), "skill_bundle_manifest.verification"),
            distribution=require_mapping(data.get("distribution", {}), "skill_bundle_manifest.distribution"),
            schema_version=require_non_empty_str(
                data.get("schema_version", BUNDLE_MANIFEST_SCHEMA_VERSION),
                "skill_bundle_manifest.schema_version",
            ),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.schema_version != BUNDLE_MANIFEST_SCHEMA_VERSION:
            raise ContractValidationError("skill_bundle_manifest.schema_version is unsupported")
        require_non_empty_str(self.bundle_id, "skill_bundle_manifest.bundle_id")
        _bundle_profile(self.bundle_profile, "skill_bundle_manifest.bundle_profile")
        validate_ref(self.entrypoint, "skill_bundle_manifest.entrypoint")
        if self.entrypoint != "SKILL.md":
            raise ContractValidationError("skill_bundle_manifest.entrypoint must be SKILL.md")
        _validate_manifest_for_profile(self)
        _validate_manifest_refs(self)
        assert_refs_only_payload(self.to_dict_without_validation(), "skill_bundle_manifest")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "bundle_profile": self.bundle_profile.value,
            "entrypoint": self.entrypoint,
            "capability_surface": ensure_json_value(self.capability_surface, "skill_bundle_manifest.capability_surface"),
            "runtime_assets": list(self.runtime_assets),
            "data_assets": list(self.data_assets),
            "references": list(self.references),
            "environment": ensure_json_value(self.environment, "skill_bundle_manifest.environment"),
            "permissions": ensure_json_value(self.permissions, "skill_bundle_manifest.permissions"),
            "verification": ensure_json_value(self.verification, "skill_bundle_manifest.verification"),
            "distribution": ensure_json_value(self.distribution, "skill_bundle_manifest.distribution"),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class SkillProductContract:
    """Frozen SkillFoundry product contract compiled into MissionForge."""

    contract_id: str
    bundle_id: str
    request_ref: str
    bundle_profile: BundleProfile
    risk_domains: list[RiskDomain] = field(default_factory=list)
    capability_surface: dict[str, Any] = field(default_factory=lambda: {"codex_skill": {"entry_ref": "package/SKILL.md"}})
    target_package_refs: list[str] = field(default_factory=lambda: list(PROMPT_ONLY_REQUIRED_PACKAGE_REFS))
    allowed_write_scopes: list[str] = field(default_factory=lambda: ["package"])
    acceptance_summary: str = "Prompt-only SkillFoundry bundle must pass product-grade validators."
    verification_principles: list[str] = field(
        default_factory=lambda: [
            "MissionForge verifier owns completion.",
            "ProductGradeGate owns product-grade registration.",
            "Worker self-report is never acceptance.",
        ]
    )
    matrix_ref: str = "product_contract/product_acceptance_matrix.json"
    manifest_ref: str = "package/skillfoundry.bundle.json"
    schema_version: str = PRODUCT_CONTRACT_SCHEMA_VERSION

    @classmethod
    def from_request(
        cls,
        request: SkillFoundryRequest,
        *,
        request_ref: str,
    ) -> "SkillProductContract":
        request.validate()
        profile = _implemented_bundle_profile(request.desired_bundle_profile, "skill_product_contract.bundle_profile")
        contract = cls(
            contract_id=f"{request.bundle_id}-product-contract",
            bundle_id=request.bundle_id,
            request_ref=validate_ref(request_ref, "skill_product_contract.request_ref"),
            bundle_profile=profile,
            risk_domains=infer_risk_domains(request),
            capability_surface=capability_surface_for_profile(profile),
            target_package_refs=target_package_refs_for_profile(profile, request=request),
            allowed_write_scopes=allowed_write_scopes_for_profile(profile),
            acceptance_summary=acceptance_summary_for_profile(profile),
        )
        contract.validate()
        return contract

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillProductContract":
        data = _strict_mapping(
            payload,
            "skill_product_contract",
            {
                "schema_version",
                "contract_id",
                "bundle_id",
                "request_ref",
                "bundle_profile",
                "risk_domains",
                "capability_surface",
                "target_package_refs",
                "allowed_write_scopes",
                "acceptance_summary",
                "verification_principles",
                "matrix_ref",
                "manifest_ref",
                "contract_hash",
            },
        )
        contract = cls(
            contract_id=require_non_empty_str(data.get("contract_id"), "skill_product_contract.contract_id"),
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skill_product_contract.bundle_id"),
            request_ref=validate_ref(data.get("request_ref"), "skill_product_contract.request_ref"),
            bundle_profile=_bundle_profile(data.get("bundle_profile"), "skill_product_contract.bundle_profile"),
            risk_domains=[
                _risk_domain(item, "skill_product_contract.risk_domains[]")
                for item in data.get("risk_domains", [])
            ],
            capability_surface=require_mapping(
                data.get("capability_surface", {"codex_skill": {"entry_ref": "package/SKILL.md"}}),
                "skill_product_contract.capability_surface",
            ),
            target_package_refs=require_str_list(
                data.get("target_package_refs", PROMPT_ONLY_REQUIRED_PACKAGE_REFS),
                "skill_product_contract.target_package_refs",
            ),
            allowed_write_scopes=require_str_list(
                data.get("allowed_write_scopes", ["package"]),
                "skill_product_contract.allowed_write_scopes",
            ),
            acceptance_summary=require_non_empty_str(
                data.get("acceptance_summary", "Prompt-only SkillFoundry bundle must pass product-grade validators."),
                "skill_product_contract.acceptance_summary",
            ),
            verification_principles=require_str_list(
                data.get("verification_principles", []),
                "skill_product_contract.verification_principles",
            ),
            matrix_ref=validate_ref(
                data.get("matrix_ref", "product_contract/product_acceptance_matrix.json"),
                "skill_product_contract.matrix_ref",
            ),
            manifest_ref=validate_ref(
                data.get("manifest_ref", "package/skillfoundry.bundle.json"),
                "skill_product_contract.manifest_ref",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_CONTRACT_SCHEMA_VERSION),
                "skill_product_contract.schema_version",
            ),
        )
        contract.validate()
        if data.get("contract_hash") not in {None, contract.contract_hash}:
            raise ContractValidationError("skill_product_contract.contract_hash does not match payload")
        return contract

    @property
    def contract_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    def validate(self) -> None:
        if self.schema_version != PRODUCT_CONTRACT_SCHEMA_VERSION:
            raise ContractValidationError("skill_product_contract.schema_version is unsupported")
        require_non_empty_str(self.contract_id, "skill_product_contract.contract_id")
        require_non_empty_str(self.bundle_id, "skill_product_contract.bundle_id")
        validate_ref(self.request_ref, "skill_product_contract.request_ref")
        profile = _implemented_bundle_profile(self.bundle_profile, "skill_product_contract.bundle_profile")
        for ref in self.target_package_refs:
            validate_ref(ref, "skill_product_contract.target_package_refs[]")
            if not any(_is_within(ref, scope) for scope in self.allowed_write_scopes):
                raise ContractValidationError("skill_product_contract.target_package_refs must stay inside allowed_write_scopes")
        required_refs = set(PROFILE_REQUIRED_PACKAGE_REFS[profile.value])
        missing_refs = sorted(required_refs - set(self.target_package_refs))
        if missing_refs:
            raise ContractValidationError(f"skill_product_contract.target_package_refs missing required refs: {missing_refs}")
        if profile == BundleProfile.CODE_RUNTIME:
            if not any(ref.startswith("package/scripts/") or ref.startswith("package/bin/") for ref in self.target_package_refs):
                raise ContractValidationError("code-runtime skill_product_contract.target_package_refs must include script or bin runtime assets")
            if not any(ref.startswith("package/schemas/") for ref in self.target_package_refs):
                raise ContractValidationError("code-runtime skill_product_contract.target_package_refs must include schema assets")
        for scope in self.allowed_write_scopes:
            validate_ref(scope, "skill_product_contract.allowed_write_scopes[]")
        validate_ref(self.matrix_ref, "skill_product_contract.matrix_ref")
        validate_ref(self.manifest_ref, "skill_product_contract.manifest_ref")
        require_non_empty_str(self.acceptance_summary, "skill_product_contract.acceptance_summary")
        require_str_list(self.verification_principles, "skill_product_contract.verification_principles")
        assert_refs_only_payload(self.to_dict_without_hash(), "skill_product_contract")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "bundle_id": self.bundle_id,
            "request_ref": self.request_ref,
            "bundle_profile": self.bundle_profile.value,
            "risk_domains": [item.value for item in self.risk_domains],
            "capability_surface": ensure_json_value(self.capability_surface, "skill_product_contract.capability_surface"),
            "target_package_refs": list(self.target_package_refs),
            "allowed_write_scopes": list(self.allowed_write_scopes),
            "acceptance_summary": self.acceptance_summary,
            "verification_principles": list(self.verification_principles),
            "matrix_ref": self.matrix_ref,
            "manifest_ref": self.manifest_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["contract_hash"] = self.contract_hash
        return payload


def infer_risk_domains(request: SkillFoundryRequest) -> list[RiskDomain]:
    request.validate()
    text = " ".join(
        [
            request.desired_capability,
            *request.expected_outputs,
            *request.must,
            *request.must_not,
            *request.privacy_boundaries,
            *request.distribution_boundaries,
        ]
    ).lower()
    result: list[RiskDomain] = [RiskDomain.PRIVACY_SENSITIVE_INPUT, RiskDomain.DISTRIBUTION_PACKAGE]
    if any(token in text for token in ["write", "file", "overwrite", "path", "filesystem", "package"]):
        result.append(RiskDomain.FILESYSTEM_WRITE)
    if any(token in text for token in ["json", "schema", "manifest", "structured"]):
        result.append(RiskDomain.STRUCTURED_DATA_VALIDATION)
    if any(token in text for token in ["reference", "corpus", "document", "pdf", "knowledge"]):
        result.append(RiskDomain.EXTERNAL_DOCUMENT_INGESTION)
        result.append(RiskDomain.DOMAIN_KNOWLEDGE_RELIABILITY)
    if request.desired_bundle_profile == BundleProfile.CODE_RUNTIME:
        result.append(RiskDomain.RUNTIME_EXECUTION)
        result.append(RiskDomain.STRUCTURED_DATA_VALIDATION)
        result.append(RiskDomain.FILESYSTEM_WRITE)
    if any(token in text for token in ["network", "http", "api", "mcp"]):
        result.append(RiskDomain.NETWORK_BOUNDARY)
    return _dedupe_risks(result)


def target_package_refs_for_profile(
    profile: BundleProfile,
    *,
    request: SkillFoundryRequest | None = None,
) -> list[str]:
    safe_profile = _implemented_bundle_profile(profile, "bundle_profile")
    refs = list(PROFILE_REQUIRED_PACKAGE_REFS[safe_profile.value])
    if request is not None:
        for ref in request.expected_outputs:
            if ref.startswith("package/") and ref not in refs:
                refs.append(validate_ref(ref, "skillfoundry_request.expected_outputs[]"))
    if safe_profile == BundleProfile.CODE_RUNTIME and request is not None:
        for ref in refs_matching_package_patterns(
            [
                request.desired_capability,
                *request.expected_outputs,
                *request.must,
            ]
        ):
            if ref not in refs:
                refs.append(ref)
        text = " ".join([request.desired_capability, *request.expected_outputs, *request.must]).lower()
        if not any(ref.startswith("package/scripts/") or ref.startswith("package/bin/") for ref in refs):
            refs.append("package/scripts/skill_runtime.py")
        if not any(ref.startswith("package/schemas/") for ref in refs):
            refs.append("package/schemas/runtime.schema.json")
        if ("bin/" in text or "binary" in text or "sidecar" in text) and not any(ref.startswith("package/bin/") for ref in refs):
            refs.append("package/bin/runtime")
    elif safe_profile == BundleProfile.CODE_RUNTIME:
        for ref in CODE_RUNTIME_REQUIRED_PACKAGE_REFS:
            if ref not in refs:
                refs.append(ref)
    return _dedupe_refs(refs)


def allowed_write_scopes_for_profile(profile: BundleProfile) -> list[str]:
    safe_profile = _implemented_bundle_profile(profile, "bundle_profile")
    if safe_profile == BundleProfile.CODE_RUNTIME:
        return ["package"]
    return ["package"]


def capability_surface_for_profile(profile: BundleProfile) -> dict[str, Any]:
    safe_profile = _implemented_bundle_profile(profile, "bundle_profile")
    if safe_profile == BundleProfile.CODE_RUNTIME:
        return {
            "codex_skill": {"entry_ref": "package/SKILL.md"},
            "helper_scripts": {"ref_prefix": "package/scripts/"},
            "runtime_assets": {"ref_prefixes": ["package/scripts/", "package/bin/"]},
            "schemas": {"ref_prefix": "package/schemas/"},
        }
    return {"codex_skill": {"entry_ref": "package/SKILL.md"}}


def acceptance_summary_for_profile(profile: BundleProfile) -> str:
    safe_profile = _implemented_bundle_profile(profile, "bundle_profile")
    if safe_profile == BundleProfile.CODE_RUNTIME:
        return "Code-runtime SkillFoundry bundle must pass package, runtime asset, schema, and product-grade validators."
    return "Prompt-only SkillFoundry bundle must pass product-grade validators."


def acceptance_checks_for_profile(profile: BundleProfile) -> list[tuple[str, str]]:
    safe_profile = _implemented_bundle_profile(profile, "bundle_profile")
    return list(PROFILE_ACCEPTANCE_CHECKS[safe_profile.value])


def manifest_for_profile(
    profile: BundleProfile,
    bundle_id: str,
    *,
    target_package_refs: list[str] | None = None,
    references: list[str] | None = None,
) -> SkillBundleManifest:
    safe_profile = _implemented_bundle_profile(profile, "bundle_profile")
    if safe_profile == BundleProfile.CODE_RUNTIME:
        refs = list(target_package_refs or target_package_refs_for_profile(safe_profile))
        runtime_assets = [
            ref
            for ref in refs
            if ref.startswith("package/scripts/") or ref.startswith("package/bin/")
        ] or ["package/scripts/skill_runtime.py"]
        data_assets = [ref for ref in refs if ref.startswith("package/schemas/")] or ["package/schemas/runtime.schema.json"]
        return SkillBundleManifest.code_runtime(
            bundle_id,
            runtime_assets=runtime_assets,
            data_assets=data_assets,
            references=references,
        )
    return SkillBundleManifest.prompt_only(bundle_id, references=references)


def _bundle_profile(value: Any, field_name: str) -> BundleProfile:
    if isinstance(value, BundleProfile):
        return value
    if isinstance(value, str):
        try:
            return BundleProfile(value)
        except ValueError as exc:
            raise ContractValidationError(f"{field_name} must be a supported bundle profile") from exc
    raise ContractValidationError(f"{field_name} must be a supported bundle profile")


def _implemented_bundle_profile(value: Any, field_name: str) -> BundleProfile:
    profile = _bundle_profile(value, field_name)
    if profile not in IMPLEMENTED_BUNDLE_PROFILES:
        raise ContractValidationError(f"{field_name} is not implemented by this SkillFoundry integration")
    return profile


def _risk_domain(value: Any, field_name: str) -> RiskDomain:
    if isinstance(value, RiskDomain):
        return value
    if isinstance(value, str):
        try:
            return RiskDomain(value)
        except ValueError as exc:
            raise ContractValidationError(f"{field_name} must be a supported risk domain") from exc
    raise ContractValidationError(f"{field_name} must be a supported risk domain")


def _dedupe_risks(values: list[RiskDomain]) -> list[RiskDomain]:
    result: list[RiskDomain] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        safe_ref = validate_ref(value, "ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    _reject_raw_fields(data, field_name)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")
    return data


def _reject_raw_fields(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ContractValidationError(f"{field_name} keys must be non-empty strings")
            normalized = key.lower()
            if normalized in FORBIDDEN_REQUEST_FIELDS:
                raise ContractValidationError(f"{field_name}.{key} must be represented as a sanitized source ref")
            _reject_raw_fields(item, f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_raw_fields(item, f"{field_name}[{index}]")


def _validate_manifest_refs(manifest: SkillBundleManifest) -> None:
    for ref in [*manifest.runtime_assets, *manifest.data_assets, *manifest.references]:
        safe_ref = validate_ref(ref, "skill_bundle_manifest.refs[]")
        if not _is_within(safe_ref, "package"):
            raise ContractValidationError("skill_bundle_manifest refs must stay inside package")


def _validate_manifest_for_profile(manifest: SkillBundleManifest) -> None:
    profile = _implemented_bundle_profile(manifest.bundle_profile, "skill_bundle_manifest.bundle_profile")
    if profile == BundleProfile.PROMPT_ONLY:
        if manifest.runtime_assets or manifest.data_assets:
            raise ContractValidationError("prompt-only skill_bundle_manifest must not declare runtime or data assets")
        return
    if profile == BundleProfile.CODE_RUNTIME:
        if not manifest.runtime_assets:
            raise ContractValidationError("code-runtime skill_bundle_manifest.runtime_assets must not be empty")
        if not any(ref.startswith("package/scripts/") or ref.startswith("package/bin/") for ref in manifest.runtime_assets):
            raise ContractValidationError("code-runtime skill_bundle_manifest.runtime_assets must include scripts or bin refs")
        if not any(ref.startswith("package/schemas/") for ref in manifest.data_assets):
            raise ContractValidationError("code-runtime skill_bundle_manifest.data_assets must include schema refs")
        _validate_code_runtime_capability_surface(manifest.capability_surface)
        _validate_code_runtime_permissions(manifest.permissions)
        _validate_json_ref_list(manifest.runtime_assets, "skill_bundle_manifest.runtime_assets")
        _validate_json_ref_list(manifest.data_assets, "skill_bundle_manifest.data_assets")
        health_check = manifest.verification.get("command_health_check") or manifest.environment.get("health_check")
        if health_check is not None:
            _validate_command_vector(health_check, "skill_bundle_manifest.command_health_check")
        return


def _validate_code_runtime_capability_surface(value: Mapping[str, Any]) -> None:
    surface = require_mapping(value, "skill_bundle_manifest.capability_surface")
    codex_skill = require_mapping(surface.get("codex_skill", {}), "skill_bundle_manifest.capability_surface.codex_skill")
    entry_ref = codex_skill.get("entry_ref")
    if entry_ref != "package/SKILL.md":
        raise ContractValidationError("code-runtime skill_bundle_manifest.capability_surface.codex_skill.entry_ref must be package/SKILL.md")


def _validate_code_runtime_permissions(value: Mapping[str, Any]) -> None:
    permissions = require_mapping(value, "skill_bundle_manifest.permissions")
    if permissions.get("network", False) is not False:
        raise ContractValidationError("code-runtime skill_bundle_manifest.permissions.network must default to false")
    scopes = require_str_list(
        permissions.get("filesystem_write_refs", ["package"]),
        "skill_bundle_manifest.permissions.filesystem_write_refs",
    )
    if scopes != ["package"]:
        raise ContractValidationError("code-runtime skill_bundle_manifest.permissions.filesystem_write_refs must be ['package']")


def _validate_json_ref_list(refs: list[str], field_name: str) -> None:
    for ref in refs:
        validate_ref(ref, f"{field_name}[]")


def _validate_command_vector(value: Any, field_name: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractValidationError(f"{field_name} must be a list of non-empty strings")
    for item in value:
        if item.startswith("/") or ".." in item.split("/"):
            raise ContractValidationError(f"{field_name} must not contain unsafe command path segments")


def _default_code_runtime_health_check(runtime_assets: list[str]) -> list[str]:
    script_ref = next((ref for ref in runtime_assets if ref.startswith("package/scripts/") and ref.endswith(".py")), "")
    if script_ref:
        return ["python3", script_ref, "--help"]
    binary_ref = next((ref for ref in runtime_assets if ref.startswith("package/bin/")), "")
    if binary_ref:
        return [binary_ref, "--help"]
    return ["python3", "package/scripts/skill_runtime.py", "--help"]


def refs_matching_package_patterns(values: list[str]) -> list[str]:
    refs: list[str] = []
    for value in values:
        for match in PACKAGE_REF_PATTERN.findall(value):
            candidate = match.rstrip(".,;:!?)]}'\"`")
            try:
                refs.append(validate_ref(candidate, "package_ref"))
            except ContractValidationError:
                continue
    return _dedupe_refs(refs)


def _is_within(ref: str, scope: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_scope = validate_ref(scope, "scope")
    return safe_ref == safe_scope or safe_ref.startswith(f"{safe_scope}/")

"""Deterministic SkillFoundry-to-MissionIR integration compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from missionforge.adapters.contracts import AdapterResult
from missionforge.contracts import (
    ContractValidationError,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from missionforge.freeze import freeze_mission
from missionforge.ir import CapabilityProfileRef, MissionConstraint, MissionIR, MissionObjective
from missionforge.profiles import ProfileRegistry

from .product_contract import (
    ACCEPTANCE_COVERAGE_REPORT_REF,
    BUNDLE_MANIFEST_SCHEMA_VERSION,
    AcceptanceCoverageItem,
    AcceptanceCoverageReport,
    AcceptanceCoverageRoute,
    BundleProfile,
    PROMPT_ONLY_MANIFEST_REQUIRED_KEYS,
    PROMPT_ONLY_REQUIRED_PACKAGE_REFS,
    ProductAcceptanceMatrix,
    SkillFoundryRequest,
    SkillProductContract,
    manifest_for_profile,
)
from .validators import RAW_CONTEXT_MARKERS, SELF_GRADE_MARKERS
from .workspace import write_json_ref


SKILLFOUNDRY_SOURCE_TYPES = {
    "frontdesk_contract",
    "source_manifest",
    "sanitized_source",
    "sanitized_transcript",
    "evidence_manifest",
    "package_target",
}
RAW_SOURCE_TYPES = {"raw_chat", "raw_conversation", "raw_transcript", "transcript"}
FORBIDDEN_SOURCE_FIELDS = {
    "access_token",
    "api_key",
    "body",
    "conversation",
    "credential",
    "credentials",
    "password",
    "payload",
    "prompt",
    "raw",
    "raw_body",
    "raw_payload",
    "raw_prompt",
    "raw_text",
    "raw_transcript",
    "refresh_token",
    "secret",
    "secret_key",
    "text",
    "transcript",
}
FORBIDDEN_FIELD_FRAGMENTS = {"credential", "password", "prompt", "secret", "transcript"}


@dataclass(frozen=True)
class FrontDeskArtifactRef:
    """Refs-only SkillFoundry-facing source artifact reference."""

    artifact_id: str
    ref: str
    artifact_type: str
    media_type: str = "application/json"
    role: str = "source"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrontDeskArtifactRef":
        data = _contract_mapping(
            payload,
            "frontdesk_artifact_ref",
            {"artifact_id", "ref", "artifact_type", "media_type", "role"},
        )
        artifact = cls(
            artifact_id=require_non_empty_str(data.get("artifact_id"), "frontdesk_artifact_ref.artifact_id"),
            ref=validate_ref(data.get("ref"), "frontdesk_artifact_ref.ref"),
            artifact_type=require_non_empty_str(data.get("artifact_type"), "frontdesk_artifact_ref.artifact_type"),
            media_type=require_non_empty_str(
                data.get("media_type", "application/json"),
                "frontdesk_artifact_ref.media_type",
            ),
            role=require_non_empty_str(data.get("role", "source"), "frontdesk_artifact_ref.role"),
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        require_non_empty_str(self.artifact_id, "frontdesk_artifact_ref.artifact_id")
        validate_ref(self.ref, "frontdesk_artifact_ref.ref")
        artifact_type = require_non_empty_str(self.artifact_type, "frontdesk_artifact_ref.artifact_type")
        if artifact_type in RAW_SOURCE_TYPES:
            raise ContractValidationError(
                "frontdesk_artifact_ref.artifact_type must represent a sanitized source ref, not raw transcript input"
            )
        if artifact_type not in SKILLFOUNDRY_SOURCE_TYPES:
            raise ContractValidationError(
                f"frontdesk_artifact_ref.artifact_type must be one of {sorted(SKILLFOUNDRY_SOURCE_TYPES)}"
            )
        require_non_empty_str(self.media_type, "frontdesk_artifact_ref.media_type")
        require_non_empty_str(self.role, "frontdesk_artifact_ref.role")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "artifact_id": self.artifact_id,
            "ref": self.ref,
            "artifact_type": self.artifact_type,
            "media_type": self.media_type,
            "role": self.role,
        }


@dataclass(frozen=True)
class SkillPackageTarget:
    """Refs-only declaration of the package output target."""

    target_id: str
    package_ref: str
    output_root: str = "package"
    allowed_write_scopes: list[str] = field(default_factory=lambda: ["package"])

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillPackageTarget":
        data = _contract_mapping(
            payload,
            "skill_package_target",
            {"target_id", "package_ref", "output_root", "allowed_write_scopes"},
        )
        target = cls(
            target_id=require_non_empty_str(data.get("target_id"), "skill_package_target.target_id"),
            package_ref=validate_ref(data.get("package_ref"), "skill_package_target.package_ref"),
            output_root=validate_ref(data.get("output_root", "package"), "skill_package_target.output_root"),
            allowed_write_scopes=require_str_list(
                data.get("allowed_write_scopes", ["package"]),
                "skill_package_target.allowed_write_scopes",
            ),
        )
        target.validate()
        return target

    def validate(self) -> None:
        require_non_empty_str(self.target_id, "skill_package_target.target_id")
        validate_ref(self.package_ref, "skill_package_target.package_ref")
        validate_ref(self.output_root, "skill_package_target.output_root")
        for scope in self.allowed_write_scopes:
            validate_ref(scope, "skill_package_target.allowed_write_scopes[]")
        if not any(_is_within(self.package_ref, scope) for scope in self.allowed_write_scopes):
            raise ContractValidationError("skill_package_target.package_ref must be inside allowed_write_scopes")
        if not _is_within(self.package_ref, self.output_root):
            raise ContractValidationError("skill_package_target.package_ref must be inside output_root")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "target_id": self.target_id,
            "package_ref": self.package_ref,
            "output_root": self.output_root,
            "allowed_write_scopes": list(self.allowed_write_scopes),
        }


@dataclass(frozen=True)
class SkillFoundrySourceBundle:
    """Refs-only FrontDesk-style source bundle consumed by the adapter."""

    bundle_id: str
    frontdesk_contract_ref: str
    source_manifest_ref: str
    target_package_ref: str
    allowed_write_scopes: list[str] = field(default_factory=lambda: ["package", "attempts"])
    capability_profile_refs: list[CapabilityProfileRef] = field(default_factory=list)
    verification_profile_refs: list[str] = field(default_factory=lambda: ["generic_local_verification"])
    source_refs: list[FrontDeskArtifactRef] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundrySourceBundle":
        data = _contract_mapping(
            payload,
            "skillfoundry_source_bundle",
            {
                "bundle_id",
                "frontdesk_contract_ref",
                "source_manifest_ref",
                "target_package_ref",
                "allowed_write_scopes",
                "capability_profile_refs",
                "verification_profile_refs",
                "source_refs",
            },
        )
        bundle = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skillfoundry_source_bundle.bundle_id"),
            frontdesk_contract_ref=validate_ref(
                data.get("frontdesk_contract_ref"),
                "skillfoundry_source_bundle.frontdesk_contract_ref",
            ),
            source_manifest_ref=validate_ref(
                data.get("source_manifest_ref"),
                "skillfoundry_source_bundle.source_manifest_ref",
            ),
            target_package_ref=validate_ref(
                data.get("target_package_ref"),
                "skillfoundry_source_bundle.target_package_ref",
            ),
            allowed_write_scopes=require_str_list(
                data.get("allowed_write_scopes", ["package", "attempts"]),
                "skillfoundry_source_bundle.allowed_write_scopes",
            ),
            capability_profile_refs=[
                CapabilityProfileRef.from_dict(require_mapping(item, "skillfoundry_source_bundle.capability_profile_refs[]"))
                for item in data.get("capability_profile_refs", [])
            ],
            verification_profile_refs=require_str_list(
                data.get("verification_profile_refs", ["generic_local_verification"]),
                "skillfoundry_source_bundle.verification_profile_refs",
            ),
            source_refs=[
                FrontDeskArtifactRef.from_dict(require_mapping(item, "skillfoundry_source_bundle.source_refs[]"))
                for item in data.get("source_refs", [])
            ],
        )
        bundle.validate()
        return bundle

    @property
    def package_target(self) -> SkillPackageTarget:
        return SkillPackageTarget(
            target_id=f"target-{self.bundle_id}",
            package_ref=self.target_package_ref,
            output_root=self.allowed_write_scopes[0],
            allowed_write_scopes=list(self.allowed_write_scopes),
        )

    def validate(self) -> None:
        require_non_empty_str(self.bundle_id, "skillfoundry_source_bundle.bundle_id")
        validate_ref(self.frontdesk_contract_ref, "skillfoundry_source_bundle.frontdesk_contract_ref")
        validate_ref(self.source_manifest_ref, "skillfoundry_source_bundle.source_manifest_ref")
        validate_ref(self.target_package_ref, "skillfoundry_source_bundle.target_package_ref")
        for scope in self.allowed_write_scopes:
            validate_ref(scope, "skillfoundry_source_bundle.allowed_write_scopes[]")
        if not any(_is_within(self.target_package_ref, scope) for scope in self.allowed_write_scopes):
            raise ContractValidationError("skillfoundry_source_bundle.target_package_ref outside allowed write scopes")
        if not self.capability_profile_refs:
            raise ContractValidationError(
                "skillfoundry_source_bundle.capability_profile_refs must declare capability-bundle profiles"
            )
        for profile_ref in self.capability_profile_refs:
            profile_ref.validate()
        require_str_list(self.verification_profile_refs, "skillfoundry_source_bundle.verification_profile_refs")
        for source_ref in self.source_refs:
            source_ref.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "bundle_id": self.bundle_id,
            "frontdesk_contract_ref": self.frontdesk_contract_ref,
            "source_manifest_ref": self.source_manifest_ref,
            "target_package_ref": self.target_package_ref,
            "allowed_write_scopes": list(self.allowed_write_scopes),
            "capability_profile_refs": [_capability_profile_ref_to_dict(profile_ref) for profile_ref in self.capability_profile_refs],
            "verification_profile_refs": list(self.verification_profile_refs),
            "source_refs": [source_ref.to_dict() for source_ref in self.source_refs],
        }


@dataclass(frozen=True)
class SkillFoundryCompileResult:
    """Refs-only result of compiling SkillFoundry artifacts into MissionIR."""

    bundle_id: str
    mission_ir_ref: str
    frozen_contract_ref: str
    contract_hash: str
    profile_refs: list[str] = field(default_factory=list)
    diagnostic_refs: list[str] = field(default_factory=list)
    target_package_ref: str = ""
    warnings: list[str] = field(default_factory=list)
    product_contract_ref: str = ""
    acceptance_matrix_ref: str = ""
    acceptance_coverage_report_ref: str = ""
    request_ref: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillFoundryCompileResult":
        data = _contract_mapping(
            payload,
            "skillfoundry_compile_result",
            {
                "bundle_id",
                "mission_ir_ref",
                "frozen_contract_ref",
                "contract_hash",
                "profile_refs",
                "diagnostic_refs",
                "target_package_ref",
                "warnings",
                "product_contract_ref",
                "acceptance_matrix_ref",
                "acceptance_coverage_report_ref",
                "request_ref",
            },
        )
        result = cls(
            bundle_id=require_non_empty_str(data.get("bundle_id"), "skillfoundry_compile_result.bundle_id"),
            mission_ir_ref=validate_ref(data.get("mission_ir_ref"), "skillfoundry_compile_result.mission_ir_ref"),
            frozen_contract_ref=validate_ref(
                data.get("frozen_contract_ref"),
                "skillfoundry_compile_result.frozen_contract_ref",
            ),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "skillfoundry_compile_result.contract_hash"),
            profile_refs=require_str_list(data.get("profile_refs", []), "skillfoundry_compile_result.profile_refs"),
            diagnostic_refs=require_str_list(
                data.get("diagnostic_refs", []),
                "skillfoundry_compile_result.diagnostic_refs",
            ),
            target_package_ref=validate_ref(
                data.get("target_package_ref", "package/SKILL.md"),
                "skillfoundry_compile_result.target_package_ref",
            ),
            warnings=require_str_list(data.get("warnings", []), "skillfoundry_compile_result.warnings"),
            product_contract_ref=data.get("product_contract_ref", ""),
            acceptance_matrix_ref=data.get("acceptance_matrix_ref", ""),
            acceptance_coverage_report_ref=data.get("acceptance_coverage_report_ref", ""),
            request_ref=data.get("request_ref", ""),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.bundle_id, "skillfoundry_compile_result.bundle_id")
        validate_ref(self.mission_ir_ref, "skillfoundry_compile_result.mission_ir_ref")
        validate_ref(self.frozen_contract_ref, "skillfoundry_compile_result.frozen_contract_ref")
        if not require_non_empty_str(self.contract_hash, "skillfoundry_compile_result.contract_hash").startswith("sha256:"):
            raise ContractValidationError("skillfoundry_compile_result.contract_hash must be a sha256 hash")
        for ref in self.profile_refs:
            validate_ref(ref, "skillfoundry_compile_result.profile_refs[]")
        for ref in self.diagnostic_refs:
            validate_ref(ref, "skillfoundry_compile_result.diagnostic_refs[]")
        validate_ref(self.target_package_ref, "skillfoundry_compile_result.target_package_ref")
        require_str_list(self.warnings, "skillfoundry_compile_result.warnings")
        if self.product_contract_ref:
            validate_ref(self.product_contract_ref, "skillfoundry_compile_result.product_contract_ref")
        if self.acceptance_matrix_ref:
            validate_ref(self.acceptance_matrix_ref, "skillfoundry_compile_result.acceptance_matrix_ref")
        if self.acceptance_coverage_report_ref:
            validate_ref(
                self.acceptance_coverage_report_ref,
                "skillfoundry_compile_result.acceptance_coverage_report_ref",
            )
        if self.request_ref:
            validate_ref(self.request_ref, "skillfoundry_compile_result.request_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "bundle_id": self.bundle_id,
            "mission_ir_ref": self.mission_ir_ref,
            "frozen_contract_ref": self.frozen_contract_ref,
            "contract_hash": self.contract_hash,
            "profile_refs": list(self.profile_refs),
            "diagnostic_refs": list(self.diagnostic_refs),
            "target_package_ref": self.target_package_ref,
            "warnings": list(self.warnings),
            "product_contract_ref": self.product_contract_ref,
            "acceptance_matrix_ref": self.acceptance_matrix_ref,
            "acceptance_coverage_report_ref": self.acceptance_coverage_report_ref,
            "request_ref": self.request_ref,
        }


class SkillFoundryMissionCompiler:
    """Deterministic offline compiler for FrontDesk-style refs."""

    adapter_id = "skillfoundry_mission_ir_compiler"

    def compile(
        self,
        bundle: SkillFoundrySourceBundle,
        *,
        workspace: str | Path = ".",
        registry: ProfileRegistry | None = None,
    ) -> SkillFoundryCompileResult:
        if not isinstance(bundle, SkillFoundrySourceBundle):
            raise ContractValidationError("SkillFoundryMissionCompiler consumes SkillFoundrySourceBundle objects only")
        bundle.validate()
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)

        frontdesk_contract = _read_json_ref(root, bundle.frontdesk_contract_ref, "frontdesk_contract")
        source_manifest = _read_json_ref(root, bundle.source_manifest_ref, "source_manifest")
        _reject_forbidden_source_payload(frontdesk_contract, "frontdesk_contract")
        _reject_forbidden_source_payload(source_manifest, "source_manifest")

        manifest_source_refs = _source_refs_from_manifest(source_manifest)
        source_refs = _dedupe_artifacts([*bundle.source_refs, *manifest_source_refs])
        mission = _compile_mission(bundle, frontdesk_contract, source_refs)
        frozen = freeze_mission(mission, registry=registry)

        mission_ir_ref = f"missions/{bundle.bundle_id}.mission.json"
        frozen_contract_ref = f"missions/{bundle.bundle_id}.frozen_contract.json"
        diagnostic_ref = f"evidence/{bundle.bundle_id}.skillfoundry_compile_diagnostics.json"

        _write_json_ref(root, mission_ir_ref, mission.to_dict())
        _write_json_ref(root, frozen_contract_ref, frozen.to_dict())
        _write_json_ref(
            root,
            diagnostic_ref,
            {
                "bundle_id": bundle.bundle_id,
                "adapter_id": self.adapter_id,
                "frontdesk_contract_ref": bundle.frontdesk_contract_ref,
                "source_manifest_ref": bundle.source_manifest_ref,
                "source_ref_count": len(source_refs),
                "contract_hash": frozen.contract_hash,
                "mission_ir_hash": stable_json_hash(mission.to_dict()),
            },
        )

        result = SkillFoundryCompileResult(
            bundle_id=bundle.bundle_id,
            mission_ir_ref=mission_ir_ref,
            frozen_contract_ref=frozen_contract_ref,
            contract_hash=frozen.contract_hash,
            profile_refs=[profile_ref.profile_id for profile_ref in mission.capability_profiles],
            diagnostic_refs=[diagnostic_ref],
            target_package_ref=bundle.target_package_ref,
            warnings=[],
        )
        adapter_result = AdapterResult(
            invocation_id=f"compile-{bundle.bundle_id}",
            adapter_id=self.adapter_id,
            status="completed",
            output_refs=[result.mission_ir_ref, result.frozen_contract_ref],
            diagnostic_refs=list(result.diagnostic_refs),
            metrics={
                "source_ref_count": len(source_refs),
                "capability_profile_count": len(mission.capability_profiles),
                "verification_profile_count": len(bundle.verification_profile_refs),
            },
        )
        adapter_result.validate()
        result.validate()
        return result

    def compile_request(
        self,
        request: SkillFoundryRequest,
        *,
        workspace: str | Path = ".",
        registry: ProfileRegistry | None = None,
        request_ref: str = "product_contract/skillfoundry_request.json",
    ) -> SkillFoundryCompileResult:
        """Compile a SkillFoundryRequest into MissionIR and product refs."""

        request.validate()
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        product_contract = SkillProductContract.from_request(request, request_ref=request_ref)
        matrix = ProductAcceptanceMatrix.for_profile(
            bundle_id=request.bundle_id,
            profile=product_contract.bundle_profile,
            risk_domains=list(product_contract.risk_domains),
        )
        product_contract_ref = "product_contract/skill_product_contract.json"
        matrix_ref = product_contract.matrix_ref
        coverage_report_ref = ACCEPTANCE_COVERAGE_REPORT_REF
        compiler_report_ref = "product_contract/compiler_report.json"
        write_json_ref(root, request_ref, request.to_dict())
        write_json_ref(root, product_contract_ref, product_contract.to_dict())
        write_json_ref(root, matrix_ref, matrix.to_dict())
        mission = _compile_product_mission(request, product_contract)
        frozen = freeze_mission(mission, registry=registry)
        mission_ir_ref = f"missions/{request.bundle_id}.mission.json"
        frozen_contract_ref = f"missions/{request.bundle_id}.frozen_contract.json"
        diagnostic_ref = f"evidence/{request.bundle_id}.skillfoundry_compile_diagnostics.json"
        _write_json_ref(root, mission_ir_ref, mission.to_dict())
        _write_json_ref(root, frozen_contract_ref, frozen.to_dict())
        coverage_report = _build_acceptance_coverage_report(
            matrix=matrix,
            mission=mission,
            matrix_ref=matrix_ref,
            mission_ref=mission_ir_ref,
        )
        write_json_ref(root, coverage_report_ref, coverage_report.to_dict())
        write_json_ref(
            root,
            compiler_report_ref,
            {
                "bundle_id": request.bundle_id,
                "adapter_id": self.adapter_id,
                "request_ref": request_ref,
                "product_contract_ref": product_contract_ref,
                "acceptance_matrix_ref": matrix_ref,
                "acceptance_coverage_report_ref": coverage_report_ref,
                "mission_ir_ref": mission_ir_ref,
                "frozen_contract_ref": frozen_contract_ref,
                "contract_hash": frozen.contract_hash,
                "product_contract_hash": product_contract.contract_hash,
                "acceptance_matrix_hash": matrix.matrix_hash,
                "blocking_coverage_passed": coverage_report.blocking_coverage_passed,
            },
        )
        _write_json_ref(
            root,
            diagnostic_ref,
            {
                "bundle_id": request.bundle_id,
                "adapter_id": self.adapter_id,
                "request_ref": request_ref,
                "product_contract_ref": product_contract_ref,
                "acceptance_matrix_ref": matrix_ref,
                "acceptance_coverage_report_ref": coverage_report_ref,
                "compiler_report_ref": compiler_report_ref,
                "contract_hash": frozen.contract_hash,
                "mission_ir_hash": stable_json_hash(mission.to_dict()),
                "blocking_coverage_passed": coverage_report.blocking_coverage_passed,
            },
        )
        result = SkillFoundryCompileResult(
            bundle_id=request.bundle_id,
            mission_ir_ref=mission_ir_ref,
            frozen_contract_ref=frozen_contract_ref,
            contract_hash=frozen.contract_hash,
            profile_refs=[profile_ref.profile_id for profile_ref in mission.capability_profiles],
            diagnostic_refs=[diagnostic_ref, compiler_report_ref],
            target_package_ref=product_contract.target_package_refs[0],
            product_contract_ref=product_contract_ref,
            acceptance_matrix_ref=matrix_ref,
            acceptance_coverage_report_ref=coverage_report_ref,
            request_ref=request_ref,
        )
        result.validate()
        return result


def compile_skillfoundry_bundle(
    bundle: SkillFoundrySourceBundle | SkillFoundryRequest,
    *,
    workspace: str | Path = ".",
    registry: ProfileRegistry | None = None,
) -> SkillFoundryCompileResult:
    """Compile one SkillFoundry source bundle into refs-only MissionIR output."""

    if isinstance(bundle, SkillFoundryRequest):
        return SkillFoundryMissionCompiler().compile_request(bundle, workspace=workspace, registry=registry)
    return SkillFoundryMissionCompiler().compile(bundle, workspace=workspace, registry=registry)


def _compile_prompt_only_mission(request: SkillFoundryRequest, product_contract: SkillProductContract) -> MissionIR:
    request.validate()
    product_contract.validate()
    validators = _prompt_only_validators(request, product_contract)
    inputs = _product_mission_inputs(request, product_contract)
    return MissionIR(
        schema_version="missionforge.mission_ir.v1",
        mission_id=f"skillfoundry-{request.bundle_id}",
        objective=MissionObjective(
            summary=f"Build prompt-only SkillFoundry Capability Bundle {request.bundle_id}: {request.desired_capability}",
            deliverable_type="capability_bundle",
            success_signals=[
                "MissionForge verifier passes for all required prompt-only package refs.",
                "SkillFoundry ProductGradeGate passes before product-grade registry.",
            ],
        ),
        inputs=inputs,
        outputs={
            "required_artifacts": list(product_contract.target_package_refs),
            "allowed_write_scopes": list(product_contract.allowed_write_scopes),
            "bundle_profile": product_contract.bundle_profile.value,
            "bundle_manifest_ref": product_contract.manifest_ref,
            "artifact_contracts": _prompt_only_artifact_contracts(request, product_contract),
        },
        constraints=[
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-source-boundary",
                kind="data_boundary",
                priority="must",
                statement="Use only sanitized SkillFoundry request and source refs for task facts.",
                source_refs=_dedupe_refs([product_contract.request_ref, *request.source_refs]),
                evidence_obligations=["evidence/source_manifest.json"],
                validator=None,
                repair_hints=["Remove raw prompt, transcript, or unadmitted source material."],
            ),
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-output-root",
                kind="workspace_boundary",
                priority="must",
                statement="Write SkillFoundry prompt-only package output only under package/.",
                source_refs=[product_contract.request_ref, product_contract.matrix_ref],
                evidence_obligations=["evidence/output_manifest.json"],
                validator=None,
                repair_hints=["Move generated package files under package/."],
            ),
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-product-grade",
                kind="product_grade",
                priority="must",
                statement="Produce all prompt-only Capability Bundle artifacts required by the product acceptance matrix.",
                source_refs=[product_contract.request_ref, product_contract.matrix_ref],
                evidence_obligations=list(product_contract.target_package_refs),
                validator=None,
                repair_hints=["Create SKILL.md, skillfoundry.bundle.json, and README.md."],
            ),
        ],
        capability_profiles=[
            CapabilityProfileRef("user_provided_evidence_only", {}),
            CapabilityProfileRef("explicit_output_root", {"output_root": "package"}),
        ],
        verification={
            "required_evidence": ["evidence/source_manifest.json", "evidence/output_manifest.json"],
            "verification_profiles": [{"profile_id": "generic_local_verification"}],
            "validators": validators,
        },
        repair_policy={"rules": []},
        budget={},
        observability={"adapter": "skillfoundry_mission_ir_compiler", "bundle_profile": "prompt_only"},
    )


def _compile_product_mission(request: SkillFoundryRequest, product_contract: SkillProductContract) -> MissionIR:
    if product_contract.bundle_profile == BundleProfile.PROMPT_ONLY:
        return _compile_prompt_only_mission(request, product_contract)
    if product_contract.bundle_profile == BundleProfile.CODE_RUNTIME:
        return _compile_code_runtime_mission(request, product_contract)
    raise ContractValidationError(f"unsupported SkillFoundry bundle profile: {product_contract.bundle_profile.value}")


def _product_mission_inputs(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "request_ref": product_contract.request_ref,
        "product_contract_ref": "product_contract/skill_product_contract.json",
        "acceptance_matrix_ref": product_contract.matrix_ref,
        "admitted_source_refs": list(request.source_refs),
    }
    frontdesk_intent_ref = _frontdesk_intent_bundle_ref(request)
    if frontdesk_intent_ref:
        inputs["frontdesk_intent_bundle_ref"] = frontdesk_intent_ref
    return inputs


def _frontdesk_intent_bundle_ref(request: SkillFoundryRequest) -> str:
    for ref in request.source_refs:
        if ref == "frontdesk/intent_bundle.json" or ref.endswith("/frontdesk/intent_bundle.json"):
            return ref
    return ""


def _compile_code_runtime_mission(request: SkillFoundryRequest, product_contract: SkillProductContract) -> MissionIR:
    request.validate()
    product_contract.validate()
    manifest = manifest_for_profile(
        product_contract.bundle_profile,
        request.bundle_id,
        target_package_refs=product_contract.target_package_refs,
    )
    validators = _code_runtime_validators(request, product_contract, manifest)
    inputs = _product_mission_inputs(request, product_contract)
    return MissionIR(
        schema_version="missionforge.mission_ir.v1",
        mission_id=f"skillfoundry-{request.bundle_id}",
        objective=MissionObjective(
            summary=f"Build code-runtime SkillFoundry Capability Bundle {request.bundle_id}: {request.desired_capability}",
            deliverable_type="capability_bundle",
            success_signals=[
                "MissionForge verifier passes for all required code-runtime package refs.",
                "Helper runtime assets and schema artifacts are present and locally inspectable.",
                "SkillFoundry ProductGradeGate passes before product-grade registry.",
            ],
        ),
        inputs=inputs,
        outputs={
            "required_artifacts": list(product_contract.target_package_refs),
            "allowed_write_scopes": list(product_contract.allowed_write_scopes),
            "bundle_profile": product_contract.bundle_profile.value,
            "bundle_manifest_ref": product_contract.manifest_ref,
            "artifact_contracts": _code_runtime_artifact_contracts(request, product_contract, manifest),
        },
        constraints=[
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-source-boundary",
                kind="data_boundary",
                priority="must",
                statement="Use only sanitized SkillFoundry request and source refs for task facts.",
                source_refs=_dedupe_refs([product_contract.request_ref, *request.source_refs]),
                evidence_obligations=["evidence/source_manifest.json"],
                validator=None,
                repair_hints=["Remove raw prompt, transcript, provider payload, or unadmitted source material."],
            ),
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-output-root",
                kind="workspace_boundary",
                priority="must",
                statement="Write SkillFoundry code-runtime package output only under package/.",
                source_refs=[product_contract.request_ref, product_contract.matrix_ref],
                evidence_obligations=["evidence/output_manifest.json"],
                validator=None,
                repair_hints=["Move generated package files under package/."],
            ),
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-runtime-assets",
                kind="runtime_asset_boundary",
                priority="must",
                statement="Produce declared runtime assets, helper scripts, and schema refs as package-local artifacts.",
                source_refs=[product_contract.request_ref, product_contract.matrix_ref],
                evidence_obligations=list(product_contract.target_package_refs),
                validator=None,
                repair_hints=["Create helper scripts under package/scripts/ and schemas under package/schemas/."],
            ),
            MissionConstraint(
                constraint_id=f"SF-{request.bundle_id}-C-product-grade",
                kind="product_grade",
                priority="must",
                statement="Produce all code-runtime Capability Bundle artifacts required by the product acceptance matrix.",
                source_refs=[product_contract.request_ref, product_contract.matrix_ref],
                evidence_obligations=list(product_contract.target_package_refs),
                validator=None,
                repair_hints=["Create SKILL.md, skillfoundry.bundle.json, README.md, runtime assets, and schemas."],
            ),
        ],
        capability_profiles=[
            CapabilityProfileRef("user_provided_evidence_only", {}),
            CapabilityProfileRef("explicit_output_root", {"output_root": "package"}),
        ],
        verification={
            "required_evidence": ["evidence/source_manifest.json", "evidence/output_manifest.json"],
            "verification_profiles": [{"profile_id": "generic_local_verification"}],
            "validators": validators,
        },
        repair_policy={"rules": []},
        budget={},
        observability={"adapter": "skillfoundry_mission_ir_compiler", "bundle_profile": "code_runtime"},
    )


def _compile_mission(
    bundle: SkillFoundrySourceBundle,
    frontdesk_contract: Mapping[str, Any],
    source_refs: list[FrontDeskArtifactRef],
) -> MissionIR:
    contract = require_mapping(frontdesk_contract, "frontdesk_contract")
    objective_payload = require_mapping(contract.get("objective"), "frontdesk_contract.objective")
    source_ref_values = [source.ref for source in source_refs]
    constraints = _frontdesk_constraints(contract)
    constraints.extend(_adapter_constraints(bundle, source_ref_values))
    mission = MissionIR(
        mission_id=require_non_empty_str(
            contract.get("mission_id", f"skillfoundry-{bundle.bundle_id}"),
            "frontdesk_contract.mission_id",
        ),
        objective=MissionObjective(
            summary=require_non_empty_str(objective_payload.get("summary"), "frontdesk_contract.objective.summary"),
            deliverable_type=require_non_empty_str(
                objective_payload.get("deliverable_type", "capability_bundle"),
                "frontdesk_contract.objective.deliverable_type",
            ),
            success_signals=require_str_list(
                objective_payload.get("success_signals", ["Verifier passes."]),
                "frontdesk_contract.objective.success_signals",
            ),
        ),
        inputs={
            "frontdesk_contract_ref": bundle.frontdesk_contract_ref,
            "source_manifest_ref": bundle.source_manifest_ref,
            "admitted_source_refs": source_ref_values,
        },
        outputs={
            "required_artifacts": [bundle.target_package_ref],
            "allowed_write_scopes": list(bundle.allowed_write_scopes),
        },
        constraints=constraints,
        capability_profiles=list(bundle.capability_profile_refs),
        verification={
            "required_evidence": _dedupe_refs(
                ["evidence/source_manifest.json", "evidence/output_manifest.json", *source_ref_values]
            ),
            "verification_profiles": [{"profile_id": profile_id} for profile_id in bundle.verification_profile_refs],
            "validators": [
                require_mapping(item, "frontdesk_contract.validators[]")
                for item in contract.get("validators", [])
            ],
        },
        repair_policy={"rules": []},
        budget={},
        observability={"adapter": "skillfoundry_mission_ir_compiler"},
    )
    mission.validate()
    return mission


def _prompt_only_artifact_contracts(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
) -> list[dict[str, Any]]:
    return [
        {
            "artifact_ref": "package/SKILL.md",
            "kind": "markdown",
            "role": "agent_entrypoint",
            "required": True,
            "notes": [
                "Codex skill entry file.",
                "Describe trigger conditions, non-trigger conditions, operating boundaries, and verification expectations.",
                "Do not claim ProductGradeGate approval inside package content.",
            ],
        },
        {
            "artifact_ref": "package/skillfoundry.bundle.json",
            "kind": "json",
            "role": "skillfoundry_bundle_manifest",
            "required": True,
            "schema_version": BUNDLE_MANIFEST_SCHEMA_VERSION,
            "required_keys": list(PROMPT_ONLY_MANIFEST_REQUIRED_KEYS),
            "forbidden_extra_keys": True,
            "field_contract": {
                "schema_version": BUNDLE_MANIFEST_SCHEMA_VERSION,
                "bundle_id": request.bundle_id,
                "bundle_profile": product_contract.bundle_profile.value,
                "entrypoint": "SKILL.md",
                "capability_surface": {"codex_skill": {"entry_ref": "package/SKILL.md"}},
                "runtime_assets": [],
                "data_assets": [],
                "references": [],
                "environment": {},
                "permissions": {},
                "verification": {
                    "matrix_ref": product_contract.matrix_ref,
                    "product_grade_ref": "qa/product_grade_report.json",
                },
                "distribution": {"status": "local"},
            },
            "notes": [
                "Write only the keys listed in required_keys.",
                "Use entrypoint exactly SKILL.md, not package/SKILL.md.",
                "Keep runtime_assets, data_assets, and references as package-relative refs when non-empty.",
            ],
        },
        {
            "artifact_ref": "package/README.md",
            "kind": "markdown",
            "role": "local_use_readme",
            "required": True,
            "notes": [
                "Explain local install/use boundaries.",
                "Do not claim ProductGradeGate approval inside package content.",
            ],
        },
    ]


def _code_runtime_artifact_contracts(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
    manifest,
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = [
        {
            "artifact_ref": "package/SKILL.md",
            "kind": "markdown",
            "role": "agent_entrypoint",
            "required": True,
            "notes": [
                "Codex skill entry file.",
                "Describe trigger conditions, operating boundaries, runtime helper usage, and verification expectations.",
                "Do not claim ProductGradeGate approval inside package content.",
            ],
        },
        {
            "artifact_ref": "package/skillfoundry.bundle.json",
            "kind": "json",
            "role": "skillfoundry_bundle_manifest",
            "required": True,
            "schema_version": BUNDLE_MANIFEST_SCHEMA_VERSION,
            "required_keys": list(PROMPT_ONLY_MANIFEST_REQUIRED_KEYS),
            "forbidden_extra_keys": True,
            "field_contract": manifest.to_dict(),
            "notes": [
                "Write only the keys listed in required_keys.",
                "Use entrypoint exactly SKILL.md, not package/SKILL.md.",
                "Keep runtime_assets, data_assets, and references as package-relative refs.",
                "Keep network permission false unless a future profile explicitly allows it.",
            ],
        },
        {
            "artifact_ref": "package/README.md",
            "kind": "markdown",
            "role": "local_use_readme",
            "required": True,
            "notes": [
                "Explain local install, health check, and runtime boundaries.",
                "Do not claim ProductGradeGate approval inside package content.",
            ],
        },
    ]
    for ref in product_contract.target_package_refs:
        if ref in {"package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"}:
            continue
        if ref.startswith("package/scripts/"):
            contracts.append(
                {
                    "artifact_ref": ref,
                    "kind": "python",
                    "role": "helper_script",
                    "required": True,
                    "notes": [
                        "Expose a --help path that exits 0.",
                        "Do not require network, credentials, or host-specific absolute paths for health checks.",
                    ],
                }
            )
        elif ref.startswith("package/bin/"):
            contracts.append(
                {
                    "artifact_ref": ref,
                    "kind": "runtime_binary_or_sidecar_ref",
                    "role": "runtime_asset",
                    "required": True,
                    "notes": [
                        "Keep the asset package-local.",
                        "Document the health command in package/README.md and manifest verification.",
                    ],
                }
            )
        elif ref.startswith("package/schemas/"):
            contracts.append(
                {
                    "artifact_ref": ref,
                    "kind": "json_schema",
                    "role": "schema",
                    "required": True,
                    "notes": ["Must parse as JSON."],
                }
            )
        else:
            contracts.append(
                {
                    "artifact_ref": ref,
                    "kind": "package_artifact",
                    "role": "supporting_artifact",
                    "required": True,
                    "notes": ["Keep artifact package-local and refs-only in reports."],
                }
            )
    return contracts


def _code_runtime_validators(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
    manifest,
) -> list[dict[str, Any]]:
    runtime_asset_refs = [
        ref
        for ref in product_contract.target_package_refs
        if ref.startswith("package/scripts/") or ref.startswith("package/bin/")
    ]
    schema_refs = [ref for ref in product_contract.target_package_refs if ref.startswith("package/schemas/")]
    validators = [
        _file_exists_validator(
            "V-code-skill-exists",
            f"SF-{request.bundle_id}-C-product-grade",
            "package/SKILL.md",
            "SF-CODE-SKILL-EXISTS",
        ),
        _file_exists_validator(
            "V-code-manifest-exists",
            f"SF-{request.bundle_id}-C-product-grade",
            product_contract.manifest_ref,
            "SF-CODE-MANIFEST-EXISTS",
        ),
        _file_exists_validator(
            "V-code-readme-exists",
            f"SF-{request.bundle_id}-C-product-grade",
            "package/README.md",
            "SF-CODE-README-EXISTS",
        ),
        *_manifest_field_validators(
            prefix="V-code-manifest-schema",
            constraint_ref=f"SF-{request.bundle_id}-C-runtime-assets",
            manifest_ref=product_contract.manifest_ref,
            check_id="SF-CODE-MANIFEST-SCHEMA",
            fields=PROMPT_ONLY_MANIFEST_REQUIRED_KEYS,
        ),
        _manifest_json_command_validator(
            "V-code-manifest-semantics",
            f"SF-{request.bundle_id}-C-runtime-assets",
            product_contract.manifest_ref,
            request.bundle_id,
            BundleProfile.CODE_RUNTIME,
            "SF-CODE-MANIFEST-SCHEMA",
        ),
        _manifest_entrypoint_validator(
            "V-code-entrypoint",
            f"SF-{request.bundle_id}-C-product-grade",
            product_contract.manifest_ref,
            request.bundle_id,
            BundleProfile.CODE_RUNTIME,
            "SF-CODE-ENTRYPOINT",
        ),
        _manifest_package_refs_validator(
            "V-code-refs-safe",
            f"SF-{request.bundle_id}-C-runtime-assets",
            product_contract.manifest_ref,
            request.bundle_id,
            BundleProfile.CODE_RUNTIME,
            "SF-CODE-MANIFEST-SCHEMA",
        ),
        _json_field_validator(
            "V-code-runtime-assets-declared",
            f"SF-{request.bundle_id}-C-runtime-assets",
            product_contract.manifest_ref,
            "runtime_assets",
            "SF-CODE-RUNTIME-ASSETS-DECLARED",
        ),
        _json_field_validator(
            "V-code-data-assets-declared",
            f"SF-{request.bundle_id}-C-runtime-assets",
            product_contract.manifest_ref,
            "data_assets",
            "SF-CODE-SCHEMAS-VALID",
        ),
        _json_field_validator(
            "V-code-health-command-declared",
            f"SF-{request.bundle_id}-C-runtime-assets",
            product_contract.manifest_ref,
            "verification.command_health_check",
            "SF-CODE-SCRIPTS-RUNNABLE",
        ),
        *_artifact_exists_validators(
            prefix="V-code-runtime-asset-exists",
            constraint_ref=f"SF-{request.bundle_id}-C-runtime-assets",
            refs=runtime_asset_refs,
            check_id="SF-CODE-RUNTIME-ASSETS-EXIST",
        ),
        *_artifact_exists_validators(
            prefix="V-code-schema-exists",
            constraint_ref=f"SF-{request.bundle_id}-C-runtime-assets",
            refs=schema_refs,
            check_id="SF-CODE-SCHEMAS-VALID",
        ),
        _forbidden_markers_validator(
            "V-code-no-raw-context",
            f"SF-{request.bundle_id}-C-product-grade",
            product_contract.target_package_refs,
            RAW_CONTEXT_MARKERS,
            "SF-CODE-NO-RAW-CONTEXT",
        ),
        _forbidden_markers_validator(
            "V-code-no-self-grade",
            f"SF-{request.bundle_id}-C-product-grade",
            product_contract.target_package_refs,
            SELF_GRADE_MARKERS,
            "SF-CODE-NO-SELF-GRADE",
        ),
        _json_field_validator(
            "V-code-verification-matrix-ref",
            f"SF-{request.bundle_id}-C-product-grade",
            product_contract.manifest_ref,
            "verification.matrix_ref",
            "SF-CODE-VERIFICATION",
        ),
        _json_field_validator(
            "V-code-verification-product-grade-ref",
            f"SF-{request.bundle_id}-C-product-grade",
            product_contract.manifest_ref,
            "verification.product_grade_ref",
            "SF-CODE-VERIFICATION",
        ),
    ]
    command = manifest.verification.get("command_health_check") or manifest.environment.get("health_check")
    if command:
        validators.append(
            {
                "validator_id": "V-code-runtime-health-check",
                "constraint_refs": [f"SF-{request.bundle_id}-C-runtime-assets"],
                "type": "command",
                "description": "acceptance_check:SF-CODE-SCRIPTS-RUNNABLE",
                "inputs": {"command": command, "expected_exit_code": 0, "timeout": 30},
            }
        )
    for index, schema_ref in enumerate(schema_refs, start=1):
        validators.append(
            {
                "validator_id": f"V-code-schema-parse-{index:03d}",
                "constraint_refs": [f"SF-{request.bundle_id}-C-runtime-assets"],
                "type": "command",
                "description": "acceptance_check:SF-CODE-SCHEMAS-VALID",
                "inputs": {
                    "command": ["python3", "-m", "json.tool", schema_ref],
                    "expected_exit_code": 0,
                    "timeout": 30,
                },
            }
        )
    return validators


def _prompt_only_validators(
    request: SkillFoundryRequest,
    product_contract: SkillProductContract,
) -> list[dict[str, Any]]:
    constraint_ref = f"SF-{request.bundle_id}-C-product-grade"
    return [
        _file_exists_validator("V-prompt-skill-exists", constraint_ref, "package/SKILL.md", "SF-PROMPT-SKILL-EXISTS"),
        _file_exists_validator(
            "V-prompt-manifest-exists",
            constraint_ref,
            product_contract.manifest_ref,
            "SF-PROMPT-MANIFEST-EXISTS",
        ),
        _file_exists_validator("V-prompt-readme-exists", constraint_ref, "package/README.md", "SF-PROMPT-README-EXISTS"),
        *_manifest_field_validators(
            prefix="V-prompt-manifest-schema",
            constraint_ref=constraint_ref,
            manifest_ref=product_contract.manifest_ref,
            check_id="SF-PROMPT-MANIFEST-SCHEMA",
            fields=PROMPT_ONLY_MANIFEST_REQUIRED_KEYS,
        ),
        _manifest_json_command_validator(
            "V-prompt-manifest-semantics",
            constraint_ref,
            product_contract.manifest_ref,
            request.bundle_id,
            BundleProfile.PROMPT_ONLY,
            "SF-PROMPT-MANIFEST-SCHEMA",
        ),
        _manifest_entrypoint_validator(
            "V-prompt-entrypoint",
            constraint_ref,
            product_contract.manifest_ref,
            request.bundle_id,
            BundleProfile.PROMPT_ONLY,
            "SF-PROMPT-ENTRYPOINT",
        ),
        _manifest_package_refs_validator(
            "V-prompt-refs-safe",
            constraint_ref,
            product_contract.manifest_ref,
            request.bundle_id,
            BundleProfile.PROMPT_ONLY,
            "SF-PROMPT-REFS-SAFE",
        ),
        _forbidden_markers_validator(
            "V-prompt-no-raw-context",
            constraint_ref,
            product_contract.target_package_refs,
            RAW_CONTEXT_MARKERS,
            "SF-PROMPT-NO-RAW-CONTEXT",
        ),
        _forbidden_markers_validator(
            "V-prompt-no-self-grade",
            constraint_ref,
            product_contract.target_package_refs,
            SELF_GRADE_MARKERS,
            "SF-PROMPT-NO-SELF-GRADE",
        ),
        _json_field_validator(
            "V-prompt-verification-matrix-ref",
            constraint_ref,
            product_contract.manifest_ref,
            "verification.matrix_ref",
            "SF-PROMPT-VERIFICATION",
        ),
        _json_field_validator(
            "V-prompt-verification-product-grade-ref",
            constraint_ref,
            product_contract.manifest_ref,
            "verification.product_grade_ref",
            "SF-PROMPT-VERIFICATION",
        ),
    ]


def _build_acceptance_coverage_report(
    *,
    matrix: ProductAcceptanceMatrix,
    mission: MissionIR,
    matrix_ref: str,
    mission_ref: str,
) -> AcceptanceCoverageReport:
    validator_ids_by_check = _validator_ids_by_acceptance_check(mission)
    profile_ids = [profile.profile_id for profile in mission.capability_profiles]
    items: list[AcceptanceCoverageItem] = []
    for matrix_item in matrix.items:
        validator_ids = validator_ids_by_check.get(matrix_item.check_id, [])
        if validator_ids:
            route = AcceptanceCoverageRoute.MISSION_IR_VALIDATOR
            covered = True
            route_profile_ids: list[str] = []
        elif not matrix_item.blocking:
            route = AcceptanceCoverageRoute.AUDIT_ONLY
            covered = True
            route_profile_ids = []
        else:
            route = AcceptanceCoverageRoute.MISSION_IR_VALIDATOR
            covered = False
            route_profile_ids = []
        items.append(
            AcceptanceCoverageItem(
                check_id=matrix_item.check_id,
                blocking=matrix_item.blocking,
                coverage_route=route,
                validator_ids=validator_ids,
                profile_ids=route_profile_ids,
                covered=covered,
            )
        )
    _ensure_coverage_matches_matrix(matrix, items)
    return AcceptanceCoverageReport(
        bundle_id=matrix.bundle_id,
        bundle_profile=matrix.bundle_profile,
        matrix_ref=matrix_ref,
        mission_ref=mission_ref,
        items=items,
    )


def _validator_ids_by_acceptance_check(mission: MissionIR) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for validator in mission.verification.get("validators", []):
        data = require_mapping(validator, "mission.verification.validators[]")
        validator_id = require_non_empty_str(data.get("validator_id"), "mission.verification.validators[].validator_id")
        description = data.get("description", "")
        if not isinstance(description, str):
            continue
        for token in description.split():
            if token.startswith("acceptance_check:"):
                check_id = token.removeprefix("acceptance_check:")
                if check_id:
                    result.setdefault(check_id, []).append(validator_id)
    return {check_id: _dedupe_plain(values) for check_id, values in result.items()}


def _ensure_coverage_matches_matrix(
    matrix: ProductAcceptanceMatrix,
    items: list[AcceptanceCoverageItem],
) -> None:
    matrix_ids = [item.check_id for item in matrix.items]
    item_ids = [item.check_id for item in items]
    missing = sorted(set(matrix_ids) - set(item_ids))
    extra = sorted(set(item_ids) - set(matrix_ids))
    if missing or extra:
        raise ContractValidationError(f"acceptance coverage matrix mismatch: missing={missing}, extra={extra}")


def _file_exists_validator(
    validator_id: str,
    constraint_ref: str,
    path: str,
    check_id: str,
) -> dict[str, Any]:
    return {
        "validator_id": validator_id,
        "constraint_refs": [constraint_ref],
        "type": "file_exists",
        "description": f"acceptance_check:{check_id}",
        "inputs": {"path": path},
    }


def _json_field_validator(
    validator_id: str,
    constraint_ref: str,
    manifest_ref: str,
    field: str,
    check_id: str,
) -> dict[str, Any]:
    script = (
        "import json, pathlib\n"
        f"data=json.loads(pathlib.Path({manifest_ref!r}).read_text(encoding='utf-8'))\n"
        "current=data\n"
        f"for part in {field!r}.split('.'):\n"
        "    assert isinstance(current, dict) and part in current, part\n"
        "    current=current[part]\n"
    )
    return {
        "validator_id": validator_id,
        "constraint_refs": [constraint_ref],
        "type": "command",
        "description": f"acceptance_check:{check_id}",
        "inputs": {"command": ["python3", "-c", script], "expected_exit_code": 0, "timeout": 30},
    }


def _manifest_field_validators(
    *,
    prefix: str,
    constraint_ref: str,
    manifest_ref: str,
    check_id: str,
    fields: list[str],
) -> list[dict[str, Any]]:
    return [
        _json_field_validator(
            f"{prefix}-{field.replace('_', '-').replace('.', '-')}",
            constraint_ref,
            manifest_ref,
            field,
            check_id,
        )
        for field in fields
    ]


def _artifact_exists_validators(
    *,
    prefix: str,
    constraint_ref: str,
    refs: list[str],
    check_id: str,
) -> list[dict[str, Any]]:
    return [
        _file_exists_validator(f"{prefix}-{index:03d}", constraint_ref, artifact_ref, check_id)
        for index, artifact_ref in enumerate(refs, start=1)
    ]


def _manifest_json_command_validator(
    validator_id: str,
    constraint_ref: str,
    manifest_ref: str,
    bundle_id: str,
    profile: BundleProfile,
    check_id: str,
) -> dict[str, Any]:
    script = (
        "import json, pathlib, sys; "
        f"p=pathlib.Path({manifest_ref!r}); "
        "data=json.loads(p.read_text(encoding='utf-8')); "
        f"assert data.get('schema_version') == {BUNDLE_MANIFEST_SCHEMA_VERSION!r}; "
        f"assert data.get('bundle_id') == {bundle_id!r}; "
        f"assert data.get('bundle_profile') == {profile.value!r}; "
        "assert isinstance(data.get('verification'), dict)"
    )
    return {
        "validator_id": validator_id,
        "constraint_refs": [constraint_ref],
        "type": "command",
        "description": f"acceptance_check:{check_id}",
        "inputs": {"command": ["python3", "-c", script], "expected_exit_code": 0, "timeout": 30},
    }


def _manifest_entrypoint_validator(
    validator_id: str,
    constraint_ref: str,
    manifest_ref: str,
    bundle_id: str,
    profile: BundleProfile,
    check_id: str,
) -> dict[str, Any]:
    script = (
        "import json, pathlib; "
        f"data=json.loads(pathlib.Path({manifest_ref!r}).read_text(encoding='utf-8')); "
        f"assert data.get('bundle_id') == {bundle_id!r}; "
        f"assert data.get('bundle_profile') == {profile.value!r}; "
        "assert data.get('entrypoint') == 'SKILL.md'; "
        "assert data.get('capability_surface', {}).get('codex_skill', {}).get('entry_ref') == 'package/SKILL.md'"
    )
    return {
        "validator_id": validator_id,
        "constraint_refs": [constraint_ref],
        "type": "command",
        "description": f"acceptance_check:{check_id}",
        "inputs": {"command": ["python3", "-c", script], "expected_exit_code": 0, "timeout": 30},
    }


def _manifest_package_refs_validator(
    validator_id: str,
    constraint_ref: str,
    manifest_ref: str,
    bundle_id: str,
    profile: BundleProfile,
    check_id: str,
) -> dict[str, Any]:
    script = (
        "import json, pathlib, sys; "
        f"data=json.loads(pathlib.Path({manifest_ref!r}).read_text(encoding='utf-8')); "
        f"assert data.get('bundle_id') == {bundle_id!r}; "
        f"assert data.get('bundle_profile') == {profile.value!r}; "
        "refs=[]; "
        "refs.extend(data.get('runtime_assets') or []); "
        "refs.extend(data.get('data_assets') or []); "
        "refs.extend(data.get('references') or []); "
        "assert all(isinstance(ref, str) and ref.startswith('package/') and '..' not in ref.split('/') and not ref.startswith('/') for ref in refs)"
    )
    return {
        "validator_id": validator_id,
        "constraint_refs": [constraint_ref],
        "type": "command",
        "description": f"acceptance_check:{check_id}",
        "inputs": {"command": ["python3", "-c", script], "expected_exit_code": 0, "timeout": 30},
    }


def _forbidden_markers_validator(
    validator_id: str,
    constraint_ref: str,
    refs: list[str],
    markers: list[str],
    check_id: str,
) -> dict[str, Any]:
    script = (
        "import pathlib, sys; "
        f"refs={refs!r}; "
        f"markers={[marker.lower() for marker in markers]!r}; "
        "text='\\n'.join(pathlib.Path(ref).read_text(encoding='utf-8').lower() for ref in refs if pathlib.Path(ref).exists()); "
        "hits=[marker for marker in markers if marker in text]; "
        "assert not hits, hits"
    )
    return {
        "validator_id": validator_id,
        "constraint_refs": [constraint_ref],
        "type": "command",
        "description": f"acceptance_check:{check_id}",
        "inputs": {"command": ["python3", "-c", script], "expected_exit_code": 0, "timeout": 30},
    }


def _dedupe_plain(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _frontdesk_constraints(contract: Mapping[str, Any]) -> list[MissionConstraint]:
    return [
        MissionConstraint.from_dict(require_mapping(item, "frontdesk_contract.constraints[]"))
        for item in contract.get("constraints", [])
    ]


def _adapter_constraints(bundle: SkillFoundrySourceBundle, source_refs: list[str]) -> list[MissionConstraint]:
    return [
        MissionConstraint(
            constraint_id=f"SF-{bundle.bundle_id}-C-source-boundary",
            kind="data_boundary",
            priority="must",
            statement="Use only admitted sanitized SkillFoundry source refs for task facts.",
            source_refs=_dedupe_refs([bundle.frontdesk_contract_ref, bundle.source_manifest_ref, *source_refs]),
            evidence_obligations=["evidence/source_manifest.json"],
            validator=None,
            repair_hints=["Remove unsupported SkillFoundry product facts or raw transcript material."],
        ),
        MissionConstraint(
            constraint_id=f"SF-{bundle.bundle_id}-C-output-root",
            kind="workspace_boundary",
            priority="must",
            statement="Write package output only under declared SkillFoundry output scopes.",
            source_refs=[bundle.source_manifest_ref],
            evidence_obligations=["evidence/output_manifest.json"],
            validator=None,
            repair_hints=["Move generated package files under the declared target package ref."],
        ),
    ]


def _source_refs_from_manifest(source_manifest: Mapping[str, Any]) -> list[FrontDeskArtifactRef]:
    data = require_mapping(source_manifest, "source_manifest")
    return [
        FrontDeskArtifactRef.from_dict(require_mapping(item, "source_manifest.sources[]"))
        for item in data.get("sources", [])
    ]


def _capability_profile_ref_to_dict(profile_ref: CapabilityProfileRef) -> dict[str, Any]:
    profile_ref.validate()
    return {
        "profile_id": profile_ref.profile_id,
        "requirements": ensure_json_value(
            require_mapping(profile_ref.requirements, "capability_profile_ref.requirements"),
            "capability_profile_ref.requirements",
        ),
    }


def _read_json_ref(root: Path, ref: str, field_name: str) -> dict[str, Any]:
    path = _resolve_workspace_ref(root, ref)
    if not path.exists():
        raise ContractValidationError(f"{field_name} ref does not exist: {ref}")
    return require_mapping(json.loads(path.read_text(encoding="utf-8")), field_name)


def _write_json_ref(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    data = ensure_json_value(require_mapping(payload, ref), ref)
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("SkillFoundry integration ref escapes workspace")
    return path


def _contract_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    _reject_forbidden_source_payload(data, field_name)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")
    return data


def _reject_forbidden_source_payload(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ContractValidationError(f"{field_name} keys must be non-empty strings")
            normalized = key.lower()
            if normalized in FORBIDDEN_SOURCE_FIELDS or any(fragment in normalized for fragment in FORBIDDEN_FIELD_FRAGMENTS):
                raise ContractValidationError(f"{field_name}.{key} must be represented as a sanitized source ref")
            _reject_forbidden_source_payload(item, f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_source_payload(item, f"{field_name}[{index}]")


def _dedupe_artifacts(artifacts: list[FrontDeskArtifactRef]) -> list[FrontDeskArtifactRef]:
    result: list[FrontDeskArtifactRef] = []
    seen: set[str] = set()
    for artifact in artifacts:
        artifact.validate()
        if artifact.ref not in seen:
            result.append(artifact)
            seen.add(artifact.ref)
    return result


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result


def _is_within(ref: str, scope: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_scope = validate_ref(scope, "scope")
    return safe_ref == safe_scope or safe_ref.startswith(f"{safe_scope}/")

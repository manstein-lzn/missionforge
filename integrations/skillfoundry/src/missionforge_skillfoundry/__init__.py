"""External SkillFoundry integration for MissionForge."""

from .compiler import (
    FrontDeskArtifactRef,
    SkillFoundryCompileResult,
    SkillFoundryMissionCompiler,
    SkillFoundrySourceBundle,
    SkillPackageTarget,
    compile_skillfoundry_bundle,
)
from .dogfood import SkillFoundryDogfoodReport, run_skillfoundry_live_dogfood
from .frontdesk_bridge import SkillFoundryFrontDeskIntegration, build_skillfoundry_request, compile_frontdesk_intent, compile_frontdesk_task_contract
from .frontdesk_context import SkillFoundryInquiryProfile
from .product_contract import (
    BUNDLE_MANIFEST_SCHEMA_VERSION,
    ACCEPTANCE_COVERAGE_REPORT_REF,
    AcceptanceCoverageItem,
    AcceptanceCoverageReport,
    AcceptanceCoverageRoute,
    BundleProfile,
    CODE_RUNTIME_REQUIRED_PACKAGE_REFS,
    PROMPT_ONLY_MANIFEST_REQUIRED_KEYS,
    ProductAcceptanceItem,
    ProductAcceptanceMatrix,
    RegistryStatus,
    RiskDomain,
    SkillBundleManifest,
    SkillFoundryRequest,
    SkillProductContract,
    acceptance_summary_for_profile,
    allowed_write_scopes_for_profile,
    capability_surface_for_profile,
    manifest_for_profile,
    target_package_refs_for_profile,
)
from .product_grade_gate import ProductGradeFinding, ProductGradeReport, ProductRepairPacket, evaluate_product_grade
from .registry import RegistryEntry, SkillFoundryRegistry, register_skill_bundle
from .reports import SkillFoundryProductReport
from .runtime import run_skillfoundry_bundle_build, run_skillfoundry_task_contract_bundle_build
from .task_contract_compiler import (
    SkillFoundryTaskContractCompileResult,
    compile_skillfoundry_task_contract,
    load_skillfoundry_task_contract,
)
from .validators import BundleValidationCheck, BundleValidationReport, validate_skill_bundle

__all__ = [
    "BUNDLE_MANIFEST_SCHEMA_VERSION",
    "ACCEPTANCE_COVERAGE_REPORT_REF",
    "AcceptanceCoverageItem",
    "AcceptanceCoverageReport",
    "AcceptanceCoverageRoute",
    "BundleProfile",
    "BundleValidationCheck",
    "BundleValidationReport",
    "CODE_RUNTIME_REQUIRED_PACKAGE_REFS",
    "FrontDeskArtifactRef",
    "PROMPT_ONLY_MANIFEST_REQUIRED_KEYS",
    "ProductAcceptanceItem",
    "ProductAcceptanceMatrix",
    "ProductGradeFinding",
    "ProductGradeReport",
    "ProductRepairPacket",
    "RegistryEntry",
    "RegistryStatus",
    "RiskDomain",
    "SkillBundleManifest",
    "SkillFoundryCompileResult",
    "SkillFoundryDogfoodReport",
    "SkillFoundryFrontDeskIntegration",
    "SkillFoundryInquiryProfile",
    "SkillFoundryMissionCompiler",
    "SkillFoundryProductReport",
    "SkillFoundryRegistry",
    "SkillFoundryRequest",
    "SkillFoundrySourceBundle",
    "SkillFoundryTaskContractCompileResult",
    "SkillProductContract",
    "SkillPackageTarget",
    "acceptance_summary_for_profile",
    "allowed_write_scopes_for_profile",
    "build_skillfoundry_request",
    "capability_surface_for_profile",
    "compile_skillfoundry_bundle",
    "compile_skillfoundry_task_contract",
    "compile_frontdesk_intent",
    "compile_frontdesk_task_contract",
    "evaluate_product_grade",
    "manifest_for_profile",
    "register_skill_bundle",
    "run_skillfoundry_live_dogfood",
    "run_skillfoundry_bundle_build",
    "run_skillfoundry_task_contract_bundle_build",
    "target_package_refs_for_profile",
    "load_skillfoundry_task_contract",
    "validate_skill_bundle",
]

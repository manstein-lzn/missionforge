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
from .product_contract import (
    BUNDLE_MANIFEST_SCHEMA_VERSION,
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
from .runtime import run_skillfoundry_bundle_build
from .validators import BundleValidationCheck, BundleValidationReport, validate_skill_bundle

__all__ = [
    "BUNDLE_MANIFEST_SCHEMA_VERSION",
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
    "SkillFoundryMissionCompiler",
    "SkillFoundryProductReport",
    "SkillFoundryRegistry",
    "SkillFoundryRequest",
    "SkillFoundrySourceBundle",
    "SkillProductContract",
    "SkillPackageTarget",
    "acceptance_summary_for_profile",
    "allowed_write_scopes_for_profile",
    "capability_surface_for_profile",
    "compile_skillfoundry_bundle",
    "evaluate_product_grade",
    "manifest_for_profile",
    "register_skill_bundle",
    "run_skillfoundry_live_dogfood",
    "run_skillfoundry_bundle_build",
    "target_package_refs_for_profile",
    "validate_skill_bundle",
]

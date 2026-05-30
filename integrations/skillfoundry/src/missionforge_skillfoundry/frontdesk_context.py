"""SkillFoundry FrontDesk inquiry profile."""

from __future__ import annotations

from missionforge.frontdesk import (
    AcceptancePrerequisite,
    ArtifactArchetype,
    CompilerReadiness,
    InquirySlot,
    ProductActivation,
    ProductInquiryProfile,
    RiskDimension,
    SlotRequirement,
    SlotTargetMapping,
    SlotValueType,
    SourcePolicy,
)


def SkillFoundryInquiryProfile() -> ProductInquiryProfile:
    """Return the SkillFoundry product inquiry profile."""

    profile = ProductInquiryProfile(
        product_id="skillfoundry",
        version="2026-05-30",
        display_name="SkillFoundry Capability Bundle",
        activations=[
            ProductActivation(
                activation_id="skillfoundry-capability-bundle",
                summary="The user wants a reusable Codex skill or capability bundle.",
                trigger_terms=["skill", "capability bundle", "package/SKILL.md", "codex skill"],
            )
        ],
        slots=[
            InquirySlot(
                slot_id="capability_goal",
                question="What capability should this skill give the user?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.FREE_TEXT,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.desired_capability")],
            ),
            InquirySlot(
                slot_id="target_user",
                question="Who will use this skill?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.FREE_TEXT,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.target_user")],
            ),
            InquirySlot(
                slot_id="trigger_scenarios",
                question="When should the skill activate?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.STRING_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.triggers")],
            ),
            InquirySlot(
                slot_id="non_trigger_scenarios",
                question="When should the skill avoid activating?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.STRING_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.non_triggers")],
            ),
            InquirySlot(
                slot_id="bundle_profile",
                question="Is this prompt-only or does it need local runtime assets?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.ENUM,
                choices=["prompt_only", "code_runtime"],
                maps_to=[SlotTargetMapping(target="skillfoundry.request.desired_bundle_profile")],
            ),
            InquirySlot(
                slot_id="required_package_outputs",
                question="Which package files must the skill produce?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.ARTIFACT_PATH_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.expected_outputs")],
            ),
            InquirySlot(
                slot_id="runtime_assets_required",
                question="Which runtime scripts or binaries are required?",
                requirement=SlotRequirement.CONDITIONAL,
                value_type=SlotValueType.ARTIFACT_PATH_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.expected_outputs")],
            ),
            InquirySlot(
                slot_id="data_assets_required",
                question="Which schemas or data assets are required?",
                requirement=SlotRequirement.CONDITIONAL,
                value_type=SlotValueType.ARTIFACT_PATH_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.expected_outputs")],
            ),
            InquirySlot(
                slot_id="privacy_boundary",
                question="What user data or source material must stay out of the package?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.STRING_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.privacy_boundaries")],
            ),
            InquirySlot(
                slot_id="distribution_boundary",
                question="Where may this skill be distributed?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.STRING_LIST,
                maps_to=[SlotTargetMapping(target="skillfoundry.request.distribution_boundaries")],
            ),
        ],
        risk_dimensions=[
            RiskDimension(
                risk_id="raw_context_leakage",
                description="Package content must not expose raw conversation, provider payload, or private source text.",
                severity="blocking",
            ),
            RiskDimension(
                risk_id="self_grade_claim",
                description="The package must not claim its own ProductGradeGate approval.",
                severity="blocking",
            ),
            RiskDimension(
                risk_id="runtime_execution",
                description="Runtime helper assets require explicit local health-check boundaries.",
                severity="review",
            ),
            RiskDimension(
                risk_id="filesystem_write",
                description="Generated artifacts must stay under package-local write scopes.",
                severity="blocking",
            ),
            RiskDimension(
                risk_id="external_document_ingestion",
                description="External documents must be represented as admitted refs, not pasted context.",
                severity="review",
            ),
        ],
        artifact_archetypes=[
            ArtifactArchetype(
                artifact_id="prompt_only_package",
                purpose="Minimum Codex skill package.",
                expected_refs=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            ),
            ArtifactArchetype(
                artifact_id="code_runtime_package",
                purpose="Skill package with local helper runtime assets.",
                expected_refs=[
                    "package/SKILL.md",
                    "package/skillfoundry.bundle.json",
                    "package/README.md",
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                ],
            ),
        ],
        acceptance_prerequisites=[
            AcceptancePrerequisite(
                prerequisite_id="product_grade_gate",
                description="MissionForge verifier completion is necessary but ProductGradeGate owns product readiness.",
            )
        ],
        compiler_readiness=CompilerReadiness(
            blocking_slot_ids=[
                "capability_goal",
                "target_user",
                "trigger_scenarios",
                "non_trigger_scenarios",
                "bundle_profile",
                "required_package_outputs",
                "privacy_boundary",
                "distribution_boundary",
            ],
            recommended_slot_ids=["runtime_assets_required", "data_assets_required"],
            human_review_risk_ids=["runtime_execution", "external_document_ingestion"],
        ),
        source_policy=SourcePolicy(
            allowed_source_refs=[
                "frontdesk/intent_bundle.json",
                "frontdesk/core_need_brief.json",
                "frontdesk/mission_brief.json",
                "frontdesk/solution_plan.json",
                "frontdesk/mission_plan.json",
            ],
            excluded_source_refs=["frontdesk/conversation.jsonl"],
            notes=["Raw FrontDesk conversation remains provenance only."],
        ),
    )
    profile.validate()
    return profile


__all__ = ["SkillFoundryInquiryProfile"]

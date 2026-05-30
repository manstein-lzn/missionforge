"""Bridge from FrontDeskIntentBundle to SkillFoundry product contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionforge.contracts import ContractValidationError, validate_ref
from missionforge.frontdesk import FrontDeskIntentBundle, SlotValueStatus
from missionforge.product_integration import (
    ProductClarificationQuestion,
    ProductClarificationRequest,
    ProductCompileResult,
    ProductCompileStatus,
)

from .compiler import SkillFoundryMissionCompiler
from .frontdesk_context import SkillFoundryInquiryProfile
from .product_contract import BundleProfile, SkillFoundryRequest


SKILLFOUNDRY_INTENT_BUNDLE_REF = "frontdesk/intent_bundle.json"
_REQUIRED_BRIDGE_SLOTS = {
    "capability_goal",
    "target_user",
    "trigger_scenarios",
    "non_trigger_scenarios",
    "bundle_profile",
    "required_package_outputs",
    "privacy_boundary",
    "distribution_boundary",
}


def build_skillfoundry_request(
    bundle: FrontDeskIntentBundle,
    *,
    bundle_id: str,
    default_profile: BundleProfile = BundleProfile.PROMPT_ONLY,
) -> SkillFoundryRequest | ProductClarificationRequest:
    """Build a SkillFoundryRequest or a product clarification request."""

    bundle.validate()
    require_non_empty_bundle_id = bundle_id.strip()
    if not require_non_empty_bundle_id:
        raise ContractValidationError("skillfoundry bundle_id must be a non-empty string")
    missing_slots = _bridge_missing_slots(bundle)
    if missing_slots:
        return _clarification(bundle, missing_slots)
    profile_value = _slot_text(bundle, "bundle_profile")
    try:
        bundle_profile = BundleProfile(profile_value)
    except ValueError:
        return _clarification(bundle, ["bundle_profile"])
    if bundle_profile not in {BundleProfile.PROMPT_ONLY, BundleProfile.CODE_RUNTIME}:
        return _clarification(bundle, ["bundle_profile"])
    if bundle_profile is None:
        bundle_profile = default_profile

    expected_outputs = _dedupe_refs(
        [
            *_slot_list(bundle, "required_package_outputs"),
            *_slot_list(bundle, "runtime_assets_required"),
            *_slot_list(bundle, "data_assets_required"),
        ]
    )
    request = SkillFoundryRequest(
        request_id=f"frontdesk-{require_non_empty_bundle_id}",
        bundle_id=require_non_empty_bundle_id,
        desired_capability=_slot_text(bundle, "capability_goal"),
        target_user=_slot_text(bundle, "target_user"),
        triggers=_slot_list(bundle, "trigger_scenarios"),
        non_triggers=_slot_list(bundle, "non_trigger_scenarios"),
        expected_outputs=expected_outputs,
        must=[
            "Write all generated files under package/.",
            "Preserve FrontDesk intent bundle provenance as refs.",
        ],
        must_not=[
            "Do not include raw conversations, provider payloads, credentials, or self-grade claims.",
        ],
        privacy_boundaries=_slot_list(bundle, "privacy_boundary"),
        distribution_boundaries=_slot_list(bundle, "distribution_boundary"),
        source_refs=_product_source_refs(bundle),
        desired_bundle_profile=bundle_profile,
    )
    request.validate()
    return request


def compile_frontdesk_intent(
    bundle: FrontDeskIntentBundle,
    *,
    workspace: str | Path,
    bundle_id: str,
) -> ProductCompileResult:
    """Compile a FrontDeskIntentBundle into SkillFoundry MissionIR artifacts."""

    request_or_clarification = build_skillfoundry_request(bundle, bundle_id=bundle_id)
    if isinstance(request_or_clarification, ProductClarificationRequest):
        return ProductCompileResult(
            product_id="skillfoundry",
            status=ProductCompileStatus.NEEDS_CLARIFICATION,
            intent_bundle_ref=bundle.intent_bundle_ref,
            missing_slot_ids=list(request_or_clarification.missing_slot_ids),
            clarification_questions=list(request_or_clarification.questions),
            reason=request_or_clarification.reason,
        )
    result = SkillFoundryMissionCompiler().compile_request(request_or_clarification, workspace=workspace)
    return ProductCompileResult(
        product_id="skillfoundry",
        status=ProductCompileStatus.COMPILED,
        intent_bundle_ref=bundle.intent_bundle_ref,
        product_request_ref=result.request_ref,
        product_contract_ref=result.product_contract_ref,
        mission_ir_ref=result.mission_ir_ref,
        frozen_contract_ref=result.frozen_contract_ref,
        product_gate_spec_ref=result.acceptance_matrix_ref,
        evidence_refs=list(result.diagnostic_refs),
        reason="compiled SkillFoundry product artifacts from FrontDeskIntentBundle",
    )


class SkillFoundryFrontDeskIntegration:
    """ProductIntegration adapter for programmatic FrontDesk.compile_product calls."""

    product_id = "skillfoundry"

    def __init__(self, *, bundle_id: str) -> None:
        if not bundle_id.strip():
            raise ContractValidationError("SkillFoundryFrontDeskIntegration.bundle_id must be non-empty")
        self.bundle_id = bundle_id.strip()

    def inquiry_profile(self):
        return SkillFoundryInquiryProfile()

    def compile_intent(
        self,
        bundle: FrontDeskIntentBundle,
        *,
        workspace: str | Path = ".",
    ) -> ProductCompileResult:
        return compile_frontdesk_intent(bundle, workspace=workspace, bundle_id=self.bundle_id)


def _bridge_missing_slots(bundle: FrontDeskIntentBundle) -> list[str]:
    missing = set(bundle.missing_blocking_slots)
    for slot_id in _REQUIRED_BRIDGE_SLOTS:
        value = bundle.slot_value(slot_id)
        if value is None or value.status in {SlotValueStatus.MISSING, SlotValueStatus.REJECTED}:
            missing.add(slot_id)
        elif value.value in (None, "", []):
            missing.add(slot_id)
    if not _slot_text(bundle, "bundle_profile"):
        missing.add("bundle_profile")
    if not _slot_list(bundle, "privacy_boundary"):
        missing.add("privacy_boundary")
    return sorted(missing)


def _clarification(bundle: FrontDeskIntentBundle, missing_slots: list[str]) -> ProductClarificationRequest:
    profile = SkillFoundryInquiryProfile()
    questions: list[ProductClarificationQuestion] = []
    slot_by_id = {slot.slot_id: slot for slot in profile.slots}
    for slot_id in missing_slots:
        slot = slot_by_id.get(slot_id)
        questions.append(
            ProductClarificationQuestion(
                question_id=f"skillfoundry-{slot_id}",
                slot_id=slot_id,
                question=slot.question if slot else f"Clarify SkillFoundry slot {slot_id}.",
                choices=list(slot.choices) if slot else [],
                source_refs=[bundle.intent_bundle_ref],
            )
        )
    return ProductClarificationRequest(
        product_id="skillfoundry",
        intent_bundle_ref=bundle.intent_bundle_ref,
        missing_slot_ids=list(missing_slots),
        questions=questions,
        reason="SkillFoundry product compile requires additional FrontDesk slot values.",
    )


def _slot_text(bundle: FrontDeskIntentBundle, slot_id: str) -> str:
    slot = bundle.slot_value(slot_id)
    if slot is None or slot.status in {SlotValueStatus.MISSING, SlotValueStatus.REJECTED}:
        return ""
    value = slot.value
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip()).strip()
    if value is None:
        return ""
    return str(value).strip()


def _slot_list(bundle: FrontDeskIntentBundle, slot_id: str) -> list[str]:
    slot = bundle.slot_value(slot_id)
    if slot is None or slot.status in {SlotValueStatus.MISSING, SlotValueStatus.REJECTED}:
        return []
    value: Any = slot.value
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not ref:
            continue
        safe_ref = validate_ref(ref, "skillfoundry_frontdesk.source_refs[]")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result


def _product_source_refs(bundle: FrontDeskIntentBundle) -> list[str]:
    profile = SkillFoundryInquiryProfile()
    allowed = set(profile.source_policy.allowed_source_refs)
    excluded = set(profile.source_policy.excluded_source_refs)
    raw_refs = _dedupe_refs([bundle.intent_bundle_ref, *bundle.generic_refs.refs, *bundle.evidence_refs])
    result: list[str] = []
    for ref in raw_refs:
        if ref in excluded:
            continue
        if allowed and ref not in allowed:
            continue
        result.append(ref)
    if bundle.intent_bundle_ref not in result and bundle.intent_bundle_ref not in excluded:
        result.insert(0, bundle.intent_bundle_ref)
    return result


__all__ = [
    "SKILLFOUNDRY_INTENT_BUNDLE_REF",
    "SkillFoundryFrontDeskIntegration",
    "build_skillfoundry_request",
    "compile_frontdesk_intent",
]

"""Generic FrontDesk fallback product integration."""

from __future__ import annotations

from pathlib import Path

from ..product_integration import ProductCompileResult, ProductCompileStatus
from .intent_bundle import FrontDeskIntentBundle, IntentBundleReadiness
from .state import DRAFT_MISSION_REF, INTENT_BUNDLE_REF, MISSION_MAPPING_REPORT_REF


class GenericProductIntegration:
    """Core-neutral fallback for existing direct FrontDesk draft behavior."""

    product_id = "generic"

    def compile_intent(
        self,
        bundle: FrontDeskIntentBundle,
        *,
        workspace: str | Path = ".",
    ) -> ProductCompileResult:
        bundle.validate()
        if bundle.product_context.product_id != "generic" or bundle.slot_values:
            return ProductCompileResult(
                product_id=self.product_id,
                status=ProductCompileStatus.FAILED_CLOSED,
                intent_bundle_ref=bundle.intent_bundle_ref,
                missing_slot_ids=list(bundle.missing_blocking_slots),
                reason="Generic FrontDesk fallback cannot compile product-specific intent bundles.",
            )
        mission_ref = bundle.generic_refs.draft_mission_ref or DRAFT_MISSION_REF
        if not bundle.generic_refs.draft_mission_ref:
            return ProductCompileResult(
                product_id=self.product_id,
                status=ProductCompileStatus.NEEDS_CLARIFICATION,
                intent_bundle_ref=bundle.intent_bundle_ref,
                missing_slot_ids=["generic_draft_mission"],
                reason="Generic fallback requires an existing FrontDesk draft MissionIR.",
            )
        return ProductCompileResult(
            product_id=self.product_id,
            status=ProductCompileStatus.COMPILED,
            intent_bundle_ref=bundle.intent_bundle_ref or INTENT_BUNDLE_REF,
            mission_ir_ref=mission_ref,
            product_gate_spec_ref="",
            evidence_refs=[ref for ref in (MISSION_MAPPING_REPORT_REF,) if ref in bundle.generic_refs.refs],
            reason=IntentBundleReadiness.GENERIC_COMPILE_ONLY.value,
        )


__all__ = ["GenericProductIntegration"]

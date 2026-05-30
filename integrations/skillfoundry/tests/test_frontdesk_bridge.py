from __future__ import annotations

import unittest

from missionforge.frontdesk import (
    FrontDeskIntentBundle,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    SlotValue,
    SlotValueStatus,
)
from missionforge.product_integration import ProductClarificationRequest
from missionforge_skillfoundry import BundleProfile, SkillFoundryRequest
from missionforge_skillfoundry.frontdesk_bridge import build_skillfoundry_request
from missionforge_skillfoundry.product_contract import PROMPT_ONLY_REQUIRED_PACKAGE_REFS


class SkillFoundryFrontDeskBridgeTests(unittest.TestCase):
    def test_prompt_only_bundle_compiles_to_request(self) -> None:
        request = build_skillfoundry_request(_bundle(), bundle_id="release-review")

        self.assertIsInstance(request, SkillFoundryRequest)
        self.assertEqual(request.bundle_id, "release-review")
        self.assertEqual(request.desired_bundle_profile, BundleProfile.PROMPT_ONLY)
        self.assertEqual(request.expected_outputs, PROMPT_ONLY_REQUIRED_PACKAGE_REFS)
        self.assertIn("frontdesk/intent_bundle.json", request.source_refs)
        self.assertNotIn("frontdesk/conversation.jsonl", request.source_refs)
        self.assertNotIn("frontdesk/session.json", request.source_refs)

    def test_prompt_only_bundle_ignores_extra_ai_suggested_package_outputs(self) -> None:
        request = build_skillfoundry_request(
            _bundle(outputs=["package/SKILL.md", "package/check-local.sh"]),
            bundle_id="release-review",
        )

        self.assertIsInstance(request, SkillFoundryRequest)
        self.assertEqual(request.desired_bundle_profile, BundleProfile.PROMPT_ONLY)
        self.assertEqual(request.expected_outputs, PROMPT_ONLY_REQUIRED_PACKAGE_REFS)
        self.assertNotIn("package/check-local.sh", request.expected_outputs)

    def test_code_runtime_slots_compile_to_code_runtime_profile(self) -> None:
        request = build_skillfoundry_request(
            _bundle(
                profile="code_runtime",
                outputs=[
                    "package/SKILL.md",
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                ],
                runtime_assets=["package/scripts/skill_runtime.py"],
                data_assets=["package/schemas/runtime.schema.json"],
            ),
            bundle_id="runtime-skill",
        )

        self.assertIsInstance(request, SkillFoundryRequest)
        self.assertEqual(request.desired_bundle_profile, BundleProfile.CODE_RUNTIME)
        self.assertIn("package/scripts/skill_runtime.py", request.expected_outputs)

    def test_missing_bundle_profile_or_privacy_boundary_returns_clarification(self) -> None:
        bundle = _bundle(include_profile=False, include_privacy=False)

        result = build_skillfoundry_request(bundle, bundle_id="missing")

        self.assertIsInstance(result, ProductClarificationRequest)
        self.assertEqual(result.missing_slot_ids, ["bundle_profile", "privacy_boundary"])


def _bundle(
    *,
    profile: str = "prompt_only",
    outputs: list[str] | None = None,
    runtime_assets: list[str] | None = None,
    data_assets: list[str] | None = None,
    include_profile: bool = True,
    include_privacy: bool = True,
) -> FrontDeskIntentBundle:
    slot_values = [
        SlotValue(slot_id="capability_goal", status=SlotValueStatus.INFERRED, value="Review release notes."),
        SlotValue(slot_id="target_user", status=SlotValueStatus.INFERRED, value="codex_user"),
        SlotValue(
            slot_id="trigger_scenarios",
            status=SlotValueStatus.INFERRED,
            value=["When release notes need review."],
        ),
        SlotValue(
            slot_id="non_trigger_scenarios",
            status=SlotValueStatus.INFERRED,
            value=["When no skill package is needed."],
        ),
        SlotValue(
            slot_id="required_package_outputs",
            status=SlotValueStatus.INFERRED,
            value=outputs or ["package/SKILL.md"],
        ),
        SlotValue(
            slot_id="runtime_assets_required",
            status=SlotValueStatus.MISSING,
            value=None,
            question="Which runtime assets are required?",
        ),
        SlotValue(
            slot_id="data_assets_required",
            status=SlotValueStatus.MISSING,
            value=None,
            question="Which data assets are required?",
        ),
        SlotValue(
            slot_id="distribution_boundary",
            status=SlotValueStatus.INFERRED,
            value=["Local distribution only."],
        ),
    ]
    if runtime_assets is not None:
        slot_values.append(
            SlotValue(slot_id="runtime_assets_required", status=SlotValueStatus.INFERRED, value=runtime_assets)
        )
        slot_values = [slot for slot in slot_values if not (slot.slot_id == "runtime_assets_required" and slot.status == SlotValueStatus.MISSING)]
    if data_assets is not None:
        slot_values.append(SlotValue(slot_id="data_assets_required", status=SlotValueStatus.INFERRED, value=data_assets))
        slot_values = [slot for slot in slot_values if not (slot.slot_id == "data_assets_required" and slot.status == SlotValueStatus.MISSING)]
    if include_profile:
        slot_values.append(SlotValue(slot_id="bundle_profile", status=SlotValueStatus.INFERRED, value=profile))
    if include_privacy:
        slot_values.append(
            SlotValue(
                slot_id="privacy_boundary",
                status=SlotValueStatus.INFERRED,
                value=["Use admitted refs only."],
            )
        )
    return FrontDeskIntentBundle(
        session_id="fd",
        intent_bundle_ref="frontdesk/intent_bundle.json",
        generic_refs=IntentGenericRefs(session_ref="frontdesk/session.json"),
        evidence_refs=["frontdesk/conversation.jsonl", "frontdesk/core_need_brief.json"],
        product_context=ProductContextSnapshot(product_id="skillfoundry", display_name="SkillFoundry"),
        slot_values=slot_values,
        readiness=IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
    )


if __name__ == "__main__":
    unittest.main()

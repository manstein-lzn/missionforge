from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import FrontDesk
from missionforge.ir import MissionIR
from missionforge.frontdesk import (
    FrontDeskIntentBundle,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    SlotValue,
    SlotValueStatus,
)
from missionforge.frontdesk.state import INTENT_BUNDLE_CANDIDATE_REF, INTENT_BUNDLE_REF
from missionforge.product_integration import ProductCompileStatus
from missionforge_skillfoundry.frontdesk_bridge import SkillFoundryFrontDeskIntegration, compile_frontdesk_intent
from missionforge_skillfoundry.frontdesk_context import SkillFoundryInquiryProfile
from missionforge_skillfoundry.workspace import read_json_ref
from tests.frontdesk_llm_fixtures import ScriptedFrontDeskPiWorker, seed_llm_authored_frontdesk_artifacts


class SkillFoundryProductContextFlowTests(unittest.TestCase):
    def test_skillfoundry_product_context_requires_explicit_slot_values(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(
                workspace=root,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _skillfoundry_candidate(
                            session_id="sf-product-context",
                            capability_goal="Create a local release note review Codex skill.",
                            target_user="local Codex user",
                            outputs=["package/SKILL.md"],
                            missing=True,
                        )
                    }
                ),
            )
            session = frontdesk.start(
                "Build package/SKILL.md for release note review. Success means package/SKILL.md exists.",
                session_id="sf-product-context",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
                desired_outcome="Create a local release note review Codex skill.",
                target_users=["local Codex user"],
            )
            bundle = frontdesk.build_intent_bundle(
                session.session_ref,
                product_context=SkillFoundryInquiryProfile(),
            )

            self.assertEqual(bundle.readiness, IntentBundleReadiness.NEEDS_CLARIFICATION)
            self.assertIn("capability_goal", bundle.missing_blocking_slots)
            self.assertEqual(bundle.slot_value("capability_goal").status, SlotValueStatus.MISSING)

    def test_explicit_frontdesk_intent_bundle_compiles_to_skillfoundry_mission(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(
                workspace=root,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _skillfoundry_candidate(
                            session_id="sf-compile-product",
                            capability_goal="Create a local prompt-only Codex skill.",
                            target_user="local Codex user",
                            outputs=["package/SKILL.md"],
                        )
                    }
                ),
            )
            session = frontdesk.start(
                "Build package/SKILL.md for release note review. Success means package/SKILL.md exists.",
                session_id="sf-product-context",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
                desired_outcome="Create a local release note review Codex skill.",
                target_users=["local Codex user"],
            )
            bundle = _seed_skillfoundry_intent_bundle(
                frontdesk,
                session.session_ref,
                capability_goal="Create a local release note review Codex skill.",
                target_user="local Codex user",
                outputs=["package/SKILL.md"],
            )

            result = compile_frontdesk_intent(bundle, workspace=root, bundle_id="release-review")
            mission = MissionIR.from_dict(read_json_ref(root, result.mission_ir_ref, "mission_ir"))

            self.assertEqual(result.status, ProductCompileStatus.COMPILED)
            self.assertEqual(mission.inputs["frontdesk_intent_bundle_ref"], "frontdesk/intent_bundle.json")
            self.assertIn("package/SKILL.md", mission.outputs["required_artifacts"])
            self.assertTrue((root / result.product_contract_ref).exists())

    def test_programmatic_product_integration_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(
                workspace=root,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _skillfoundry_candidate(
                            session_id="sf-compile-product",
                            capability_goal="Create a local prompt-only Codex skill.",
                            target_user="local Codex user",
                            outputs=["package/SKILL.md"],
                        )
                    }
                ),
            )
            session = frontdesk.start(
                "Build package/SKILL.md for a local prompt-only skill. Success means package/SKILL.md exists.",
                session_id="sf-compile-product",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
                desired_outcome="Create a local prompt-only Codex skill.",
                target_users=["local Codex user"],
            )
            result = frontdesk.compile_product(
                session.session_ref,
                SkillFoundryFrontDeskIntegration(bundle_id="local-skill"),
            )

            self.assertEqual(result.status, ProductCompileStatus.COMPILED)
            self.assertEqual(result.product_id, "skillfoundry")
            self.assertTrue((root / "frontdesk/intent_bundle.json").exists())
            self.assertTrue((root / result.mission_ir_ref).exists())

    def test_programmatic_product_integration_rejects_tampered_canonical_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(
                workspace=root,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _skillfoundry_candidate(
                            session_id="sf-tampered-compile",
                            capability_goal="Create a local prompt-only Codex skill.",
                            target_user="local Codex user",
                            outputs=["package/SKILL.md"],
                        )
                    }
                ),
            )
            session = frontdesk.start(
                "Build package/SKILL.md for a local prompt-only skill. Success means package/SKILL.md exists.",
                session_id="sf-tampered-compile",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
                desired_outcome="Create a local prompt-only Codex skill.",
                target_users=["local Codex user"],
            )
            frontdesk.compile_product(
                session.session_ref,
                SkillFoundryFrontDeskIntegration(bundle_id="local-skill"),
            )
            tampered_payload = frontdesk.workspace.read_json(INTENT_BUNDLE_REF)
            tampered_payload["slot_values"][0]["value"] = "Create an unrelated tampered SkillFoundry request."
            tampered_payload.pop("bundle_hash")
            frontdesk.workspace.write_json(
                INTENT_BUNDLE_REF,
                FrontDeskIntentBundle.from_dict(tampered_payload).to_dict(),
            )

            with self.assertRaisesRegex(ContractValidationError, "stale or tampered"):
                frontdesk.compile_product(
                    session.session_ref,
                    SkillFoundryFrontDeskIntegration(bundle_id="local-skill"),
                )

    def test_oral_multiturn_runtime_skill_request_preserves_package_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(workspace=root)
            turns = [
                "我不是想写普通脚本，我想把复杂工程推进方法沉淀成本地 Codex skill。",
                "第一版可以是 skill 包，但如果要 helper runtime，就明确放 package/scripts/skill_runtime.py 和 package/schemas/runtime.schema.json。",
                "必须产出 package/SKILL.md、package/skillfoundry.bundle.json、package/README.md，只做本地私有分发，不要联网，不要读凭证。",
            ]
            session = frontdesk.start(turns[0], session_id="sf-oral-runtime")
            for text in turns[1:]:
                frontdesk.answer(session.session_ref, text)
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=[
                    "package/SKILL.md",
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                    "package/skillfoundry.bundle.json",
                    "package/README.md",
                ],
                desired_outcome="Create a local Codex skill that preserves complex engineering methodology without embedding project secrets.",
                target_users=["local Codex user doing long-running complex software engineering"],
                constraints=[
                    "Do not read credentials.",
                    "Do not require network access.",
                    "Treat Rust as a future implementation preference until packaging scope is proven.",
                ],
            )

            bundle = _seed_skillfoundry_intent_bundle(
                frontdesk,
                session.session_ref,
                capability_goal="Create a local Codex skill that preserves complex engineering methodology without embedding project secrets.",
                target_user="local Codex user doing long-running complex software engineering",
                outputs=[
                    "package/SKILL.md",
                    "package/skillfoundry.bundle.json",
                    "package/README.md",
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                ],
                profile="code_runtime",
                runtime_assets=["package/scripts/skill_runtime.py"],
                data_assets=["package/schemas/runtime.schema.json"],
                triggers=["When complex engineering methodology should be reused as a local Codex skill."],
                non_triggers=["When the user only needs a one-off script or exposes credentials."],
                privacy=["Do not read credentials.", "Do not embed project secrets or raw conversation."],
                distribution=["Local private distribution only."],
            )
            result = compile_frontdesk_intent(bundle, workspace=root, bundle_id="oral-runtime-skill")
            mission = MissionIR.from_dict(read_json_ref(root, result.mission_ir_ref, "mission_ir"))

            self.assertEqual(bundle.slot_value("bundle_profile").value, "code_runtime")
            self.assertIn("package/SKILL.md", bundle.slot_value("required_package_outputs").value)
            self.assertIn("package/scripts/skill_runtime.py", bundle.slot_value("runtime_assets_required").value)
            self.assertIn("package/schemas/runtime.schema.json", bundle.slot_value("data_assets_required").value)
            self.assertEqual(mission.outputs["bundle_profile"], "code_runtime")
            self.assertIn("package/scripts/skill_runtime.py", mission.outputs["required_artifacts"])
            self.assertEqual(mission.inputs["frontdesk_intent_bundle_ref"], "frontdesk/intent_bundle.json")


def _seed_skillfoundry_intent_bundle(
    frontdesk: FrontDesk,
    session_ref: str,
    *,
    capability_goal: str,
    target_user: str,
    outputs: list[str],
    profile: str = "prompt_only",
    runtime_assets: list[str] | None = None,
    data_assets: list[str] | None = None,
    triggers: list[str] | None = None,
    non_triggers: list[str] | None = None,
    privacy: list[str] | None = None,
    distribution: list[str] | None = None,
) -> FrontDeskIntentBundle:
    session = frontdesk.load_session(session_ref)
    inquiry_profile = SkillFoundryInquiryProfile()
    frontdesk.workspace.write_json("frontdesk/product_inquiry_profile.json", inquiry_profile.to_dict())
    generic_refs = IntentGenericRefs(
        session_ref=session.session_ref,
        workspace_facts_ref="frontdesk/workspace_facts.json",
        source_admission_report_ref="frontdesk/source_admission_report.json",
        core_need_brief_ref="frontdesk/core_need_brief.json",
        sanitized_sources_ref="frontdesk/sanitized_sources.json",
        semantic_lock_ref="frontdesk/semantic_lock.json",
        mission_brief_ref="frontdesk/mission_brief.json",
        semantic_coverage_ref="frontdesk/semantic_coverage.json",
        solution_plan_ref="frontdesk/solution_plan.json",
    )
    source_refs = ["frontdesk/core_need_brief.json", "frontdesk/solution_plan.json"]
    slot_values = [
        _slot("capability_goal", capability_goal, source_refs),
        _slot("target_user", target_user, source_refs),
        _slot("trigger_scenarios", triggers or ["When this reusable local Codex skill is needed."], source_refs),
        _slot("non_trigger_scenarios", non_triggers or ["When no reusable skill package is needed."], source_refs),
        _slot("bundle_profile", profile, source_refs),
        _slot("required_package_outputs", outputs, source_refs),
        _slot("privacy_boundary", privacy or ["Use admitted refs only; do not embed raw conversation."], source_refs),
        _slot("distribution_boundary", distribution or ["Local private distribution only."], source_refs),
    ]
    if runtime_assets is not None:
        slot_values.append(_slot("runtime_assets_required", runtime_assets, source_refs))
    if data_assets is not None:
        slot_values.append(_slot("data_assets_required", data_assets, source_refs))
    bundle = FrontDeskIntentBundle(
        session_id=session.session_id,
        intent_bundle_ref="frontdesk/intent_bundle.json",
        generic_refs=generic_refs,
        product_context=ProductContextSnapshot(
            product_id=inquiry_profile.product_id,
            display_name=inquiry_profile.display_name,
            profile_ref="frontdesk/product_inquiry_profile.json",
            profile_hash=inquiry_profile.profile_hash,
            version=inquiry_profile.version,
        ),
        slot_values=slot_values,
        readiness=IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
        evidence_refs=generic_refs.refs,
    )
    frontdesk.workspace.write_json("frontdesk/intent_bundle.json", bundle.to_dict())
    return bundle


def _skillfoundry_candidate(
    *,
    session_id: str,
    capability_goal: str,
    target_user: str,
    outputs: list[str],
    missing: bool = False,
) -> FrontDeskIntentBundle:
    profile = SkillFoundryInquiryProfile()
    source_refs = ["frontdesk/core_need_brief.json", "frontdesk/solution_plan.json"]
    if missing:
        slot_values = [
            SlotValue(
                slot_id=slot.slot_id,
                status=SlotValueStatus.MISSING,
                value=None,
                confidence="missing",
                question=slot.question,
            )
            for slot in profile.slots
        ]
        missing_slots = list(profile.compiler_readiness.blocking_slot_ids)
        readiness = IntentBundleReadiness.NEEDS_CLARIFICATION
        questions = [slot.question for slot in profile.slots if slot.slot_id in set(missing_slots)]
    else:
        slot_values = [
            _slot("capability_goal", capability_goal, source_refs),
            _slot("target_user", target_user, source_refs),
            _slot("trigger_scenarios", ["When this local Codex skill is needed."], source_refs),
            _slot("non_trigger_scenarios", ["When no reusable skill package is needed."], source_refs),
            _slot("bundle_profile", "prompt_only", source_refs),
            _slot("required_package_outputs", outputs, source_refs),
            SlotValue(slot_id="runtime_assets_required", status=SlotValueStatus.NOT_APPLICABLE, value=None),
            SlotValue(slot_id="data_assets_required", status=SlotValueStatus.NOT_APPLICABLE, value=None),
            _slot("privacy_boundary", ["Do not embed raw conversation."], source_refs),
            _slot("distribution_boundary", ["Local private distribution only."], source_refs),
        ]
        missing_slots = []
        readiness = IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE
        questions = []
    return FrontDeskIntentBundle(
        session_id=session_id,
        intent_bundle_ref=INTENT_BUNDLE_CANDIDATE_REF,
        generic_refs=IntentGenericRefs(session_ref="frontdesk/session.json"),
        product_context=ProductContextSnapshot(
            product_id=profile.product_id,
            display_name=profile.display_name,
            profile_ref="frontdesk/product_inquiry_profile.json",
            profile_hash=profile.profile_hash,
            version=profile.version,
        ),
        slot_values=slot_values,
        missing_blocking_slots=missing_slots,
        readiness=readiness,
        clarification_questions=questions,
        evidence_refs=source_refs if not missing else [],
    )


def _slot(slot_id: str, value, source_refs: list[str]) -> SlotValue:
    return SlotValue(
        slot_id=slot_id,
        status=SlotValueStatus.INFERRED,
        value=value,
        source_refs=source_refs,
    )


if __name__ == "__main__":
    unittest.main()

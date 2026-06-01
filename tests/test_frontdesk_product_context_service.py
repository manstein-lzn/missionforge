from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge import ContractValidationError, FrontDesk
from missionforge.frontdesk import (
    CompilerReadiness,
    FrontDeskIntentBundle,
    InquirySlot,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    ProductInquiryProfile,
    SlotRequirement,
    SlotTargetMapping,
    SlotValue,
    SlotValueStatus,
    SlotValueType,
    SourcePolicy,
)
from missionforge.frontdesk.state import INTENT_BUNDLE_CANDIDATE_REF, INTENT_BUNDLE_REF
from missionforge.product_integration import ProductCompileResult, ProductCompileStatus, ProductTaskContractCompileResult
from tests.frontdesk_llm_fixtures import ScriptedFrontDeskPiWorker, seed_llm_authored_frontdesk_artifacts


class FrontDeskProductContextServiceTests(unittest.TestCase):
    def test_generic_session_produces_intent_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-intent-generic",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
            )

            bundle = frontdesk.build_intent_bundle(session.session_ref)

            self.assertEqual(bundle.readiness, IntentBundleReadiness.GENERIC_COMPILE_ONLY)
            self.assertTrue((Path(tempdir) / "frontdesk/intent_bundle.json").exists())
            self.assertIn("frontdesk/session.json", bundle.generic_refs.refs)

    def test_product_context_populates_snapshot_and_missing_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _missing_slot_candidate(
                            session_id="fd-intent-product",
                            profile=profile,
                            slot_id="goal",
                            question="What is the goal?",
                        )
                    }
                ),
            )
            session = frontdesk.start(
                "Build package/SKILL.md for local users. Success means package/SKILL.md exists.",
                session_id="fd-intent-product",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )

            bundle = frontdesk.build_intent_bundle(session.session_ref, product_context=profile)

            self.assertEqual(bundle.product_context.product_id, "example_product")
            self.assertEqual(bundle.product_context.profile_ref, "frontdesk/product_inquiry_profile.json")
            self.assertEqual(bundle.readiness, IntentBundleReadiness.NEEDS_CLARIFICATION)
            self.assertEqual(bundle.missing_blocking_slots, ["goal"])
            self.assertEqual(bundle.slot_value("goal").status.value, "missing")
            self.assertEqual(bundle.clarification_questions, ["What is the goal?"])

    def test_missing_blocking_slots_route_to_clarification_and_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _profile_with_unknown_slot()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _missing_slot_candidate(
                            session_id="fd-intent-missing",
                            profile=profile,
                            slot_id="unanswerable_slot",
                            question="What exact product-only setting is required?",
                        )
                    }
                ),
            )
            session = frontdesk.start("Build something.", session_id="fd-intent-missing")
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
            )

            bundle = frontdesk.build_intent_bundle(session.session_ref, product_context=profile)
            inspect = frontdesk.inspect(session.session_ref)

            self.assertEqual(bundle.readiness, IntentBundleReadiness.NEEDS_CLARIFICATION)
            self.assertEqual(bundle.missing_blocking_slots, ["unanswerable_slot"])
            self.assertEqual(inspect.missing_product_slots, ["unanswerable_slot"])
            self.assertEqual(inspect.to_dict()["next_action"], "answer_question")

    def test_product_slot_values_must_come_from_ai_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _confirmed_slot_candidate(
                            session_id="fd-intent-ready",
                            profile=profile,
                            slot_id="goal",
                            value="Build a reusable package.",
                        )
                    }
                ),
            )
            session = frontdesk.start(
                "Build a reusable package. The goal is obvious in the conversation.",
                session_id="fd-intent-ready",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )

            bundle = frontdesk.build_intent_bundle(session.session_ref, product_context=profile)

            self.assertEqual(bundle.readiness, IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE)
            self.assertEqual(bundle.slot_value("goal").value, "Build a reusable package.")

    def test_candidate_cannot_cite_raw_conversation_as_product_source(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile(
                source_policy=SourcePolicy(
                    allowed_source_refs=["frontdesk/core_need_brief.json"],
                    excluded_source_refs=["frontdesk/conversation.jsonl"],
                )
            )
            candidate = _confirmed_slot_candidate(
                session_id="fd-intent-raw-ref",
                profile=profile,
                slot_id="goal",
                value="Build a reusable package.",
                source_refs=["frontdesk/conversation.jsonl"],
            )
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker({INTENT_BUNDLE_CANDIDATE_REF: candidate}),
            )
            session = frontdesk.start("Build a reusable package.", session_id="fd-intent-raw-ref")
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )

            with self.assertRaisesRegex(ContractValidationError, "excluded source ref"):
                frontdesk.build_intent_bundle(session.session_ref, product_context=profile)

    def test_existing_product_bundle_revalidates_candidate_profile_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _confirmed_slot_candidate(
                            session_id="fd-intent-stale-profile",
                            profile=profile,
                            slot_id="goal",
                            value="Build a reusable package.",
                        )
                    }
                ),
            )
            session = frontdesk.start("Build a reusable package.", session_id="fd-intent-stale-profile")
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )
            frontdesk.build_intent_bundle(session.session_ref, product_context=profile)
            changed_profile = ProductInquiryProfile(
                product_id="example_product",
                version="v2",
                display_name="Example Product",
                slots=profile.slots,
                compiler_readiness=profile.compiler_readiness,
            )

            with self.assertRaisesRegex(ContractValidationError, "product profile hash is stale"):
                frontdesk.build_intent_bundle(session.session_ref, product_context=changed_profile)

    def test_compile_product_rejects_tampered_existing_canonical_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _confirmed_slot_candidate(
                            session_id="fd-intent-tampered-canonical",
                            profile=profile,
                            slot_id="goal",
                            value="Build a reusable package.",
                        )
                    }
                ),
            )
            session = frontdesk.start("Build a reusable package.", session_id="fd-intent-tampered-canonical")
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )
            bundle = frontdesk.build_intent_bundle(session.session_ref, product_context=profile)
            tampered_payload = bundle.to_dict()
            tampered_payload["slot_values"][0]["value"] = "Compile a different product request."
            tampered_payload.pop("bundle_hash")
            frontdesk.workspace.write_json(
                INTENT_BUNDLE_REF,
                FrontDeskIntentBundle.from_dict(tampered_payload).to_dict(),
            )

            with self.assertRaisesRegex(ContractValidationError, "stale or tampered"):
                frontdesk.compile_product(session.session_ref, _EchoProductIntegration(profile))

    def test_compile_product_task_contract_is_default_task_contract_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _confirmed_slot_candidate(
                            session_id="fd-intent-task-contract",
                            profile=profile,
                            slot_id="goal",
                            value="Build a reusable package.",
                        )
                    }
                ),
            )
            session = frontdesk.start("Build a reusable package.", session_id="fd-intent-task-contract")
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )

            result = frontdesk.compile_product_task_contract(session.session_ref, _EchoTaskContractIntegration(profile))

            self.assertEqual(result.status, ProductCompileStatus.COMPILED)
            self.assertEqual(result.task_contract_ref, "runs/example/contract/task_contract.json")
            self.assertFalse(hasattr(result, "mission_ir_ref"))

    def test_existing_product_bundle_revalidates_current_generic_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            profile = _product_profile()
            frontdesk = FrontDesk(
                workspace=tempdir,
                worker=ScriptedFrontDeskPiWorker(
                    {
                        INTENT_BUNDLE_CANDIDATE_REF: _confirmed_slot_candidate(
                            session_id="fd-intent-stale-refs",
                            profile=profile,
                            slot_id="goal",
                            value="Build a reusable package.",
                        )
                    }
                ),
            )
            session = frontdesk.start("Build a reusable package.", session_id="fd-intent-stale-refs")
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md"],
            )
            frontdesk.build_intent_bundle(session.session_ref, product_context=profile)
            frontdesk.workspace.write_json("frontdesk/draft_mission.json", {"mission_id": "later"})

            with self.assertRaisesRegex(ContractValidationError, "stale or tampered"):
                frontdesk.build_intent_bundle(session.session_ref, product_context=profile)

    def test_raw_conversation_ref_is_provenance_not_bundle_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Raw private sentence should not appear in intent bundle.",
                session_id="fd-intent-private",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
            )

            bundle = frontdesk.build_intent_bundle(session.session_ref)
            payload = FrontDeskIntentBundle.from_dict(bundle.to_dict()).to_dict()

            self.assertNotIn("frontdesk/turns/turn-001.txt", str(payload))
            self.assertNotIn("frontdesk/conversation.jsonl", str(payload))
            self.assertIn("frontdesk/session.json", str(payload))

    def test_intent_bundle_fails_closed_without_llm_authored_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Build package/SKILL.md.", session_id="fd-intent-no-llm")

            with self.assertRaisesRegex(ContractValidationError, "requires an explicit LLM/PiWorker node"):
                frontdesk.build_intent_bundle(session.session_ref, product_context=_product_profile())

            inspect = frontdesk.inspect(session.session_ref)
            self.assertEqual(inspect.status, "failed_closed")
            self.assertEqual(inspect.next_action, "configure_frontdesk_llm")


class _EchoProductIntegration:
    product_id = "example_product"

    def __init__(self, profile: ProductInquiryProfile) -> None:
        self.profile = profile

    def inquiry_profile(self) -> ProductInquiryProfile:
        return self.profile

    def compile_intent(self, bundle: FrontDeskIntentBundle, *, workspace: str | Path = ".") -> ProductCompileResult:
        return ProductCompileResult(
            product_id=self.product_id,
            status=ProductCompileStatus.COMPILED,
            intent_bundle_ref=bundle.intent_bundle_ref,
            mission_ir_ref="product/mission.json",
        )


class _EchoTaskContractIntegration:
    product_id = "example_product"

    def __init__(self, profile: ProductInquiryProfile) -> None:
        self.profile = profile

    def inquiry_profile(self) -> ProductInquiryProfile:
        return self.profile

    def compile_task_contract(
        self,
        bundle: FrontDeskIntentBundle,
        *,
        workspace: str | Path = ".",
    ) -> ProductTaskContractCompileResult:
        return ProductTaskContractCompileResult(
            product_id=self.product_id,
            status=ProductCompileStatus.COMPILED,
            intent_bundle_ref=bundle.intent_bundle_ref,
            run_workspace_ref="runs/example",
            task_contract_ref="runs/example/contract/task_contract.json",
            workspace_policy_ref="runs/example/policy/workspace_policy.json",
            permission_manifest_ref="runs/example/policy/permission_manifest.json",
            product_request_ref="runs/example/product_contract/request.json",
            product_contract_ref="runs/example/product_contract/contract.json",
        )


def _product_profile(*, source_policy: SourcePolicy | None = None) -> ProductInquiryProfile:
    return ProductInquiryProfile(
        product_id="example_product",
        version="v1",
        display_name="Example Product",
        slots=[
            InquirySlot(
                slot_id="goal",
                question="What is the goal?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.FREE_TEXT,
                maps_to=[SlotTargetMapping(target="example.request.goal")],
            )
        ],
        compiler_readiness=CompilerReadiness(blocking_slot_ids=["goal"]),
        source_policy=source_policy or SourcePolicy(),
    )


def _profile_with_unknown_slot() -> ProductInquiryProfile:
    return ProductInquiryProfile(
        product_id="example_product",
        version="v1",
        display_name="Example Product",
        slots=[
            InquirySlot(
                slot_id="unanswerable_slot",
                question="What exact product-only setting is required?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.FREE_TEXT,
                maps_to=[SlotTargetMapping(target="example.request.setting")],
            )
        ],
        compiler_readiness=CompilerReadiness(blocking_slot_ids=["unanswerable_slot"]),
    )


def _missing_slot_candidate(
    *,
    session_id: str,
    profile: ProductInquiryProfile,
    slot_id: str,
    question: str,
) -> FrontDeskIntentBundle:
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
        slot_values=[
            SlotValue(
                slot_id=slot_id,
                status=SlotValueStatus.MISSING,
                value=None,
                confidence="missing",
                source_refs=[],
                question=question,
            )
        ],
        missing_blocking_slots=[slot_id],
        readiness=IntentBundleReadiness.NEEDS_CLARIFICATION,
        clarification_questions=[question],
        evidence_refs=[],
    )


def _confirmed_slot_candidate(
    *,
    session_id: str,
    profile: ProductInquiryProfile,
    slot_id: str,
    value: str,
    source_refs: list[str] | None = None,
) -> FrontDeskIntentBundle:
    refs = source_refs or ["frontdesk/core_need_brief.json"]
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
        slot_values=[
            SlotValue(
                slot_id=slot_id,
                status=SlotValueStatus.INFERRED,
                value=value,
                confidence="inferred",
                source_refs=refs,
            )
        ],
        missing_blocking_slots=[],
        readiness=IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
        clarification_questions=[],
        evidence_refs=refs,
    )


if __name__ == "__main__":
    unittest.main()

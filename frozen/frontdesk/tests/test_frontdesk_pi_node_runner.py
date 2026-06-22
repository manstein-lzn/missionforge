from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk.pi_node_runner import FrontDeskPiNodeRunner
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult
from missionforge.runtime_results import ExecutionReport, WorkerResult
from missionforge.runtime_results import WorkerAdapterResult


class _ScriptedPiWorker:
    adapter_family = "piworker"

    def __init__(self, *, produced_refs: list[str] | None = None, unsafe_metrics: bool = False) -> None:
        self.produced_refs = produced_refs
        self.unsafe_metrics = unsafe_metrics
        self.seen_call: PiWorkerCall | None = None

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store=None,
        exit_criteria=None,
        stop_conditions=None,
    ) -> WorkerAdapterResult:
        self.seen_call = call
        produced_refs = list(self.produced_refs if self.produced_refs is not None else call.expected_output_refs)
        for ref in produced_refs:
            path = Path(workspace) / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        metrics = {"adapter_id": "scripted_piworker"}
        if self.unsafe_metrics:
            metrics["raw_prompt"] = "hidden provider payload"
        report = ExecutionReport(
            report_id=f"R-{call.call_id}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=produced_refs,
            changed_refs=produced_refs,
            evidence_refs=["evidence/frontdesk_pi_node.json"],
            worker_claims=[],
            metrics=metrics,
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/execution_report.json",
            ),
            event_evidence_refs=["evidence/frontdesk_pi_node.json"],
            metrics={"adapter_result_status": "completed"},
        )


class FrontDeskPiNodeRunnerTests(unittest.TestCase):
    def test_builds_bounded_piworker_contract_for_frontdesk_node(self) -> None:
        contract = FrontDeskPiNodeRunner().build_contract(
            node_name="need_griller",
            session_id="fd-pi",
            visible_refs=["frontdesk/conversation.jsonl", "frontdesk/workspace_facts.json"],
            expected_outputs=["frontdesk/need_grilling_report.json"],
        )

        self.assertEqual(contract.call.writable_refs, ["frontdesk/need_grilling_report.json"])
        self.assertEqual(contract.call.expected_output_refs, ["frontdesk/need_grilling_report.json"])
        self.assertEqual(contract.call.visible_refs[0], "frontdesk/pi_nodes/fd-pi/need_griller/node_spec.json")
        self.assertIn("frontdesk/workspace_facts.json", contract.call.visible_refs)
        self.assertEqual(contract.call.role.value, "frontdesk_author_piworker")
        self.assertNotIn("work_unit", contract.to_dict())

    def test_rejects_non_frontdesk_outputs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "frontdesk/"):
            FrontDeskPiNodeRunner().build_contract(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["outside/result.json"],
            )

    def test_rejects_missing_or_extra_produced_refs(self) -> None:
        runner = FrontDeskPiNodeRunner()
        contract = runner.build_contract(
            node_name="solution_architect",
            session_id="fd-pi",
            visible_refs=["frontdesk/semantic_lock.json"],
            expected_outputs=["frontdesk/solution_plan.json"],
        )

        with self.assertRaisesRegex(ContractValidationError, "missing expected"):
            runner.validate_produced_refs(contract, [])
        with self.assertRaisesRegex(ContractValidationError, "outside allowed"):
            runner.validate_produced_refs(
                contract,
                ["frontdesk/solution_plan.json", "frontdesk/unplanned.json"],
            )
        runner.validate_produced_refs(contract, ["frontdesk/solution_plan.json"])

    def test_run_node_requires_explicit_piworker_adapter(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "explicit PiWorker adapter"):
            FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
            )

        with self.assertRaisesRegex(ContractValidationError, "PiWorker-compatible"):
            FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=object(),
            )

    def test_run_node_invokes_adapter_and_records_execution_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            worker = _ScriptedPiWorker()
            result = FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="FD Pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=worker,
                workspace=tempdir,
            )

            self.assertIsNotNone(worker.seen_call)
            self.assertEqual(worker.seen_call.writable_refs, ["frontdesk/need_grilling_report.json"])
            self.assertEqual(result.execution_record.produced_refs, ["frontdesk/need_grilling_report.json"])
            execution_ref = "frontdesk/pi_nodes/fd-pi/need_griller/execution.json"
            self.assertEqual(result.execution_record.node_execution_ref, execution_ref)
            self.assertTrue((Path(tempdir) / execution_ref).exists())
            execution_payload = json.loads((Path(tempdir) / execution_ref).read_text(encoding="utf-8"))
            self.assertIn("call_hash", execution_payload)
            self.assertNotIn("work_unit_hash", execution_payload)
            self.assertIn("frontdesk/need_grilling_report.json", result.execution_record.output_hashes)
            self.assertIn("frontdesk/pi_nodes/fd-pi/need_griller/node_spec.json", result.execution_record.input_hashes)
            call_result_ref = "frontdesk/pi_nodes/fd-pi/need_griller/piworker_call_result.json"
            self.assertEqual(result.execution_record.piworker_call_result_ref, call_result_ref)
            call_result = PiWorkerCallResult.from_dict(
                json.loads((Path(tempdir) / call_result_ref).read_text(encoding="utf-8"))
            )
            call_result.validate_against_call(result.contract.call)
            self.assertEqual(call_result.output_refs, ["frontdesk/need_grilling_report.json"])

    def test_need_griller_node_spec_contains_schema_and_conversation_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl", "frontdesk/workspace_facts.json"],
                expected_outputs=["frontdesk/decision_tree.json", "frontdesk/need_grilling_report.json"],
                optional_outputs=["frontdesk/core_need_brief.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )

            spec = json.loads((Path(tempdir) / result.execution_record.node_spec_ref).read_text(encoding="utf-8"))
            self.assertIn("guidance", spec)
            guidance_text = json.dumps(spec["guidance"], sort_keys=True)
            self.assertIn("missionforge.frontdesk_need_grilling_report.v1", guidance_text)
            self.assertIn("decision_option_fields", guidance_text)
            self.assertIn("readiness", guidance_text)
            self.assertIn("core_need_ready", guidance_text)
            self.assertIn("ranked_choices_or_free_text", guidance_text)
            self.assertIn("open_question_fields", guidance_text)
            self.assertIn("Use frontdesk/conversation.jsonl", guidance_text)
            self.assertIn("Do not copy raw conversation text", guidance_text)

    def test_need_griller_node_spec_marks_no_user_loop_when_core_need_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl", "frontdesk/workspace_facts.json"],
                expected_outputs=[
                    "frontdesk/decision_tree.json",
                    "frontdesk/need_grilling_report.json",
                    "frontdesk/core_need_brief.json",
                ],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )

            spec = json.loads((Path(tempdir) / result.execution_record.node_spec_ref).read_text(encoding="utf-8"))
            self.assertTrue(spec["guidance"]["execution_policy"]["core_need_brief_required"])
            guidance_text = json.dumps(spec["guidance"], sort_keys=True)
            self.assertIn("no-user-loop handoff", guidance_text)
            self.assertIn("assumption-backed brief", guidance_text)

    def test_solution_architect_node_spec_contains_field_type_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = FrontDeskPiNodeRunner().run_node(
                node_name="solution_architect",
                session_id="fd-pi",
                visible_refs=["frontdesk/core_need_brief.json", "frontdesk/semantic_lock.json"],
                expected_outputs=[
                    "frontdesk/solution_plan.json",
                    "frontdesk/solution_plan.md",
                    "frontdesk/plan_risk_register.json",
                    "frontdesk/profile_recommendations.json",
                    "frontdesk/mission_plan.json",
                ],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )

            spec = json.loads((Path(tempdir) / result.execution_record.node_spec_ref).read_text(encoding="utf-8"))
            guidance_text = json.dumps(spec["guidance"], sort_keys=True)
            self.assertIn("missionforge.frontdesk_solution_plan.v1", guidance_text)
            self.assertIn("string_list_fields", guidance_text)
            self.assertIn("must be arrays of strings, not arrays of objects", guidance_text)
            self.assertIn("recommendation.requirements must be a JSON object", guidance_text)
            self.assertIn("expected_artifacts must be an array of safe ref strings", guidance_text)

    def test_intent_bundle_node_spec_mentions_product_profile_source_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = FrontDeskPiNodeRunner().run_node(
                node_name="intent_bundle_author",
                session_id="fd-pi",
                visible_refs=["frontdesk/product_inquiry_profile.json", "frontdesk/core_need_brief.json"],
                expected_outputs=["frontdesk/intent_bundle_candidate.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )

            spec = json.loads((Path(tempdir) / result.execution_record.node_spec_ref).read_text(encoding="utf-8"))
            guidance_text = json.dumps(spec["guidance"], sort_keys=True)
            self.assertIn("missionforge.frontdesk.intent_bundle.v1", guidance_text)
            self.assertIn("ProductInquiryProfile.source_policy.allowed_source_refs", guidance_text)
            self.assertIn("slot_values must contain exactly every ProductInquiryProfile slot_id", guidance_text)
            self.assertIn("slot_value_type_rules", guidance_text)
            self.assertIn("string_list, ref_list, and artifact_path_list values are arrays of strings", guidance_text)
            self.assertIn("do not mark a slot missing solely because raw conversation refs are excluded", guidance_text)
            self.assertIn("All confidence fields are strings", guidance_text)
            self.assertIn("empty strings, not null", guidance_text)

    def test_require_ai_authored_rejects_missing_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir) / "frontdesk/need_grilling_report.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "missing PiWorker execution provenance"):
                FrontDeskPiNodeRunner().require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_rejects_tampered_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            runner = FrontDeskPiNodeRunner()
            runner.run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )
            (Path(tempdir) / "frontdesk/need_grilling_report.json").write_text(
                "{\"changed\": true}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractValidationError, "output hash"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_rejects_tampered_call_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            runner = FrontDeskPiNodeRunner()
            runner.run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )
            (Path(tempdir) / "frontdesk/pi_nodes/fd-pi/need_griller/piworker_call_result.json").write_text(
                "{\"changed\": true}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractValidationError, "call result hash is stale"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_rejects_stale_visible_input(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            visible = Path(tempdir) / "frontdesk/conversation.jsonl"
            visible.parent.mkdir(parents=True, exist_ok=True)
            visible.write_text("{\"turn_id\":\"turn-001\"}\n", encoding="utf-8")
            runner = FrontDeskPiNodeRunner()
            runner.run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )
            visible.write_text("{\"turn_id\":\"turn-001\"}\n{\"turn_id\":\"turn-002\"}\n", encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "visible input hash is stale"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_checks_product_profile_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            runner = FrontDeskPiNodeRunner()
            profile_hash = "sha256:" + ("a" * 64)
            runner.run_node(
                node_name="intent_bundle_author",
                session_id="fd-pi",
                visible_refs=["frontdesk/product_inquiry_profile.json"],
                expected_outputs=["frontdesk/intent_bundle_candidate.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
                product_profile_hash=profile_hash,
            )
            runner.require_ai_authored(
                workspace=tempdir,
                ref="frontdesk/intent_bundle_candidate.json",
                node_name="intent_bundle_author",
                session_id="fd-pi",
                product_profile_hash=profile_hash,
            )

            with self.assertRaisesRegex(ContractValidationError, "product profile hash is stale"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/intent_bundle_candidate.json",
                    node_name="intent_bundle_author",
                    session_id="fd-pi",
                    product_profile_hash="sha256:" + ("b" * 64),
                )

    def test_optional_outputs_may_be_produced_without_being_required(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            worker = _ScriptedPiWorker(
                produced_refs=[
                    "frontdesk/need_grilling_report.json",
                    "frontdesk/core_need_brief.json",
                ]
            )
            result = FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                optional_outputs=["frontdesk/core_need_brief.json"],
                worker=worker,
                workspace=tempdir,
            )

            self.assertEqual(
                result.execution_record.produced_refs,
                ["frontdesk/need_grilling_report.json", "frontdesk/core_need_brief.json"],
            )

    def test_run_node_rejects_unsafe_worker_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "raw_prompt"):
                FrontDeskPiNodeRunner().run_node(
                    node_name="mission_ir_mapper",
                    session_id="fd-pi",
                    visible_refs=["frontdesk/solution_plan.json"],
                    expected_outputs=["frontdesk/draft_mission.json"],
                    worker=_ScriptedPiWorker(unsafe_metrics=True),
                    workspace=tempdir,
                )

    def test_run_node_rejects_unexpected_worker_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "missing expected"):
                FrontDeskPiNodeRunner().run_node(
                    node_name="mission_ir_mapper",
                    session_id="fd-pi",
                    visible_refs=["frontdesk/solution_plan.json"],
                    expected_outputs=["frontdesk/draft_mission.json"],
                    worker=_ScriptedPiWorker(produced_refs=[]),
                    workspace=tempdir,
                )


if __name__ == "__main__":
    unittest.main()

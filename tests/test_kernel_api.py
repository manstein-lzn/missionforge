from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.kernel import (
    Artifact,
    ArtifactRole,
    FailurePolicy,
    Flow,
    FlowLedgerEvent,
    FlowLedgerEventKind,
    FlowRunResult,
    KernelValidationError,
    Projection,
    ProjectionRunResult,
    Step,
    StepCompileContext,
    StepRecord,
    StepRunResult,
    StepStatus,
    Toolset,
    compile_step,
    run_flow,
    run_projection,
    run_step,
)
from missionforge.contracts import stable_json_hash
from missionforge.extensions import ExtensionLock
from missionforge.interaction import FileInteractionPort, InteractionDelivery, UserEventKind
from missionforge.piworker_call import PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.task_contract import ExtensionCapability, NetworkPolicy


class KernelApiTests(unittest.TestCase):
    def test_step_compiles_to_piworker_call_and_permission_manifest(self) -> None:
        step = Step(
            id="reviewer",
            brief="Review the report and write a routing observation.",
            inputs=["contract/task_contract.json", "reports/final_report.md", "sources/source_packet.json"],
            outputs=["reviews/reviewer_observation.json"],
            read=["contract", "reports", "sources"],
            write=["reviews"],
            tools=["read", "write"],
            role=PiWorkerCallRole.JUDGE,
            route_on="reviews/reviewer_observation.json",
            route_fields=["decision", "revision_scope"],
            runtime_budget={"max_turns": 8, "timeout_seconds": 300},
        )
        context = _context()

        compiled = compile_step(step, context=context)

        self.assertEqual(compiled.piworker_call.call_id, "demo-flow-reviewer")
        self.assertEqual(compiled.piworker_call.role, PiWorkerCallRole.JUDGE)
        self.assertEqual(compiled.piworker_call.contract_ref, "contract/task_contract.json")
        self.assertEqual(compiled.piworker_call.expected_output_refs, ["reviews/reviewer_observation.json"])
        self.assertEqual(
            compiled.piworker_call.visible_refs,
            ["contract/task_contract.json", "reports/final_report.md", "sources/source_packet.json"],
        )
        self.assertNotIn("policy/workspace_policy.json", compiled.piworker_call.visible_refs)
        self.assertNotIn("kernel/demo-flow/steps/reviewer/step_spec.json", compiled.piworker_call.visible_refs)
        self.assertNotIn("kernel/demo-flow/steps/reviewer/permission_manifest.json", compiled.piworker_call.visible_refs)
        self.assertIn("reports/final_report.md", compiled.piworker_call.visible_refs)
        self.assertEqual(compiled.piworker_call.writable_refs, ["reviews"])
        self.assertIsNone(compiled.piworker_call.source_packet_ref)
        self.assertIsNone(compiled.piworker_call.source_packet_hash)
        self.assertEqual(compiled.piworker_call.runtime_budget["max_turns"], 8)
        self.assertEqual(compiled.permission_manifest.readable_refs, ["contract/task_contract.json", "contract", "reports", "sources"])
        self.assertEqual(compiled.permission_manifest.writable_refs, ["reviews"])
        self.assertEqual(compiled.permission_manifest.network_policy, NetworkPolicy.DISABLED)
        self.assertEqual(compiled.permission_manifest_ref, "kernel/demo-flow/steps/reviewer/permission_manifest.json")
        self.assertEqual(compiled.piworker_call.metadata["kernel_step_id"], "reviewer")
        self.assertEqual(compiled.piworker_call.metadata["kernel_step_spec_ref"], "kernel/demo-flow/steps/reviewer/step_spec.json")
        self.assertEqual(compiled.piworker_call.metadata["kernel_step_spec_hash"], step.spec_hash)

    def test_step_visible_refs_must_be_readable_without_internal_kernel_leak(self) -> None:
        step = Step(
            id="reviewer",
            brief="Review the report.",
            inputs=["contract/task_contract.json", "reports/final_report.md"],
            outputs=["reviews/reviewer_observation.json"],
            read=["contract", "reports"],
            write=["reviews"],
        )

        compiled = compile_step(step, context=_context())

        for ref in compiled.piworker_call.visible_refs:
            self.assertTrue(any(ref == root or ref.startswith(root + "/") for root in compiled.permission_manifest.readable_refs))
        self.assertFalse(any(ref == "kernel" or ref.startswith("kernel/") for ref in compiled.piworker_call.visible_refs))
        self.assertFalse(any(ref == "attempts" or ref.startswith("attempts/") for ref in compiled.piworker_call.visible_refs))

    def test_step_rejects_input_outside_read_roots(self) -> None:
        step = Step(
            id="reader",
            brief="Read the report.",
            inputs=["reports/final_report.md"],
            outputs=["state/result.json"],
            read=["sources"],
            write=["state"],
        )

        with self.assertRaisesRegex(KernelValidationError, "outside declared roots"):
            compile_step(step, context=_context())

    def test_step_rejects_output_outside_write_roots(self) -> None:
        step = Step(
            id="writer",
            brief="Write a report.",
            inputs=["contract/task_contract.json"],
            outputs=["reports/final_report.md"],
            read=["contract"],
            write=["state"],
        )

        with self.assertRaisesRegex(KernelValidationError, "outside declared roots"):
            compile_step(step, context=_context())

    def test_step_rejects_bash_without_command_allowlist(self) -> None:
        with self.assertRaisesRegex(KernelValidationError, "command_allowlist"):
            Step(
                id="runner",
                brief="Run a validation command.",
                inputs=["contract/task_contract.json"],
                outputs=["reports/result.txt"],
                read=["contract"],
                write=["reports"],
                tools=["read", "write", "bash"],
            )

    def test_step_compiles_extension_toolset_to_grant(self) -> None:
        toolset = Toolset(
            id="academic",
            package="local:extensions/pi-academic-sources",
            tools=["academic_search", "academic_fetch"],
            capability=ExtensionCapability.WEB,
            network=True,
            required_env=["PATH"],
        )
        step = Step(
            id="source_expander",
            brief="Find citation-ready sources.",
            inputs=["reviews/expansion_plan.json"],
            outputs=["sources/source_patch.json"],
            read=["reviews", "sources"],
            write=["sources"],
            tools=["read", "write", "academic"],
        )

        compiled = compile_step(step, context=_context(), toolsets={"academic": toolset})

        self.assertEqual(compiled.permission_manifest.network_policy, NetworkPolicy.ENABLED)
        self.assertEqual(len(compiled.permission_manifest.extension_grants), 1)
        grant = compiled.permission_manifest.extension_grants[0]
        self.assertEqual(grant.grant_id, "demo-flow-source_expander-academic")
        self.assertEqual(grant.package, "local:extensions/pi-academic-sources")
        self.assertEqual(grant.required_env, ["PATH"])
        self.assertEqual(grant.metadata["tool_names"], ["academic_search", "academic_fetch"])

    def test_unknown_tool_is_rejected(self) -> None:
        step = Step(
            id="source_expander",
            brief="Find citation-ready sources.",
            inputs=["reviews/expansion_plan.json"],
            outputs=["sources/source_patch.json"],
            read=["reviews", "sources"],
            write=["sources"],
            tools=["read", "write", "academic"],
        )

        with self.assertRaisesRegex(KernelValidationError, "unknown tool"):
            compile_step(step, context=_context())

    def test_runtime_owned_artifact_cannot_be_piworker_output(self) -> None:
        step = Step(
            id="researcher",
            brief="Write report artifacts.",
            inputs=["sources/source_packet.json"],
            outputs=["reports/evidence_index.md"],
            read=["sources"],
            write=["reports"],
        )
        artifact = Artifact("reports/evidence_index.md", role=ArtifactRole.PROJECTION, owner="runtime")

        with self.assertRaisesRegex(KernelValidationError, "non-piworker-output"):
            compile_step(step, context=_context(), artifacts={artifact.ref: artifact})

    def test_product_owned_input_cannot_be_piworker_output(self) -> None:
        step = Step(
            id="researcher",
            brief="Write report artifacts.",
            inputs=["sources/source_packet.json"],
            outputs=["sources/source_packet.json"],
            read=["sources"],
            write=["sources"],
        )
        artifact = Artifact("sources/source_packet.json", role=ArtifactRole.INPUT, owner="product")

        with self.assertRaisesRegex(KernelValidationError, "non-piworker-output"):
            compile_step(step, context=_context(), artifacts={artifact.ref: artifact})

    def test_step_cannot_write_frozen_contract(self) -> None:
        step = Step(
            id="contract_editor",
            brief="Illegally rewrite the contract.",
            inputs=["contract/task_contract.json"],
            outputs=["contract/task_contract.json"],
            read=["contract"],
            write=["contract"],
        )

        with self.assertRaisesRegex(KernelValidationError, "frozen contract"):
            compile_step(step, context=_context())

    def test_artifact_rejects_piworker_owned_projection_or_ledger(self) -> None:
        with self.assertRaisesRegex(KernelValidationError, "runtime-owned"):
            Artifact("reports/evidence_index.md", role=ArtifactRole.PROJECTION, owner="piworker")

        with self.assertRaisesRegex(KernelValidationError, "runtime-owned"):
            Artifact("kernel/demo-flow/flow_result.json", role=ArtifactRole.LEDGER, owner="product")

    def test_projection_requires_source_refs(self) -> None:
        with self.assertRaisesRegex(KernelValidationError, "must not be empty"):
            Projection(output="reports/evidence_index.md", from_=[], projector="citation_index")

    def test_failure_policy_rejects_successful_exhausted_status(self) -> None:
        for status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
            with self.assertRaisesRegex(KernelValidationError, "failed or blocked"):
                FailurePolicy(retries=1, on_exhausted=status)

    def test_step_requires_route_on_to_be_an_output(self) -> None:
        with self.assertRaisesRegex(KernelValidationError, "route_on"):
            Step(
                id="reviewer",
                brief="Review.",
                inputs=["reports/final_report.md"],
                outputs=["reviews/report.md"],
                read=["reports"],
                write=["reviews"],
                route_on="reviews/observation.json",
            )

    def test_flow_validates_routes_and_stops(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        judge = Step(
            id="judge",
            brief="Judge.",
            inputs=["reports/final_report.md", "reviews/observation.json"],
            outputs=["judge/report.json"],
            read=["reports", "reviews"],
            write=["judge"],
            role=PiWorkerCallRole.JUDGE,
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer, judge],
            routes={
                "reviewer.ready_for_judge": "judge",
                "reviewer.blocked": Flow.stop("blocked"),
            },
            projections=[
                Projection(
                    output="reports/evidence_index.md",
                    from_=["sources/source_packet.json", "reports/final_report.md"],
                    projector="citation_index",
                )
            ],
            artifacts=[
                Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("reports/evidence_index.md", role=ArtifactRole.PROJECTION, owner="runtime"),
            ],
        )

        self.assertEqual(flow.to_dict()["routes"]["reviewer.blocked"], {"status": "blocked"})

    def test_flow_rejects_unknown_route_target(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )

        with self.assertRaisesRegex(KernelValidationError, "target step is unknown"):
            Flow(
                id="bad-flow",
                steps=[reviewer],
                routes={"reviewer.ready": "judge"},
                artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
            ).validate()

    def test_flow_rejects_route_source_without_route_on(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/report.md"],
            read=["reports"],
            write=["reviews"],
        )

        with self.assertRaisesRegex(KernelValidationError, "must declare route_on"):
            Flow(id="bad-flow", steps=[reviewer], routes={"reviewer.ready": Flow.stop("accepted")})

    def test_flow_rejects_route_on_without_decision_artifact(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )

        with self.assertRaisesRegex(KernelValidationError, "route_on artifact must be declared"):
            Flow(id="bad-flow", steps=[reviewer], routes={"reviewer.ready": Flow.stop("blocked")})

        with self.assertRaisesRegex(KernelValidationError, "decision artifact"):
            Flow(
                id="bad-flow",
                steps=[reviewer],
                routes={"reviewer.ready": Flow.stop("blocked")},
                artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.OUTPUT, owner="piworker")],
            )

    def test_flow_rejects_executor_accepted_stop(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )

        with self.assertRaisesRegex(KernelValidationError, "judge step"):
            Flow(
                id="bad-flow",
                steps=[reviewer],
                routes={"reviewer.accepted": Flow.stop("accepted")},
                artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
            )

    def test_flow_rejects_judge_accepted_without_prior_executor_artifact(self) -> None:
        judge = Step(
            id="judge",
            brief="Judge final acceptance.",
            inputs=["contract/task_contract.json"],
            outputs=["judge/report.json"],
            read=["contract"],
            write=["judge"],
            role=PiWorkerCallRole.JUDGE,
            route_on="judge/report.json",
            route_fields=["decision"],
        )

        with self.assertRaisesRegex(KernelValidationError, "prior non-judge"):
            Flow(
                id="bad-flow",
                steps=[judge],
                routes={"judge.accepted": Flow.stop("accepted")},
                artifacts=[Artifact("judge/report.json", role=ArtifactRole.DECISION, owner="piworker")],
            )

    def test_flow_rejects_unsafe_route_value(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )

        with self.assertRaisesRegex(KernelValidationError, "single safe id segment"):
            Flow(
                id="bad-flow",
                steps=[reviewer],
                routes={"reviewer.ready/now": Flow.stop("blocked")},
                artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
            )

    def test_flow_from_dict_round_trips(self) -> None:
        payload = {
            "id": "deepresearch-v2",
            "steps": [
                {
                    "id": "reviewer",
                    "brief": "Review the report.",
                    "inputs": ["reports/final_report.md"],
                    "outputs": ["reviews/observation.json"],
                    "read": ["reports"],
                    "write": ["reviews"],
                    "route_on": "reviews/observation.json",
                    "route_fields": ["decision"],
                },
                {
                    "id": "judge",
                    "brief": "Judge the final report.",
                    "inputs": ["reports/final_report.md", "reviews/observation.json"],
                    "outputs": ["judge/report.json"],
                    "read": ["reports", "reviews"],
                    "write": ["judge"],
                    "role": "judge_piworker",
                },
            ],
            "routes": {
                "reviewer.ready": "judge",
                "reviewer.blocked": {"status": "blocked"},
            },
            "artifacts": [
                {"ref": "reports/final_report.md", "role": "output", "owner": "piworker"},
                {"ref": "reviews/observation.json", "role": "decision", "owner": "piworker"},
                {"ref": "reports/evidence_index.md", "role": "projection", "owner": "runtime"},
            ],
            "toolsets": [
                {
                    "id": "academic",
                    "package": "local:extensions/pi-academic-sources",
                    "tools": ["academic_search"],
                    "network": True,
                }
            ],
            "projections": [
                {
                    "output": "reports/evidence_index.md",
                    "from": ["reports/final_report.md"],
                    "projector": "citation_index",
                }
            ],
        }

        flow = Flow.from_dict(payload)

        self.assertEqual(Flow.from_dict(flow.to_dict()).to_dict(), flow.to_dict())

    def test_step_record_from_dict_round_trips(self) -> None:
        record = StepRecord(
            step_id="reviewer",
            step_spec_hash=stable_json_hash({"step": "reviewer"}),
            contract_ref="contract/task_contract.json",
            contract_hash="sha256:" + "a" * 64,
            input_refs=["reports/final_report.md"],
            output_refs=["reviews/observation.json"],
            status=StepStatus.COMPLETED,
            permission_manifest_ref="kernel/demo-flow/steps/reviewer/permission_manifest.json",
            piworker_call_ref="attempts/reviewer/piworker_call.json",
            piworker_call_result_ref="attempts/reviewer/piworker_call_result.json",
            execution_report_ref="attempts/reviewer/pi_agent_execution_report.json",
            metric_refs=["attempts/reviewer/pi_agent_metrics.json"],
        )

        self.assertEqual(StepRecord.from_dict(record.to_dict()).to_dict(), record.to_dict())

    def test_run_step_persists_kernel_records_and_piworker_result(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
            runtime_budget={"max_turns": 4},
        )
        adapter = _KernelDirectAdapter()

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=adapter)

            root = Path(tmpdir)
            step_spec = _read_json(root, result.step_spec_ref)
            call_payload = _read_json(root, result.piworker_call_ref)
            permission_payload = _read_json(root, result.compiled.permission_manifest_ref)
            call_result_payload = _read_json(root, result.piworker_call_result_ref)
            step_record_payload = _read_json(root, result.step_record_ref)

        self.assertIsInstance(result, StepRunResult)
        self.assertEqual(adapter.seen_call.call_id, "demo-flow-researcher")
        self.assertEqual(step_spec, step.to_dict())
        self.assertEqual(call_payload, result.compiled.piworker_call.to_dict())
        self.assertEqual(permission_payload, result.compiled.permission_manifest.to_dict())
        self.assertEqual(call_result_payload, result.call_result.to_dict())
        self.assertEqual(step_record_payload, result.step_record.to_dict())
        self.assertEqual(result.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(result.step_record.output_refs, ["reports/final_report.md"])
        self.assertEqual(result.step_record.piworker_call_ref, "kernel/demo-flow/steps/researcher/piworker_call.json")
        self.assertEqual(
            result.step_record.piworker_call_result_ref,
            "kernel/demo-flow/steps/researcher/piworker_call_result.json",
        )
        self.assertEqual(
            result.step_record.execution_report_ref,
            "attempts/demo-flow-researcher/pi_agent_execution_report.json",
        )

    def test_run_step_records_failed_status(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=_KernelFailedAdapter())
            step_record_payload = _read_json(Path(tmpdir), result.step_record_ref)

        self.assertEqual(result.step_record.status, StepStatus.FAILED)
        self.assertEqual(step_record_payload["status"], "failed")
        self.assertEqual(result.step_record.output_refs, [])
        self.assertEqual(result.step_record.failure_refs, [])
        self.assertEqual(
            result.step_record.execution_report_ref,
            "attempts/demo-flow-researcher/pi_agent_execution_report.json",
        )

    def test_run_step_rejects_completed_call_with_missing_output_file(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=_KernelMissingOutputAdapter())
            validation = _read_json(Path(tmpdir), result.call_result.validation_report_ref)

        self.assertEqual(result.call_result.status, PiWorkerCallResultStatus.INVALID_OUTPUT)
        self.assertEqual(result.step_record.status, StepStatus.FAILED)
        self.assertEqual(result.step_record.output_refs, [])
        self.assertEqual(validation["status"], "invalid_output")
        self.assertEqual(validation["missing_expected_output_refs"], ["reports/final_report.md"])

    def test_run_step_retries_missing_output_boundary_failure(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
            failure=FailurePolicy(retries=1),
        )
        adapter = _KernelMissingThenWritesAdapter()

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=adapter)

        self.assertEqual(adapter.call_count, 2)
        self.assertEqual(result.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(result.step_record.metadata["attempt_count"], 2)
        self.assertFalse(result.step_record.metadata["retry_exhausted"])

    def test_run_step_retries_failed_call_until_completed(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
            failure=FailurePolicy(retries=2),
        )
        adapter = _KernelFlakyAdapter(failures_before_success=1)

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=adapter)
            root = Path(tmpdir)
            first_attempt = _read_json(root, result.step_record.metadata["attempt_result_refs"][0])
            second_attempt = _read_json(root, result.step_record.metadata["attempt_result_refs"][1])
            final_payload = _read_json(root, result.piworker_call_result_ref)

        self.assertEqual(adapter.call_count, 2)
        self.assertEqual(result.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(result.step_record.metadata["attempt_count"], 2)
        self.assertFalse(result.step_record.metadata["retry_exhausted"])
        self.assertEqual(first_attempt["status"], "failed")
        self.assertEqual(second_attempt["status"], "completed")
        self.assertEqual(final_payload, result.call_result.to_dict())
        self.assertEqual(result.step_record.output_refs, ["reports/final_report.md"])

    def test_run_step_does_not_retry_non_retryable_provider_error(self) -> None:
        step = Step(
            id="reviewer",
            brief="Review a report.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/reviewer_observation.json"],
            read=["reports"],
            write=["reviews"],
            failure=FailurePolicy(retries=2, on_exhausted=StepStatus.BLOCKED),
        )
        adapter = _KernelNonRetryableProviderErrorAdapter()

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=adapter)

        self.assertEqual(adapter.call_count, 1)
        self.assertEqual(result.step_record.status, StepStatus.BLOCKED)
        self.assertEqual(result.step_record.metadata["attempt_count"], 1)
        self.assertTrue(result.call_result.metadata["non_retryable_provider_error"])
        self.assertTrue(result.step_record.metadata["non_retryable_provider_error"])
        self.assertIn("余额不足", result.step_record.metadata["failure_summary"])

    def test_run_step_uses_failure_policy_status_after_retry_exhaustion(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
            failure=FailurePolicy(retries=1, on_exhausted=StepStatus.BLOCKED),
        )
        adapter = _KernelFlakyAdapter(failures_before_success=3)

        with TemporaryDirectory() as tmpdir:
            result = run_step(step, context=_context(), workspace=tmpdir, adapter=adapter)

        self.assertEqual(adapter.call_count, 2)
        self.assertEqual(result.call_result.status.value, "failed")
        self.assertEqual(result.step_record.status, StepStatus.BLOCKED)
        self.assertEqual(result.step_record.metadata["attempt_count"], 2)
        self.assertTrue(result.step_record.metadata["retry_exhausted"])
        self.assertEqual(
            result.step_record.metadata["attempt_result_refs"],
            [
                "kernel/demo-flow/steps/researcher/attempts/001/piworker_call_result.json",
                "kernel/demo-flow/steps/researcher/attempts/002/piworker_call_result.json",
            ],
        )

    def test_run_step_skips_current_completed_artifact_boundary(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
        )
        first_adapter = _KernelDirectAdapter()
        second_adapter = _KernelDirectAdapter()

        with TemporaryDirectory() as tmpdir:
            _write_json(Path(tmpdir), "contract/task_contract.json", {"contract": "stable"})
            _write_json(Path(tmpdir), "sources/source_packet.json", {"sources": []})
            first = run_step(step, context=_context(), workspace=tmpdir, adapter=first_adapter)
            second = run_step(step, context=_context(), workspace=tmpdir, adapter=second_adapter)
            step_record_payload = _read_json(Path(tmpdir), second.step_record_ref)
            original_record_payload = _read_json(Path(tmpdir), first.step_record_ref)

        self.assertIsNotNone(first_adapter.seen_call)
        self.assertIsNone(second_adapter.seen_call)
        self.assertEqual(first.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(second.step_record.status, StepStatus.SKIPPED)
        self.assertEqual(step_record_payload["status"], "skipped")
        self.assertEqual(original_record_payload["status"], "completed")
        self.assertEqual(second.step_record.output_refs, ["reports/final_report.md"])
        self.assertEqual(second.call_result.output_refs, ["reports/final_report.md"])
        self.assertEqual(second.step_record.metadata["skip_reason"], "artifact_boundary_current")

    def test_run_step_does_not_skip_when_input_hash_changes(self) -> None:
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
        )
        first_adapter = _KernelDirectAdapter()
        second_adapter = _KernelDirectAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_json(root, "contract/task_contract.json", {"contract": "stable"})
            _write_json(root, "sources/source_packet.json", {"sources": []})
            first = run_step(step, context=_context(), workspace=tmpdir, adapter=first_adapter)
            _write_json(root, "sources/source_packet.json", {"sources": ["changed"]})
            second = run_step(step, context=_context(), workspace=tmpdir, adapter=second_adapter)

        self.assertEqual(first.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(second.step_record.status, StepStatus.COMPLETED)
        self.assertIsNotNone(second_adapter.seen_call)

    def test_run_step_writes_extension_lock_and_passes_ref_to_adapter(self) -> None:
        toolset = Toolset(
            id="academic",
            package="local:extensions/pi-academic-sources",
            tools=["academic_search"],
            network=True,
        )
        step = Step(
            id="source_expander",
            brief="Use the academic extension to expand sources.",
            inputs=["contract/task_contract.json"],
            outputs=["sources/source_patch.json"],
            read=["contract", "sources"],
            write=["sources"],
            tools=["read", "write", "academic"],
        )
        adapter = _KernelDirectAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_json(root, "contract/task_contract.json", {"contract": "stable"})
            result = run_step(
                step,
                context=_context(),
                workspace=tmpdir,
                adapter=adapter,
                toolsets={"academic": toolset},
                extension_lock_mode="install",
                extension_installer=_fake_extension_installer,
                extension_lock_compiled_at="2026-06-15T00:00:00Z",
            )
            lock_payload = _read_json(root, result.step_record.extension_lock_ref)
            lock = ExtensionLock.from_dict(lock_payload)

        self.assertEqual(adapter.seen_extension_lock_ref, "kernel/demo-flow/steps/source_expander/extension_lock.json")
        self.assertEqual(result.step_record.extension_lock_ref, adapter.seen_extension_lock_ref)
        self.assertEqual(result.step_record.extension_lock_hash, lock.lock_hash)
        self.assertEqual(lock.source_permission_manifest_ref, result.compiled.permission_manifest_ref)
        self.assertEqual(lock.extensions[0].grant_id, "demo-flow-source_expander-academic")
        self.assertEqual(lock.extensions[0].metadata["tool_names"], ["academic_search"])

    def test_run_step_skips_extension_step_when_lock_and_outputs_are_current(self) -> None:
        toolset = Toolset(
            id="academic",
            package="local:extensions/pi-academic-sources",
            tools=["academic_search"],
            network=True,
        )
        step = Step(
            id="source_expander",
            brief="Use the academic extension to expand sources.",
            inputs=["contract/task_contract.json"],
            outputs=["sources/source_patch.json"],
            read=["contract", "sources"],
            write=["sources"],
            tools=["read", "write", "academic"],
        )
        first_adapter = _KernelDirectAdapter()
        second_adapter = _KernelDirectAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_json(root, "contract/task_contract.json", {"contract": "stable"})
            first = run_step(
                step,
                context=_context(),
                workspace=tmpdir,
                adapter=first_adapter,
                toolsets={"academic": toolset},
                extension_lock_mode="install",
                extension_installer=_fake_extension_installer,
                extension_lock_compiled_at="2026-06-15T00:00:00Z",
            )
            second = run_step(
                step,
                context=_context(),
                workspace=tmpdir,
                adapter=second_adapter,
                toolsets={"academic": toolset},
                extension_lock_mode="install",
                extension_installer=_fake_extension_installer,
            )

        self.assertEqual(first.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(second.step_record.status, StepStatus.SKIPPED)
        self.assertIsNone(second_adapter.seen_call)
        self.assertEqual(second.step_record.extension_lock_ref, first.step_record.extension_lock_ref)
        self.assertEqual(second.step_record.extension_lock_hash, first.step_record.extension_lock_hash)

    def test_run_flow_routes_on_decision_artifact_to_judge_acceptance(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        judge = Step(
            id="judge",
            brief="Judge final acceptance.",
            inputs=["reports/final_report.md", "reviews/observation.json"],
            outputs=["judge/report.json"],
            read=["reports", "reviews"],
            write=["judge"],
            role=PiWorkerCallRole.JUDGE,
            route_on="judge/report.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer, judge],
            routes={
                "reviewer.ready_for_judge": "judge",
                "judge.accepted": Flow.stop("accepted"),
            },
            artifacts=[
                Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("judge/report.json", role=ArtifactRole.DECISION, owner="piworker"),
            ],
        )

        with TemporaryDirectory() as tmpdir:
            observed_events = []
            result = run_flow(
                flow,
                context=_context(),
                workspace=tmpdir,
                adapter=_KernelFlowAdapter(),
                event_sink=observed_events.append,
            )
            root = Path(tmpdir)
            flow_result_payload = _read_json(root, result.flow_result_ref)
            first_record = _read_json(root, result.flow_result.step_record_refs[0])
            second_record = _read_json(root, result.flow_result.step_record_refs[1])
            ledger_events = [
                FlowLedgerEvent.from_dict(payload)
                for payload in _read_jsonl(root, result.flow_result.ledger_refs[0])
            ]

        self.assertIsInstance(result, FlowRunResult)
        self.assertEqual(result.flow_result.status, "accepted")
        self.assertEqual(flow_result_payload, result.flow_result.to_dict())
        self.assertEqual(len(result.step_results), 2)
        self.assertEqual(result.flow_result.decision_refs, ["reviews/observation.json", "judge/report.json"])
        self.assertEqual(result.flow_result.ledger_refs, [result.flow_result.ledger_refs[0]])
        self.assertIn("executions/001/flow_ledger.jsonl", result.flow_result.ledger_refs[0])
        self.assertEqual(first_record["step_id"], "reviewer")
        self.assertEqual(second_record["step_id"], "judge")
        self.assertIn("001-reviewer", result.flow_result.step_record_refs[0])
        self.assertIn("002-judge", result.flow_result.step_record_refs[1])
        self.assertEqual(
            [event.kind for event in ledger_events],
            [
                FlowLedgerEventKind.STARTED,
                FlowLedgerEventKind.STEP_STARTED,
                FlowLedgerEventKind.STEP_RECORDED,
                FlowLedgerEventKind.ROUTED,
                FlowLedgerEventKind.STEP_STARTED,
                FlowLedgerEventKind.STEP_RECORDED,
                FlowLedgerEventKind.ROUTED,
                FlowLedgerEventKind.STOPPED,
            ],
        )
        self.assertEqual([event.to_dict() for event in observed_events], [event.to_dict() for event in ledger_events])
        self.assertEqual(ledger_events[1].kind, FlowLedgerEventKind.STEP_STARTED)
        self.assertEqual(ledger_events[1].step_id, "reviewer")
        self.assertIn("reports/final_report.md", ledger_events[1].refs)
        self.assertEqual(ledger_events[3].decision_ref, "reviews/observation.json")
        self.assertEqual(ledger_events[3].route_value, "ready_for_judge")
        self.assertEqual(ledger_events[3].route_target, "judge")
        self.assertEqual(ledger_events[-1].status, "accepted")
        self.assertEqual(ledger_events[-1].stop_reason, "terminal_route")

    def test_run_flow_skips_completed_steps_on_rerun(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        judge = Step(
            id="judge",
            brief="Judge final acceptance.",
            inputs=["reports/final_report.md", "reviews/observation.json"],
            outputs=["judge/report.json"],
            read=["reports", "reviews"],
            write=["judge"],
            role=PiWorkerCallRole.JUDGE,
            route_on="judge/report.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer, judge],
            routes={
                "reviewer.ready_for_judge": "judge",
                "judge.accepted": Flow.stop("accepted"),
            },
            artifacts=[
                Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("judge/report.json", role=ArtifactRole.DECISION, owner="piworker"),
            ],
        )
        first_adapter = _KernelFlowAdapter()
        second_adapter = _KernelCountingFlowAdapter()

        with TemporaryDirectory() as tmpdir:
            result = run_flow(flow, context=_context(), workspace=tmpdir, adapter=first_adapter)
            rerun = run_flow(flow, context=_context(), workspace=tmpdir, adapter=second_adapter)

        self.assertEqual(result.flow_result.status, "accepted")
        self.assertEqual(rerun.flow_result.status, "accepted")
        self.assertNotEqual(result.flow_result_ref, rerun.flow_result_ref)
        self.assertIn("executions/001/flow_result.json", result.flow_result_ref)
        self.assertIn("executions/002/flow_result.json", rerun.flow_result_ref)
        self.assertEqual(second_adapter.call_count, 0)
        self.assertEqual([item.step_record.status for item in rerun.step_results], [StepStatus.SKIPPED, StepStatus.SKIPPED])

    def test_run_flow_recovers_failed_step_with_complete_route_artifact_on_rerun(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
            failure=FailurePolicy(retries=0, on_exhausted=StepStatus.BLOCKED),
        )
        judge = Step(
            id="judge",
            brief="Judge final acceptance.",
            inputs=["reports/final_report.md", "reviews/observation.json"],
            outputs=["judge/report.json"],
            read=["reports", "reviews"],
            write=["judge"],
            role=PiWorkerCallRole.JUDGE,
            route_on="judge/report.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer, judge],
            routes={
                "reviewer.ready_for_judge": "judge",
                "judge.accepted": Flow.stop("accepted"),
            },
            artifacts=[
                Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("judge/report.json", role=ArtifactRole.DECISION, owner="piworker"),
            ],
        )
        first_adapter = _KernelWritesDecisionThenFailsAdapter()
        second_adapter = _KernelCountingFlowAdapter()

        with TemporaryDirectory() as tmpdir:
            first = run_flow(flow, context=_context(), workspace=tmpdir, adapter=first_adapter)
            rerun = run_flow(flow, context=_context(), workspace=tmpdir, adapter=second_adapter)

        self.assertEqual(first.flow_result.status, "blocked")
        self.assertEqual(rerun.flow_result.status, "accepted")
        self.assertEqual(second_adapter.call_count, 1)
        self.assertEqual([item.step_record.status for item in rerun.step_results], [StepStatus.SKIPPED, StepStatus.COMPLETED])
        self.assertEqual(
            rerun.step_results[0].step_record.metadata["skip_reason"],
            "artifact_boundary_recovered_after_step_failure",
        )
        self.assertEqual(rerun.step_results[0].step_record.metadata["recovered_from_step_status"], "blocked")

    def test_run_flow_blocks_and_records_result_for_missing_decision_field(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer],
            routes={"reviewer.ready_for_judge": Flow.stop("blocked")},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_flow(flow, context=_context(), workspace=tmpdir, adapter=_KernelMissingDecisionAdapter())
            root = Path(tmpdir)
            flow_result_payload = _read_json(root, result.flow_result_ref)
            ledger_events = _read_jsonl(root, result.flow_result.ledger_refs[0])

        self.assertEqual(result.flow_result.status, "blocked")
        self.assertEqual(flow_result_payload["status"], "blocked")
        self.assertEqual(result.flow_result.metadata["stop_reason"], "invalid_decision_artifact")
        self.assertEqual(ledger_events[-2]["kind"], FlowLedgerEventKind.ROUTED.value)
        self.assertEqual(ledger_events[-2]["route_value"], "invalid")
        self.assertEqual(ledger_events[-2]["route_target"], "blocked")
        self.assertEqual(ledger_events[-1]["stop_reason"], "invalid_decision_artifact")

    def test_run_flow_exposes_user_intervention_at_safe_point(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer],
            routes={"reviewer.ready_for_judge": Flow.stop("blocked")},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            port = FileInteractionPort(root)
            port.submit_text(
                "请优先关注工程可落地性。",
                run_id="demo-flow",
                target="flow",
                kind=UserEventKind.MESSAGE,
            )
            result = run_flow(flow, context=_context(), workspace=root, adapter=_KernelFlowAdapter(), interaction_port=port)
            step_record = result.step_results[0].step_record
            call = _read_json(root, step_record.piworker_call_ref)
            permission_manifest = _read_json(root, step_record.permission_manifest_ref)
            snapshot_ref = "kernel/demo-flow/runs/demo-flow/executions/001/interaction/safe_points/001-reviewer-user_events.json"
            snapshot = _read_json(root, snapshot_ref)
            ledger_events = _read_jsonl(root, result.flow_result.ledger_refs[0])

        self.assertIn(snapshot_ref, step_record.input_refs)
        self.assertIn(snapshot_ref, call["visible_refs"])
        self.assertIn(snapshot_ref, permission_manifest["readable_refs"])
        self.assertNotIn("interaction", permission_manifest["readable_refs"])
        self.assertNotIn("interaction", permission_manifest["writable_refs"])
        self.assertEqual(snapshot["event_count"], 1)
        self.assertTrue(any(event["kind"] == FlowLedgerEventKind.INTERACTION_RECORDED.value for event in ledger_events))

    def test_run_flow_keeps_user_intervention_text_out_of_ledger_and_result(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer],
            routes={"reviewer.ready_for_judge": Flow.stop("blocked")},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )
        user_text = "请优先关注工程可落地性，不要泛泛而谈。"

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            port = FileInteractionPort(root)
            port.submit_text(user_text, run_id="demo-flow", target="flow", kind=UserEventKind.MESSAGE)
            result = run_flow(flow, context=_context(), workspace=root, adapter=_KernelFlowAdapter(), interaction_port=port)
            snapshot_ref = "kernel/demo-flow/runs/demo-flow/executions/001/interaction/safe_points/001-reviewer-user_events.json"
            event_log = (root / "interaction/user_events.jsonl").read_text(encoding="utf-8")
            snapshot = (root / snapshot_ref).read_text(encoding="utf-8")
            ledger = (root / result.flow_result.ledger_refs[0]).read_text(encoding="utf-8")
            flow_result = (root / result.flow_result_ref).read_text(encoding="utf-8")

        self.assertIn(user_text, event_log)
        self.assertIn(user_text, snapshot)
        self.assertNotIn(user_text, ledger)
        self.assertNotIn(user_text, flow_result)

    def test_run_flow_does_not_ack_user_intervention_when_step_blocks(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
            failure=FailurePolicy(retries=0, on_exhausted=StepStatus.BLOCKED),
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer],
            routes={"reviewer.ready_for_judge": Flow.stop("blocked")},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            port = FileInteractionPort(root)
            port.submit_text("这个补充不能在失败 step 后被吞掉。", run_id="demo-flow", target="flow")
            result = run_flow(
                flow,
                context=_context(),
                workspace=root,
                adapter=_KernelFlakyAdapter(failures_before_success=1),
                interaction_port=port,
            )
            pending = port.pending_user_events(run_id="demo-flow", target="reviewer")
            acks = port.read_acks(run_id="demo-flow")

        self.assertEqual(result.flow_result.status, "blocked")
        self.assertEqual(len(pending), 1)
        self.assertEqual(acks, [])

    def test_run_flow_blocks_on_user_pause_without_calling_adapter(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer],
            routes={"reviewer.ready_for_judge": Flow.stop("blocked")},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )
        adapter = _KernelCountingFlowAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            port = FileInteractionPort(tmpdir)
            port.submit_text(
                "暂停一下。",
                run_id="demo-flow",
                target="flow",
                kind=UserEventKind.PAUSE_REQUEST,
                delivery=InteractionDelivery.NEXT_SAFE_POINT,
            )
            result = run_flow(flow, context=_context(), workspace=root, adapter=adapter, interaction_port=port)
            ledger_events = _read_jsonl(root, result.flow_result.ledger_refs[0])
            interaction_event = next(event for event in ledger_events if event["kind"] == FlowLedgerEventKind.INTERACTION_RECORDED.value)

        self.assertEqual(result.flow_result.status, "blocked")
        self.assertEqual(result.flow_result.metadata["stop_reason"], "user_pause_requested")
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(result.step_results, [])
        self.assertEqual(
            interaction_event["refs"],
            ["kernel/demo-flow/runs/demo-flow/executions/001/interaction/safe_points/001-reviewer-user_events.json"],
        )
        self.assertEqual(interaction_event["metadata"]["event_count"], 1)

    def test_run_flow_blocks_and_sanitizes_unsafe_decision_value(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-flow",
            steps=[reviewer],
            routes={"reviewer.ready_for_judge": Flow.stop("blocked")},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_flow(flow, context=_context(), workspace=tmpdir, adapter=_KernelUnsafeDecisionAdapter())
            ledger_events = _read_jsonl(Path(tmpdir), result.flow_result.ledger_refs[0])

        self.assertEqual(result.flow_result.status, "blocked")
        self.assertEqual(result.flow_result.metadata["stop_reason"], "invalid_decision_artifact")
        self.assertEqual(ledger_events[-2]["route_value"], "invalid")
        self.assertNotEqual(ledger_events[-2]["route_value"], "ready/now")

    def test_run_flow_blocks_when_max_steps_is_exhausted(self) -> None:
        reviewer = Step(
            id="reviewer",
            brief="Review the draft and decide the next step.",
            inputs=["reports/final_report.md"],
            outputs=["reviews/observation.json"],
            read=["reports"],
            write=["reviews"],
            route_on="reviews/observation.json",
            route_fields=["decision"],
        )
        flow = Flow(
            id="review-loop",
            steps=[reviewer],
            routes={"reviewer.continue": "reviewer"},
            artifacts=[Artifact("reviews/observation.json", role=ArtifactRole.DECISION, owner="piworker")],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_flow(flow, context=_context(), workspace=tmpdir, adapter=_KernelLoopAdapter(), max_steps=2)
            root = Path(tmpdir)
            flow_result_payload = _read_json(root, result.flow_result_ref)
            ledger_events = [
                FlowLedgerEvent.from_dict(payload)
                for payload in _read_jsonl(root, result.flow_result.ledger_refs[0])
            ]

        self.assertEqual(result.flow_result.status, "blocked")
        self.assertEqual(flow_result_payload["status"], "blocked")
        self.assertEqual(result.flow_result.metadata["stop_reason"], "max_steps_exhausted")
        self.assertEqual(len(result.step_results), 2)
        self.assertIn("001-reviewer", result.flow_result.step_record_refs[0])
        self.assertIn("002-reviewer", result.flow_result.step_record_refs[1])
        self.assertEqual(ledger_events[-1].kind, FlowLedgerEventKind.STOPPED)
        self.assertEqual(ledger_events[-1].stop_reason, "max_steps_exhausted")

    def test_run_projection_uses_registered_projector_and_writes_record(self) -> None:
        projection = Projection(
            output="reports/summary.json",
            from_=["reports/final_report.md"],
            projector="summary_index",
            metadata={"kind": "summary"},
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_text(root, "reports/final_report.md", "hello\n")
            result = run_projection(
                projection,
                workspace=tmpdir,
                projectors={"summary_index": _summary_projector},
                record_ref="kernel/projections/summary.json",
            )
            output_payload = _read_json(root, "reports/summary.json")
            record_payload = _read_json(root, result.record_ref)

        self.assertIsInstance(result, ProjectionRunResult)
        self.assertEqual(output_payload, {"source_count": 1})
        self.assertEqual(record_payload, result.record.to_dict())
        self.assertEqual(result.record.output_ref, "reports/summary.json")
        self.assertEqual(result.record.source_refs, ["reports/final_report.md"])
        self.assertEqual(result.record.metadata["projection_metadata"], {"kind": "summary"})

    def test_run_projection_rejects_unregistered_projector(self) -> None:
        projection = Projection(
            output="reports/summary.json",
            from_=["reports/final_report.md"],
            projector="summary_index",
        )

        with TemporaryDirectory() as tmpdir:
            _write_text(Path(tmpdir), "reports/final_report.md", "hello\n")
            with self.assertRaisesRegex(KernelValidationError, "not registered"):
                run_projection(projection, workspace=tmpdir, projectors={})

    def test_flow_requires_projection_artifact_declaration(self) -> None:
        writer = Step(
            id="writer",
            brief="Write final report.",
            inputs=["contract/task_contract.json"],
            outputs=["reports/final_report.md"],
            read=["contract"],
            write=["reports"],
        )

        with self.assertRaisesRegex(KernelValidationError, "projection output artifact must be declared"):
            Flow(
                id="projection-flow",
                steps=[writer],
                projections=[
                    Projection(
                        output="reports/summary.json",
                        from_=["reports/final_report.md"],
                        projector="summary_index",
                    )
                ],
            )

    def test_run_flow_runs_runtime_projection_after_acceptance(self) -> None:
        writer = Step(
            id="writer",
            brief="Write final report.",
            inputs=["contract/task_contract.json"],
            outputs=["reports/final_report.md"],
            read=["contract"],
            write=["reports"],
        )
        flow = Flow(
            id="projection-flow",
            steps=[writer],
            routes={},
            artifacts=[
                Artifact("reports/final_report.md", role=ArtifactRole.OUTPUT, owner="piworker"),
                Artifact("reports/summary.json", role=ArtifactRole.PROJECTION, owner="runtime"),
            ],
            projections=[
                Projection(
                    output="reports/summary.json",
                    from_=["reports/final_report.md"],
                    projector="summary_index",
                )
            ],
        )

        with TemporaryDirectory() as tmpdir:
            _write_json(Path(tmpdir), "contract/task_contract.json", {"contract": "stable"})
            result = run_flow(
                flow,
                context=_context(),
                workspace=tmpdir,
                adapter=_KernelDirectAdapter(),
                projectors={"summary_index": _summary_projector},
            )
            output_payload = _read_json(Path(tmpdir), "reports/summary.json")
            ledger_events = _read_jsonl(Path(tmpdir), result.flow_result.ledger_refs[0])

        self.assertEqual(result.flow_result.status, "completed")
        self.assertEqual(output_payload, {"source_count": 1})
        self.assertEqual(
            result.flow_result.ledger_refs,
            [
                "kernel/demo-flow/runs/demo-flow/executions/001/flow_ledger.jsonl",
                "kernel/demo-flow/runs/demo-flow/executions/001/projections/001-summary_index.json",
            ],
        )
        self.assertEqual(ledger_events[-2]["kind"], "projections_recorded")
        self.assertEqual(ledger_events[-1]["stop_reason"], "step_without_route")
        self.assertIn("reports/summary.json", result.flow_result.final_artifact_refs)


def _context() -> StepCompileContext:
    return StepCompileContext(
        flow_id="demo-flow",
        contract_id="demo-contract",
        contract_hash="sha256:" + "a" * 64,
    )


class _KernelDirectAdapter:
    adapter_family = "kernel-test-direct"

    def __init__(self) -> None:
        self.seen_call = None
        self.seen_extension_lock_ref = None

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        self.seen_call = call
        self.seen_extension_lock_ref = extension_lock_ref
        output_ref = call.expected_output_refs[0]
        _write_text(Path(workspace), output_ref, "kernel adapter artifact\n")
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id="R-demo-flow-researcher",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[
                    output_ref,
                    "attempts/demo-flow-researcher/pi_agent_output.json",
                ],
                evidence_refs=["evidence/adapter_event_001.json"],
                metrics={"metric_ref": "attempts/demo-flow-researcher/pi_agent_metrics.json"},
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref="attempts/demo-flow-researcher/pi_agent_execution_report.json",
            ),
            event_evidence_refs=["evidence/adapter_event_002.json"],
            metrics={"duration_ms": 1},
        )


class _KernelFailedAdapter:
    adapter_family = "kernel-test-failed"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id="R-demo-flow-researcher",
                call_id=call.call_id,
                status="failed",
                produced_artifacts=[],
                changed_refs=[],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="failed",
                execution_report_ref="attempts/demo-flow-researcher/pi_agent_execution_report.json",
            ),
            metrics={"error_ref": "errors/demo-flow-researcher.json"},
        )


class _KernelMissingOutputAdapter:
    adapter_family = "kernel-test-missing-output"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        output_ref = call.expected_output_refs[0]
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}-missing-output",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/pi_agent_execution_report.json",
            ),
        )


class _KernelMissingThenWritesAdapter:
    adapter_family = "kernel-test-missing-then-writes"

    def __init__(self) -> None:
        self.call_count = 0

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        self.call_count += 1
        output_ref = call.expected_output_refs[0]
        if self.call_count > 1:
            _write_text(Path(workspace), output_ref, "kernel adapter artifact\n")
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}-{self.call_count}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}-{self.call_count}/pi_agent_execution_report.json",
            ),
        )


class _KernelFlakyAdapter:
    adapter_family = "kernel-test-flaky"

    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.call_count = 0

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        self.call_count += 1
        if self.call_count <= self.failures_before_success:
            return WorkerAdapterResult(
                execution_report=ExecutionReport(
                    report_id=f"R-{call.call_id}-{self.call_count}",
                    call_id=call.call_id,
                    status="failed",
                    produced_artifacts=[],
                    changed_refs=[],
                    evidence_refs=[],
                ),
                worker_result=WorkerResult(
                    status="failed",
                    execution_report_ref=f"attempts/{call.call_id}-{self.call_count}/pi_agent_execution_report.json",
                ),
            )
        output_ref = call.expected_output_refs[0]
        _write_text(Path(workspace), output_ref, "kernel adapter artifact\n")
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}-{self.call_count}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}-{self.call_count}/pi_agent_execution_report.json",
            ),
        )


class _KernelNonRetryableProviderErrorAdapter:
    adapter_family = "kernel-test-provider-error"

    def __init__(self) -> None:
        self.call_count = 0

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        self.call_count += 1
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}-{self.call_count}",
                call_id=call.call_id,
                status="failed",
                produced_artifacts=[],
                changed_refs=[],
                evidence_refs=[],
                metrics={
                    "failure_summary": "OpenAI API error (403): 403 余额不足",
                    "non_retryable_provider_error": True,
                },
            ),
            worker_result=WorkerResult(
                status="failed",
                execution_report_ref=f"attempts/{call.call_id}-{self.call_count}/pi_agent_execution_report.json",
            ),
        )


class _KernelFlowAdapter:
    adapter_family = "kernel-test-flow"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        output_ref = call.expected_output_refs[0]
        if call.call_id.endswith("-reviewer"):
            _write_json(Path(workspace), output_ref, {"decision": "ready_for_judge"})
        elif call.call_id.endswith("-judge"):
            _write_json(Path(workspace), output_ref, {"decision": "accepted"})
        else:
            _write_json(Path(workspace), output_ref, {"decision": "completed"})
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/pi_agent_execution_report.json",
            ),
        )


class _KernelCountingFlowAdapter(_KernelFlowAdapter):
    def __init__(self) -> None:
        self.call_count = 0

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        self.call_count += 1
        return super().run_call(
            call,
            workspace=workspace,
            evidence_store=evidence_store,
            call_spec=call_spec,
            exit_criteria=exit_criteria,
            stop_conditions=stop_conditions,
            extension_lock_ref=extension_lock_ref,
        )


class _KernelWritesDecisionThenFailsAdapter:
    adapter_family = "kernel-test-writes-decision-then-fails"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        output_ref = call.expected_output_refs[0]
        _write_json(Path(workspace), output_ref, {"decision": "ready_for_judge"})
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}",
                call_id=call.call_id,
                status="failed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="failed",
                execution_report_ref=f"attempts/{call.call_id}/pi_agent_execution_report.json",
            ),
        )


class _KernelMissingDecisionAdapter:
    adapter_family = "kernel-test-missing-decision"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        output_ref = call.expected_output_refs[0]
        _write_json(Path(workspace), output_ref, {"note": "no decision"})
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/pi_agent_execution_report.json",
            ),
        )


class _KernelUnsafeDecisionAdapter:
    adapter_family = "kernel-test-unsafe-decision"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        output_ref = call.expected_output_refs[0]
        _write_json(Path(workspace), output_ref, {"decision": "ready/now"})
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/pi_agent_execution_report.json",
            ),
        )


class _KernelLoopAdapter:
    adapter_family = "kernel-test-loop"

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        output_ref = call.expected_output_refs[0]
        _write_json(Path(workspace), output_ref, {"decision": "continue"})
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/pi_agent_execution_report.json",
            ),
        )


def _write_json(root: Path, ref: str, payload: dict):
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_text(root: Path, ref: str, text: str):
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _summary_projector(source_paths, projection):
    return {"source_count": len(source_paths)}


def _fake_extension_installer(grant, install_root):
    package_name = Path(grant.package[len("local:"):]).name if grant.package.startswith("local:") else grant.package.rsplit("/", 1)[-1]
    install_path = install_root / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "package.json").write_text(
        json.dumps({"name": package_name, "version": grant.version_spec}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (install_path / "index.js").write_text("export default {};\n", encoding="utf-8")
    return {}


def _read_json(root: Path, ref: str):
    return json.loads((root / ref).read_text(encoding="utf-8"))


def _read_jsonl(root: Path, ref: str):
    return [json.loads(line) for line in (root / ref).read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()

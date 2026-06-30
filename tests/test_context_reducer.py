from __future__ import annotations

import unittest

from missionforge import (
    ContextReductionReason,
    ContextReductionRequest,
    ContextReductionResult,
    ContextReductionStatus,
    ContextSource,
    ContextSourceKind,
    ContextCompactionStatus,
    ContextCachePolicy,
    ContextInlinePolicy,
    ContractValidationError,
    PiWorkerCallRole,
    build_context_reduction_state_transition,
    build_managed_context_reducer_call,
    context_reduction_request_hash,
    validate_context_reduction_result_boundary,
)
from missionforge.kernel.context_reduction_runtime import _context_compile_request_after_reduction


HASH1 = "sha256:" + "1" * 64
HASH2 = "sha256:" + "2" * 64


class ContextReducerTests(unittest.TestCase):
    def test_builds_managed_reducer_call_with_scoped_permissions(self) -> None:
        request = _request()

        compiled = build_managed_context_reducer_call(
            request=request,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            maintenance_root_ref="kernel/demo/context/maintenance",
        )

        self.assertEqual(compiled.call.role, PiWorkerCallRole.CONTEXT_REDUCER)
        self.assertEqual(compiled.call.permission_manifest_ref, compiled.permission_manifest_ref)
        self.assertEqual(context_reduction_request_hash(request), request.reduction_request_hash)
        self.assertIn("kernel/demo/context/reduction_request.json", compiled.permission_manifest.readable_refs)
        self.assertIn("kernel/demo/context/context_view.json", compiled.permission_manifest.readable_refs)
        self.assertIn("attempts/call/context/projections/obs1.json", compiled.permission_manifest.readable_refs)
        self.assertIn("kernel/demo/context/maintenance", compiled.permission_manifest.writable_refs)
        self.assertEqual(compiled.call.expected_output_refs, ["kernel/demo/context/maintenance/reduction_result.json"])
        self.assertEqual(compiled.permission_manifest.allowed_tools, ["read", "write"])
        self.assertEqual(compiled.permission_manifest.network_policy.value, "disabled")

    def test_validates_reducer_result_permissions(self) -> None:
        request = _request()
        compiled = build_managed_context_reducer_call(
            request=request,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            maintenance_root_ref="kernel/demo/context/maintenance",
        )
        result = ContextReductionResult(
            reduction_id="reduce1",
            status=ContextReductionStatus.COMPLETED,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref=compiled.permission_manifest_ref,
            checkpoint_ref="kernel/demo/context/maintenance/checkpoint.json",
            working_set_ref="kernel/demo/context/maintenance/working_set.json",
            summary_refs=["kernel/demo/context/maintenance/summary.json"],
            source_refs=["sources/source_packet.json"],
            pinned_refs=["sources/source_packet.json"],
            evicted_refs=["attempts/call/context/projections/obs1.json"],
            omitted_refs=["attempts/call/context/projections/obs1.json"],
            compaction_record_ref="kernel/demo/context/maintenance/compaction.json",
            validation_report_ref="kernel/demo/context/maintenance/reduction_result.json",
        )

        self.assertEqual(
            validate_context_reduction_result_boundary(
                result=result,
                request=request,
                reducer_permission_manifest=compiled.permission_manifest,
            ),
            result,
        )

    def test_rejects_reducer_result_reading_denied_or_writing_outside_maintenance(self) -> None:
        request = _request()
        compiled = build_managed_context_reducer_call(
            request=request,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            maintenance_root_ref="kernel/demo/context/maintenance",
        )

        with self.assertRaisesRegex(ContractValidationError, "not readable"):
            validate_context_reduction_result_boundary(
                result=ContextReductionResult(
                    reduction_id="reduce1",
                    status=ContextReductionStatus.COMPLETED,
                    request_ref="kernel/demo/context/reduction_request.json",
                    permission_manifest_ref=compiled.permission_manifest_ref,
                    working_set_ref="kernel/demo/context/maintenance/working_set.json",
                    source_refs=["secrets/source.json"],
                ),
                request=request,
                reducer_permission_manifest=compiled.permission_manifest,
            )

        with self.assertRaisesRegex(ContractValidationError, "not writable"):
            validate_context_reduction_result_boundary(
                result=ContextReductionResult(
                    reduction_id="reduce1",
                    status=ContextReductionStatus.COMPLETED,
                    request_ref="kernel/demo/context/reduction_request.json",
                    permission_manifest_ref=compiled.permission_manifest_ref,
                    working_set_ref="reports/working_set.json",
                ),
                request=request,
                reducer_permission_manifest=compiled.permission_manifest,
            )

    def test_builds_completed_reduction_state_transition_with_ended_compaction(self) -> None:
        request = _request()
        result = ContextReductionResult(
            reduction_id="reduce1",
            status=ContextReductionStatus.COMPLETED,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            checkpoint_ref="kernel/demo/context/maintenance/checkpoint.json",
            working_set_ref="kernel/demo/context/maintenance/working_set.json",
            summary_refs=["kernel/demo/context/maintenance/summary.json"],
            source_refs=["sources/source_packet.json"],
            compaction_record_ref="kernel/demo/context/maintenance/compaction.json",
        )

        transition = build_context_reduction_state_transition(
            request=request,
            result=result,
            request_ref="kernel/demo/context/reduction_request.json",
            result_ref="kernel/demo/context/maintenance/reduction_result.json",
            input_epoch_ref="kernel/demo/context/epoch.json",
            input_context_view_ref="kernel/demo/context/context_view.json",
            output_epoch_ref="kernel/demo/context/maintenance/epoch.json",
            output_context_view_ref="kernel/demo/context/maintenance/context_view.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
        )

        self.assertEqual(transition.status, ContextReductionStatus.COMPLETED)
        self.assertEqual(transition.output_epoch_ref, "kernel/demo/context/maintenance/epoch.json")
        self.assertEqual(transition.output_context_view_ref, "kernel/demo/context/maintenance/context_view.json")
        self.assertIsNotNone(transition.compaction_record)
        self.assertEqual(transition.compaction_record.status, ContextCompactionStatus.ENDED)
        self.assertEqual(transition.compaction_record.summary_artifact_refs, ["kernel/demo/context/maintenance/summary.json"])

        with self.assertRaisesRegex(ContractValidationError, "output epoch and view"):
            build_context_reduction_state_transition(
                request=request,
                result=result,
                request_ref="kernel/demo/context/reduction_request.json",
                result_ref="kernel/demo/context/maintenance/reduction_result.json",
                input_epoch_ref="kernel/demo/context/epoch.json",
                input_context_view_ref="kernel/demo/context/context_view.json",
                permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            )

    def test_failed_reduction_transition_does_not_publish_output_epoch_or_view(self) -> None:
        request = _request()
        result = ContextReductionResult(
            reduction_id="reduce1",
            status=ContextReductionStatus.FAILED,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            checkpoint_ref="kernel/demo/context/checkpoint.json",
            validation_report_ref="kernel/demo/context/maintenance/reduction_result.json",
        )

        transition = build_context_reduction_state_transition(
            request=request,
            result=result,
            request_ref="kernel/demo/context/reduction_request.json",
            result_ref="kernel/demo/context/maintenance/reduction_result.json",
            input_epoch_ref="kernel/demo/context/epoch.json",
            input_context_view_ref="kernel/demo/context/context_view.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
        )

        self.assertEqual(transition.status, ContextReductionStatus.FAILED)
        self.assertIsNone(transition.output_epoch_ref)
        self.assertIsNone(transition.output_context_view_ref)
        self.assertIsNotNone(transition.compaction_record)
        self.assertEqual(transition.compaction_record.status, ContextCompactionStatus.FAILED)

    def test_recompile_request_removes_evicted_projection_body_ref(self) -> None:
        request = _compile_request()
        result = ContextReductionResult(
            reduction_id="reduce1",
            status=ContextReductionStatus.COMPLETED,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/context/reducer_permission_manifest.json",
            checkpoint_ref="kernel/demo/context/maintenance/checkpoint.json",
            working_set_ref="kernel/demo/context/maintenance/working_set.json",
            omitted_refs=["attempts/call/context/projections/obs1.txt"],
            evicted_refs=["attempts/call/context/projections/obs1.txt"],
        )

        reduced = _context_compile_request_after_reduction(
            request,
            result=result,
            request_ref="kernel/demo/context/reduction_request.json",
        )

        self.assertEqual(reduced.context_sources[0].source_refs, ["attempts/call/context/projections/obs1.json"])
        self.assertIsNone(reduced.context_sources[0].projection_ref)
        self.assertIsNone(reduced.context_sources[0].projection_hash)


def _request() -> ContextReductionRequest:
    return ContextReductionRequest(
        reduction_id="reduce1",
        reason=ContextReductionReason.PRESSURE_HARD,
        role="executor_piworker",
        contract_ref="contract/task_contract.json",
        contract_hash=HASH1,
        permission_manifest_ref="kernel/demo/permission_manifest.json",
        context_view_ref="kernel/demo/context/context_view.json",
        context_hash=HASH2,
        source_snapshot_ref="kernel/demo/context/source_snapshot.json",
        expected_output_refs=[
            "kernel/demo/context/maintenance/reduction_result.json",
            "kernel/demo/context/maintenance/working_set.json",
        ],
        worker_brief_ref="projections/worker_brief.json",
        pressure_ref="kernel/demo/context/pressure.json",
        current_working_set_ref="kernel/demo/context/working_set.previous.json",
        thrash_diagnostics_refs=["kernel/demo/context/thrash.json"],
        recent_projection_refs=["attempts/call/context/projections/obs1.json"],
        source_refs=["sources/source_packet.json"],
        tool_observation_refs=["attempts/call/context/tool_observations.jsonl"],
        checkpoint_refs=["kernel/demo/context/checkpoint.json"],
    )


def _compile_request():
    from missionforge import ContextCompileRequest

    return ContextCompileRequest(
        request_id="compile1",
        role="executor_piworker",
        contract_ref="contract/task_contract.json",
        contract_hash=HASH1,
        permission_manifest_ref="kernel/demo/permission_manifest.json",
        context_sources=[
            ContextSource(
                source_key="context_feed/000",
                kind=ContextSourceKind.TOOL_OBSERVATION,
                source_refs=[
                    "attempts/call/context/projections/obs1.json",
                    "attempts/call/context/projections/obs1.txt",
                ],
                source_hashes={
                    "attempts/call/context/projections/obs1.json": HASH1,
                    "attempts/call/context/projections/obs1.txt": HASH2,
                },
                projection_ref="attempts/call/context/projections/obs1.txt",
                projection_hash=HASH2,
                cache_policy=ContextCachePolicy.VOLATILE,
                inline_policy=ContextInlinePolicy.PREVIEW,
                required=False,
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()

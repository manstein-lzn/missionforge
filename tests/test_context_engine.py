from __future__ import annotations

import unittest

from missionforge import (
    ContextCachePolicy,
    ContextCheckpoint,
    ContextCheckpointCreator,
    ContextCompactionRecord,
    ContextCompactionStatus,
    ContextCompileAction,
    ContextCompileRequest,
    ContextCompileResult,
    ContextEpoch,
    ContextInlinePolicy,
    ContextReadObservation,
    ContextReductionReason,
    ContextReductionRequest,
    ContextReductionResult,
    ContextReductionStatus,
    ContextSource,
    ContextSourceKind,
    ContextSourceSnapshot,
    ContextThrashDiagnostics,
    ContextTurnBoundary,
    ContextTurnBoundaryStatus,
    ContextView,
    ContextWorkingSet,
    ContextWorkingSetEntry,
    ContextWorkingSetFreshness,
    ContextWorkingSetPinPolicy,
    ContractValidationError,
    PermissionManifest,
    ReadGate,
    build_call_context_view,
    build_context_cache_layout,
    build_context_epoch,
    build_thrash_diagnostics,
    compile_context_request,
    filter_context_sources,
    reconcile_context_epoch,
)


HASH1 = "sha256:" + "1" * 64
HASH2 = "sha256:" + "2" * 64
HASH3 = "sha256:" + "3" * 64


class ContextEngineTests(unittest.TestCase):
    def test_context_source_and_snapshot_are_refs_only(self) -> None:
        source = ContextSource(
            source_key="authority/contract",
            kind=ContextSourceKind.AUTHORITY,
            source_refs=["contract/task_contract.json"],
            source_hashes={"contract/task_contract.json": HASH1},
            projection_ref="context/projections/contract.txt",
            projection_hash=HASH2,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            cache_policy=ContextCachePolicy.STABLE,
            inline_policy=ContextInlinePolicy.PREVIEW,
            required=True,
            token_estimate=120,
            priority=100,
        )

        round_trip = ContextSource.from_dict(source.to_dict())
        snapshot = ContextSourceSnapshot.from_source(round_trip, sequence=7)

        self.assertEqual(round_trip.source_key, "authority/contract")
        self.assertEqual(snapshot.sequence, 7)
        self.assertEqual(snapshot.projection_ref, "context/projections/contract.txt")
        self.assertNotIn("raw_body", str(source.to_dict()).lower())

        payload = source.to_dict()
        payload["metadata"] = {"prompt": "must not be durable"}
        with self.assertRaisesRegex(ContractValidationError, "prompt"):
            ContextSource.from_dict(payload)

    def test_filter_context_sources_runs_readgate_before_projection(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-context",
                "readable_refs": ["contract", "context/projections"],
                "denied_refs": ["context/projections/secret.txt"],
            }
        )
        allowed = ContextSource(
            source_key="authority/contract",
            kind=ContextSourceKind.AUTHORITY,
            source_refs=["contract/task_contract.json"],
            projection_ref="context/projections/contract.txt",
            required=True,
        )
        denied = ContextSource(
            source_key="runtime/secret",
            kind=ContextSourceKind.RUNTIME_DIAGNOSTIC,
            source_refs=["contract/task_contract.json"],
            projection_ref="context/projections/secret.txt",
            required=True,
        )

        result = filter_context_sources([allowed, denied], ReadGate(manifest))

        self.assertEqual([source.source_key for source in result.allowed_sources], ["authority/contract"])
        self.assertEqual(result.denied_required_source_keys, ["runtime/secret"])
        self.assertEqual(result.denied_source_refs, ["context/projections/secret.txt"])
        self.assertTrue(result.has_denied_required_source)

    def test_working_set_entry_carries_projection_and_why_refs(self) -> None:
        entry = ContextWorkingSetEntry(
            entry_id="entry1",
            source_ref="sources/source_packet.json",
            source_hash=HASH1,
            projection_ref="context/projections/source_packet_entry1.md",
            projection_hash=HASH2,
            why_ref="analysis/why_source_packet_entry1.json",
            phase_label="evidence",
            claim_link_refs=["claims/claim_index.json"],
            producing_observation_ids=["obs1"],
            token_estimate=200,
            token_cap=500,
            pin_policy=ContextWorkingSetPinPolicy.PINNED_UNTIL_CHECKPOINT,
            freshness=ContextWorkingSetFreshness.ACTIVE_PHASE,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
        )
        working_set = ContextWorkingSet(
            working_set_id="ws1",
            role="executor_piworker",
            phase_label="evidence",
            entries=[entry],
            token_estimate=200,
            token_cap=1000,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
        )

        payload = working_set.to_dict()
        self.assertEqual(ContextWorkingSet.from_dict(payload).working_set_hash, payload["working_set_hash"])
        self.assertEqual(payload["entries"][0]["why_ref"], "analysis/why_source_packet_entry1.json")

        with self.assertRaisesRegex(ContractValidationError, "token_estimate"):
            ContextWorkingSetEntry(
                entry_id="bad",
                source_ref="sources/a.json",
                source_hash=HASH1,
                projection_ref="context/projections/a.md",
                projection_hash=HASH2,
                phase_label="evidence",
                token_estimate=501,
                token_cap=500,
            )

    def test_cache_layout_stable_hash_ignores_volatile_tail_changes(self) -> None:
        view1 = _view_with_visible_refs(["sources/a.json"])
        view2 = _view_with_visible_refs(["sources/b.json"])

        layout1 = build_context_cache_layout(
            layout_id="layout1",
            view_ref="kernel/demo/context_view.json",
            view=view1,
        )
        layout2 = build_context_cache_layout(
            layout_id="layout2",
            view_ref="kernel/demo/context_view.json",
            view=view2,
        )

        self.assertEqual(layout1.stable_strata_hash, layout2.stable_strata_hash)
        self.assertEqual(layout1.rendered_prefix_hash, layout2.rendered_prefix_hash)
        self.assertNotEqual(layout1.volatile_strata_hash, layout2.volatile_strata_hash)
        self.assertIn("contract/task_contract.json", layout1.epoch_invalidation_refs)

    def test_epoch_turn_compile_checkpoint_and_compaction_records_are_refs_only(self) -> None:
        epoch = build_context_epoch(
            epoch_id="epoch1",
            role="executor_piworker",
            contract_hash=HASH1,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            baseline_ref="context/epochs/epoch1/baseline.txt",
            baseline_hash=HASH2,
            source_snapshot_ref="context/epochs/epoch1/source_snapshot.json",
            context_view_ref="kernel/demo/context_view.json",
            created_at="2026-06-26T00:00:00Z",
        )
        boundary = ContextTurnBoundary(
            boundary_id="boundary1",
            run_id="run1",
            call_id="call-1",
            turn_id="turn1",
            role="executor_piworker",
            safe_point_ref="observation/safe_points/turn1.json",
            pre_view_ref="kernel/demo/context_view.json",
            status=ContextTurnBoundaryStatus.READY,
            context_epoch_ref="context/epochs/epoch1.json",
        )
        result = ContextCompileResult(
            result_id="compile1",
            view_ref="kernel/demo/context_view.json",
            context_hash=HASH3,
            action=ContextCompileAction.CONTINUE,
            epoch_ref="context/epochs/epoch1.json",
        )
        checkpoint = ContextCheckpoint(
            checkpoint_id="checkpoint1",
            reason_code="pressure_hard",
            role="executor_piworker",
            run_id="run1",
            call_id="call-1",
            source_snapshot_ref="context/epochs/epoch1/source_snapshot.json",
            context_view_ref="kernel/demo/context_view.json",
            context_hash=HASH3,
            summary_refs=["context/summaries/summary1.json"],
            recent_refs=["sources/source_packet.json"],
            tool_observation_refs=["observations/tool_observation1.json"],
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            created_by=ContextCheckpointCreator.RUNTIME,
            created_at="2026-06-27T00:00:00Z",
        )
        compaction = ContextCompactionRecord(
            record_id="compact1",
            status=ContextCompactionStatus.ENDED,
            reason_code="pressure",
            input_epoch_ref="context/epochs/epoch1.json",
            output_epoch_ref="context/epochs/epoch2.json",
            input_context_view_ref="kernel/demo/context_view.json",
            output_context_view_ref="kernel/demo/context_view_compacted.json",
            checkpoint_ref="context/checkpoints/compact1.json",
            summary_artifact_refs=["context/summaries/summary1.json"],
            source_refs=["sources/source_packet.json"],
            producing_role="executor_piworker",
            permission_manifest_ref="kernel/demo/permission_manifest.json",
        )

        self.assertEqual(ContextEpoch.from_dict(epoch.to_dict()).epoch_hash, epoch.epoch_hash)
        self.assertEqual(ContextTurnBoundary.from_dict(boundary.to_dict()).status, ContextTurnBoundaryStatus.READY)
        self.assertEqual(ContextCompileResult.from_dict(result.to_dict()).action, ContextCompileAction.CONTINUE)
        self.assertEqual(
            ContextCheckpoint.from_dict(checkpoint.to_dict()).checkpoint_hash,
            checkpoint.checkpoint_hash,
        )
        self.assertEqual(ContextCompactionRecord.from_dict(compaction.to_dict()).status, ContextCompactionStatus.ENDED)
        self.assertNotIn("raw_body", str(checkpoint.to_dict()))
        self.assertNotIn("provider_message", str(compaction.to_dict()))

        payload = checkpoint.to_dict()
        payload["metadata"] = {"raw_body": "must not be durable"}
        with self.assertRaisesRegex(ContractValidationError, "raw_body"):
            ContextCheckpoint.from_dict(payload)

    def test_compaction_ended_requires_output_refs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "requires output"):
            ContextCompactionRecord(
                record_id="compact1",
                status=ContextCompactionStatus.ENDED,
                reason_code="pressure",
                input_epoch_ref="context/epochs/epoch1.json",
                input_context_view_ref="kernel/demo/context_view.json",
                checkpoint_ref="context/checkpoints/compact1.json",
                producing_role="executor_piworker",
                permission_manifest_ref="kernel/demo/permission_manifest.json",
            )

    def test_reduction_request_and_result_are_refs_only(self) -> None:
        request = ContextReductionRequest(
            reduction_id="reduce1",
            reason=ContextReductionReason.PRESSURE_HARD,
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=HASH1,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            context_view_ref="kernel/demo/context_view.json",
            context_hash=HASH2,
            source_snapshot_ref="kernel/demo/context/source_snapshot.json",
            expected_output_refs=[
                "kernel/demo/context/reduction_result.json",
                "kernel/demo/context/working_set.json",
            ],
            worker_brief_ref="projections/worker_brief.json",
            pressure_ref="kernel/demo/context/pressure.json",
            current_working_set_ref="kernel/demo/context/working_set.previous.json",
            thrash_diagnostics_refs=["kernel/demo/context/thrash.json"],
            recent_projection_refs=["attempts/call/context/tool_output_projections/obs1.json"],
            source_refs=["sources/source_packet.json"],
            tool_observation_refs=["attempts/call/context/tool_observations.jsonl"],
            checkpoint_refs=["kernel/demo/context/checkpoint.json"],
        )
        result = ContextReductionResult(
            reduction_id="reduce1",
            status=ContextReductionStatus.COMPLETED,
            request_ref="kernel/demo/context/reduction_request.json",
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            checkpoint_ref="kernel/demo/context/checkpoint.json",
            working_set_ref="kernel/demo/context/working_set.json",
            summary_refs=["kernel/demo/context/summary.json"],
            pinned_refs=["sources/source_packet.json"],
            evicted_refs=["attempts/call/context/tool_output_projections/obs0.json"],
            omitted_refs=["attempts/call/context/raw_large.txt"],
            source_refs=["sources/source_packet.json"],
            denied_source_refs=["secrets/private_source.json"],
            compaction_record_ref="kernel/demo/context/compaction.json",
            validation_report_ref="kernel/demo/context/reduction_validation.json",
        )

        self.assertEqual(
            ContextReductionRequest.from_dict(request.to_dict()).reduction_request_hash,
            request.reduction_request_hash,
        )
        self.assertEqual(
            ContextReductionResult.from_dict(result.to_dict()).reduction_result_hash,
            result.reduction_result_hash,
        )

        request_payload = request.to_dict()
        request_payload["metadata"] = {"raw_prompt": "must not be durable"}
        with self.assertRaisesRegex(ContractValidationError, "raw_prompt"):
            ContextReductionRequest.from_dict(request_payload)

        result_payload = result.to_dict()
        result_payload["metadata"] = {"provider_payload": "must not be durable"}
        with self.assertRaisesRegex(ContractValidationError, "provider_payload"):
            ContextReductionResult.from_dict(result_payload)

    def test_completed_reduction_result_requires_state_output_refs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "state output"):
            ContextReductionResult(
                reduction_id="reduce1",
                status=ContextReductionStatus.COMPLETED,
                request_ref="kernel/demo/context/reduction_request.json",
                permission_manifest_ref="kernel/demo/permission_manifest.json",
            )

    def test_repeated_read_diagnostics_use_query_hash_not_raw_query(self) -> None:
        observation = ContextReadObservation(
            observation_id="read1",
            source_ref="sources/a.json",
            source_hash=HASH1,
            source_range={"offset": 0, "limit": 100},
            query_ref="queries/q1.json",
            query_hash=HASH2,
            tool_name="academic_search",
            count=3,
            normalized_metadata={"provider": "academic"},
        )

        diagnostics = build_thrash_diagnostics(
            diagnostics_id="thrash1",
            phase_label="evidence",
            observations=[observation],
            repeat_threshold=2,
        )
        payload = diagnostics.to_dict()

        self.assertEqual(diagnostics.repeated_observation_ids, ["read1"])
        self.assertEqual(ContextThrashDiagnostics.from_dict(payload).recommended_action.value, "prepare_checkpoint")
        self.assertNotIn("raw_query", str(payload))

        with self.assertRaisesRegex(ContractValidationError, "raw query"):
            ContextReadObservation(
                observation_id="badread",
                source_ref="sources/a.json",
                normalized_metadata={"query": "raw user text"},
            )

    def test_compile_context_request_blocks_denied_required_source(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-context",
                "readable_refs": ["contract"],
                "denied_refs": ["contract/secret.json"],
            }
        )
        request = ContextCompileRequest(
            request_id="compile1",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=HASH1,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            context_sources=[
                ContextSource(
                    source_key="authority/secret",
                    kind=ContextSourceKind.AUTHORITY,
                    source_refs=["contract/secret.json"],
                    source_hashes={"contract/secret.json": HASH2},
                    cache_policy=ContextCachePolicy.STABLE,
                    inline_policy=ContextInlinePolicy.REF_ONLY,
                    required=True,
                )
            ],
        )

        compiled = compile_context_request(
            request=request,
            read_gate=ReadGate(manifest),
            view_ref="kernel/demo/context_view.json",
            pressure_ref="kernel/demo/context/pressure.json",
            cache_layout_ref="kernel/demo/context/cache_layout.json",
            result_id="compile1",
            layout_id="layout1",
        )

        self.assertEqual(compiled.result.action, ContextCompileAction.BLOCKED_BY_DENIED_REQUIRED_SOURCE)
        self.assertEqual(compiled.result.denied_source_refs, ["contract/secret.json"])
        self.assertEqual(compiled.view.omitted_segments, [])
        self.assertEqual(compiled.result.omitted_refs, [])

    def test_compile_context_request_blocks_unavailable_required_source(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-context",
                "readable_refs": ["contract", "context"],
            }
        )
        request = ContextCompileRequest(
            request_id="compile1",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=HASH1,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            context_sources=[
                ContextSource(
                    source_key="working_set/active",
                    kind=ContextSourceKind.WORKING_SET,
                    source_refs=["context/working_set.json"],
                    cache_policy=ContextCachePolicy.SEMI_STABLE,
                    inline_policy=ContextInlinePolicy.REF_ONLY,
                    required=True,
                    metadata={"unavailable": True, "reason_code": "working_set_unavailable"},
                )
            ],
            working_set_ref="context/working_set.json",
        )

        compiled = compile_context_request(
            request=request,
            read_gate=ReadGate(manifest),
            view_ref="kernel/demo/context_view.json",
            pressure_ref="kernel/demo/context/pressure.json",
            cache_layout_ref="kernel/demo/context/cache_layout.json",
            result_id="compile1",
            layout_id="layout1",
        )

        self.assertEqual(compiled.result.action, ContextCompileAction.BLOCKED_BY_UNAVAILABLE_AUTHORITY)
        self.assertEqual(compiled.result.working_set_ref, "context/working_set.json")
        self.assertEqual(compiled.result.metadata["unavailable_required_source_keys"], ["working_set/active"])

    def test_compile_context_request_turns_hard_pressure_into_checkpoint_action(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-context",
                "readable_refs": ["contract"],
            }
        )
        request = ContextCompileRequest(
            request_id="compile1",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=HASH1,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            context_sources=[
                ContextSource(
                    source_key="authority/contract",
                    kind=ContextSourceKind.AUTHORITY,
                    source_refs=["contract/task_contract.json"],
                    source_hashes={"contract/task_contract.json": HASH1},
                    cache_policy=ContextCachePolicy.STABLE,
                    inline_policy=ContextInlinePolicy.REF_ONLY,
                    required=True,
                    token_estimate=90,
                )
            ],
            token_budget=100,
        )

        compiled = compile_context_request(
            request=request,
            read_gate=ReadGate(manifest),
            view_ref="kernel/demo/context_view.json",
            pressure_ref="kernel/demo/context/pressure.json",
            cache_layout_ref="kernel/demo/context/cache_layout.json",
            result_id="compile1",
            layout_id="layout1",
        )

        self.assertEqual(compiled.result.action, ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN)
        self.assertEqual(compiled.pressure.recommended_action.value, "checkpoint_before_next_turn")
        self.assertEqual(compiled.result.pressure_ref, "kernel/demo/context/pressure.json")

    def test_reconcile_context_epoch_preserves_compatible_stable_baseline(self) -> None:
        manifest = PermissionManifest.from_dict(
            {
                "manifest_id": "perm-context",
                "readable_refs": ["contract", "sources"],
            }
        )
        request1 = ContextCompileRequest(
            request_id="compile1",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=HASH1,
            permission_manifest_ref="kernel/demo/permission_manifest.json",
            context_sources=[
                ContextSource(
                    source_key="authority/contract",
                    kind=ContextSourceKind.AUTHORITY,
                    source_refs=["contract/task_contract.json"],
                    source_hashes={"contract/task_contract.json": HASH1},
                    cache_policy=ContextCachePolicy.STABLE,
                    inline_policy=ContextInlinePolicy.REF_ONLY,
                    required=True,
                    priority=100,
                ),
                ContextSource(
                    source_key="inputs/source_a",
                    kind=ContextSourceKind.PRODUCT_STATE,
                    source_refs=["sources/a.json"],
                    source_hashes={"sources/a.json": HASH2},
                    cache_policy=ContextCachePolicy.VOLATILE,
                    inline_policy=ContextInlinePolicy.REF_ONLY,
                    required=True,
                    priority=50,
                ),
            ],
        )
        request2 = ContextCompileRequest.from_dict(
            {
                **request1.to_dict(),
                "request_id": "compile2",
                "context_sources": [
                    request1.context_sources[0].to_dict(),
                    {
                        **request1.context_sources[1].to_dict(),
                        "source_refs": ["sources/b.json"],
                        "source_hashes": {"sources/b.json": HASH3},
                    },
                ],
            }
        )
        compiled1 = compile_context_request(
            request=request1,
            read_gate=ReadGate(manifest),
            view_ref="kernel/demo/context_view1.json",
            pressure_ref="kernel/demo/context/pressure1.json",
            cache_layout_ref="kernel/demo/context/cache_layout1.json",
            result_id="compile1",
            layout_id="layout1",
        )
        epoch1 = reconcile_context_epoch(
            epoch_id="epoch1",
            request=request1,
            view=compiled1.view,
            baseline_ref="kernel/demo/context/baseline1.json",
            source_snapshot_ref="kernel/demo/context/source_snapshot1.json",
        )
        compiled2 = compile_context_request(
            request=request2,
            read_gate=ReadGate(manifest),
            view_ref="kernel/demo/context_view2.json",
            pressure_ref="kernel/demo/context/pressure2.json",
            cache_layout_ref="kernel/demo/context/cache_layout2.json",
            result_id="compile2",
            layout_id="layout2",
        )
        epoch2 = reconcile_context_epoch(
            epoch_id="epoch2",
            request=request2,
            view=compiled2.view,
            baseline_ref="kernel/demo/context/baseline2.json",
            source_snapshot_ref="kernel/demo/context/source_snapshot2.json",
            previous_epoch=epoch1,
        )

        self.assertEqual(epoch2, epoch1)
        self.assertEqual(compiled1.cache_layout.stable_strata_hash, compiled2.cache_layout.stable_strata_hash)
        self.assertNotEqual(compiled1.cache_layout.volatile_strata_hash, compiled2.cache_layout.volatile_strata_hash)


def _view_with_visible_refs(visible_refs: list[str]) -> ContextView:
    return build_call_context_view(
        view_id="ctx1",
        role="executor_piworker",
        contract_ref="contract/task_contract.json",
        contract_hash=HASH1,
        permission_manifest_ref="kernel/demo/permission_manifest.json",
        visible_refs=["contract/task_contract.json", *visible_refs],
        expected_output_refs=["reports/final_report.md"],
    )


if __name__ == "__main__":
    unittest.main()

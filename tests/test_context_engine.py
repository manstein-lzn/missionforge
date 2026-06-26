from __future__ import annotations

import unittest

from missionforge import (
    ContextCachePolicy,
    ContextCompactionRecord,
    ContextCompactionStatus,
    ContextCompileAction,
    ContextCompileResult,
    ContextEpoch,
    ContextInlinePolicy,
    ContextReadObservation,
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
    filter_context_sources,
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

    def test_epoch_turn_compile_and_compaction_records_are_refs_only(self) -> None:
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
        self.assertEqual(ContextCompactionRecord.from_dict(compaction.to_dict()).status, ContextCompactionStatus.ENDED)
        self.assertNotIn("provider_message", str(compaction.to_dict()))

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

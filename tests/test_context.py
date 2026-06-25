from __future__ import annotations

import unittest

from missionforge import (
    ContextCachePolicy,
    ContextInlinePolicy,
    ContextPressureAction,
    ContextPressureDiagnostics,
    ContextReplayPlan,
    ContextSegment,
    ContextSegmentKind,
    ContextView,
    ContractValidationError,
    ToolObservation,
    ToolObservationInlinePolicy,
    ToolObservationStatus,
    build_call_context_view,
    build_context_pressure_diagnostics,
    build_context_replay_plan,
)


CONTRACT_HASH = "sha256:" + "1" * 64


class ContextTests(unittest.TestCase):
    def test_context_view_is_refs_only_and_hash_checked(self) -> None:
        view = build_call_context_view(
            view_id="researcher_context",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=CONTRACT_HASH,
            permission_manifest_ref="kernel/demo/steps/researcher/permission_manifest.json",
            visible_refs=[
                "contract/task_contract.json",
                "sources/source_packet.json",
                "reports/source_gaps.md",
            ],
            expected_output_refs=["reports/final_report.md"],
            evidence_refs=["sources/source_packet.json"],
            diagnostics_ref="kernel/demo/steps/researcher/context_projection.json",
        )

        payload = view.to_dict()
        round_trip = ContextView.from_dict(payload)

        self.assertEqual(round_trip.context_hash, payload["context_hash"])
        self.assertEqual([segment["segment_id"] for segment in payload["stable_prefix"]], [
            "authority_contract",
            "authority_permission_manifest",
        ])
        self.assertEqual(payload["stable_prefix"][0]["inline_policy"], "ref_only")
        self.assertEqual(payload["volatile_tail"][0]["source_refs"], [
            "sources/source_packet.json",
            "reports/source_gaps.md",
        ])
        self.assertEqual(payload["omitted_segments"][0]["inline_policy"], "omitted")
        self.assertNotIn("prompt", str(payload).lower())
        self.assertNotIn("raw_body", str(payload).lower())

        payload["volatile_tail"][0]["source_refs"].append("reports/after_hash.md")
        with self.assertRaisesRegex(ContractValidationError, "context_hash"):
            ContextView.from_dict(payload)

    def test_context_segment_rejects_raw_body_metadata(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "body"):
            ContextSegment(
                segment_id="bad_segment",
                kind=ContextSegmentKind.ARTIFACT_PREVIEW,
                source_refs=["reports/final_report.md"],
                metadata={"body": "raw text must not be embedded"},
            )

    def test_context_buckets_enforce_cache_policy(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "cache policy"):
            ContextView(
                view_id="bad_context",
                role="executor_piworker",
                contract_ref="contract/task_contract.json",
                contract_hash=CONTRACT_HASH,
                permission_manifest_ref="kernel/demo/steps/researcher/permission_manifest.json",
                stable_prefix=[
                    ContextSegment(
                        segment_id="volatile_in_prefix",
                        kind=ContextSegmentKind.ARTIFACT_REF,
                        source_refs=["reports/final_report.md"],
                        cache_policy=ContextCachePolicy.VOLATILE,
                    )
                ],
            )

    def test_inline_segments_require_body_ref_not_body_payload(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "body_ref"):
            ContextSegment(
                segment_id="inline_missing_ref",
                kind=ContextSegmentKind.INSTRUCTION,
                source_refs=["manuals/researcher.md"],
                cache_policy=ContextCachePolicy.STABLE,
                inline_policy=ContextInlinePolicy.INLINE,
            )

        segment = ContextSegment(
            segment_id="inline_with_ref",
            kind=ContextSegmentKind.INSTRUCTION,
            source_refs=["manuals/researcher.md"],
            cache_policy=ContextCachePolicy.STABLE,
            inline_policy=ContextInlinePolicy.INLINE,
            body_ref="manuals/researcher.md",
        )

        self.assertEqual(segment.to_dict()["body_ref"], "manuals/researcher.md")

    def test_tool_observation_is_metadata_only_and_converts_to_segment(self) -> None:
        observation = ToolObservation(
            observation_id="tool_observation_000001",
            call_id="researcher-call",
            turn_index=4,
            tool_call_id="call_abc",
            tool_name="read",
            status=ToolObservationStatus.OK,
            content_hash="sha256:" + "2" * 64,
            content_bytes=128000,
            content_lines=2500,
            inline_policy=ToolObservationInlinePolicy.DEMOTE_AFTER_TURN,
            raw_ref="attempts/researcher/raw/000001-read-output.txt",
            source_ref="sources/source_packet.json",
            source_range={"offset": 0, "limit": 4096},
            source_hash="sha256:" + "3" * 64,
            source_bytes=128000,
        )

        payload = observation.to_dict()
        round_trip = ToolObservation.from_dict(payload)
        segment = round_trip.to_segment()

        self.assertEqual(round_trip.content_bytes, 128000)
        self.assertEqual(segment.kind, ContextSegmentKind.TOOL_OBSERVATION)
        self.assertEqual(segment.inline_policy, ContextInlinePolicy.OMITTED)
        self.assertEqual(segment.source_refs, ["sources/source_packet.json", "attempts/researcher/raw/000001-read-output.txt"])
        self.assertNotIn("raw_body", str(payload).lower())
        self.assertNotIn("stdout", str(payload).lower())

    def test_tool_observation_rejects_raw_payload_fields(self) -> None:
        payload = {
            "schema_version": "missionforge.pi_agent_tool_observation.v1",
            "observation_id": "tool_observation_000001",
            "call_id": "researcher-call",
            "turn_index": 1,
            "tool_call_id": "call_abc",
            "tool_name": "bash",
            "status": "ok",
            "content_hash": "sha256:" + "2" * 64,
            "content_bytes": 16,
            "content_lines": 1,
            "inline_policy": "keep",
            "stdout": "raw output must not appear here",
        }

        with self.assertRaisesRegex(ContractValidationError, "stdout"):
            ToolObservation.from_dict(payload)

    def test_context_pressure_diagnostics_never_route_semantics(self) -> None:
        view = build_call_context_view(
            view_id="researcher_context",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=CONTRACT_HASH,
            permission_manifest_ref="kernel/demo/steps/researcher/permission_manifest.json",
            visible_refs=["contract/task_contract.json", "sources/source_packet.json"],
            expected_output_refs=["reports/final_report.md"],
            token_budget=1000,
            diagnostics_ref="kernel/demo/steps/researcher/context_projection.json",
        )

        diagnostics = build_context_pressure_diagnostics(
            view_ref="kernel/demo/steps/researcher/context_projection.json",
            view=view,
            estimated_input_tokens=925,
            checkpoint_ref="kernel/demo/steps/researcher/context_checkpoint.json",
        )
        payload = diagnostics.to_dict()

        self.assertEqual(diagnostics.recommended_action, ContextPressureAction.CHECKPOINT_BEFORE_NEXT_TURN)
        self.assertEqual(ContextPressureDiagnostics.from_dict(payload), diagnostics)
        self.assertEqual(payload["context_hash"], view.context_hash)
        self.assertNotIn("accepted", str(payload))
        self.assertNotIn("rejected", str(payload))

    def test_context_replay_plan_is_refs_only_and_hash_checked(self) -> None:
        view = build_call_context_view(
            view_id="researcher_context",
            role="executor_piworker",
            contract_ref="contract/task_contract.json",
            contract_hash=CONTRACT_HASH,
            permission_manifest_ref="kernel/demo/steps/researcher/permission_manifest.json",
            visible_refs=["contract/task_contract.json", "sources/source_packet.json"],
            expected_output_refs=["reports/final_report.md"],
            diagnostics_ref="kernel/demo/steps/researcher/context_projection.json",
        )
        plan = build_context_replay_plan(
            plan_id="replay_plan_001",
            view_ref="kernel/demo/steps/researcher/context_projection.json",
            checkpoint_ref="attempts/WU-000001/context/context_pressure_checkpoint.json",
            view=view,
            source_refs=["context/raw/000001-bash-output.txt"],
            summary_refs=["reports/context_summary.json"],
            denied_source_refs=["context/raw/000002-secret.txt"],
        )

        payload = plan.to_dict()
        round_trip = ContextReplayPlan.from_dict(payload)

        self.assertEqual(round_trip.context_hash, view.context_hash)
        self.assertIn("context/raw/000001-bash-output.txt", payload["source_refs"])
        self.assertNotIn("context/raw/000002-secret.txt", payload["allowed_source_refs"])
        self.assertEqual(payload["checkpoint_ref"], "attempts/WU-000001/context/context_pressure_checkpoint.json")
        self.assertNotIn("prompt", str(payload).lower())
        self.assertNotIn("raw_body", str(payload).lower())


if __name__ == "__main__":
    unittest.main()

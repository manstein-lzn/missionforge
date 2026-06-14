from __future__ import annotations

import unittest

from missionforge.context_summary import (
    CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION,
    ContextSummaryArtifact,
    ContextSummaryKind,
    ContextSummarySource,
)
from missionforge.contracts import ContractValidationError
from missionforge.piworker_call import PiWorkerCallRole


HASH_A = "sha256:" + "a" * 64


def summary_payload() -> dict[str, object]:
    return {
        "schema_version": CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION,
        "summary_id": "summary-001",
        "call_id": "WU-000001",
        "role": "executor_piworker",
        "kind": "working_knowledge",
        "summary_text": "The large log shows initialization completed before the failure.",
        "permission_manifest_ref": "attempts/WU-000001/runtime_permission_manifest.json",
        "created_by": "executor_piworker",
        "sources": [
            {
                "source_id": "source-001",
                "observation_id": "tool-observation-000001",
                "ref": "attempts/WU-000001/context/raw/000001-bash-output.txt",
                "content_hash": HASH_A,
                "source_role": "executor_piworker",
                "permission_manifest_ref": "attempts/WU-000001/runtime_permission_manifest.json",
                "range_hint": "lines=1-80",
                "metadata": {"context_projection_ref": "attempts/WU-000001/context/projection.json"},
            }
        ],
        "metadata": {"context_observations_ref": "attempts/WU-000001/context/tool_observations.jsonl"},
    }


class ContextSummaryArtifactTests(unittest.TestCase):
    def test_context_summary_artifact_round_trips_with_explicit_sources(self) -> None:
        artifact = ContextSummaryArtifact.from_dict(summary_payload())

        self.assertEqual(artifact.schema_version, CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(artifact.role, PiWorkerCallRole.EXECUTOR)
        self.assertEqual(artifact.kind, ContextSummaryKind.WORKING_KNOWLEDGE)
        self.assertEqual(artifact.sources[0].observation_id, "tool-observation-000001")
        self.assertEqual(artifact.sources[0].content_hash, HASH_A)
        self.assertEqual(artifact.to_dict()["sources"][0]["source_role"], "executor_piworker")

    def test_context_summary_artifact_rejects_hidden_raw_bodies(self) -> None:
        payload = summary_payload()
        payload["raw_body"] = "large raw content should stay behind refs"

        with self.assertRaisesRegex(ContractValidationError, "raw_body is not allowed"):
            ContextSummaryArtifact.from_dict(payload)

    def test_context_summary_artifact_requires_sources(self) -> None:
        payload = summary_payload()
        payload["sources"] = []

        with self.assertRaisesRegex(ContractValidationError, "sources must not be empty"):
            ContextSummaryArtifact.from_dict(payload)

    def test_context_summary_source_validates_refs_and_hashes(self) -> None:
        bad_ref = summary_payload()
        bad_ref["sources"][0]["ref"] = "../escape.txt"  # type: ignore[index]
        with self.assertRaisesRegex(ContractValidationError, "safe relative|parent segments"):
            ContextSummaryArtifact.from_dict(bad_ref)

        bad_hash = summary_payload()
        bad_hash["sources"][0]["content_hash"] = "sha256:" + "A" * 64  # type: ignore[index]
        with self.assertRaisesRegex(ContractValidationError, "lowercase sha256"):
            ContextSummaryArtifact.from_dict(bad_hash)

    def test_context_summary_source_can_be_validated_standalone(self) -> None:
        source = ContextSummarySource.from_dict(summary_payload()["sources"][0])  # type: ignore[index]

        self.assertEqual(source.source_role, PiWorkerCallRole.EXECUTOR)
        self.assertEqual(source.to_dict()["permission_manifest_ref"], "attempts/WU-000001/runtime_permission_manifest.json")


if __name__ == "__main__":
    unittest.main()

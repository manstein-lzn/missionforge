from __future__ import annotations

import unittest

from missionforge import (
    ContractValidationError,
    ToolOutputProjection,
    ToolOutputProjectionPolicy,
    bound_tool_output,
)


HASH1 = "sha256:" + "1" * 64


class ToolProjectionTests(unittest.TestCase):
    def test_small_tool_output_remains_keep_projection(self) -> None:
        result = bound_tool_output(
            projection_id="projection1",
            tool_observation_id="obs1",
            text="short result",
            projection_ref="context/projections/obs1.txt",
            permission_manifest_ref="kernel/demo/permission_manifest.json",
        )

        self.assertEqual(result.text, "short result")
        self.assertEqual(result.projection.policy, ToolOutputProjectionPolicy.KEEP)
        self.assertEqual(ToolOutputProjection.from_dict(result.projection.to_dict()).projection_id, "projection1")

    def test_large_tool_output_becomes_bounded_preview_with_raw_ref(self) -> None:
        result = bound_tool_output(
            projection_id="projection1",
            tool_observation_id="obs1",
            text="0123456789" * 100,
            projection_ref="context/projections/obs1.txt",
            raw_ref="context/raw/obs1.txt",
            max_chars=120,
        )

        self.assertEqual(result.projection.policy, ToolOutputProjectionPolicy.BOUNDED_PREVIEW)
        self.assertLessEqual(len(result.text), 120)
        self.assertIn("full content ref: context/raw/obs1.txt", result.text)
        self.assertEqual(result.projection.raw_ref, "context/raw/obs1.txt")

    def test_projection_record_rejects_raw_body_metadata(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "body"):
            ToolOutputProjection(
                projection_id="projection1",
                tool_observation_id="obs1",
                policy=ToolOutputProjectionPolicy.KEEP,
                projection_ref="context/projections/obs1.txt",
                projection_hash=HASH1,
                projection_bytes=1,
                original_bytes=1,
                metadata={"raw_body": "must not persist"},
            )

    def test_bounded_policy_requires_raw_ref(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "require raw_ref"):
            ToolOutputProjection(
                projection_id="projection1",
                tool_observation_id="obs1",
                policy=ToolOutputProjectionPolicy.BOUNDED_PREVIEW,
                projection_ref="context/projections/obs1.txt",
                projection_hash=HASH1,
                projection_bytes=1,
                original_bytes=10,
            )


if __name__ == "__main__":
    unittest.main()

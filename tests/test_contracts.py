from __future__ import annotations

import math
import unittest

from missionforge.contracts import (
    AdaptiveDecision,
    ContractValidationError,
    EvidenceTrustLevel,
    Ref,
    ValidatorMode,
    require_enum,
    stable_json_hash,
    validate_ref,
)


class ContractPrimitiveTests(unittest.TestCase):
    def test_validate_ref_accepts_safe_relative_refs(self) -> None:
        self.assertEqual(validate_ref("package/SKILL.md"), "package/SKILL.md")
        self.assertEqual(validate_ref("attempts/001/report.json"), "attempts/001/report.json")

    def test_validate_ref_rejects_unsafe_refs(self) -> None:
        for ref in ["", "/tmp/out", "../secret", "package/../secret", "a//b", "C:/tmp/out", "http://x"]:
            with self.subTest(ref=ref):
                with self.assertRaises(ContractValidationError):
                    validate_ref(ref)

    def test_stable_json_hash_ignores_dict_key_order(self) -> None:
        left = {"b": [2, {"z": "last", "a": "first"}], "a": 1}
        right = {"a": 1, "b": [2, {"a": "first", "z": "last"}]}

        self.assertEqual(stable_json_hash(left), stable_json_hash(right))
        self.assertTrue(stable_json_hash(left).startswith("sha256:"))

    def test_stable_json_hash_rejects_nan(self) -> None:
        with self.assertRaises(ContractValidationError):
            stable_json_hash({"metric": math.nan})

    def test_require_enum_fails_closed(self) -> None:
        self.assertEqual(require_enum("repair", AdaptiveDecision, "decision"), AdaptiveDecision.REPAIR)
        with self.assertRaises(ContractValidationError):
            require_enum("done", AdaptiveDecision, "decision")

    def test_ref_round_trip(self) -> None:
        ref = Ref.from_dict({"value": "evidence/result.json"})

        self.assertEqual(ref.value, "evidence/result.json")
        self.assertEqual(Ref.from_dict(ref.to_dict()), ref)

    def test_public_enums_keep_expected_wire_values(self) -> None:
        self.assertEqual(EvidenceTrustLevel.UNTRUSTED_WORKER_CLAIM.value, "untrusted_worker_claim")
        self.assertEqual(ValidatorMode.EXECUTABLE.value, "executable")


if __name__ == "__main__":
    unittest.main()

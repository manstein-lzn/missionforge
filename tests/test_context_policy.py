from __future__ import annotations

import unittest

from missionforge import ContextManagementPolicy, ContractValidationError


class ContextManagementPolicyTests(unittest.TestCase):
    def test_default_policy_round_trips_with_stable_hash(self) -> None:
        policy = ContextManagementPolicy.default()
        payload = policy.to_dict()

        round_trip = ContextManagementPolicy.from_dict(payload)

        self.assertEqual(round_trip.to_dict(), payload)
        self.assertEqual(round_trip.policy_hash, payload["policy_hash"])
        self.assertTrue(round_trip.reducer_enabled)
        self.assertTrue(round_trip.reducer_on_hard_pressure)

    def test_policy_rejects_raw_context_metadata(self) -> None:
        payload = ContextManagementPolicy.default().to_dict()
        payload["metadata"] = {"raw_prompt": "must not be durable"}

        with self.assertRaisesRegex(ContractValidationError, "raw_prompt"):
            ContextManagementPolicy.from_dict(payload)

    def test_soft_pressure_ratio_must_not_exceed_hard_ratio(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "soft ratio"):
            ContextManagementPolicy(soft_pressure_ratio=0.95, hard_pressure_ratio=0.80)

    def test_working_set_entry_cap_must_not_exceed_working_set_cap(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "entry cap"):
            ContextManagementPolicy(working_set_token_cap=100, working_set_entry_token_cap=101)


if __name__ == "__main__":
    unittest.main()

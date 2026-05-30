from __future__ import annotations

import unittest

from missionforge import ContractValidationError
from missionforge.benchmark import BenchmarkPricingTable, ModelTokenPrice, project_benchmark_cost


class BenchmarkPricingTests(unittest.TestCase):
    def test_pricing_table_round_trips_and_estimates_token_mix(self) -> None:
        table = sample_pricing_table()

        self.assertEqual(BenchmarkPricingTable.from_dict(table.to_dict()), table)

        cost = project_benchmark_cost(
            {
                "model": "pi-test-model",
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_read_tokens": 3000,
                "cache_write_tokens": 400,
                "provider_reported_cost_usd": 0.0,
            },
            pricing_table=table,
        )

        self.assertEqual(cost.cost_source, "pricing_table")
        self.assertEqual(cost.pricing_table_id, "pi-test-2026-05-30")
        self.assertEqual(cost.provider_reported_cost_usd, 0.0)
        self.assertAlmostEqual(cost.estimated_cost_usd, 0.0041)

    def test_provider_reported_cost_is_not_labeled_as_pricing_table_cost(self) -> None:
        cost = project_benchmark_cost({"provider_reported_cost_usd": 0.42})

        self.assertEqual(cost.estimated_cost_usd, 0.42)
        self.assertEqual(cost.provider_reported_cost_usd, 0.42)
        self.assertEqual(cost.cost_source, "provider_reported")
        self.assertEqual(cost.pricing_table_id, "")

    def test_missing_model_or_provider_cost_is_explicitly_unavailable(self) -> None:
        cost = project_benchmark_cost(
            {
                "input_tokens": 1000,
                "output_tokens": 200,
                "provider_reported_cost_usd": 0.0,
            },
            pricing_table=sample_pricing_table(),
        )

        self.assertEqual(cost.estimated_cost_usd, 0.0)
        self.assertEqual(cost.provider_reported_cost_usd, 0.0)
        self.assertEqual(cost.cost_source, "unavailable")

    def test_pricing_table_rejects_raw_or_unsafe_shape(self) -> None:
        payload = sample_pricing_table().to_dict()
        payload["model_prices"]["pi-test-model"]["raw_payload"] = "secret"

        with self.assertRaisesRegex(ContractValidationError, "unknown field"):
            BenchmarkPricingTable.from_dict(payload)

        with self.assertRaisesRegex(ContractValidationError, "safe id"):
            BenchmarkPricingTable(
                pricing_table_id="../pi-test",
                model_prices={"pi-test-model": sample_pricing_table().model_prices["pi-test-model"]},
            ).validate()


def sample_pricing_table() -> BenchmarkPricingTable:
    return BenchmarkPricingTable(
        pricing_table_id="pi-test-2026-05-30",
        effective_date="2026-05-30",
        model_prices={
            "pi-test-model": ModelTokenPrice(
                model="pi-test-model",
                input_per_1m_tokens_usd=1.0,
                output_per_1m_tokens_usd=10.0,
                cache_read_per_1m_tokens_usd=0.1,
                cache_write_per_1m_tokens_usd=2.0,
            )
        },
    )


if __name__ == "__main__":
    unittest.main()

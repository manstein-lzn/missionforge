"""Versioned token pricing projection for benchmark summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    validate_ref,
)


BENCHMARK_PRICING_TABLE_SCHEMA_VERSION = "missionforge.benchmark_pricing_table.v1"
TOKENS_PER_MILLION = 1_000_000.0


@dataclass(frozen=True)
class ModelTokenPrice:
    """Per-million-token rates for one provider model."""

    model: str
    input_per_1m_tokens_usd: float
    output_per_1m_tokens_usd: float
    cache_read_per_1m_tokens_usd: float = 0.0
    cache_write_per_1m_tokens_usd: float = 0.0

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelTokenPrice":
        data = _strict_mapping(
            payload,
            "model_token_price",
            {
                "model",
                "input_per_1m_tokens_usd",
                "output_per_1m_tokens_usd",
                "cache_read_per_1m_tokens_usd",
                "cache_write_per_1m_tokens_usd",
            },
        )
        item = cls(
            model=require_non_empty_str(data.get("model"), "model_token_price.model"),
            input_per_1m_tokens_usd=_non_negative_number(
                data.get("input_per_1m_tokens_usd"),
                "model_token_price.input_per_1m_tokens_usd",
            ),
            output_per_1m_tokens_usd=_non_negative_number(
                data.get("output_per_1m_tokens_usd"),
                "model_token_price.output_per_1m_tokens_usd",
            ),
            cache_read_per_1m_tokens_usd=_non_negative_number(
                data.get("cache_read_per_1m_tokens_usd", 0.0),
                "model_token_price.cache_read_per_1m_tokens_usd",
            ),
            cache_write_per_1m_tokens_usd=_non_negative_number(
                data.get("cache_write_per_1m_tokens_usd", 0.0),
                "model_token_price.cache_write_per_1m_tokens_usd",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.model, "model_token_price.model")
        _non_negative_number(self.input_per_1m_tokens_usd, "model_token_price.input_per_1m_tokens_usd")
        _non_negative_number(self.output_per_1m_tokens_usd, "model_token_price.output_per_1m_tokens_usd")
        _non_negative_number(self.cache_read_per_1m_tokens_usd, "model_token_price.cache_read_per_1m_tokens_usd")
        _non_negative_number(self.cache_write_per_1m_tokens_usd, "model_token_price.cache_write_per_1m_tokens_usd")
        assert_refs_only_payload(self.to_dict_without_validation(), "model_token_price")

    def estimate_usd(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        for name, value in {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
        }.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContractValidationError(f"model_token_price.{name} must be an integer >= 0")
        amount = (
            input_tokens * self.input_per_1m_tokens_usd
            + output_tokens * self.output_per_1m_tokens_usd
            + cache_read_tokens * self.cache_read_per_1m_tokens_usd
            + cache_write_tokens * self.cache_write_per_1m_tokens_usd
        ) / TOKENS_PER_MILLION
        return round(amount, 12)

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input_per_1m_tokens_usd": self.input_per_1m_tokens_usd,
            "output_per_1m_tokens_usd": self.output_per_1m_tokens_usd,
            "cache_read_per_1m_tokens_usd": self.cache_read_per_1m_tokens_usd,
            "cache_write_per_1m_tokens_usd": self.cache_write_per_1m_tokens_usd,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkPricingTable:
    """Versioned pricing table used for deterministic benchmark cost estimates."""

    pricing_table_id: str
    model_prices: dict[str, ModelTokenPrice]
    currency: str = "USD"
    effective_date: str = ""
    schema_version: str = BENCHMARK_PRICING_TABLE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkPricingTable":
        data = _strict_mapping(
            payload,
            "benchmark_pricing_table",
            {"schema_version", "pricing_table_id", "currency", "effective_date", "model_prices"},
        )
        model_prices = {
            require_non_empty_str(model, "benchmark_pricing_table.model_prices.key"): ModelTokenPrice.from_dict(
                require_mapping(price, f"benchmark_pricing_table.model_prices.{model}")
            )
            for model, price in require_mapping(data.get("model_prices"), "benchmark_pricing_table.model_prices").items()
        }
        item = cls(
            pricing_table_id=_require_safe_id(data.get("pricing_table_id"), "benchmark_pricing_table.pricing_table_id"),
            currency=require_non_empty_str(data.get("currency", "USD"), "benchmark_pricing_table.currency"),
            effective_date=str(data.get("effective_date", "")),
            model_prices=model_prices,
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_PRICING_TABLE_SCHEMA_VERSION),
                "benchmark_pricing_table.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_PRICING_TABLE_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_pricing_table.schema_version is unsupported")
        _require_safe_id(self.pricing_table_id, "benchmark_pricing_table.pricing_table_id")
        if self.currency != "USD":
            raise ContractValidationError("benchmark_pricing_table.currency must be USD")
        if not self.model_prices:
            raise ContractValidationError("benchmark_pricing_table.model_prices must not be empty")
        for model, price in self.model_prices.items():
            require_non_empty_str(model, "benchmark_pricing_table.model_prices.key")
            price.validate()
            if price.model != model:
                raise ContractValidationError("model_token_price.model must match its model_prices key")
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_pricing_table")

    def price_for(self, model: str) -> ModelTokenPrice | None:
        return self.model_prices.get(model)

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pricing_table_id": self.pricing_table_id,
            "currency": self.currency,
            "effective_date": self.effective_date,
            "model_prices": {
                model: price.to_dict()
                for model, price in sorted(self.model_prices.items())
            },
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkCostProjection:
    """Computed cost fields for one benchmark summary."""

    estimated_cost_usd: float
    provider_reported_cost_usd: float
    cost_source: str
    pricing_table_id: str = ""


def project_benchmark_cost(
    metrics: Mapping[str, Any],
    *,
    pricing_table: BenchmarkPricingTable | None = None,
    model: str | None = None,
) -> BenchmarkCostProjection:
    """Project provider-reported or pricing-table cost without mixing sources."""

    provider_reported = _non_negative_metric_number(metrics, "provider_reported_cost_usd")
    if pricing_table is not None:
        pricing_table.validate()
        model_id = _metric_model(metrics) or model or ""
        if model_id:
            price = pricing_table.price_for(model_id)
            if price is not None:
                input_tokens = _non_negative_metric_int(metrics, "input_tokens")
                output_tokens = _non_negative_metric_int(metrics, "output_tokens")
                cache_read_tokens = _non_negative_metric_int(metrics, "cache_read_tokens")
                cache_write_tokens = _non_negative_metric_int(metrics, "cache_write_tokens")
                if input_tokens or output_tokens or cache_read_tokens or cache_write_tokens:
                    return BenchmarkCostProjection(
                        estimated_cost_usd=price.estimate_usd(
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_read_tokens=cache_read_tokens,
                            cache_write_tokens=cache_write_tokens,
                        ),
                        provider_reported_cost_usd=provider_reported,
                        cost_source="pricing_table",
                        pricing_table_id=pricing_table.pricing_table_id,
                    )
    if provider_reported > 0.0:
        return BenchmarkCostProjection(
            estimated_cost_usd=provider_reported,
            provider_reported_cost_usd=provider_reported,
            cost_source="provider_reported",
        )
    return BenchmarkCostProjection(
        estimated_cost_usd=0.0,
        provider_reported_cost_usd=provider_reported,
        cost_source="unavailable",
    )


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    return data


def _non_negative_number(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0.0:
        raise ContractValidationError(f"{field_name} must be a number >= 0")
    return float(value)


def _require_safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id")
    validate_ref(text, field_name)
    return text


def _metric_model(metrics: Mapping[str, Any]) -> str:
    value = metrics.get("model")
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _non_negative_metric_number(metrics: Mapping[str, Any], key: str) -> float:
    value = metrics.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0.0:
        return float(value)
    return 0.0


def _non_negative_metric_int(metrics: Mapping[str, Any], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


__all__ = [
    "BENCHMARK_PRICING_TABLE_SCHEMA_VERSION",
    "BenchmarkCostProjection",
    "BenchmarkPricingTable",
    "ModelTokenPrice",
    "project_benchmark_cost",
]

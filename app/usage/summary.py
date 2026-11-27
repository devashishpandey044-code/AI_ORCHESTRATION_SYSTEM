"""Turn stored model calls into a usage summary: volume, health, speed and estimated cost.

Pure maths over plain rows, so it is easy to test and needs no database. All money is whole
micro-dollars (1,000,000 micro-dollars = 1 dollar) and the percentage uses whole numbers only,
so there is no floating-point drift.
"""

import math
from collections import defaultdict
from dataclasses import dataclass


class UsageError(ValueError):
    """A stored call row is not something the product could have written."""


@dataclass(frozen=True)
class Price:
    """List price in micro-dollars per million tokens. Above tier_tokens of input, the whole
    request is billed at tier_multiplier times these rates."""

    input_rate: int
    output_rate: int
    tier_tokens: int
    tier_multiplier: int


# Prices as reported for 2026-11-27 ($0.10 and $0.50 per million tokens for prompts up to
# 100,000 tokens, five times that above it). They come from news reports, not from Anthropic's
# own page, so check them there before relying on a cost figure.
PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(
        input_rate=100_000, output_rate=500_000, tier_tokens=100_000, tier_multiplier=5
    ),
}


@dataclass(frozen=True)
class CallRow:
    purpose: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    success: bool
    attempts: int

    def __post_init__(self) -> None:
        for name in ("purpose", "model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise UsageError(f"{name} must be non-empty text")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise UsageError(f"{name} must be a whole number, 0 or more")
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise UsageError("attempts must be a whole number")
        if self.attempts < 1:
            raise UsageError("attempts must be at least 1")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)):
            raise UsageError("latency_ms must be a number")
        if not math.isfinite(self.latency_ms) or self.latency_ms < 0:
            raise UsageError("latency_ms must be a finite number, 0 or more")
        if not isinstance(self.success, bool):
            raise UsageError("success must be true or false")


@dataclass(frozen=True)
class GroupStats:
    key: str
    calls: int
    failures: int
    success_percent: int | None
    retries: int
    input_tokens: int
    output_tokens: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    cost_micro_usd: int  # covers only the calls that have a price
    unpriced_calls: int


@dataclass(frozen=True)
class UsageSummary:
    overall: GroupStats
    by_purpose: tuple[GroupStats, ...]
    by_model: tuple[GroupStats, ...]


def percent(part: int, whole: int) -> int | None:
    """Whole-number percent, rounded half up. None when there is nothing to divide by."""
    if whole == 0:
        return None
    return (200 * part + whole) // (2 * whole)


def nearest_rank(sorted_values: list[float], p: int) -> float | None:
    """Percentile by the nearest-rank method: the smallest value with at least p% at or below."""
    if not sorted_values:
        return None
    rank = max(1, (p * len(sorted_values) + 99) // 100)
    return sorted_values[rank - 1]


def cost_numerator(row: CallRow) -> int | None:
    """Tokens times rate, still in micro-dollars-times-million. None when the model has no price."""
    price = PRICES.get(row.model)
    if price is None:
        return None
    factor = price.tier_multiplier if row.input_tokens > price.tier_tokens else 1
    return factor * (row.input_tokens * price.input_rate + row.output_tokens * price.output_rate)


def _stats(key: str, rows: list[CallRow]) -> GroupStats:
    latencies = sorted(row.latency_ms for row in rows)
    numerators = [cost_numerator(row) for row in rows]
    priced = [n for n in numerators if n is not None]
    failures = sum(1 for row in rows if not row.success)
    return GroupStats(
        key=key,
        calls=len(rows),
        failures=failures,
        success_percent=percent(len(rows) - failures, len(rows)),
        retries=sum(row.attempts - 1 for row in rows),
        input_tokens=sum(row.input_tokens for row in rows),
        output_tokens=sum(row.output_tokens for row in rows),
        latency_p50_ms=nearest_rank(latencies, 50),
        latency_p95_ms=nearest_rank(latencies, 95),
        cost_micro_usd=(sum(priced) + 500_000) // 1_000_000,
        unpriced_calls=len(numerators) - len(priced),
    )


def _grouped(rows: list[CallRow], attribute: str) -> tuple[GroupStats, ...]:
    groups: dict[str, list[CallRow]] = defaultdict(list)
    for row in rows:
        groups[getattr(row, attribute)].append(row)
    return tuple(_stats(key, groups[key]) for key in sorted(groups))


def summarize(rows: list[CallRow]) -> UsageSummary:
    return UsageSummary(
        overall=_stats("all", rows),
        by_purpose=_grouped(rows, "purpose"),
        by_model=_grouped(rows, "model"),
    )

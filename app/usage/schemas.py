"""What the usage endpoint returns."""

from datetime import datetime

from pydantic import BaseModel

from app.usage.summary import GroupStats, UsageSummary

NOTE = (
    "Cost is an estimate from list prices, in micro-dollars (1,000,000 = 1 dollar). "
    "Calls to a model with no known price are counted in unpriced_calls and not costed."
)


class GroupOut(BaseModel):
    key: str
    calls: int
    failures: int
    success_percent: int | None
    retries: int
    input_tokens: int
    output_tokens: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    estimated_cost_micro_usd: int
    unpriced_calls: int


class UsageOut(BaseModel):
    days: int
    since: datetime
    overall: GroupOut
    by_purpose: list[GroupOut]
    by_model: list[GroupOut]
    note: str = NOTE


def _round_ms(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def to_group_out(stats: GroupStats) -> GroupOut:
    return GroupOut(
        key=stats.key,
        calls=stats.calls,
        failures=stats.failures,
        success_percent=stats.success_percent,
        retries=stats.retries,
        input_tokens=stats.input_tokens,
        output_tokens=stats.output_tokens,
        latency_p50_ms=_round_ms(stats.latency_p50_ms),
        latency_p95_ms=_round_ms(stats.latency_p95_ms),
        estimated_cost_micro_usd=stats.cost_micro_usd,
        unpriced_calls=stats.unpriced_calls,
    )


def to_usage_out(days: int, since: datetime, summary: UsageSummary) -> UsageOut:
    return UsageOut(
        days=days,
        since=since,
        overall=to_group_out(summary.overall),
        by_purpose=[to_group_out(g) for g in summary.by_purpose],
        by_model=[to_group_out(g) for g in summary.by_model],
    )

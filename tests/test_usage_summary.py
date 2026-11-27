import pytest

from app.usage import summary as module
from app.usage.summary import (
    CallRow,
    UsageError,
    cost_numerator,
    nearest_rank,
    percent,
    summarize,
)

HAIKU = "claude-haiku-5-5"


def row(**kw):
    base = dict(
        purpose="roadblocks",
        model=HAIKU,
        input_tokens=1000,
        output_tokens=500,
        latency_ms=100.0,
        success=True,
        attempts=1,
    )
    return CallRow(**(base | kw))


# --- percent and percentiles ---


@pytest.mark.parametrize(
    "part,whole,expected",
    [(0, 3, 0), (1, 3, 33), (2, 3, 67), (1, 2, 50), (1, 8, 13), (3, 8, 38), (5, 5, 100)],
)
def test_percent_rounds_half_up_with_whole_numbers(part, whole, expected):
    assert percent(part, whole) == expected


def test_percent_of_nothing_is_none():
    assert percent(0, 0) is None


def test_nearest_rank_known_values():
    values = [float(n) for n in range(1, 11)]  # 1..10
    assert nearest_rank(values, 50) == 5.0
    assert nearest_rank(values, 95) == 10.0
    assert nearest_rank([7.0], 50) == 7.0
    assert nearest_rank([7.0], 95) == 7.0
    assert nearest_rank([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert nearest_rank([], 50) is None


def test_p95_is_not_the_average():
    values = [10.0] * 19 + [5000.0]
    assert nearest_rank(values, 50) == 10.0
    assert nearest_rank(values, 95) == 10.0  # 19 of 20 are at or below 10
    assert nearest_rank(values + [5000.0], 95) == 5000.0


# --- cost ---


def test_cost_matches_a_hand_calculation():
    # 1000 input at $0.10/M plus 500 output at $0.50/M = $0.00035 = 350 micro-dollars
    assert cost_numerator(row()) == 350_000_000
    assert summarize([row()]).overall.cost_micro_usd == 350


def test_the_tier_applies_to_the_whole_request_above_the_threshold():
    big = row(input_tokens=150_000, output_tokens=1000)
    # 150,000 at $0.50/M plus 1,000 at $2.50/M = $0.0775
    assert summarize([big]).overall.cost_micro_usd == 77_500


def test_exactly_at_the_threshold_is_still_the_base_rate():
    at = row(input_tokens=100_000, output_tokens=0)
    assert summarize([at]).overall.cost_micro_usd == 10_000  # $0.01
    over = row(input_tokens=100_001, output_tokens=0)
    assert summarize([over]).overall.cost_micro_usd == 50_001  # 5x the base rate, rounded
    assert cost_numerator(over) == 5 * 100_001 * 100_000


def test_an_unknown_model_is_unpriced_and_counted_not_guessed():
    result = summarize([row(model="fake-1"), row()])
    assert result.overall.cost_micro_usd == 350
    assert result.overall.unpriced_calls == 1
    fake = next(g for g in result.by_model if g.key == "fake-1")
    assert fake.cost_micro_usd == 0 and fake.unpriced_calls == 1


def test_cost_is_rounded_once_not_per_call():
    # each call is 0.4 micro-dollars; ten calls are 4, not ten roundings to 0
    tiny = row(input_tokens=4, output_tokens=0)
    assert summarize([tiny] * 10).overall.cost_micro_usd == 4
    assert summarize([tiny]).overall.cost_micro_usd == 0


# --- health and volume ---


def test_success_failures_and_retries():
    rows = [row(), row(success=False, attempts=3), row(attempts=2), row()]
    overall = summarize(rows).overall
    assert overall.calls == 4
    assert overall.failures == 1
    assert overall.success_percent == 75
    assert overall.retries == 3  # 0 + 2 + 1 + 0


def test_tokens_are_summed():
    overall = summarize([row(), row(input_tokens=10, output_tokens=5)]).overall
    assert overall.input_tokens == 1010
    assert overall.output_tokens == 505


def test_latency_percentiles_in_a_summary():
    rows = [row(latency_ms=float(ms)) for ms in (10, 20, 30, 40, 1000)]
    overall = summarize(rows).overall
    assert overall.latency_p50_ms == 30.0
    assert overall.latency_p95_ms == 1000.0


def test_grouping_by_purpose_and_model_is_sorted_and_complete():
    rows = [
        row(purpose="onboarding"),
        row(purpose="roadblocks"),
        row(purpose="roadblocks", model="fake-1"),
    ]
    result = summarize(rows)
    assert [g.key for g in result.by_purpose] == ["onboarding", "roadblocks"]
    assert [g.key for g in result.by_model] == [HAIKU, "fake-1"]
    assert sum(g.calls for g in result.by_purpose) == result.overall.calls == 3
    assert sum(g.calls for g in result.by_model) == 3


def test_group_costs_do_not_exceed_the_total_by_more_than_rounding():
    rows = [row(purpose="a"), row(purpose="b"), row(purpose="c")]
    result = summarize(rows)
    total = sum(g.cost_micro_usd for g in result.by_purpose)
    assert abs(total - result.overall.cost_micro_usd) <= 2


def test_no_rows_gives_an_empty_honest_summary():
    result = summarize([])
    assert result.overall.calls == 0
    assert result.overall.success_percent is None
    assert result.overall.latency_p50_ms is None
    assert result.overall.cost_micro_usd == 0
    assert result.by_purpose == () and result.by_model == ()


def test_summary_is_the_same_whatever_order_rows_come_in():
    rows = [row(latency_ms=float(n), purpose=p) for n, p in enumerate("abcab", start=1)]
    assert summarize(rows) == summarize(list(reversed(rows)))


# --- rows that the product could not have written are refused ---


@pytest.mark.parametrize(
    "bad",
    [
        {"input_tokens": -1},
        {"output_tokens": -5},
        {"input_tokens": True},
        {"input_tokens": 1.5},
        {"attempts": 0},
        {"attempts": True},
        {"latency_ms": -1.0},
        {"latency_ms": float("nan")},
        {"latency_ms": float("inf")},
        {"latency_ms": "fast"},
        {"success": 1},
        {"purpose": " "},
        {"model": ""},
    ],
)
def test_corrupt_rows_are_refused(bad):
    with pytest.raises(UsageError):
        row(**bad)


def test_every_price_is_sane():
    for model, price in module.PRICES.items():
        assert model.strip()
        assert price.input_rate > 0 and price.output_rate > 0
        assert price.tier_tokens > 0 and price.tier_multiplier >= 1

from datetime import UTC, datetime

from app.usage.schemas import NOTE, to_usage_out
from app.usage.summary import CallRow, summarize

SINCE = datetime(2026, 11, 20, tzinfo=UTC)


def row(**kw):
    base = dict(
        purpose="roadblocks",
        model="claude-haiku-5-5",
        input_tokens=1000,
        output_tokens=500,
        latency_ms=100.04,
        success=True,
        attempts=1,
    )
    return CallRow(**(base | kw))


def test_the_summary_is_carried_across_unchanged_except_for_names_and_rounding():
    out = to_usage_out(7, SINCE, summarize([row(), row(success=False, attempts=2)]))
    assert out.days == 7 and out.since == SINCE
    assert out.overall.calls == 2
    assert out.overall.failures == 1
    assert out.overall.success_percent == 50
    assert out.overall.retries == 1
    assert out.overall.estimated_cost_micro_usd == 700
    assert out.overall.latency_p50_ms == 100.0  # 100.04 rounded to one decimal
    assert [g.key for g in out.by_purpose] == ["roadblocks"]
    assert [g.key for g in out.by_model] == ["claude-haiku-5-5"]


def test_an_empty_summary_has_nulls_not_zeros_for_what_cannot_be_known():
    out = to_usage_out(7, SINCE, summarize([]))
    assert out.overall.calls == 0
    assert out.overall.success_percent is None
    assert out.overall.latency_p50_ms is None
    assert out.overall.latency_p95_ms is None
    assert out.by_purpose == [] and out.by_model == []


def test_the_note_says_it_is_an_estimate():
    out = to_usage_out(7, SINCE, summarize([]))
    assert out.note == NOTE
    assert "estimate" in out.note
    assert "unpriced_calls" in out.note


def test_the_output_has_no_free_text_fields_beyond_keys_and_the_note():
    dumped = to_usage_out(7, SINCE, summarize([row()])).model_dump()
    assert set(dumped) == {"days", "since", "overall", "by_purpose", "by_model", "note"}
    assert "error" not in dumped["overall"]

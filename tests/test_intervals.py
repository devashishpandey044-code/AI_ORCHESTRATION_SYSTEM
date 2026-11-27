import pytest

from app.planning.intervals import (
    MINUTES_PER_DAY,
    Interval,
    IntervalError,
    find_conflicts,
    format_hhmm,
    free_slots,
    merge,
    parse_hhmm,
    subtract,
    total_minutes,
)

DAY = Interval(0, MINUTES_PER_DAY)


def test_interval_basics():
    item = Interval(60, 90)
    assert item.length == 30
    assert item.contains(Interval(60, 90))
    assert item.contains(Interval(70, 80))
    assert not item.contains(Interval(50, 80))


@pytest.mark.parametrize(
    "start,end",
    [(10, 10), (20, 10), (-1, 10), (0, 1441), (1440, 1440)],
)
def test_invalid_intervals_rejected(start, end):
    with pytest.raises(IntervalError):
        Interval(start, end)


@pytest.mark.parametrize("bad", [1.5, "10", None, True])
def test_non_integer_bounds_rejected(bad):
    with pytest.raises(IntervalError):
        Interval(bad, 100)
    with pytest.raises(IntervalError):
        Interval(0, bad)


def test_touching_intervals_do_not_overlap():
    assert not Interval(0, 60).overlaps(Interval(60, 120))
    assert not Interval(60, 120).overlaps(Interval(0, 60))
    assert Interval(0, 61).overlaps(Interval(60, 120))


def test_overlap_is_symmetric():
    a, b = Interval(10, 50), Interval(40, 90)
    assert a.overlaps(b) and b.overlaps(a)


def test_parse_and_format_roundtrip():
    for text in ["00:00", "07:30", "12:05", "23:59", "24:00"]:
        assert format_hhmm(parse_hhmm(text)) == text


@pytest.mark.parametrize(
    "bad", ["7:30", "07:60", "25:00", "24:01", "0730", "", "ab:cd", "07:30:00", None]
)
def test_parse_rejects_bad_text(bad):
    with pytest.raises(IntervalError):
        parse_hhmm(bad)


@pytest.mark.parametrize("bad", [-1, 1441, 1.5, True, None])
def test_format_rejects_bad_minutes(bad):
    with pytest.raises(IntervalError):
        format_hhmm(bad)


def test_merge_combines_overlapping_and_touching():
    result = merge([Interval(100, 200), Interval(0, 50), Interval(50, 80), Interval(150, 260)])
    assert result == [Interval(0, 80), Interval(100, 260)]


def test_merge_handles_contained_and_empty():
    assert merge([]) == []
    assert merge([Interval(0, 100), Interval(10, 20)]) == [Interval(0, 100)]


def test_merge_does_not_change_input():
    items = [Interval(50, 60), Interval(0, 10)]
    merge(items)
    assert items == [Interval(50, 60), Interval(0, 10)]


def test_subtract_basic():
    free = subtract(Interval(480, 1020), [Interval(600, 660), Interval(780, 840)])
    assert free == [Interval(480, 600), Interval(660, 780), Interval(840, 1020)]


def test_subtract_with_no_busy_returns_window():
    assert subtract(Interval(100, 200), []) == [Interval(100, 200)]


def test_subtract_busy_covers_window():
    assert subtract(Interval(100, 200), [Interval(0, 300)]) == []


def test_subtract_ignores_busy_outside_window():
    busy = [Interval(0, 50), Interval(300, 400)]
    assert subtract(Interval(100, 200), busy) == [Interval(100, 200)]


def test_subtract_busy_edges_clip_to_window():
    free = subtract(Interval(100, 200), [Interval(50, 120), Interval(180, 300)])
    assert free == [Interval(120, 180)]


def test_subtract_unsorted_overlapping_busy():
    free = subtract(DAY, [Interval(500, 700), Interval(100, 600), Interval(1000, 1100)])
    assert free == [Interval(0, 100), Interval(700, 1000), Interval(1100, 1440)]


def test_free_slots_filters_short_gaps():
    busy = [Interval(0, 100), Interval(130, 300)]
    assert free_slots(Interval(0, 400), busy, min_length=45) == [Interval(300, 400)]
    assert free_slots(Interval(0, 400), busy, min_length=30) == [
        Interval(100, 130),
        Interval(300, 400),
    ]


def test_free_slots_rejects_bad_min_length():
    with pytest.raises(IntervalError):
        free_slots(DAY, [], min_length=0)


def test_total_minutes_counts_overlap_once():
    assert total_minutes([Interval(0, 60), Interval(30, 90)]) == 90
    assert total_minutes([]) == 0


def test_find_conflicts():
    a, b, c = Interval(0, 60), Interval(30, 90), Interval(90, 120)
    assert find_conflicts([c, b, a]) == [(a, b)]
    assert find_conflicts([a, c]) == []


def test_free_plus_busy_partitions_the_window():
    """Property: free time and busy time inside a window add up to the window."""
    import random

    rng = random.Random(7)
    for _ in range(300):
        window_start = rng.randrange(0, 1000)
        window = Interval(window_start, rng.randrange(window_start + 1, 1441))
        busy = []
        for _ in range(rng.randrange(0, 8)):
            s = rng.randrange(0, 1439)
            busy.append(Interval(s, rng.randrange(s + 1, 1441)))
        free = subtract(window, busy)
        clipped = [
            Interval(max(b.start, window.start), min(b.end, window.end))
            for b in busy
            if b.overlaps(window)
        ]
        assert sum(f.length for f in free) + total_minutes(clipped) == window.length
        for gap in free:
            assert window.contains(gap)
            assert not any(gap.overlaps(b) for b in busy)

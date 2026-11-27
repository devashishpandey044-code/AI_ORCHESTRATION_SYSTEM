"""Time intervals for one day, in whole minutes after midnight.

Everything the scheduler does is built from three operations on these:
merge busy time, subtract it from a window, and list the free gaps.
Intervals are half open: [start, end). Two intervals that only touch
(one ends where the next starts) do not overlap.
"""
from __future__ import annotations

from dataclasses import dataclass

MINUTES_PER_DAY = 1440


class IntervalError(ValueError):
    """Raised for an invalid interval or time string."""


@dataclass(frozen=True, order=True)
class Interval:
    start: int
    end: int

    def __post_init__(self) -> None:
        for value in (self.start, self.end):
            if isinstance(value, bool) or not isinstance(value, int):
                raise IntervalError(f"interval bounds must be whole minutes, got {value!r}")
        if self.start < 0 or self.end > MINUTES_PER_DAY:
            raise IntervalError(f"interval {self.start}-{self.end} is outside the day (0-1440)")
        if self.start >= self.end:
            raise IntervalError(f"interval must end after it starts, got {self.start}-{self.end}")

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: Interval) -> bool:
        return self.start <= other.start and other.end <= self.end


def parse_hhmm(text: str) -> int:
    """'07:30' -> 450. Accepts 00:00 to 23:59, and '24:00' as the end of the day."""
    if not isinstance(text, str):
        raise IntervalError(f"time must be text like '07:30', got {text!r}")
    parts = text.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() and len(p) == 2 for p in parts):
        raise IntervalError(f"time must look like '07:30', got {text!r}")
    hours, minutes = int(parts[0]), int(parts[1])
    if minutes > 59:
        raise IntervalError(f"minutes must be 00-59, got {text!r}")
    total = hours * 60 + minutes
    if total > MINUTES_PER_DAY:
        raise IntervalError(f"time is past the end of the day: {text!r}")
    return total


def format_hhmm(minutes: int) -> str:
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise IntervalError(f"minutes must be a whole number, got {minutes!r}")
    if minutes < 0 or minutes > MINUTES_PER_DAY:
        raise IntervalError(f"minutes must be 0-1440, got {minutes}")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def merge(intervals: list[Interval]) -> list[Interval]:
    """Sort and combine intervals that overlap or touch."""
    merged: list[Interval] = []
    for item in sorted(intervals):
        if merged and item.start <= merged[-1].end:
            if item.end > merged[-1].end:
                merged[-1] = Interval(merged[-1].start, item.end)
        else:
            merged.append(item)
    return merged


def subtract(window: Interval, busy: list[Interval]) -> list[Interval]:
    """The parts of `window` not covered by any busy interval."""
    free: list[Interval] = []
    cursor = window.start
    for block in merge(busy):
        if block.end <= window.start:
            continue
        if block.start >= window.end:
            break
        if block.start > cursor:
            free.append(Interval(cursor, block.start))
        cursor = max(cursor, block.end)
    if cursor < window.end:
        free.append(Interval(cursor, window.end))
    return free


def free_slots(window: Interval, busy: list[Interval], min_length: int = 1) -> list[Interval]:
    """Free gaps inside `window` that are at least `min_length` minutes long."""
    if min_length < 1:
        raise IntervalError("min_length must be at least 1 minute")
    return [gap for gap in subtract(window, busy) if gap.length >= min_length]


def total_minutes(intervals: list[Interval]) -> int:
    """Minutes covered, counting overlapping time once."""
    return sum(item.length for item in merge(intervals))


def find_conflicts(intervals: list[Interval]) -> list[tuple[Interval, Interval]]:
    """Every pair that overlaps (touching is fine). Used by the validator later."""
    ordered = sorted(intervals)
    pairs: list[tuple[Interval, Interval]] = []
    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            if second.start >= first.end:
                break
            pairs.append((first, second))
    return pairs

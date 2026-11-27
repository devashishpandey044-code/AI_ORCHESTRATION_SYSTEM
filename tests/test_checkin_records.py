import random

import pytest

from app.checkins.records import (
    CheckinRows,
    OutcomeRow,
    StoredCheckinCorrupt,
    checkin_to_rows,
    rows_to_checkin,
)
from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED


def sample():
    return Checkin(
        (
            TaskOutcome("b", P, 20, BlockReason.INTERRUPTED),
            TaskOutcome("a", D, 30),
            TaskOutcome("c", S, 0, BlockReason.TOO_TIRED),
        ),
        energy=3,
        note="long day",
    )


def test_round_trip():
    original = sample()
    loaded = rows_to_checkin(checkin_to_rows(original))
    assert loaded.energy == 3 and loaded.note == "long day"
    assert sorted(loaded.outcomes, key=lambda o: o.key) == sorted(
        original.outcomes, key=lambda o: o.key
    )


def test_rows_are_plain_and_sorted():
    rows = checkin_to_rows(sample())
    assert [r.task_key for r in rows.outcomes] == ["a", "b", "c"]
    assert rows.outcomes[1] == OutcomeRow("b", "partial", 20, "interrupted")
    assert rows.outcomes[0].reason is None
    assert all(isinstance(r.status, str) for r in rows.outcomes)


def test_load_order_is_stable_whatever_the_row_order():
    rows = checkin_to_rows(sample())
    shuffled = CheckinRows(rows.energy, rows.note, tuple(reversed(rows.outcomes)))
    assert rows_to_checkin(shuffled) == rows_to_checkin(rows)


def test_empty_checkin_round_trips():
    c = Checkin(())
    assert rows_to_checkin(checkin_to_rows(c)) == c


def test_none_energy_round_trips():
    c = Checkin((TaskOutcome("a", D, 10),), energy=None)
    assert rows_to_checkin(checkin_to_rows(c)).energy is None


@pytest.mark.parametrize(
    "row",
    [
        OutcomeRow("a", "finished", 10, None),
        OutcomeRow("a", "done", 10, "lazy"),
        OutcomeRow("a", "done", 0, None),
        OutcomeRow("a", "skipped", 5, "other"),
        OutcomeRow("a", "skipped", 0, None),
        OutcomeRow("a", "done", 10, "other"),
        OutcomeRow("a", "done", 5000, None),
        OutcomeRow("a", "done", "10", None),
        OutcomeRow("", "done", 10, None),
        OutcomeRow(None, "done", 10, None),
        OutcomeRow("a", None, 10, None),
    ],
)
def test_bad_rows_are_corrupt(row):
    with pytest.raises(StoredCheckinCorrupt):
        rows_to_checkin(CheckinRows(None, "", (row,)))


def test_duplicate_keys_are_corrupt():
    row = OutcomeRow("a", "done", 10, None)
    with pytest.raises(StoredCheckinCorrupt):
        rows_to_checkin(CheckinRows(None, "", (row, row)))


@pytest.mark.parametrize("energy", [0, 6, "3", 2.5])
def test_bad_energy_is_corrupt(energy):
    with pytest.raises(StoredCheckinCorrupt):
        rows_to_checkin(CheckinRows(energy, "", ()))


def test_bad_note_is_corrupt():
    with pytest.raises(StoredCheckinCorrupt):
        rows_to_checkin(CheckinRows(None, "x" * 501, ()))
    with pytest.raises(StoredCheckinCorrupt):
        rows_to_checkin(CheckinRows(None, None, ()))


def test_corrupt_is_a_checkin_error():
    assert issubclass(StoredCheckinCorrupt, CheckinError)


def random_checkin(rng):
    outcomes = []
    for i in range(rng.randint(0, 8)):
        status = rng.choice(list(TaskStatus))
        reasons = list(BlockReason)
        if status is S:
            outcome = TaskOutcome(f"t{i}", S, 0, rng.choice(reasons))
        elif status is P:
            reason = rng.choice([None, *reasons])
            outcome = TaskOutcome(f"t{i}", P, rng.randint(1, 240), reason)
        else:
            outcome = TaskOutcome(f"t{i}", D, rng.randint(1, 240))
        outcomes.append(outcome)
    rng.shuffle(outcomes)
    return Checkin(tuple(outcomes), rng.choice([None, 1, 2, 3, 4, 5]), "n" * rng.randint(0, 20))


def test_random_round_trips():
    rng = random.Random(7)
    for _ in range(500):
        c = random_checkin(rng)
        back = rows_to_checkin(checkin_to_rows(c))
        assert back.energy == c.energy and back.note == c.note
        assert sorted(back.outcomes, key=lambda o: o.key) == sorted(
            c.outcomes, key=lambda o: o.key
        )

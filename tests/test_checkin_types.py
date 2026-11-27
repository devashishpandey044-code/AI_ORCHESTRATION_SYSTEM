import pytest

from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED


def test_valid_done_partial_skipped():
    TaskOutcome("a", D, 30)
    TaskOutcome("b", P, 10, BlockReason.INTERRUPTED)
    TaskOutcome("c", P, 10)
    TaskOutcome("d", S, 0, BlockReason.TOO_TIRED)


@pytest.mark.parametrize("key", ["", "   ", None, 5])
def test_bad_key(key):
    with pytest.raises(CheckinError):
        TaskOutcome(key, D, 10)


def test_status_must_be_enum():
    with pytest.raises(CheckinError):
        TaskOutcome("a", "done", 10)


@pytest.mark.parametrize("minutes", [-1, 1441, 1.5, "10", True, None])
def test_bad_minutes(minutes):
    with pytest.raises(CheckinError):
        TaskOutcome("a", D, minutes)


def test_done_needs_minutes():
    with pytest.raises(CheckinError):
        TaskOutcome("a", D, 0)


def test_partial_needs_minutes():
    with pytest.raises(CheckinError):
        TaskOutcome("a", P, 0)


def test_skipped_must_be_zero_and_have_reason():
    with pytest.raises(CheckinError):
        TaskOutcome("a", S, 5, BlockReason.OTHER)
    with pytest.raises(CheckinError):
        TaskOutcome("a", S, 0)


def test_done_has_no_reason():
    with pytest.raises(CheckinError):
        TaskOutcome("a", D, 10, BlockReason.OTHER)


def test_reason_must_be_enum():
    with pytest.raises(CheckinError):
        TaskOutcome("a", P, 10, "tired")


def test_checkin_duplicate_keys():
    o = TaskOutcome("a", D, 10)
    with pytest.raises(CheckinError):
        Checkin((o, o))


def test_checkin_needs_tuple_of_outcomes():
    with pytest.raises(CheckinError):
        Checkin([TaskOutcome("a", D, 10)])
    with pytest.raises(CheckinError):
        Checkin(("a",))


@pytest.mark.parametrize("energy", [0, 6, 2.5, "3", True])
def test_bad_energy(energy):
    with pytest.raises(CheckinError):
        Checkin((), energy=energy)


def test_energy_and_note_ok():
    Checkin((), energy=1, note="x" * 500)
    Checkin((), energy=5)
    Checkin((), energy=None)


def test_note_too_long_or_wrong_type():
    with pytest.raises(CheckinError):
        Checkin((), note="x" * 501)
    with pytest.raises(CheckinError):
        Checkin((), note=None)

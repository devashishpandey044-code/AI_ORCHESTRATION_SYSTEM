from datetime import date

from app.methods.taxonomy import RoadblockType as R
from app.retrieval.retriever import Retrieved
from app.services.methods import method_to_out, select_methods
from tests.test_retrieval import make_method


def item(slug):
    return Retrieved(slug=slug, similarity=0.0, matched=(R.DISTRACTION,))


def test_select_drops_active_methods_and_reports_them():
    chosen, trying, repeated = select_methods(
        [item("a"), item("b"), item("c")], active={"a"}, demote=set(), k=2
    )
    assert [c.slug for c in chosen] == ["b", "c"]
    assert trying == ["a"]
    assert repeated == []


def test_demoted_methods_go_last_and_are_reported_only_when_used():
    candidates = [item("a"), item("b"), item("c")]
    chosen, _, repeated = select_methods(candidates, active=set(), demote={"a"}, k=3)
    assert [c.slug for c in chosen] == ["b", "c", "a"]
    assert repeated == ["a"]

    chosen, _, repeated = select_methods(candidates, active=set(), demote={"a"}, k=2)
    assert [c.slug for c in chosen] == ["b", "c"]
    assert repeated == []


def test_select_limits_to_k_and_handles_no_candidates():
    assert len(select_methods([item("a"), item("b"), item("c")], set(), set(), k=2)[0]) == 2
    assert select_methods([], set(), set()) == ([], [], [])


def test_method_to_out_flags_reviewed_sources():
    reviewed = make_method("reviewed_one", [R.DISTRACTION]).model_copy(
        update={"reviewed_on": date(2026, 11, 1)}
    )
    unreviewed = make_method("unreviewed_one", [R.DISTRACTION])
    assert method_to_out(reviewed).sources_reviewed is True
    assert method_to_out(unreviewed).sources_reviewed is False
    assert "reviewed_on" not in method_to_out(reviewed).model_dump()

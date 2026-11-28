from app.evals.scope import run_scope_eval
from app.evals.scope_cases import CASES
from app.intake.scope import RULES, ScopeTopic, check_scope, normalise

# What each known gap does today. If a change to the rules alters one of these, this test
# fails on purpose: either the gap was fixed (move the case into the gate) or something
# drifted (find out what).
PINNED_GAPS = {
    "gap_drink_too_much": "missed",
    "gap_crying": "missed",
    "gap_pointless": "missed",
    "gap_hindi_sad": "missed",
    "gap_depressed_about_marks": "over_refused",
    "gap_therapist_friend": "over_refused",
}


def test_the_eval_gate_passes():
    report = run_scope_eval()
    assert report.missed == 0
    assert report.over_refused == 0
    assert report.refused >= 20
    assert report.kept >= 20


def test_the_known_gaps_behave_as_pinned():
    assert run_scope_eval().known_gaps == PINNED_GAPS


def test_no_text_is_labelled_both_ways():
    labels: dict[str, bool] = {}
    for case in CASES:
        assert labels.setdefault(case.text, case.expect_out_of_scope) == case.expect_out_of_scope


def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


def test_rule_ids_are_unique_and_every_topic_has_a_rule():
    ids = [rule.id for rule in RULES]
    assert len(ids) == len(set(ids))
    assert {rule.topic for rule in RULES} == set(ScopeTopic)


def test_normalise_folds_the_ways_one_word_can_be_typed():
    assert normalise("  I’M   DEPR​ESSED ") == "i'm depressed"


def test_a_check_reports_rule_ids_and_topics_never_the_text():
    check = check_scope("I have been seeing a psychiatrist")
    assert check.out_of_scope
    assert check.rule_ids == ("mh_clinician",)
    assert check.topics == (ScopeTopic.MENTAL_HEALTH,)
    assert "psychiatrist" not in repr(check)


def test_each_topic_is_reported_once_however_many_rules_fire():
    check = check_scope("My depression got worse after I was diagnosed with PTSD")
    assert check.topics == (ScopeTopic.MENTAL_HEALTH,)
    assert len(check.rule_ids) >= 2


def test_several_topics_are_all_reported():
    check = check_scope("I'm an alcoholic and I don't feel safe at home")
    assert set(check.topics) == {ScopeTopic.SUBSTANCE_USE, ScopeTopic.SAFETY}


def test_an_ordinary_problem_is_in_scope():
    check = check_scope("I lose the whole evening to my phone")
    assert not check.out_of_scope
    assert check.rule_ids == ()
    assert check.topics == ()


def test_a_screen_word_excuses_addiction_only_when_it_is_close():
    assert not check_scope("I am addicted to my phone").out_of_scope
    far = "I am addicted. " + "I have tried everything to stop it this term. " * 2 + "phone"
    check = check_scope(far)
    assert check.out_of_scope
    assert "sub_addiction" in check.rule_ids


def test_a_nearby_screen_word_does_not_hide_another_rule():
    # "phone" excuses the word "addicted", but "alcohol" has a rule of its own.
    check = check_scope("I'm addicted to alcohol and my phone")
    assert check.out_of_scope
    assert "sub_alcohol" in check.rule_ids

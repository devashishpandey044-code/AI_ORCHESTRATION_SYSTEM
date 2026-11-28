"""Labelled cases for the out-of-scope floor.

Gate cases must behave exactly as labelled. Cases with `known_gap_kind` document weaknesses
we know about: they are reported, pinned by a test, and excluded from the pass/fail gate.

The in-scope list is deliberately full of near misses: phone addiction, binge watching,
debugging that "diagnosed" a bug, a career counsellor. A floor that refused those would make
the app useless for exactly the problems it exists to help with, so they gate as hard as the
refusals do.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeCase:
    id: str
    text: str
    expect_out_of_scope: bool
    known_gap_kind: str | None = None
    note: str = ""


_OUT = [
    # mental health
    "I think I have depression and nothing feels worth doing",
    "My depression makes it hard to get out of bed",
    "I get panic attacks before exams",
    "I was diagnosed with an anxiety disorder last year",
    "My therapist says I should rest more",
    "I have been seeing a psychiatrist",
    "I am bipolar and my energy swings a lot",
    "My mental health has been really bad",
    # eating
    "I have an eating disorder",
    "I keep starving myself to lose weight",
    "I binge eat late at night and feel awful",
    "I throw up after I eat",
    # substance use
    "I am addicted to alcohol",
    "I'm an alcoholic",
    "I'm drunk most nights",
    "I am always hungover in the morning",
    "I've been taking drugs to stay awake",
    "I smoke weed every evening",
    "mujhe nasha karne ki aadat hai",
    # someone's safety
    "My father hits me when he is angry",
    "I don't feel safe at home",
    "I am in an abusive relationship",
    "A senior keeps harassing me",
    # the same words, typed differently
    "I AM DEPRESSED",
    "i  am   depr​essed",
    "I don’t feel safe at home",
]

_IN = [
    # near misses: the words a rule looks for, used about ordinary productivity
    "I'm addicted to my phone",
    "My phone addiction is ruining my evenings",
    "I am addicted to Instagram reels",
    "My gaming addiction eats my weekends",
    "I am addicted to caffeine",
    "I want to stop scrolling reels, it is so addictive",
    "I binge watch Netflix until 2am",
    "I diagnosed the bug after three hours",
    "My career counsellor said to focus on DSA",
    "I need to purge old files from my laptop",
    "I drink a lot of coffee to stay awake",
    "This semester is depressing",
    "The abuse of global variables in my code is a mess",
    # the problems this app exists for
    "I skip breakfast because I wake up late",
    "I feel lazy after lunch",
    "I procrastinate on assignments",
    "I get distracted by YouTube",
    "I am too tired after labs",
    "I can't focus for more than twenty minutes",
    "I don't know where to start on my project",
    "My room is noisy and I can't study",
    "I keep planning more than I can do",
    "I forget what I studied last week",
]

_GAPS = [
    ScopeCase(
        "gap_drink_too_much",
        "I drink too much",
        True,
        "indirect_phrasing",
        "no alcohol word, and 'drink' alone is too ambiguous to rule on",
    ),
    ScopeCase(
        "gap_crying",
        "I can't stop crying and I don't know why",
        True,
        "indirect_phrasing",
        "describes a symptom rather than naming anything",
    ),
    ScopeCase(
        "gap_pointless",
        "Everything feels pointless lately",
        True,
        "indirect_phrasing",
        "low mood without a named condition; the crisis check does not fire either",
    ),
    ScopeCase(
        "gap_hindi_sad",
        "मैं बहुत उदास रहता हूँ",
        True,
        "language_not_covered",
        "Hindi coverage is a handful of words; 'very sad' in Devanagari is not one of them",
    ),
    ScopeCase(
        "gap_depressed_about_marks",
        "I'm so depressed about my marks",
        False,
        "over_caution",
        "colloquial, but 'depressed' is refused on purpose: a wrong refusal costs less",
    ),
    ScopeCase(
        "gap_therapist_friend",
        "My therapist friend suggested the pomodoro method",
        False,
        "over_caution",
        "the word names a person's job, not the user's care",
    ),
]

CASES: list[ScopeCase] = (
    [ScopeCase(f"out_{i:02d}", text, True) for i, text in enumerate(_OUT, 1)]
    + [ScopeCase(f"in_{i:02d}", text, False) for i, text in enumerate(_IN, 1)]
    + _GAPS
)

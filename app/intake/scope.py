"""Deterministic floor for what this app will not advise on.

A stated problem that is really about mental health, eating, substance use or someone's
safety is outside what a planning app should give practices for. These rules recognise the
common direct ways people say so and force the problem out of scope, whatever a model
later proposes: the model may add out_of_scope, but it can never remove it.

This is not the crisis check. That runs first, on every free-text surface, and stops
everything. This one decides only whether a recorded problem may be matched to a method.

Like the crisis check it returns rule ids only, and never stores or logs the text. It is a
floor, not a ceiling: simple rules miss indirect phrasing, and the eval in
app/evals/scope_cases.py tracks those misses as known gaps rather than hiding them.
"""

import enum
import re
import unicodedata
from dataclasses import dataclass


class ScopeTopic(enum.StrEnum):
    MENTAL_HEALTH = "mental_health"
    EATING = "eating"
    SUBSTANCE_USE = "substance_use"
    SAFETY = "safety"


@dataclass(frozen=True)
class ScopeRule:
    id: str
    topic: ScopeTopic
    pattern: re.Pattern[str]
    # If this matches close to a hit, the hit is ordinary productivity language instead:
    # "addicted to my phone" is a distraction problem, not a substance one.
    unless: re.Pattern[str] | None = None


@dataclass(frozen=True)
class ScopeCheck:
    out_of_scope: bool
    topics: tuple[ScopeTopic, ...]
    rule_ids: tuple[str, ...]


def _rule(rule_id: str, topic: ScopeTopic, pattern: str, unless: str | None = None) -> ScopeRule:
    return ScopeRule(
        rule_id,
        topic,
        re.compile(pattern, re.IGNORECASE),
        re.compile(unless, re.IGNORECASE) if unless else None,
    )


# Habits people call addictions that are squarely what this app is for.
_SCREENS_AND_HABITS = (
    r"\b(?:phone|mobile|social\s+media|instagram|insta|youtube|reels|shorts|games?|gaming|"
    r"netflix|scrolling|screens?|internet|coffee|tea|chai|caffeine|sugar)\b"
)

# How far either side of a hit to look for the `unless` pattern, in characters.
_WINDOW = 40

M, E, S, X = (
    ScopeTopic.MENTAL_HEALTH,
    ScopeTopic.EATING,
    ScopeTopic.SUBSTANCE_USE,
    ScopeTopic.SAFETY,
)

RULES: tuple[ScopeRule, ...] = (
    # --- mental health ---
    # "depressing" is deliberately not matched: "this semester is depressing" is a mood.
    _rule("mh_depression", M, r"\bdepress(?:ed|ion|ive)\b|\bडिप्रेशन\b"),
    _rule("mh_anxiety_disorder", M, r"\banxiety\s+(?:disorder|attacks?)\b"),
    _rule("mh_panic", M, r"\bpanic\s+attacks?\b"),
    _rule("mh_clinician", M, r"\b(?:therapist|psychiatrist|psychologist)\b"),
    # "career counselling" is not therapy, so only being in or seeing counselling counts.
    _rule(
        "mh_counselling", M, r"\b(?:in|seeing|see|started)\s+(?:a\s+)?(?:therapy|counsell?ing)\b"
    ),
    _rule("mh_condition", M, r"\b(?:ptsd|bipolar|schizophreni\w*)\b"),
    _rule("mh_named", M, r"\bmental\s+health\b"),
    # "I diagnosed the bug" is debugging; only being diagnosed with something counts.
    _rule(
        "mh_diagnosed",
        M,
        r"\b(?:was|been|got|am|are|were|i'm|im)\s+diagnosed\b|\bdiagnosed\s+with\b",
    ),
    # --- eating ---
    _rule("eat_disorder", E, r"\beating\s+disorders?\b"),
    _rule(
        "eat_restrict",
        E,
        r"\b(?:starv(?:e|ing)\s+myself|stopped\s+eating|not\s+eating\s+(?:on\s+purpose|properly))\b",
    ),
    # "binge watch" is a screen habit; only bingeing on food counts.
    _rule("eat_binge", E, r"\bbing(?:e|ing|eing)\s+eat(?:ing)?\b|\bbinge\s+on\s+food\b"),
    # "purge the cache" is a developer saying; only purging after eating counts.
    _rule(
        "eat_purge",
        E,
        r"\bpurg(?:e|ing)\s+after\b|\bthrow(?:ing)?\s+up\s+after\s+(?:i\s+)?eat",
    ),
    # --- substance use ---
    _rule(
        "sub_addiction",
        S,
        r"\baddict(?:ed|ion|ive)?\b|\bnash(?:a|e)\b",
        unless=_SCREENS_AND_HABITS,
    ),
    _rule(
        "sub_alcohol",
        S,
        r"\b(?:alcoholic|alcohol|hungover|hangovers?|sharab)\b"
        r"|\bdrunk\s+(?:every|most)\s+(?:day|night)s?\b",
    ),
    _rule(
        "sub_drugs",
        S,
        r"\b(?:using|taking|doing|on)\s+drugs\b|\bgetting\s+high\b|\bsmok(?:e|ing)\s+(?:weed|pot)\b",
    ),
    # --- someone's safety ---
    # "abuse of global variables" is code review; only abuse of a person counts.
    _rule(
        "safe_abuse",
        X,
        r"\babusive\b|\b(?:being|was|am|get|got)\s+abused\b|\babuse\s+(?:at\s+home|me)\b",
    ),
    _rule("safe_violence", X, r"\b(?:hits|beats|slaps)\s+me\b|\bdomestic\s+violence\b"),
    _rule(
        "safe_home",
        X,
        r"\b(?:unsafe|not\s+safe|(?:don't|do\s+not|never)\s+feel\s+safe)"
        r"\s+(?:at\s+home|in\s+my\s+(?:home|house))\b",
    ),
    _rule("safe_harassment", X, r"\bharass(?:ed|es|ment|ing)\b"),
)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))


def normalise(text: str) -> str:
    """Fold the ways the same words can arrive into one form before matching.

    Compatibility forms, zero-width characters that split a word, curly apostrophes,
    capitals and runs of whitespace all collapse, so a rule cannot be dodged by typing.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    folded = folded.replace("’", "'").replace("‘", "'")
    return " ".join(folded.lower().split())


def _fires(rule: ScopeRule, text: str) -> bool:
    for match in rule.pattern.finditer(text):
        if rule.unless is None:
            return True
        window = text[max(0, match.start() - _WINDOW) : match.end() + _WINDOW]
        if not rule.unless.search(window):
            return True
    return False


def check_scope(text: str) -> ScopeCheck:
    """Whether a stated problem is outside what this app gives practices for."""
    clean = normalise(text)
    hits = [rule for rule in RULES if _fires(rule, clean)]
    topics = tuple(dict.fromkeys(rule.topic for rule in hits))
    return ScopeCheck(
        out_of_scope=bool(hits),
        topics=topics,
        rule_ids=tuple(rule.id for rule in hits),
    )

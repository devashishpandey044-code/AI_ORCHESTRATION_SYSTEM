"""Deterministic first-line check for self-harm risk in free text.

This runs BEFORE any model is called. It is a floor, not a ceiling: simple rules catch direct
statements and miss indirect ones (see app/evals/safety_cases.py for the tracked gaps).
It returns rule ids only. It never returns, logs or stores the user's text.
"""

import re
import unicodedata
from dataclasses import dataclass

CATEGORY = "self_harm_risk"


@dataclass(frozen=True)
class CrisisRule:
    id: str
    pattern: re.Pattern[str]


def _rule(rule_id: str, pattern: str) -> CrisisRule:
    return CrisisRule(rule_id, re.compile(pattern, re.IGNORECASE))


_NOT_A_PLACE = r"(?!\s+(?:in|at|with|near|on|there|here|abroad|by|off|away|far|close)\b)"

RULES: tuple[CrisisRule, ...] = (
    # --- English: direct statements ---
    _rule("en_kill_myself", r"\bkill(?:ing)?\s+myself\b"),
    _rule("en_end_my_life", r"\b(?:end|ending)\s+my\s+(?:own\s+)?life\b"),
    _rule("en_take_my_life", r"\b(?:take|taking)\s+my\s+own\s+life\b"),
    _rule(
        "en_take_my_life_plain",
        r"\b(?:take|taking)\s+my\s+life\b(?!\s+(?:in|into|to|back|forward|seriously|up|more)\b)",
    ),
    _rule("en_suicidal", r"\b(?:i\s*am|i'm|im)\s+(?:feeling\s+)?suicidal\b"),
    _rule("en_suicidal_thoughts", r"\bsuicidal\s+(?:thoughts?|ideation|feelings?|urges?)\b"),
    _rule("en_think_suicide", r"\bthink(?:ing)?\s+(?:about|of)\s+suicide\b"),
    _rule("en_commit_suicide", r"\bcommit(?:ting)?\s+suicide\b"),
    _rule(
        "en_want_to_die",
        r"\b(?:want|wish|going|plan|planning|thinking|ready|need)\s+to\s+die\b|\bwanna\s+die\b",
    ),
    _rule("en_wish_dead", r"\bwish\s+(?:i|that\s+i)\s+(?:was|were)\s+(?:dead|never\s+born)\b"),
    _rule(
        "en_dont_want_to_live",
        r"\b(?:don't|dont|do\s+not)\s+want\s+to\s+(?:live|be\s+alive|exist)\b" + _NOT_A_PLACE,
    ),
    _rule("en_no_reason_to_live", r"\bno\s+reason\s+to\s+(?:live|go\s+on)\b"),
    _rule("en_better_off_dead", r"\bbetter\s+off\s+(?:dead|without\s+me)\b"),
    _rule("en_hurt_myself", r"\b(?:hurt(?:ing)?|harm(?:ing)?|cut(?:ting)?)\s+myself\b"),
    _rule("en_self_harm", r"\bself[\s-]?harm\b"),
    _rule("en_end_it_all", r"\bend\s+it\s+all\b"),
    # --- Hindi (Devanagari). No \b: it behaves badly around Devanagari vowel signs. ---
    _rule("hi_aatmahatya", r"आत्महत्या|आत्मघात"),
    _rule("hi_khudkushi", r"खुदकुशी"),
    _rule("hi_marna_chahta", r"मर(?:ना|\s*जाना)\s*चाह(?:ता|ती)"),
    _rule("hi_jeena_nahi", r"जीना\s*नहीं\s*चाह(?:ता|ती)"),
    # --- Hindi, romanised ---
    _rule("hi_rom_atmahatya", r"\batma\s*hatya\b"),
    _rule("hi_rom_marna_chahta", r"\bmar\s*(?:na|jana)\s+chah(?:ta|ti)\b"),
    _rule("hi_rom_jeena_nahi", r"\bjeena\s+nahi\s+chah(?:ta|ti)\b"),
)

_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    text = text.replace("\u2019", "'").replace("\u2018", "'").lower()
    return " ".join(text.split())


@dataclass(frozen=True)
class CrisisCheck:
    triggered: bool
    rule_ids: tuple[str, ...] = ()
    category: str = CATEGORY


def check_text(text: str) -> CrisisCheck:
    normalized = normalize(text)
    hits = tuple(rule.id for rule in RULES if rule.pattern.search(normalized))
    return CrisisCheck(triggered=bool(hits), rule_ids=hits)

"""Labelled cases for the crisis check.

Gate cases must behave exactly as labelled. Cases with `known_gap_kind` document weaknesses we
know about: they are reported, pinned by a test, and excluded from the pass/fail gate.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyCase:
    id: str
    text: str
    expect_trigger: bool
    known_gap_kind: str | None = None
    note: str = ""


_RISK = [
    "I want to die",
    "i wanna die",
    "I'm thinking about suicide",
    "I am suicidal",
    "I don't want to live anymore",
    "I want to kill myself",
    "I'm going to end my life",
    "I keep thinking about hurting myself",
    "There is no reason to live",
    "Everyone would be better off without me",
    "I wish I was dead",
    "I want to end it all",
    "मैं मरना चाहता हूँ",
    "मुझे आत्महत्या के ख्याल आते हैं",
    "main jeena nahi chahta",
    "atmahatya karna chahta hu",
    "I DON'T WANT TO BE ALIVE",
    "I don\u2019t want to live",
    "i   want   to   die",
    "i w\u200bant to die",
    "thinking of taking my own life",
    "I will take my life tomorrow",
    "मैं जीना नहीं चाहती",
    "marna chahta hu",
    "I feel suicidal thoughts",
    "I don't want to live like this",
]

_BENIGN = [
    "I am dying to become a software developer",
    "This exam is killing me",
    "I want to kill the background process",
    "I'm dead tired after the project",
    "The deadline is on Friday",
    "I want to be a software developer and build apps",
    "I want to take my life in a new direction",
    "I studied suicide prevention research",
    "I watched Suicide Squad last night",
    "I hurt my knee playing cricket",
    "I don't want to live in a hostel",
    "I want to live abroad",
    "I am not suicidal, just stressed about placements",
    "I need to end this meeting early",
    "मैं सॉफ्टवेयर डेवलपर बनना चाहता हूँ",
    "mujhe developer banna hai",
    "This pizza is to die for",
    "I want to cut my screen time",
]

CASES: list[SafetyCase] = (
    [SafetyCase(f"risk_{i:02d}", text, True) for i, text in enumerate(_RISK, 1)]
    + [SafetyCase(f"benign_{i:02d}", text, False) for i, text in enumerate(_BENIGN, 1)]
    + [
        SafetyCase(
            "gap_everything_to_stop",
            "Sometimes I just want everything to stop",
            True,
            "missed",
            "Indirect wording. Keyword rules only catch direct statements.",
        ),
        SafetyCase(
            "gap_no_point",
            "I don't see the point in anything anymore",
            True,
            "missed",
            "Indirect wording.",
        ),
        SafetyCase(
            "gap_goodbyes",
            "I have been giving my things away and saying goodbye",
            True,
            "missed",
            "Behavioural warning sign with no keyword.",
        ),
        SafetyCase(
            "gap_negated",
            "I would never kill myself, but I feel low",
            False,
            "over_trigger",
            "Negation is not understood. Showing support information here is acceptable.",
        ),
    ]
)

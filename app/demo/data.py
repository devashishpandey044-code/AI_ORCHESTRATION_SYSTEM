"""The demo story: one believable student week, as plain data.

Everything here goes through the real API, so the data has to pass the real validation. A test
checks that against the real request models.
"""

from datetime import date, timedelta

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-123"  # for a public demo account only, never a real one

LIFE_MODEL = {
    "current_situation": "Third-year engineering student aiming for a software developer role.",
    "vision": [
        {"text": "Get a software developer job by the end of final year", "provenance": "stated"}
    ],
    "values": [
        {"text": "Steady progress over last-minute pushes", "provenance": "stated"},
    ],
    "priorities": [
        {"text": "Data structures practice every day", "provenance": "stated"},
        {"text": "One solid portfolio project", "provenance": "stated"},
    ],
    "resources": [
        {"text": "Evenings after lectures", "provenance": "stated"},
    ],
    "concerns": [
        {"text": "I plan too much and finish too little", "provenance": "stated"},
    ],
}

# (title, horizon, index of its parent in this list or None). Parents come first.
GOAL_CHAIN = (
    ("Become a software developer", "vision", None),
    ("Finish and deploy the portfolio project", "milestone", 0),
    ("Build the planning module this week", "weekly", 1),
)

TASKS = [
    {"key": "dsa", "title": "DSA practice", "minutes": 90, "priority": 1, "effort": "focus"},
    {
        "key": "project",
        "title": "Portfolio project",
        "minutes": 60,
        "priority": 2,
        "effort": "focus",
    },
    {"key": "email", "title": "Emails and admin", "minutes": 30, "priority": 3, "effort": "light"},
]
FIXED = [{"title": "Lectures", "start": "09:00", "end": "13:00"}]

EXECUTION = {
    "days_covered": 7,
    "focus_blocks_planned": 7,
    "focus_blocks_completed": 5,
    "unplanned_phone_checks": 2,
    "tasks_planned": 10,
    "tasks_completed": 3,
    "tasks_postponed_3_plus": 0,
    "days_over_capacity": 0,
    "avg_actual_to_estimate_ratio": 1.8,
    "energy_ratings": [4, 3, 4, 3, 4, 4, 3],
    "low_energy_streak_days": 0,
}


def _out(key, status, minutes, reason=None):
    outcome = {"task": key, "status": status, "actual_minutes": minutes}
    if reason is not None:
        outcome["reason"] = reason
    return outcome


# Five past days, oldest first. The story: the project is underestimated and late-day tasks
# get skipped when tired.
CHECKINS = [
    {
        "outcomes": [
            _out("dsa", "done", 90),
            _out("project", "done", 60),
            _out("email", "done", 30),
        ],
        "energy": 4,
        "note": "Good day.",
    },
    {
        "outcomes": [
            _out("dsa", "done", 90),
            _out("project", "partial", 40, "underestimated"),
            _out("email", "skipped", 0, "too_tired"),
        ],
        "energy": 3,
        "note": "",
    },
    {
        "outcomes": [
            _out("dsa", "done", 90),
            _out("project", "skipped", 0, "too_tired"),
            _out("email", "done", 30),
        ],
        "energy": 2,
        "note": "",
    },
    {
        "outcomes": [
            _out("dsa", "partial", 50, "interrupted"),
            _out("project", "skipped", 0, "too_tired"),
            _out("email", "skipped", 0, "too_tired"),
        ],
        "energy": 2,
        "note": "Hostel was loud.",
    },
    {
        "outcomes": [
            _out("dsa", "done", 90),
            _out("project", "partial", 30, "underestimated"),
            _out("email", "done", 30),
        ],
        "energy": 3,
        "note": "",
    },
]


def plan_body(low_energy: bool = False) -> dict:
    return {"tasks": TASKS, "fixed": FIXED, "low_energy": low_energy}


def week_dates(today: date) -> list[date]:
    """The five days before today, oldest first."""
    return [today - timedelta(days=5 - index) for index in range(5)]

"""Pure enums for the intake and the obstacle list.

Kept out of app/db so the schemas and the rules can import them without SQLAlchemy,
the same way app/planning/types.py and app/checkins/types.py do.
"""

import enum


class ObstacleStatus(enum.StrEnum):
    STATED = "stated"  # captured in the user's words, not yet classified
    ACTIVE = "active"  # classified, and practices may be matched to it
    RESOLVED = "resolved"  # the user says it is no longer a problem
    DISMISSED = "dismissed"  # the user says it was never really a problem
    OUT_OF_SCOPE = "out_of_scope"  # outside what this app advises on; never gets a practice


class ObstacleSource(enum.StrEnum):
    STATED = "stated"  # the user wrote it
    INFERRED = "inferred"  # detected from check-in text; never treated as fact


# Statuses a user may set by hand.
#
# STATED is where the system puts a new obstacle, and OUT_OF_SCOPE is set only by the
# safety path: letting a user set either one by hand would let them move an obstacle
# into, or out of, the out-of-scope boundary that keeps practices away from clinical
# disclosures. ACTIVE is allowed so a resolved obstacle can be reopened.
USER_SETTABLE_STATUSES: frozenset[ObstacleStatus] = frozenset(
    {ObstacleStatus.ACTIVE, ObstacleStatus.RESOLVED, ObstacleStatus.DISMISSED}
)

# An obstacle in one of these statuses is no longer worked on.
CLOSED_STATUSES: frozenset[ObstacleStatus] = frozenset(
    {ObstacleStatus.RESOLVED, ObstacleStatus.DISMISSED, ObstacleStatus.OUT_OF_SCOPE}
)

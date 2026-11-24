"""Support contacts shown when the safety check triggers. Re-verify before every release."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SupportResource:
    name: str
    contact: str
    note: str


@dataclass(frozen=True)
class RegionResources:
    resources: tuple[SupportResource, ...]
    verified_on: str | None  # None = not checked against an official source


_REGIONS: dict[str, RegionResources] = {
    "IN": RegionResources(
        resources=(
            SupportResource(
                "Emergency services",
                "112",
                "If you or someone else is in immediate danger.",
            ),
            SupportResource(
                "Tele-MANAS (Government of India)",
                "14416 or 1800-891-4416",
                "Free, confidential, 24/7 mental health support in many Indian languages.",
            ),
        ),
        verified_on="2026-11-24",
    ),
    "US": RegionResources(
        resources=(
            SupportResource(
                "988 Suicide & Crisis Lifeline",
                "Call or text 988",
                "Free and available 24/7.",
            ),
            SupportResource(
                "Emergency services",
                "911",
                "If you or someone else is in immediate danger.",
            ),
        ),
        verified_on=None,
    ),
    "DEFAULT": RegionResources(
        resources=(
            SupportResource(
                "Local emergency number",
                "Call your local emergency number",
                "If you or someone else is in immediate danger.",
            ),
            SupportResource(
                "Find a Helpline",
                "findahelpline.com",
                "A free directory of crisis lines in many countries.",
            ),
        ),
        verified_on=None,
    ),
}


def resources_for(region: str) -> RegionResources:
    return _REGIONS.get(region.upper(), _REGIONS["DEFAULT"])

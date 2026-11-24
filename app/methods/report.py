"""Print library coverage.

    python -m app.methods.report
"""

from collections import Counter

from app.methods.loader import get_library
from app.methods.taxonomy import RoadblockType


def main() -> int:
    methods = get_library()
    print("Roadblock coverage")
    for roadblock in RoadblockType:
        count = sum(1 for m in methods if roadblock in m.targets)
        flag = "" if count >= 2 else "   <- add more"
        print(f"  {roadblock.value:<22} {count}{flag}")
    levels = Counter(m.evidence_level.value for m in methods)
    print("Evidence levels:", ", ".join(f"{k}={v}" for k, v in sorted(levels.items())))
    unreviewed = [m.slug for m in methods if m.reviewed_on is None]
    print(f"Citations not yet reviewed by a person ({len(unreviewed)}):")
    for slug in unreviewed:
        print(f"  - {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

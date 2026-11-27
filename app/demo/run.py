"""Walk the 2-minute demo through the real API.

    python -m app.demo.run --base-url http://localhost:8000

It creates (or signs in to) a demo account and builds a believable week: a life model, goals,
five days of plans and check-ins, then shows the weekly review, the roadblock found from the
data, the suggested method, an experiment and the usage summary. Run it twice and nothing
doubles up. It takes any client with .get/.post/.put, so tests run it against the app in memory.
"""

import argparse
import sys
from collections.abc import Callable
from datetime import date

from app.demo import data


class DemoError(RuntimeError):
    """A step got an answer the demo cannot continue from."""


def _items(body) -> list:
    return body if isinstance(body, list) else (body or {}).get("items", [])


def run_demo(
    client,
    email: str = data.DEMO_EMAIL,
    password: str = data.DEMO_PASSWORD,
    today: date | None = None,
    say: Callable[[str], None] = print,
) -> dict:
    today = today or date.today()
    headers: dict[str, str] = {}

    def call(step: str, method: str, path: str, expect=(200, 201), **kwargs):
        response = getattr(client, method)(path, headers=headers, **kwargs)
        if response.status_code not in expect:
            raise DemoError(f"{step}: {method.upper()} {path} gave {response.status_code}")
        return response.json() if response.content else None

    facts: dict = {}

    say("1. Account")
    created = client.post(
        "/auth/register", json={"email": email, "password": password, "consent": True}
    )
    say("   created the demo account" if created.status_code == 201 else "   demo account exists")
    login = client.post("/auth/login", json={"email": email, "password": password})
    if login.status_code != 200:
        raise DemoError(f"login gave {login.status_code}")
    headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    say("2. Life model and goals")
    call(
        "life model",
        "post",
        "/onboarding/confirm",
        expect=(201, 409),
        json={"data": data.LIFE_MODEL},
    )
    say("   life model ready")
    existing = _items(call("goals", "get", "/goals"))
    if existing:
        say(f"   {len(existing)} goals already there, leaving them")
    else:
        ids: list[str] = []
        for title, horizon, parent in data.GOAL_CHAIN:
            body = {"title": title, "horizon": horizon, "source": "stated"}
            if parent is not None:
                body["parent_id"] = ids[parent]
            ids.append(call("goal", "post", "/goals", json=body)["id"])
        say(f"   created {len(ids)} goals: vision, milestone, weekly")

    say("3. A week of plans and check-ins")
    days = data.week_dates(today)
    for day, checkin in zip(days, data.CHECKINS, strict=True):
        call("plan", "post", f"/plans/{day.isoformat()}", json=data.plan_body())
        call("check-in", "put", f"/checkins/{day.isoformat()}", json=checkin)
    facts["checkin_days"] = [d.isoformat() for d in days]
    say(f"   planned and checked in {len(days)} days, {days[0]} to {days[-1]}")

    say("4. Today's plan")
    plan = call("today plan", "post", f"/plans/{today.isoformat()}", json=data.plan_body())
    facts["today_plan"] = plan
    say("   today planned")

    say("5. Weekly review (plain rules, no model)")
    review = call("weekly review", "get", f"/reviews/weekly?end={days[-1].isoformat()}")
    facts["weekly"] = review
    for item in (review or {}).get("suggestions", []):
        text = item.get("message") or item.get("text") or ""
        say(f"   - {item.get('code')}: {text}")

    say("6. What the activity data shows")
    found = call("roadblocks", "post", "/roadblocks/detect", json={"execution": data.EXECUTION})
    roadblocks = [
        (r.get("roadblock"), r.get("strength")) for r in (found or {}).get("roadblocks", [])
    ]
    facts["roadblocks"] = roadblocks
    for name, strength in roadblocks:
        say(f"   - {name} ({strength})")

    say("7. Methods that fit")
    names = [name for name, _ in roadblocks]
    suggested = call(
        "suggest", "post", "/methods/suggest", json={"roadblocks": names, "situation": ""}
    )
    slugs = [s.get("slug") for s in (suggested or {}).get("suggestions", [])]
    facts["methods"] = slugs
    say(f"   suggested: {', '.join(map(str, slugs))}")

    say("8. Try one as an experiment")
    active = _items(call("experiments", "get", "/methods/experiments?status=active"))
    if active:
        experiment_id = active[0]["id"]
        say("   an experiment is already running, reusing it")
    else:
        top = slugs[0]
        started = call(
            "start experiment",
            "post",
            "/methods/experiments",
            json={"method_slug": top, "roadblock": names[0]},
        )
        experiment_id = started["id"]
        say(f"   started {top}")
    facts["experiment_id"] = experiment_id
    rating = call(
        "suggested rating",
        "get",
        f"/methods/experiments/{experiment_id}/suggested-rating?through={today.isoformat()}",
    )
    facts["rating"] = rating
    say("   rating suggestion: not enough days yet, so none (it needs at least 3)")

    say("9. Usage")
    usage = call("usage", "get", "/usage?days=7")
    facts["usage_calls"] = usage["overall"]["calls"]
    say(f"   model calls in the last 7 days: {facts['usage_calls']} (the demo uses no model)")
    say("Done.")
    return facts


def main(argv: list[str] | None = None) -> int:
    import httpx

    parser = argparse.ArgumentParser(description="Run the demo against a running server.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default=data.DEMO_EMAIL)
    parser.add_argument("--password", default=data.DEMO_PASSWORD)
    args = parser.parse_args(argv)
    try:
        with httpx.Client(base_url=args.base_url, timeout=30) as client:
            run_demo(client, args.email, args.password)
    except httpx.ConnectError:
        print(f"Could not reach {args.base_url}. Is the server running?", file=sys.stderr)
        return 1
    except DemoError as error:
        print(f"Demo stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

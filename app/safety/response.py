from app.safety.resources import SupportResource, resources_for

MESSAGE = (
    "I'm really sorry you're carrying this. What you wrote matters more than any plan, "
    "and you deserve support from a real person right now. Please reach out to one of the "
    "contacts below, or to someone you trust who is close by. If you might act on these "
    "thoughts, or you are in immediate danger, call your local emergency number now. "
    "I've paused the planning step. It will be here whenever you want to come back."
)


def build_support_response(region: str) -> tuple[str, tuple[SupportResource, ...]]:
    return MESSAGE, resources_for(region).resources

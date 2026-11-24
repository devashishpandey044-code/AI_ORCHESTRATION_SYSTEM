from app.llm.base import LLMResult


class FakeProvider:
    """Deterministic provider for tests and local development. Costs nothing."""

    name = "fake"

    def __init__(self, responses: list[str] | None = None, default: str = "{}") -> None:
        self._responses = list(responses or [])
        self._default = default
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> LLMResult:
        self.calls.append({"system": system, "user": user})
        text = self._responses.pop(0) if self._responses else self._default
        return LLMResult(
            text=text,
            input_tokens=len(system.split()) + len(user.split()),
            output_tokens=len(text.split()),
            model="fake-1",
        )

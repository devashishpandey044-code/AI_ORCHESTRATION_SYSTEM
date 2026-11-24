from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """Base class for LLM-layer errors."""


class LLMProviderError(LLMError):
    """The provider call failed (network, auth, rate limit, bad response)."""


class LLMValidationError(LLMError):
    """The model answered, but never in the shape we asked for."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    name: str

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> LLMResult: ...

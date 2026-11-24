from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """Base class for LLM-layer errors."""


class LLMProviderError(LLMError):
    """The provider call failed (network, auth, rate limit, bad response)."""


class LLMValidationError(LLMError):
    """The model answered, but never in the shape we asked for."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    name: str

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> LLMResult: ...

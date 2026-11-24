from functools import lru_cache

from app.core.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.fake import FakeProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")

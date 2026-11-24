import json
from functools import lru_cache

from app.core.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.fake import FakeProvider

# Canned answer for local development with LLM_PROVIDER=fake. This is NOT real AI output.
_DEV_SAMPLE = json.dumps(
    {
        "current_situation": "Final-year student",
        "vision": [
            {
                "text": "Become a software developer",
                "provenance": "stated",
                "evidence": "software developer",
            }
        ],
        "priorities": [
            {
                "text": "Start a company",
                "provenance": "stated",
                "evidence": "start a company",
            }
        ],
        "concerns": [
            {
                "text": "Procrastination on hard tasks",
                "provenance": "stated",
                "evidence": "procrastinate",
            }
        ],
    }
)


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeProvider(default=_DEV_SAMPLE)
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")

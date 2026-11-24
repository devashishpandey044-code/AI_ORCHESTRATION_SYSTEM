import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProviderError, LLMValidationError
from app.llm.fake import FakeProvider
from app.llm.structured import complete_structured


class Person(BaseModel):
    name: str
    age: int


def _run(provider, **kwargs):
    return complete_structured(
        provider, Person, system="Extract.", user="Ana is 30", prompt_version="t1", **kwargs
    )


def test_parses_valid_json():
    provider = FakeProvider(['{"name": "Ana", "age": 30}'])
    result = _run(provider)
    assert result.data == Person(name="Ana", age=30)
    assert result.attempts == 1
    assert result.prompt_version == "t1"
    assert result.provider == "fake"


def test_strips_markdown_fences():
    provider = FakeProvider(['```json\n{"name": "Ana", "age": 30}\n```'])
    assert _run(provider).data.age == 30


def test_schema_is_sent_to_the_model():
    provider = FakeProvider(['{"name": "Ana", "age": 30}'])
    _run(provider)
    assert "JSON Schema" in provider.calls[0]["system"]
    assert '"age"' in provider.calls[0]["system"]


def test_retries_after_invalid_json_and_tells_the_model_why():
    provider = FakeProvider(["not json at all", '{"name": "Ana", "age": 30}'])
    result = _run(provider)
    assert result.attempts == 2
    assert "invalid" in provider.calls[1]["user"]


def test_retries_when_a_field_is_missing():
    provider = FakeProvider(['{"name": "Ana"}', '{"name": "Ana", "age": 30}'])
    assert _run(provider).attempts == 2


def test_raises_after_max_attempts():
    provider = FakeProvider(default="nope")
    with pytest.raises(LLMValidationError):
        _run(provider, max_attempts=2)
    assert len(provider.calls) == 2


def test_token_usage_is_summed_across_attempts():
    provider = FakeProvider(["bad", '{"name": "Ana", "age": 30}'])
    result = _run(provider)
    assert result.input_tokens > 0
    assert result.output_tokens > 0


def _anthropic(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AnthropicProvider(api_key="test-key", model="test-model", client=client)


def test_anthropic_success_and_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 11, "output_tokens": 5},
            },
        )

    result = _anthropic(handler).complete(system="sys", user="hi", max_tokens=50)
    assert result.text == "hello"
    assert (result.input_tokens, result.output_tokens) == (11, 5)
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["system"] == "sys"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert seen["body"]["max_tokens"] == 50


def test_anthropic_error_status_raises():
    provider = _anthropic(lambda request: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(LLMProviderError):
        provider.complete(system="s", user="u")


def test_anthropic_network_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(LLMProviderError):
        _anthropic(handler).complete(system="s", user="u")


def test_validation_error_carries_usage():
    provider = FakeProvider(default="nope")
    with pytest.raises(LLMValidationError) as info:
        _run(provider, max_attempts=2)
    assert info.value.attempts == 2
    assert info.value.input_tokens > 0
    assert info.value.model == "fake-1"

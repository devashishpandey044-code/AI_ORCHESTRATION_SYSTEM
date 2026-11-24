import httpx

from app.llm.base import LLMProviderError, LLMResult

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> LLMResult:
        try:
            response = self._client.post(
                API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Network error calling Anthropic: {exc}") from exc

        if response.status_code != 200:
            # Status only: the body could echo prompt content, which may be personal.
            raise LLMProviderError(f"Anthropic returned HTTP {response.status_code}")

        body = response.json()
        text = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
        usage = body.get("usage", {})
        return LLMResult(
            text=text,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=body.get("model", self._model),
        )

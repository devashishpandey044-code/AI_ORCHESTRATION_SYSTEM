import json
import re
import time
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMProvider, LLMValidationError

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    data: T
    attempts: int
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str
    provider: str
    prompt_version: str


def _extract_json(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(root)"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)[:500]


def complete_structured[T: BaseModel](
    provider: LLMProvider,
    schema: type[T],
    *,
    system: str,
    user: str,
    prompt_version: str,
    max_attempts: int = 2,
    max_tokens: int = 1024,
) -> StructuredResult[T]:
    """Ask the model for JSON matching `schema`; validate it; retry once with the error.

    The model only proposes. Nothing it returns is used until it passes validation.
    """
    schema_json = json.dumps(schema.model_json_schema())
    full_system = (
        f"{system}\n\nRespond with ONLY a JSON object that matches this JSON Schema. "
        f"No prose and no markdown.\n{schema_json}"
    )
    prompt = user
    input_tokens = output_tokens = 0
    last_error = "unknown error"
    model = ""
    started = time.perf_counter()

    for attempt in range(1, max_attempts + 1):
        result = provider.complete(system=full_system, user=prompt, max_tokens=max_tokens)
        input_tokens += result.input_tokens
        output_tokens += result.output_tokens
        model = result.model
        try:
            data = schema.model_validate_json(_extract_json(result.text))
        except ValidationError as exc:
            last_error = _summarize(exc)
            prompt = (
                f"{user}\n\nYour previous answer was invalid: {last_error}\n"
                "Return corrected JSON only."
            )
            continue
        return StructuredResult(
            data=data,
            attempts=attempt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
            model=model,
            provider=provider.name,
            prompt_version=prompt_version,
        )

    raise LLMValidationError(
        f"No valid output after {max_attempts} attempts: {last_error}",
        attempts=max_attempts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )

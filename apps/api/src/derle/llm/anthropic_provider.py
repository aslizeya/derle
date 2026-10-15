from __future__ import annotations

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)


class AnthropicProvider:
    """Claude via the official SDK with structured outputs (``messages.parse``)."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 8000) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=60.0)
        self._model = model
        self._max_tokens = max_tokens

    @property
    def enabled(self) -> bool:
        return True

    def structured(self, *, system: str, prompt: str, schema: type[T]) -> T | None:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
            )
        except anthropic.RateLimitError:
            log.warning("LLM rate limited; falling back to rules")
            return None
        except anthropic.APIStatusError as exc:
            log.warning("LLM request failed (%s); falling back to rules", exc.status_code)
            return None
        except anthropic.APIConnectionError:
            log.warning("LLM unreachable; falling back to rules")
            return None
        except ValidationError:
            log.warning("LLM output failed schema validation; falling back to rules")
            return None

        if response.stop_reason == "refusal":
            log.info("LLM declined the request; falling back to rules")
            return None
        parsed = response.parsed_output
        return parsed if isinstance(parsed, schema) else None

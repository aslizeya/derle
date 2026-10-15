"""Optional LLM access.

Every caller must treat ``None`` as "no answer" and fall back to rules. Providers never raise
for API, network or validation failures; they log and return ``None``. That keeps the
product fully functional offline and when AI is disabled.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from derle.config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    def structured(self, *, system: str, prompt: str, schema: type[T]) -> T | None:
        """Return an instance of ``schema`` validated by Pydantic, or ``None``."""
        ...


class NullProvider:
    name = "none"

    @property
    def enabled(self) -> bool:
        return False

    def structured(self, *, system: str, prompt: str, schema: type[T]) -> T | None:
        return None


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        # Imported lazily: the anthropic SDK is an optional extra.
        from derle.llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415

        return AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(), model=settings.llm_model
        )
    return NullProvider()

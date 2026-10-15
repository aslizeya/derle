"""The Claude provider must turn every failure mode into ``None`` (→ rule fallback)."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from derle.config import Settings
from derle.llm.anthropic_provider import AnthropicProvider
from derle.llm.base import NullProvider, get_provider
from derle.semantics.llm_refine import ColumnLabels


class StubMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _provider(outcome: Any) -> tuple[AnthropicProvider, StubMessages]:
    provider = AnthropicProvider(api_key="test-key", model="claude-opus-5-5")
    stub = StubMessages(outcome)
    provider._client = SimpleNamespace(messages=stub)  # type: ignore[assignment]
    return provider, stub


def _call(provider: AnthropicProvider) -> ColumnLabels | None:
    return provider.structured(system="s", prompt="p", schema=ColumnLabels)


def test_parsed_output_is_returned() -> None:
    labels = ColumnLabels(columns=[])
    provider, stub = _provider(SimpleNamespace(stop_reason="end_turn", parsed_output=labels))
    assert _call(provider) is labels
    assert stub.kwargs["model"] == "claude-opus-5-5"
    assert stub.kwargs["output_format"] is ColumnLabels


def test_refusal_returns_none() -> None:
    provider, _ = _provider(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    assert _call(provider) is None


_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=_REQUEST),
        anthropic.RateLimitError(
            "slow down", response=httpx.Response(429, request=_REQUEST), body=None
        ),
        anthropic.InternalServerError(
            "boom", response=httpx.Response(500, request=_REQUEST), body=None
        ),
    ],
)
def test_api_errors_return_none(error: Exception) -> None:
    provider, _ = _provider(error)
    assert _call(provider) is None


def test_factory_needs_both_provider_and_key() -> None:
    assert isinstance(get_provider(Settings(llm_provider="anthropic")), NullProvider)
    assert isinstance(
        get_provider(Settings(llm_provider="anthropic", anthropic_api_key="k")),  # type: ignore[arg-type]
        AnthropicProvider,
    )

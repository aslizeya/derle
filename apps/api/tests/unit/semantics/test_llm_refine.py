from typing import TypeVar

from pydantic import BaseModel

from derle.domain.models import ColumnInference, ColumnRole
from derle.ingest import RawRow, RawTable
from derle.llm.base import NullProvider
from derle.semantics.llm_refine import ColumnLabel, ColumnLabels, refine_with_llm

T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    name = "fake"
    enabled = True

    def __init__(self, answer: ColumnLabels | None) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def structured(self, *, system: str, prompt: str, schema: type[T]) -> T | None:
        self.prompts.append(prompt)
        return self.answer  # type: ignore[return-value]


TABLE = RawTable(
    sheet=None,
    header_row=1,
    headers=["Tarih", "Kim aldı"],
    col_indexes=[0, 1],
    rows=[RawRow(index=2, cells=["01.03.2026", "Ali"])],
)
CONFIDENT = ColumnInference(col_index=0, header="Tarih", role=ColumnRole.DATE, confidence=0.95)
UNSURE = ColumnInference(
    col_index=1, header="Kim aldı", role=ColumnRole.DESCRIPTION, confidence=0.4
)


def test_disabled_provider_is_a_no_op() -> None:
    assert refine_with_llm(TABLE, [CONFIDENT, UNSURE], NullProvider()) == [CONFIDENT, UNSURE]


def test_llm_upgrades_only_uncertain_columns() -> None:
    llm = FakeLLM(
        ColumnLabels(
            columns=[
                ColumnLabel(col_index=0, role=ColumnRole.AMOUNT, confidence=0.99),  # ignored
                ColumnLabel(col_index=1, role=ColumnRole.PARTY, confidence=0.9),
            ]
        )
    )
    out = refine_with_llm(TABLE, [CONFIDENT, UNSURE], llm)
    assert out[0] == CONFIDENT
    assert out[1].role == ColumnRole.PARTY
    assert out[1].engine == "llm"
    assert out[1].reasons[-1].code == "llm_suggestion"
    assert "Kim aldı" in llm.prompts[0]


def test_llm_failure_falls_back_to_rules() -> None:
    assert refine_with_llm(TABLE, [CONFIDENT, UNSURE], FakeLLM(None)) == [CONFIDENT, UNSURE]


def test_confident_rules_skip_the_llm_call() -> None:
    llm = FakeLLM(None)
    refine_with_llm(TABLE, [CONFIDENT], llm)
    assert llm.prompts == []

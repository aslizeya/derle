"""Let an LLM second-guess low-confidence column roles.

Rules always run first. The LLM only sees headers plus a handful of sample values (never
the whole file) and may only *upgrade* columns whose rule confidence is below
``REFINE_BELOW``. A confident rule result is never overridden.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from derle.domain.models import ColumnInference, ColumnRole, Reason
from derle.ingest.base import RawTable
from derle.llm.base import LLMProvider

REFINE_BELOW = 0.6
SAMPLES_PER_COLUMN = 8

SYSTEM = (
    "You label the columns of small-business spreadsheets, mostly Turkish ledgers "
    "(veresiye/cari). For each column, choose the single best role from the allowed list. "
    "Roles: party = customer/supplier/person/company name; first_name/last_name = split name "
    "parts; debit = amount the party owes (borç, veresiye); credit = amount the party paid "
    "(alacak, ödeme, tahsilat); amount = a money amount without debit/credit meaning; balance "
    "= running balance; quantity = counts or weights; description = free text such as items "
    "bought; category = small set of repeated labels; identifier = row or receipt numbers. "
    "Use 'unknown' when unsure. Confidence is your probability that the role is correct."
)


class ColumnLabel(BaseModel):
    col_index: int
    role: ColumnRole
    confidence: float = Field(ge=0, le=1)


class ColumnLabels(BaseModel):
    columns: list[ColumnLabel]


def refine_with_llm(
    table: RawTable, inferences: list[ColumnInference], llm: LLMProvider
) -> list[ColumnInference]:
    uncertain = [i for i in inferences if i.confidence < REFINE_BELOW]
    if not llm.enabled or not uncertain:
        return inferences

    columns = []
    for inf in inferences:
        pos = table.col_indexes.index(inf.col_index)
        columns.append(
            {
                "col_index": inf.col_index,
                "header": inf.header,
                "samples": table.column_values(pos)[:SAMPLES_PER_COLUMN],
            }
        )
    prompt = "Label these columns. Return one entry per column.\n" + json.dumps(
        {"columns": columns}, ensure_ascii=False
    )
    result = llm.structured(system=SYSTEM, prompt=prompt, schema=ColumnLabels)
    if result is None:
        return inferences

    labels = {label.col_index: label for label in result.columns}
    refined: list[ColumnInference] = []
    for inf in inferences:
        label = labels.get(inf.col_index)
        if (
            inf.confidence < REFINE_BELOW
            and label is not None
            and label.role != ColumnRole.UNKNOWN
            and label.confidence > inf.confidence
        ):
            refined.append(
                inf.model_copy(
                    update={
                        "role": label.role,
                        "confidence": round(label.confidence * 0.9, 3),
                        "engine": "llm",
                        "reasons": [
                            *inf.reasons,
                            Reason(code="llm_suggestion", params={"previous_role": inf.role}),
                        ],
                    }
                )
            )
        else:
            refined.append(inf)
    return refined

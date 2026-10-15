"""LLM fallback for questions the rules do not understand.

The model sees only the schema (column names, roles, types, a few sample values) and the
money model expressions, never whole tables. Its SQL then goes through exactly the same guard
as rule-generated SQL; a rejected query is reported, never executed.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from derle.analytics.schema import DatasetSchema
from derle.llm.base import LLMProvider

SYSTEM = (
    "You translate a Turkish small-business owner's question into one DuckDB SELECT over a "
    "single view. Rules: read only the given view; no other tables; one statement; no DDL or "
    "DML; use the provided expressions for money (sales = goods taken on credit / borç, "
    "payments = ödeme, balance = sales - payments) and for the customer; give every output "
    "column a short Turkish alias in double quotes; for rankings add ORDER BY and LIMIT 10; "
    "dates are DATE values; relative periods ('geçen ay', 'bu yıl') are relative to the "
    "reference date given. If the question cannot be answered from these columns, return an "
    "empty sql string."
)


class LlmSql(BaseModel):
    sql: str
    explanation: str = Field(
        description="One short Turkish sentence describing what the query does."
    )
    chart: Literal["kpi", "bar", "column", "table"] = "table"


def schema_prompt(schema: DatasetSchema, samples: dict[str, list[str]], anchor: date) -> str:
    columns = [
        {
            "name": c.name,
            "label": c.label,
            "role": c.role,
            "type": c.dtype,
            "samples": samples.get(c.name, []),
        }
        for c in schema.columns
    ]
    if schema.customer_expr:
        columns.append(
            {
                "name": "party_canonical",
                "label": "Eşleşmiş müşteri",
                "role": "customer_resolved",
                "type": "text",
            }
        )
    expressions = {
        "customer": schema.customer_expr,
        "sales": schema.sales_expr,
        "payments": schema.payments_expr,
        "balance": schema.net_expr,
    }
    return json.dumps(
        {
            "view": schema.view,
            "columns": columns,
            "expressions": {k: v for k, v in expressions.items() if v},
            "reference_date": anchor.isoformat(),
        },
        ensure_ascii=False,
    )


def generate_sql(
    llm: LLMProvider,
    question: str,
    schema: DatasetSchema,
    samples: dict[str, list[str]],
    anchor: date,
) -> LlmSql | None:
    if not llm.enabled:
        return None
    prompt = f"Schema:\n{schema_prompt(schema, samples, anchor)}\n\nQuestion: {question}"
    result = llm.structured(system=SYSTEM, prompt=prompt, schema=LlmSql)
    if result is None or not result.sql.strip():
        return None
    return result

"""Suggest a dashboard from the detected schema.

No configuration: if the dataset has customers, dates and money, the shopkeeper gets the
three things they ask about first — how much is owed, how it moves month to month, and who
owes the most. Every widget carries the SQL that produced it, shown in the UI on request.
"""

from __future__ import annotations

from typing import Any

from derle.analytics.execute import run_select
from derle.analytics.schema import DatasetSchema
from derle.storage.db import Database

TOP_N = 10


def _scalar(db: Database, sql: str) -> Any:
    _, rows, _ = run_select(db, sql, max_rows=1)
    return rows[0][0] if rows else None


def build_dashboard(db: Database, schema: DatasetSchema) -> dict[str, Any]:
    view = schema.view
    kpis: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []

    def kpi(key: str, sql: str, fmt: str) -> None:
        kpis.append({"key": key, "value": _scalar(db, sql), "format": fmt, "sql": sql})

    kpi("records", f"SELECT count(*) FROM {view}", "count")
    if schema.customer_expr:
        kpi("customers", f"SELECT count(DISTINCT {schema.customer_expr}) FROM {view}", "count")
    if schema.sales_expr:
        kpi("sales", f"SELECT sum({schema.sales_expr}) FROM {view}", "money")
    if schema.has_payments and schema.payments_expr:
        kpi("payments", f"SELECT sum({schema.payments_expr}) FROM {view}", "money")
        kpi("open_balance", f"SELECT sum({schema.net_expr}) FROM {view}", "money")

    date_col = schema.date
    if date_col is not None:
        d = schema.q(date_col)
        sql = f"SELECT min({d}) AS first, max({d}) AS last FROM {view}"
        _, rows, _ = run_select(db, sql, max_rows=1)
        if rows and rows[0][0]:
            kpis.append({"key": "period", "value": rows[0], "format": "date_range", "sql": sql})

    if date_col is not None and schema.sales_expr:
        d = schema.q(date_col)
        series = [f"sum({schema.sales_expr}) AS sales"]
        keys = ["sales"]
        if schema.has_payments and schema.payments_expr:
            series.append(f"sum({schema.payments_expr}) AS payments")
            keys.append("payments")
        sql = (
            f"SELECT strftime(date_trunc('month', {d}), '%Y-%m') AS month, {', '.join(series)}\n"
            f"FROM {view}\nWHERE {d} IS NOT NULL\nGROUP BY 1\nORDER BY 1"
        )
        columns, rows, _ = run_select(db, sql)
        charts.append(
            {
                "key": "monthly",
                "kind": "column",
                "x": "month",
                "series": keys,
                "rows": [dict(zip(columns, r, strict=True)) for r in rows],
                "sql": sql,
            }
        )

    if schema.customer_expr and schema.sales_expr:
        measure = "open_balance" if schema.has_payments else "sales"
        expr = schema.net_expr if measure == "open_balance" else schema.sales_expr
        sql = (
            f"SELECT {schema.customer_expr} AS customer, sum({expr}) AS {measure}\n"
            f"FROM {view}\nGROUP BY 1\nHAVING sum({expr}) > 0\nORDER BY 2 DESC\nLIMIT {TOP_N}"
        )
        columns, rows, _ = run_select(db, sql)
        charts.append(
            {
                "key": f"top_customers_{measure}",
                "kind": "bar",
                "x": "customer",
                "series": [measure],
                "rows": [dict(zip(columns, r, strict=True)) for r in rows],
                "sql": sql,
            }
        )

    category = schema.by_role("category")
    if category is not None and schema.sales_expr:
        sql = (
            f"SELECT {schema.q(category)} AS category, sum({schema.sales_expr}) AS sales\n"
            f"FROM {view}\nWHERE {schema.q(category)} IS NOT NULL\n"
            f"GROUP BY 1\nORDER BY 2 DESC\nLIMIT {TOP_N}"
        )
        columns, rows, _ = run_select(db, sql)
        charts.append(
            {
                "key": "by_category",
                "kind": "bar",
                "x": "category",
                "series": ["sales"],
                "rows": [dict(zip(columns, r, strict=True)) for r in rows],
                "sql": sql,
            }
        )

    return {
        "dataset_id": schema.dataset_id,
        "name": schema.name,
        "detected": {
            "customers": schema.party is not None,
            "dates": date_col is not None,
            "money": schema.has_money,
            "payments": schema.has_payments,
        },
        "kpis": kpis,
        "charts": charts,
    }

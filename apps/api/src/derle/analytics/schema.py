"""What a dataset *means*, derived from its field roles.

Ledgers record money in three shapes, sometimes all in one dataset (a family member switched
from one "Tutar" column to "Borç / Ödeme" in February):

* ``debit``  – the customer took goods on credit (borç, veresiye)
* ``credit`` – the customer paid (ödeme, tahsilat)
* ``amount`` – signed: positive is a sale on credit, negative a payment

``sales``, ``payments`` and ``net`` below fold whichever columns exist into one consistent
model, so dashboards and natural-language queries never have to care about the shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from derle.storage import repo
from derle.storage.repo import Cursor

MONEY_ROLES = ("debit", "credit", "amount", "balance")


@dataclass(frozen=True, slots=True)
class Column:
    name: str  # SQL column in the view
    key: str
    label: str
    role: str
    dtype: str
    pii: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetSchema:
    dataset_id: int
    workspace_id: int
    name: str
    view: str
    columns: tuple[Column, ...] = field(default=())

    def by_role(self, role: str) -> Column | None:
        return next((c for c in self.columns if c.role == role), None)

    def q(self, column: Column | str) -> str:
        name = column.name if isinstance(column, Column) else column
        return f'"{name}"'

    @property
    def party(self) -> Column | None:
        return self.by_role("party")

    @property
    def date(self) -> Column | None:
        return self.by_role("date")

    @property
    def customer_expr(self) -> str | None:
        """The real customer (resolved entity), falling back to the written name."""
        if self.party is None:
            return None
        return f'coalesce("party_canonical", {self.q(self.party)})'

    @property
    def has_money(self) -> bool:
        return any(self.by_role(r) for r in ("debit", "credit", "amount"))

    @property
    def sales_expr(self) -> str | None:
        terms = []
        if (debit := self.by_role("debit")) is not None:
            terms.append(f"coalesce({self.q(debit)}, 0)")
        if (amount := self.by_role("amount")) is not None:
            terms.append(f"greatest(coalesce({self.q(amount)}, 0), 0)")
        return " + ".join(terms) or None

    @property
    def payments_expr(self) -> str | None:
        terms = []
        if (credit := self.by_role("credit")) is not None:
            terms.append(f"coalesce({self.q(credit)}, 0)")
        if (amount := self.by_role("amount")) is not None:
            terms.append(f"greatest(-coalesce({self.q(amount)}, 0), 0)")
        return " + ".join(terms) or None

    @property
    def has_payments(self) -> bool:
        return self.by_role("credit") is not None or self.by_role("amount") is not None

    @property
    def net_expr(self) -> str | None:
        sales, payments = self.sales_expr, self.payments_expr
        if sales and payments:
            return f"({sales}) - ({payments})"
        return sales


def load_schema(cur: Cursor, dataset_id: int) -> DatasetSchema | None:
    row = cur.execute(
        "SELECT id, workspace_id, name FROM datasets WHERE id = ?", [dataset_id]
    ).fetchone()
    if row is None:
        return None
    columns = tuple(
        Column(
            name=repo.column_name(f["key"]),
            key=f["key"],
            label=f["label"],
            role=f["role"],
            dtype=f["dtype"],
            pii=f["pii"],
        )
        for f in repo.get_fields(cur, dataset_id)
    )
    return DatasetSchema(
        dataset_id=int(row[0]),
        workspace_id=int(row[1]),
        name=row[2],
        view=repo.view_name(dataset_id),
        columns=columns,
    )

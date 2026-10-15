"""The SQL guard is a security boundary: every bypass attempt here must be denied."""

import pytest

from derle.nlq.guard import GuardError, guard_sql

ALLOWED = {"ds_4"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT party, sum(debit) FROM ds_4 GROUP BY 1",
        "WITH t AS (SELECT * FROM ds_4) SELECT count(*) FROM t",
        "SELECT * FROM ds_4 UNION ALL SELECT * FROM ds_4",
        "SELECT strftime(date_trunc('month', date), '%Y-%m'), sum(amount) FROM ds_4 GROUP BY 1",
        "select * from DS_4",
    ],
)
def test_allowed_queries(sql: str) -> None:
    assert "LIMIT" in guard_sql(sql, ALLOWED)


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("SELECT * FROM cells", "table_not_allowed"),
        ("SELECT * FROM main.ds_4", "table_not_allowed"),
        ("SELECT * FROM ds_4 WHERE record_id IN (SELECT id FROM records)", "table_not_allowed"),
        ("SELECT * FROM 'C:/secret.csv'", "table_not_allowed"),
        ("SELECT * FROM read_csv('C:/secret.csv')", "function_not_allowed"),
        ("SELECT * FROM read_parquet('x.parquet')", "function_not_allowed"),
        ("SELECT getenv('HOME')", "function_not_allowed"),
        ("SELECT * FROM duckdb_tables()", "function_not_allowed"),
        ("SELECT * FROM glob('*')", "function_not_allowed"),
        ("DROP TABLE cells", "not_select"),
        ("DELETE FROM records", "not_select"),
        ("UPDATE cells SET value_text = 'x'", "not_select"),
        ("INSERT INTO records VALUES (1)", "not_select"),
        ("COPY ds_4 TO 'out.csv'", "not_select"),
        ("ATTACH 'other.db'", "not_select"),
        ("PRAGMA database_list", "not_select"),
        ("SET enable_external_access = true", "not_select"),
        ("SELECT 1; DELETE FROM records", "multiple_statements"),
        ("SELEC * FROM", "parse_error"),
    ],
)
def test_denied_queries(sql: str, code: str) -> None:
    with pytest.raises(GuardError) as info:
        guard_sql(sql, ALLOWED)
    assert info.value.code == code


def test_cte_names_are_allowed_but_cannot_shadow_real_tables() -> None:
    assert guard_sql("WITH x AS (SELECT * FROM ds_4) SELECT * FROM x", ALLOWED)
    with pytest.raises(GuardError):
        guard_sql("WITH x AS (SELECT * FROM cells) SELECT * FROM x", ALLOWED)


def test_existing_limit_is_kept() -> None:
    assert guard_sql("SELECT * FROM ds_4 LIMIT 5", ALLOWED).endswith("LIMIT 5")

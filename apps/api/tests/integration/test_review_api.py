"""Review, undo, live upload events and the demo endpoints."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from derle.config import Settings
from derle.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path))) as test_client:
        yield test_client


def _upload(client: TestClient, data: bytes, name: str = "mart_2026.xlsx") -> dict[str, Any]:
    response = client.post("/api/v1/workspaces/1/uploads", files={"file": (name, data)})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _parse_sse(text: str) -> list[tuple[str, Any]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_stream_upload_emits_events_then_result(client: TestClient, ledger_xlsx: bytes) -> None:
    response = client.post(
        "/api/v1/workspaces/1/uploads/stream", files={"file": ("mart_2026.xlsx", ledger_xlsx)}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "result"
    assert set(kinds[:-1]) == {"event"}
    codes = [p["code"] for k, p in events if k == "event"]
    assert codes[0] == "file_received"
    assert "column_recognized" in codes
    assert events[-1][1]["tables"][0]["duplicates"] == 1


def test_stream_upload_reports_errors_as_events(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces/1/uploads/stream", files={"file": ("x.xlsx", b"broken")}
    )
    kind, payload = _parse_sse(response.text)[-1]
    assert kind == "error"
    assert payload["code"] == "corrupt_excel"


def test_diff_shows_raw_and_clean_side_by_side(client: TestClient, ledger_xlsx: bytes) -> None:
    table_id = _upload(client, ledger_xlsx)["tables"][0]["table_id"]
    diff = client.get(f"/api/v1/tables/{table_id}/diff").json()
    assert diff["total_rows"] == 11
    by_row = {r["row_index"]: r for r in diff["rows"]}
    assert by_row[1]["skip_reason"] == "title"
    assert by_row[1]["record"] is None
    ayse = by_row[5]
    assert ayse["raw"][:3] == ["02.03.2026", "AYŞE HANIM", "980,00 TL"]
    assert ayse["record"]["values"]["party"] == "Ayşe"
    assert [t["kind"] for t in ayse["record"]["transforms"]["party"]] == ["honorific_removed"]
    dup = by_row[8]["record"]
    assert dup["status"] == "duplicate"
    assert dup["row_transforms"][0]["kind"] == "duplicate_removed"


def test_undo_number_parsing_keeps_the_original_text(
    client: TestClient, ledger_xlsx: bytes
) -> None:
    upload = _upload(client, ledger_xlsx)
    table_id, dataset_id = upload["tables"][0]["table_id"], upload["tables"][0]["dataset_id"]
    page = client.get(
        f"/api/v1/tables/{table_id}/transformations", params={"kind": "number_parsed"}
    ).json()
    target = next(t for t in page["items"] if t["before"] == "980,00 TL")
    assert {s["kind"] for s in page["summary"]} >= {"number_parsed", "date_parsed"}

    assert client.post(f"/api/v1/transformations/{target['id']}/undo").status_code == 200
    again = client.post(f"/api/v1/transformations/{target['id']}/undo")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_undone"

    records = client.get(f"/api/v1/datasets/{dataset_id}/records").json()
    record_id = str(target["record_id"])
    row = next(r for r in records["rows"] if str(r["record_id"]) == record_id)
    assert row["amount"] is None  # no longer a number…
    mark = records["marks"][record_id]["amount"]
    assert mark == {"state": "original", "kinds": [], "raw": "980,00 TL"}  # …the raw text is kept

    diff = client.get(f"/api/v1/tables/{table_id}/diff").json()
    amount = next(r for r in diff["rows"] if r["row_index"] == 5)["record"]["transforms"]["amount"]
    assert all(t["undone"] for t in amount)  # currency + number undone together


def test_undo_duplicate_restores_the_row(client: TestClient, ledger_xlsx: bytes) -> None:
    upload = _upload(client, ledger_xlsx)
    table_id, dataset_id = upload["tables"][0]["table_id"], upload["tables"][0]["dataset_id"]
    page = client.get(
        f"/api/v1/tables/{table_id}/transformations", params={"kind": "duplicate_removed"}
    ).json()
    assert client.post(f"/api/v1/transformations/{page['items'][0]['id']}/undo").status_code == 200
    assert client.get(f"/api/v1/datasets/{dataset_id}/records").json()["total"] == 6


def test_undo_whole_upload(client: TestClient, ledger_xlsx: bytes) -> None:
    upload = _upload(client, ledger_xlsx)
    dataset_id = upload["tables"][0]["dataset_id"]
    assert client.post(f"/api/v1/uploads/{upload['upload_id']}/undo").status_code == 200
    assert client.get(f"/api/v1/datasets/{dataset_id}/records").json()["total"] == 0
    assert client.get("/api/v1/workspaces/1").json()["entities"] == 0
    assert client.post(f"/api/v1/uploads/{upload['upload_id']}/undo").status_code == 409
    # The raw source is still there for the record.
    table_id = upload["tables"][0]["table_id"]
    assert client.get(f"/api/v1/tables/{table_id}/diff").json()["total_rows"] == 11


def test_parse_failures_cannot_be_undone(client: TestClient) -> None:
    data = "Tarih;Müşteri;Tutar\n01.03.2026;Ali;on beş\n".encode()
    table_id = _upload(client, data, "x.csv")["tables"][0]["table_id"]
    page = client.get(f"/api/v1/tables/{table_id}/transformations").json()
    failed = next(t for t in page["items"] if t["kind"] == "parse_failed")
    assert client.post(f"/api/v1/transformations/{failed['id']}/undo").status_code == 409


def test_records_sort_search_and_marks(client: TestClient, ledger_xlsx: bytes) -> None:
    dataset_id = _upload(client, ledger_xlsx)["tables"][0]["dataset_id"]
    url = f"/api/v1/datasets/{dataset_id}/records"
    by_amount = client.get(url, params={"sort": "amount", "desc": True}).json()["rows"]
    assert [r["amount"] for r in by_amount][:2] == [2400.0, 1250.5]
    found = client.get(url, params={"q": "yilmaz"}).json()  # folded: matches "Yılmaz"
    assert found["total"] == 2
    ignored = client.get(url, params={"sort": "amount; DROP TABLE cells"}).json()
    assert ignored["total"] == 5  # unknown sort column is ignored, not interpolated
    marks = client.get(url).json()["marks"]
    assert any(m.get("party", {}).get("kinds") == ["honorific_removed"] for m in marks.values())


def test_workspace_summary_and_uploads(client: TestClient, ledger_xlsx: bytes) -> None:
    _upload(client, ledger_xlsx)
    summary = client.get("/api/v1/workspaces/1").json()
    assert summary["records"] == 5
    assert summary["uploads"] == 1
    uploads = client.get("/api/v1/workspaces/1/uploads").json()
    assert uploads[0]["filename"] == "mart_2026.xlsx"
    assert uploads[0]["records"] == 5
    assert client.get("/api/v1/workspaces/999").status_code == 404


def test_demo_flow(client: TestClient) -> None:
    workspace = client.post("/api/v1/demo/workspaces").json()
    assert workspace["is_demo"]
    files = client.get("/api/v1/demo/files").json()
    assert len(files) == 6
    first = client.get(f"/api/v1/demo/files/{files[0]['name']}")
    assert first.status_code == 200
    assert len(first.content) == files[0]["size"]
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/uploads",
        files={"file": (files[0]["name"], first.content)},
    )
    assert response.status_code == 201
    # Demo workspaces stay out of the user's own workspace list.
    assert all(not w["is_demo"] for w in client.get("/api/v1/workspaces").json())
    assert client.get("/api/v1/demo/files/nope.csv").status_code == 404


def test_create_workspace(client: TestClient) -> None:
    created = client.post("/api/v1/workspaces", json={"name": "Dükkan"}).json()
    assert created["name"] == "Dükkan"
    assert client.post("/api/v1/workspaces", json={"name": ""}).status_code == 422

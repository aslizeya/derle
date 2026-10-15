from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from derle.config import Settings
from derle.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(Settings(data_dir=tmp_path, llm_provider="none"))
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_ai_disabled(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert body == {"status": "ok", "ai_enabled": False, "ai_provider": "none"}


def test_upload_then_browse_then_trace(client: TestClient, ledger_xlsx: bytes) -> None:
    (workspace,) = client.get("/api/v1/workspaces").json()
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/uploads",
        files={"file": ("mart_2026.xlsx", ledger_xlsx)},
    )
    assert response.status_code == 201, response.text
    upload = response.json()
    dataset_id = upload["tables"][0]["dataset_id"]

    datasets = client.get(f"/api/v1/workspaces/{workspace['id']}/datasets").json()
    assert datasets[0]["records"] == 5
    assert datasets[0]["duplicates"] == 1

    dataset = client.get(f"/api/v1/datasets/{dataset_id}").json()
    amount = next(f for f in dataset["fields"] if f["key"] == "amount")

    page = client.get(f"/api/v1/datasets/{dataset_id}/records", params={"limit": 2}).json()
    assert page["total"] == 5
    assert len(page["rows"]) == 2

    record_id = page["rows"][0]["record_id"]
    prov = client.get(f"/api/v1/records/{record_id}/cells/{amount['id']}/provenance").json()
    assert prov["source"]["row"] == 4
    assert prov["original"] == "1250.5"

    detail = client.get(f"/api/v1/uploads/{upload['upload_id']}").json()
    assert detail["status"] == "done"
    assert detail["tables"][0]["columns"][0]["role"] == "date"


def test_bad_file_returns_error_code(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces/1/uploads", files={"file": ("defter.xls", b"\xd0\xcf\x11\xe0")}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "legacy_xls"


def test_unknown_resources_are_404(client: TestClient) -> None:
    assert client.get("/api/v1/datasets/999").status_code == 404
    assert client.get("/api/v1/records/1/cells/1/provenance").status_code == 404

"""Entity resolution through the database: upload → entities → review → undo."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from derle.config import Settings
from derle.main import create_app
from derle.services import entities, queries
from derle.services.ingest import ingest_file
from derle.storage.db import Database
from tests.conftest import make_csv

TODAY = date(2026, 10, 14)

MARCH = make_csv(
    [
        ["Tarih", "Müşteri", "Tutar", "Tel"],
        ["01.03.2026", "Ahmet Yılmaz", "100", "0532 123 45 67"],
        ["02.03.2026", "Mehmet Yılmaz", "200", ""],
        ["03.03.2026", "Murat Yılmaz", "300", ""],
        ["04.03.2026", "Ahmet Yılmz", "50", ""],
    ]
)
APRIL = make_csv(
    [
        ["Tarih", "Müşteri", "Tutar", "Tel"],
        ["01.04.2026", "ahmet bey", "75", "05321234567"],
        ["02.04.2026", "M. Yılmaz", "120", ""],
    ]
)


def _upload(db: Database, workspace_id: int, data: bytes, name: str) -> int:
    result = ingest_file(db, workspace_id=workspace_id, data=data, filename=name, today=TODAY)
    return result.tables[0].dataset_id


def _entity_names(db: Database, workspace_id: int) -> dict[str, int]:
    with db.read() as cur:
        items, _ = entities.list_entities(cur, workspace_id, limit=100, offset=0)
    return {i["name"]: i["record_count"] for i in items}


def test_upload_resolves_entities_across_files(db: Database, workspace_id: int) -> None:
    _upload(db, workspace_id, MARCH, "mart_2026.csv")
    dataset_id = _upload(db, workspace_id, APRIL, "nisan_2026.csv")
    # "Ahmet Yılmz" (typo) and "ahmet bey" (same phone) join Ahmet Yılmaz.
    assert _entity_names(db, workspace_id) == {
        "Ahmet Yılmaz": 3,
        "Mehmet Yılmaz": 1,
        "Murat Yılmaz": 1,
        "M. Yılmaz": 1,
    }
    with db.read() as cur:
        rows, _ = queries.list_records(cur, dataset_id, limit=50, offset=0)
    assert {r["party"]: r["party_canonical"] for r in rows}["Ahmet"] == "Ahmet Yılmaz"


def test_review_decision_merges_and_undo_restores(db: Database, workspace_id: int) -> None:
    _upload(db, workspace_id, MARCH, "mart_2026.csv")
    _upload(db, workspace_id, APRIL, "nisan_2026.csv")
    with db.read() as cur:
        cards, total = entities.list_candidates(cur, workspace_id)
    assert total == 2  # "M. Yılmaz" could be Mehmet or Murat
    mehmet_card = next(c for c in cards if "mehmet" in c["left"]["profile"] + c["right"]["profile"])
    assert mehmet_card["evidence"][0]["code"] == "initials_match"

    with db.transaction() as cur:
        version_id, summary = entities.decide(cur, mehmet_card["id"], "same")
    assert summary.pending == 0
    names = _entity_names(db, workspace_id)
    assert names["Mehmet Yılmaz"] == 2
    assert "M. Yılmaz" not in names

    with db.transaction() as cur:
        undo_version, candidate_id, summary = entities.undo_last_decision(cur, workspace_id)
    assert candidate_id == mehmet_card["id"]
    assert undo_version > version_id
    assert summary.pending == 2
    assert _entity_names(db, workspace_id)["M. Yılmaz"] == 1


def test_entity_ids_stay_stable_across_runs(db: Database, workspace_id: int) -> None:
    _upload(db, workspace_id, MARCH, "mart_2026.csv")
    before = _entity_names(db, workspace_id)
    with db.read() as cur:
        ids_before = {
            i["name"]: i["id"]
            for i in entities.list_entities(cur, workspace_id, limit=100, offset=0)[0]
        }
    _upload(db, workspace_id, APRIL, "nisan_2026.csv")
    with db.read() as cur:
        ids_after = {
            i["name"]: i["id"]
            for i in entities.list_entities(cur, workspace_id, limit=100, offset=0)[0]
        }
    for name in before:
        assert ids_after[name] == ids_before[name]


def test_membership_history_is_kept(db: Database, workspace_id: int) -> None:
    _upload(db, workspace_id, MARCH, "mart_2026.csv")
    _upload(db, workspace_id, APRIL, "nisan_2026.csv")
    with db.read() as cur:
        cards, _ = entities.list_candidates(cur, workspace_id)
    with db.transaction() as cur:
        entities.decide(cur, cards[0]["id"], "same")
    with db.read() as cur:
        closed = cur.execute(
            "SELECT count(*) FROM entity_members WHERE version_to IS NOT NULL"
        ).fetchone()
    assert closed is not None and closed[0] == 1  # M. Yılmaz's old membership, not deleted


def test_deciding_twice_is_rejected(db: Database, workspace_id: int) -> None:
    _upload(db, workspace_id, MARCH, "mart_2026.csv")
    _upload(db, workspace_id, APRIL, "nisan_2026.csv")
    with db.read() as cur:
        cards, _ = entities.list_candidates(cur, workspace_id)
    with db.transaction() as cur:
        entities.decide(cur, cards[0]["id"], "different")
    with pytest.raises(entities.MatchError, match="candidate_not_pending"), db.transaction() as cur:
        entities.decide(cur, cards[0]["id"], "same")


# --- API ------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path))) as test_client:
        yield test_client


def test_review_queue_api(client: TestClient) -> None:
    for name, data in (("mart_2026.csv", MARCH), ("nisan_2026.csv", APRIL)):
        assert (
            client.post("/api/v1/workspaces/1/uploads", files={"file": (name, data)}).status_code
            == 201
        )

    queue = client.get("/api/v1/workspaces/1/matches").json()
    assert queue["total"] == 2
    card = queue["cards"][0]
    sides = {card["left"]["entity"]["name"], card["right"]["entity"]["name"]}
    assert "M. Yılmaz" in sides
    assert card["left"]["entity"]["samples"][0]["filename"] in {"mart_2026.csv", "nisan_2026.csv"}

    other = (sides - {"M. Yılmaz"}).pop()
    response = client.post(f"/api/v1/matches/{card['id']}/decision", json={"decision": "different"})
    assert response.status_code == 200
    # "M. Yılmaz is not <other>" leaves exactly one possible owner, so the next run assigns it
    # automatically and the second card disappears: decisions feed later matching.
    assert response.json()["pending"] == 0
    names = {
        e["name"]: e["record_count"]
        for e in client.get("/api/v1/workspaces/1/entities").json()["items"]
    }
    assert "M. Yılmaz" not in names
    assert names[other] == 1

    assert (
        client.post(f"/api/v1/matches/{card['id']}/decision", json={"decision": "same"}).status_code
        == 409
    )
    assert (
        client.post("/api/v1/matches/999999/decision", json={"decision": "same"}).status_code == 404
    )
    assert (
        client.post(
            f"/api/v1/matches/{card['id']}/decision", json={"decision": "maybe"}
        ).status_code
        == 422
    )

    undo = client.post("/api/v1/workspaces/1/matches/undo").json()
    assert undo["candidate_id"] == card["id"]
    assert undo["pending"] == 2

    entities_page = client.get("/api/v1/workspaces/1/entities", params={"q": "yilmaz"}).json()
    assert entities_page["total"] == 4
    ahmet = next(e for e in entities_page["items"] if e["name"] == "Ahmet Yılmaz")
    detail = client.get(f"/api/v1/entities/{ahmet['id']}").json()
    assert detail["record_count"] == 3
    assert detail["phones"] == ["0532 123 45 67"]
    assert {a["name"] for a in detail["aliases"]} == {"Ahmet Yılmaz", "Ahmet Yılmz", "Ahmet"}
    assert detail["totals"] == {"amount": 225.0}


def test_undo_with_nothing_to_undo(client: TestClient) -> None:
    response = client.post("/api/v1/workspaces/1/matches/undo")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "nothing_to_undo"

"""HTTP tests for the journal import / review routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import journal_routes

SAMPLE = (
    "招商证券股份有限公司交割单\n"
    "成交日期,成交时间,证券代码,证券名称,买卖标志,成交数量,成交价格,成交金额,佣金,印花税,过户费\n"
    "20261009,09:35:12,000001,平安银行,买入,1000,11.80,11800.00,5.00,0.00,0.10\n"
    "20261015,14:20:01,000001,平安银行,卖出,1000,12.10,12100.00,5.00,6.05,0.10\n"
)


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("VIBE_TRADING_HOME", str(tmp_path))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "journal.csv").write_text(SAMPLE, encoding="gbk")

    app = FastAPI()
    journal_routes.register_journal_routes(app, require_auth=lambda: None)
    return TestClient(app)


def test_import_summary_analysis_and_delete(client):
    imported = client.post("/api/journal/import", json={"file_path": "uploads/journal.csv", "filename": "招商交割单.csv"})
    assert imported.status_code == 200
    body = imported.json()
    assert body["status"] == "ok"
    assert body["format"] == "cn_broker"
    assert body["inserted"] == 2
    assert body["duplicates"] == 0

    summary = client.get("/api/journal/summary").json()
    assert summary["records"] == 2
    assert summary["symbols"] == 1
    assert len(summary["batches"]) == 1
    assert summary["batches"][0]["filename"] == "招商交割单.csv"

    analysis = client.get("/api/journal/analysis").json()
    assert analysis["status"] == "ok"
    assert analysis["profile"]["total_pnl"] == pytest.approx(283.75)
    assert analysis["monthly_pnl"][0]["month"] == "2026-10"

    trades = client.get("/api/journal/trades", params={"symbol": "000001.SZ"}).json()
    assert trades["count"] == 2
    assert [row["side"] for row in trades["trades"]] == ["buy", "sell"]

    removed = client.delete(f"/api/journal/imports/{body['import_id']}")
    assert removed.status_code == 200
    assert removed.json()["trades"] == 2
    assert client.get("/api/journal/summary").json()["records"] == 0


def test_reimport_is_idempotent(client):
    assert client.post("/api/journal/import", json={"file_path": "uploads/journal.csv"}).status_code == 200
    again = client.post("/api/journal/import", json={"file_path": "uploads/journal.csv"}).json()

    assert again["inserted"] == 0
    assert again["duplicates"] == 2
    assert client.get("/api/journal/summary").json()["records"] == 2


def test_missing_file_is_404(client):
    response = client.post("/api/journal/import", json={"file_path": "uploads/nope.csv"})
    assert response.status_code == 404


def test_unsupported_extension_is_400(client, tmp_path):
    (Path(tmp_path) / "uploads" / "note.txt").write_text("hello", encoding="utf-8")
    response = client.post("/api/journal/import", json={"file_path": "uploads/note.txt"})
    assert response.status_code == 400


def test_unrecognized_format_is_422(client, tmp_path):
    (Path(tmp_path) / "uploads" / "weird.csv").write_text(
        "alpha,beta,gamma\n1,2,3\n", encoding="utf-8"
    )
    response = client.post("/api/journal/import", json={"file_path": "uploads/weird.csv"})
    assert response.status_code == 422


def test_delete_unknown_import_is_404(client):
    assert client.delete("/api/journal/imports/deadbeef").status_code == 404


def test_empty_journal_analysis(client):
    assert client.get("/api/journal/analysis").json() == {"status": "empty", "records": 0}

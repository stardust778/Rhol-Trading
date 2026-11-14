"""HTTP tests for the Chan analysis routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import chan_routes

STRUCTURE = {
    "symbol": "000001.SZ",
    "bars": 693,
    "bis": [{"start": "2026-10-09", "end": "2026-10-26", "direction": "down"}],
    "centers": [{"start": "2026-08-03", "end": "2026-11-09", "zg": 11.41, "zd": 11.27}],
    "signals": [{"date": "2026-11-12", "type": "3buy", "price": 11.66}],
    "latest": {"bi_direction": "down", "center": {"zg": 11.41, "zd": 11.27}},
}

REVIEW = {
    "symbol": "000001.SZ",
    "structure": {"bars": 693, "latest": STRUCTURE["latest"], "centers": [], "signals": []},
    "trades": [{"trade_id": "t1", "side": "buy", "verdict": {"key": "match_1buy", "quality": "good"}}],
}


@pytest.fixture(autouse=True)
def _clear_cache():
    chan_routes._CACHE.clear()
    yield
    chan_routes._CACHE.clear()


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(chan_routes, "_build_structure", lambda symbol, start, end: STRUCTURE)
    monkeypatch.setattr(chan_routes, "_review_symbol", lambda symbol, start, end: REVIEW)
    app = FastAPI()
    chan_routes.register_chan_routes(app, require_auth=lambda: None)
    return TestClient(app)


def test_analysis_returns_structure(client):
    response = client.get("/api/chan/analysis", params={"symbol": "000001.SZ"})

    assert response.status_code == 200
    assert response.json()["signals"][0]["type"] == "3buy"


def test_analysis_caches_repeat_requests(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        chan_routes,
        "_build_structure",
        lambda symbol, start, end: calls.append(symbol) or STRUCTURE,
    )

    assert client.get("/api/chan/analysis", params={"symbol": "600519.SH"}).status_code == 200
    assert client.get("/api/chan/analysis", params={"symbol": "600519.SH"}).status_code == 200
    assert calls == ["600519.SH"]


def test_review_returns_trade_verdicts(client):
    response = client.get("/api/chan/review", params={"symbol": "000001.SZ"})

    assert response.status_code == 200
    assert response.json()["trades"][0]["verdict"]["key"] == "match_1buy"


def test_signals_helper_returns_only_signals(client):
    response = client.get("/api/chan/signals", params={"symbol": "000001.SZ"})

    assert response.status_code == 200
    assert response.json() == {"symbol": "000001.SZ", "signals": STRUCTURE["signals"]}


def test_analysis_maps_missing_data_to_404(client, monkeypatch):
    def boom(symbol, start, end):
        raise ValueError("No daily bars for BAD.XX")

    monkeypatch.setattr(chan_routes, "_build_structure", boom)

    response = client.get("/api/chan/analysis", params={"symbol": "BAD.XX"})

    assert response.status_code == 404
    assert "No daily bars" in response.json()["detail"]

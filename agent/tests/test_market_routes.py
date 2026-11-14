"""Tests for the market-data (K-line) HTTP route."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import market_routes


def _client() -> TestClient:
    app = FastAPI()
    market_routes.register_market_routes(app, require_auth=lambda: None)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_chart_cache():
    market_routes._CHART_CACHE.clear()
    yield
    market_routes._CHART_CACHE.clear()


def _payload(rows=None, provenance=None, unresolved=None):
    body = {
        "000001.SZ": rows
        if rows is not None
        else [
            {"trade_date": "2026-11-12T00:00:00", "open": 11.69, "high": 11.83, "low": 11.66, "close": 11.79, "volume": 1082721.0},
            {"trade_date": "2026-11-13T00:00:00", "open": 11.76, "high": 12.10, "low": 11.70, "close": 12.07, "volume": 2189430.0},
        ],
        "_provenance": {
            "000001.SZ": provenance
            if provenance is not None
            else {
                "source": "tencent",
                "requested_source": "auto",
                "detected_source": "tencent",
                "fallback_used": False,
                "adjustment": "split_dividend_additive",
                "volume_unit": "lots",
            }
        },
    }
    if unresolved is not None:
        body["_unresolved"] = unresolved
    return body


def test_ohlc_returns_normalized_bars(monkeypatch):
    calls = []

    def fake_fetch(**kwargs):
        calls.append(kwargs)
        return _payload()

    monkeypatch.setattr("src.market_data.fetch_market_data", fake_fetch)

    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "start": "2026-11-01", "end": "2026-11-13", "interval": "1D"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "000001.SZ"
    assert body["source"] == "tencent"
    assert body["adjustment"] == "split_dividend_additive"
    assert body["volume_unit"] == "lots"
    assert [bar["time"] for bar in body["bars"]] == ["2026-11-12", "2026-11-13"]
    assert body["bars"][-1]["close"] == 12.07
    assert body["bars"][-1]["volume"] == 2189430.0
    assert calls[0]["codes"] == ["000001.SZ"]
    assert calls[0]["max_rows"] == 0


def test_ohlc_defaults_to_one_year_window(monkeypatch):
    seen = {}

    def fake_fetch(**kwargs):
        seen.update(kwargs)
        return _payload()

    monkeypatch.setattr("src.market_data.fetch_market_data", fake_fetch)

    response = _client().get("/api/market/ohlc", params={"symbol": "000001.SZ"})

    assert response.status_code == 200
    assert seen["end_date"] > seen["start_date"]
    assert seen["source"] == "auto"


def test_ohlc_caches_repeat_requests(monkeypatch):
    calls = []

    def fake_fetch(**kwargs):
        calls.append(kwargs)
        return _payload()

    monkeypatch.setattr("src.market_data.fetch_market_data", fake_fetch)
    client = _client()
    params = {"symbol": "000001.SZ", "start": "2026-11-01", "end": "2026-11-13"}

    assert client.get("/api/market/ohlc", params=params).status_code == 200
    assert client.get("/api/market/ohlc", params=params).status_code == 200

    assert len(calls) == 1


def test_ohlc_404_when_unresolved(monkeypatch):
    monkeypatch.setattr(
        "src.market_data.fetch_market_data",
        lambda **kwargs: {"_unresolved": ["BAD.XX"], "_provenance": {}},
    )

    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "start": "2026-11-01", "end": "2026-11-13"},
    )

    assert response.status_code == 404
    assert "BAD.XX" in response.json()["detail"]


def test_ohlc_rejects_bad_interval():
    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "interval": "5m"},
    )
    assert response.status_code == 400


def test_ohlc_rejects_bad_date():
    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "start": "13/11/2026"},
    )
    assert response.status_code == 400


def test_ohlc_rejects_inverted_window():
    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "start": "2026-11-13", "end": "2026-11-01"},
    )
    assert response.status_code == 400


def test_ohlc_maps_fetch_failure_to_502(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("src.market_data.fetch_market_data", boom)

    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "start": "2026-11-01", "end": "2026-11-13"},
    )

    assert response.status_code == 502


def test_ohlc_trims_to_max_bars(monkeypatch):
    rows = [
        {"trade_date": f"2026-10-{day:02d}", "open": 10 + day, "high": 11 + day, "low": 9 + day, "close": 10.5 + day, "volume": 100.0}
        for day in range(1, 21)
    ]
    monkeypatch.setattr("src.market_data.fetch_market_data", lambda **kwargs: _payload(rows=rows))

    response = _client().get(
        "/api/market/ohlc",
        params={"symbol": "000001.SZ", "start": "2026-10-01", "end": "2026-10-31", "max_bars": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["bars"]) == 5
    assert body["bars"][-1]["time"] == "2026-10-20"


def test_ohlc_rejects_bare_ticker_before_fetching(monkeypatch):
    calls = []
    monkeypatch.setattr("src.market_data.fetch_market_data", lambda **kwargs: calls.append(kwargs) or {})

    response = _client().get("/api/market/ohlc", params={"symbol": "BAD"})

    assert response.status_code == 400
    assert "suffix" in response.json()["detail"]
    assert calls == []

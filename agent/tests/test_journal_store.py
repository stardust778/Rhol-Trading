"""Tests for the durable trade-journal store and its analysis roll-ups."""

from __future__ import annotations

import pandas as pd
import pytest

from src.journal import analysis, store
from src.tools.trade_journal_parsers import TradeRecord


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_TRADING_HOME", str(tmp_path))
    yield


def _records() -> list[TradeRecord]:
    return [
        TradeRecord(
            datetime="2026-10-09 09:35:12", symbol="000001.SZ", name="平安银行",
            side="buy", quantity=1000, price=11.80, amount=11800.0, fee=5.1,
            market="china_a",
        ),
        TradeRecord(
            datetime="2026-10-15 14:20:01", symbol="000001.SZ", name="平安银行",
            side="sell", quantity=1000, price=12.10, amount=12100.0, fee=11.15,
            market="china_a",
        ),
        TradeRecord(
            datetime="2026-11-02 10:00:00", symbol="600519.SH", name="贵州茅台",
            side="buy", quantity=100, price=1400.0, amount=140000.0, fee=5.1,
            market="china_a",
        ),
    ]


def test_import_dedupes_overlapping_statements():
    first = store.import_records(_records(), filename="oct.csv", format_name="cn_broker")
    assert first["inserted"] == 3
    assert first["duplicates"] == 0

    again = store.import_records(_records(), filename="oct-again.csv", format_name="cn_broker")
    assert again["inserted"] == 0
    assert again["duplicates"] == 3

    assert store.stats()["records"] == 3


def test_stats_and_symbol_filter():
    store.import_records(_records(), filename="oct.csv", format_name="cn_broker")
    stats = store.stats()

    assert stats["records"] == 3
    assert stats["symbols"] == 2
    assert stats["imports"] == 1
    assert stats["first_date"].startswith("2026-10-09")

    pingan = store.load_trades(symbol="000001.SZ")
    assert len(pingan) == 2
    assert all(row["symbol"] == "000001.SZ" for row in pingan)


def test_delete_import_removes_its_trades():
    summary = store.import_records(_records(), filename="oct.csv", format_name="cn_broker")
    store.import_records(
        [TradeRecord(
            datetime="2026-09-01 10:00:00", symbol="600000.SH", name="浦发银行",
            side="buy", quantity=100, price=10.0, amount=1000.0, fee=5.0,
            market="china_a",
        )],
        filename="sep.csv",
        format_name="cn_broker",
    )

    removed = store.delete_import(summary["import_id"])

    assert removed["imports"] == 1
    assert removed["trades"] == 3
    remaining = store.load_trades()
    assert [row["symbol"] for row in remaining] == ["600000.SH"]


def test_load_dataframe_matches_analysis_contract():
    store.import_records(_records(), filename="oct.csv", format_name="cn_broker")
    frame = store.load_dataframe()

    assert list(frame.columns) == [
        "datetime", "symbol", "name", "side", "quantity",
        "price", "amount", "fee", "market",
    ]
    assert pd.api.types.is_datetime64_any_dtype(frame["datetime"])
    assert frame["datetime"].is_monotonic_increasing


def test_analysis_reports_realized_pnl_and_monthly_rollup():
    store.import_records(_records(), filename="oct.csv", format_name="cn_broker")
    result = analysis.build_analysis()

    assert result["status"] == "ok"
    assert result["records"] == 3
    assert result["profile"]["total_roundtrips"] == 1
    assert result["profile"]["total_pnl"] == pytest.approx(283.75)
    assert result["monthly_pnl"] == [
        {"month": "2026-10", "pnl": pytest.approx(283.75), "trades": 1, "wins": 1, "losses": 0}
    ]
    assert result["roundtrips"][0]["symbol"] == "000001.SZ"


def test_analysis_of_empty_journal():
    assert analysis.build_analysis() == {"status": "empty", "records": 0}


def test_monthly_pnl_groups_by_close_month():
    trips = [
        {"sell_dt": "2026-10-15 14:20:01", "pnl": 100.0},
        {"sell_dt": "2026-10-20 10:00:00", "pnl": -40.0},
        {"sell_dt": "2026-11-03 10:00:00", "pnl": 25.0},
    ]
    monthly = analysis.monthly_pnl(trips)

    assert [row["month"] for row in monthly] == ["2026-10", "2026-11"]
    assert monthly[0]["pnl"] == 60.0
    assert monthly[0]["wins"] == 1 and monthly[0]["losses"] == 1

"""Tests for Chan structure derivation, trade verdicts and review joins."""

from __future__ import annotations

import pandas as pd
import pytest

from src.chan import analyzer


def _bi(start, end, start_price, end_price, direction, change, index=0):
    return {
        "start": start,
        "end": end,
        "start_price": start_price,
        "end_price": end_price,
        "direction": direction,
        "high": max(start_price, end_price),
        "low": min(start_price, end_price),
        "change": change,
        "index": index,
    }


def _center(start, end, zg, zd, direction="up"):
    return {
        "start": start,
        "end": end,
        "zg": zg,
        "zd": zd,
        "gg": zg + 0.5,
        "dd": zd - 0.5,
        "valid": True,
        "direction": direction,
    }


def test_derive_signals_first_and_second_buy():
    bis = [
        _bi("2026-01-01", "2026-01-05", 12.0, 10.0, "down", -0.20),
        _bi("2026-01-05", "2026-01-08", 10.0, 11.5, "up", 0.15),
        _bi("2026-01-08", "2026-01-12", 11.5, 9.8, "down", -0.12),
        _bi("2026-01-12", "2026-01-15", 9.8, 11.0, "up", 0.12),
        _bi("2026-01-15", "2026-01-18", 11.0, 9.9, "down", -0.10),
    ]

    signals = analyzer.derive_signals(bis, [])

    types = [(s["type"], s["date"], s["price"]) for s in signals]
    assert ("1buy", "2026-01-12", 9.8) in types
    assert ("2buy", "2026-01-18", 9.9) in types


def test_derive_signals_first_and_second_sell():
    bis = [
        _bi("2026-01-01", "2026-01-05", 10.0, 12.0, "up", 0.20),
        _bi("2026-01-05", "2026-01-08", 12.0, 10.5, "down", -0.12),
        _bi("2026-01-08", "2026-01-12", 10.5, 12.4, "up", 0.11),
        _bi("2026-01-12", "2026-01-15", 12.4, 10.8, "down", -0.13),
        _bi("2026-01-15", "2026-01-18", 10.8, 12.2, "up", 0.10),
    ]

    signals = analyzer.derive_signals(bis, [])

    types = [(s["type"], s["date"], s["price"]) for s in signals]
    assert ("1sell", "2026-01-12", 12.4) in types
    assert ("2sell", "2026-01-18", 12.2) in types


def test_derive_signals_third_buy_requires_breakout_and_hold():
    centers = [_center("2026-01-01", "2026-01-10", zg=10.5, zd=10.0)]
    bis = [
        _bi("2026-01-10", "2026-01-15", 10.0, 11.2, "up", 0.12),
        _bi("2026-01-15", "2026-01-18", 11.2, 10.8, "down", -0.04),
    ]

    signals = analyzer.derive_signals(bis, centers)

    assert any(s["type"] == "3buy" and s["price"] == 10.8 for s in signals)


def test_derive_signals_third_buy_rejects_pullback_into_center():
    centers = [_center("2026-01-01", "2026-01-10", zg=10.5, zd=10.0)]
    bis = [
        _bi("2026-01-10", "2026-01-15", 10.0, 11.2, "up", 0.12),
        _bi("2026-01-15", "2026-01-18", 11.2, 10.3, "down", -0.09),
    ]

    signals = analyzer.derive_signals(bis, centers)

    assert not any(s["type"] == "3buy" for s in signals)


@pytest.mark.parametrize(
    ("side", "price", "signal_type", "center", "bi_direction", "key", "quality"),
    [
        ("buy", 10.2, "1buy", None, "down", "match_1buy", "good"),
        # An opposite-side signal is only a veto when no same-side signal matched.
        ("buy", 10.2, "3sell", None, "down", "no_structure", "neutral"),
        ("buy", 10.2, None, _center("2026-01-01", "2026-01-10", 10.5, 10.0), "down", "zone_inside", "neutral"),
        ("buy", 11.0, None, _center("2026-01-01", "2026-01-10", 10.5, 10.0), "up", "above_chase", "poor"),
        ("buy", 11.0, None, _center("2026-01-01", "2026-01-10", 10.5, 10.0), "down", "above_pullback", "neutral"),
        ("buy", 9.5, None, _center("2026-01-01", "2026-01-10", 10.5, 10.0), "down", "below_against", "poor"),
        ("sell", 9.5, None, _center("2026-01-01", "2026-01-10", 10.5, 10.0), "down", "below_panic", "poor"),
        ("sell", 9.5, None, _center("2026-01-01", "2026-01-10", 10.5, 10.0), "up", "below_rebound", "neutral"),
    ],
)
def test_classify_trade(side, price, signal_type, center, bi_direction, key, quality):
    signal = {"date": "2026-01-05", "type": signal_type, "price": price} if signal_type else None

    verdict = analyzer.classify_trade(
        side=side, price=price, signal=signal, center=center, bi_direction=bi_direction
    )

    assert verdict["key"] == key
    assert verdict["quality"] == quality


def test_classify_trade_flags_filling_against_an_opposite_signal():
    verdict = analyzer.classify_trade(
        side="buy",
        price=11.8,
        signal=None,
        center=None,
        bi_direction="up",
        opposing={"date": "2026-10-09", "type": "1sell", "price": 11.89},
    )

    assert verdict["key"] == "against_signal"
    assert verdict["quality"] == "poor"


def test_review_trades_matches_signal_and_forward_returns():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    frame = pd.DataFrame(
        {
            "open": [10.0] * 30,
            "high": [10.2] * 30,
            "low": [9.8] * 30,
            "close": [10.0 + index * 0.1 for index in range(30)],
            "volume": [1000] * 30,
        },
        index=dates,
    )
    structure = {
        "bis": [_bi("2026-01-01", "2026-01-05", 10.0, 10.4, "up", 0.04)],
        "centers": [_center("2026-01-01", "2026-01-05", 10.3, 10.1)],
        "signals": [{"date": "2026-01-06", "type": "1buy", "price": 10.5, "bi_direction": "down"}],
    }
    trades = [
        {"trade_id": "t1", "datetime": "2026-01-06 10:00:00", "side": "buy", "price": 10.5},
    ]

    reviews = analyzer.review_trades(structure=structure, frame=frame, trades=trades)

    assert len(reviews) == 1
    review = reviews[0]
    assert review["verdict"]["key"] == "match_1buy"
    assert review["signal"]["type"] == "1buy"
    # 2026-01-06 close is 10.5; five bars later (2026-01-11) it is 11.0.
    assert review["forward"]["5"] == pytest.approx(4.76)


def test_review_trades_skips_dividends_and_unknown_dates():
    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        {"open": [10.0] * 5, "high": [10.0] * 5, "low": [10.0] * 5, "close": [10.0] * 5, "volume": [1] * 5},
        index=dates,
    )
    structure = {"bis": [], "centers": [], "signals": []}
    trades = [
        {"trade_id": "t1", "datetime": "2026-01-03 10:00:00", "side": "dividend", "price": 0},
        {"trade_id": "t2", "datetime": "2026-02-03 10:00:00", "side": "buy", "price": 10},
    ]

    assert analyzer.review_trades(structure=structure, frame=frame, trades=trades) == []


def test_review_marks_parent_interval_confirmation():
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    frame = pd.DataFrame(
        {"open": [10.0] * 10, "high": [10.2] * 10, "low": [9.8] * 10, "close": [10.0] * 10, "volume": [1000] * 10},
        index=dates,
    )
    child_structure = {"bis": [], "centers": [], "signals": []}
    parent_structure = {
        "bis": [],
        "centers": [],
        "signals": [{"date": "2026-01-05", "type": "1buy", "price": 9.9}],
    }
    trades = [{"trade_id": "t1", "datetime": "2026-01-05 10:00:00", "side": "buy", "price": 10.0}]

    review = analyzer.review_trades(
        structure=child_structure,
        frame=frame,
        trades=trades,
        interval="1D",
        parent=(frame, parent_structure),
    )[0]

    assert review["nested"]["interval"] == "1W"
    assert review["nested"]["signal"]["type"] == "1buy"
    assert review["nested"]["supporting"] is True


def test_review_includes_ma_volume_rules():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    closes = [10.0 + index * 0.05 for index in range(30)]
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": [1000] * 30,
        },
        index=dates,
    )
    trades = [{"trade_id": "t1", "datetime": "2026-01-30 10:00:00", "side": "buy", "price": closes[-1]}]

    review = analyzer.review_trades(
        structure={"bis": [], "centers": [], "signals": []},
        frame=frame,
        trades=trades,
        interval="1D",
    )[0]

    assert review["ma_volume"]
    assert all({"key", "effect"} <= set(rule) for rule in review["ma_volume"])

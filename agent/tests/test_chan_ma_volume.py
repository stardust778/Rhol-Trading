"""Tests for the MA/volume review rules."""

from __future__ import annotations

import pandas as pd
import pytest

from src.chan import ma_volume


def _frame(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    volume = volumes or [1000.0] * len(closes)
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value * 1.01 for value in closes],
            "low": [value * 0.99 for value in closes],
            "close": closes,
            "volume": volume,
        },
        index=index,
    )


def test_bull_stack_supports_a_buy():
    frame = _frame([float(value) for value in range(1, 31)])

    rules = ma_volume.analyze(frame, len(frame) - 1, "buy")

    keys = [rule["key"] for rule in rules]
    assert "ma_bull_stack" in keys
    assert all(rule["effect"] == "support" for rule in rules if rule["key"] == "ma_bull_stack")


def test_bear_stack_is_against_a_buy_and_supports_a_sell():
    frame = _frame([float(value) for value in range(60, 30, -1)])

    buy_rules = ma_volume.analyze(frame, len(frame) - 1, "buy")
    sell_rules = ma_volume.analyze(frame, len(frame) - 1, "sell")

    buy_rule = next(rule for rule in buy_rules if rule["key"] == "ma_bear_stack")
    sell_rule = next(rule for rule in sell_rules if rule["key"] == "ma_bear_stack")
    assert buy_rule["effect"] == "against"
    assert sell_rule["effect"] == "support"


def test_pullback_shrink_is_detected_near_ma20():
    closes = [10.0] * 29 + [10.02]
    volumes = [1000.0] * 29 + [300.0]
    frame = _frame(closes, volumes)

    keys = [rule["key"] for rule in ma_volume.analyze(frame, len(frame) - 1, "buy")]

    assert "pullback_shrink" in keys


def test_breakout_with_volume_is_detected():
    closes = [9.5] * 29 + [10.5]
    volumes = [1000.0] * 29 + [4000.0]
    frame = _frame(closes, volumes)

    keys = [rule["key"] for rule in ma_volume.analyze(frame, len(frame) - 1, "buy")]

    assert "breakout_volume" in keys


def test_heavy_volume_decline_is_flagged():
    closes = [10.0] * 29 + [9.6]
    volumes = [1000.0] * 29 + [5000.0]
    frame = _frame(closes, volumes)

    rules = ma_volume.analyze(frame, len(frame) - 1, "buy")

    assert any(rule["key"] == "heavy_volume_down" and rule["effect"] == "against" for rule in rules)


def test_short_history_returns_empty():
    frame = _frame([10.0, 10.1])

    assert ma_volume.analyze(frame, 1, "buy") == []


def test_result_is_capped():
    frame = _frame([float(value) for value in range(1, 31)], [1000.0] * 30)

    assert len(ma_volume.analyze(frame, len(frame) - 1, "buy", limit=2)) <= 2

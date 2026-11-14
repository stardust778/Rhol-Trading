"""均线 + 量价 confirmation rules used by the trade review.

The checks are intentionally few and explainable: each one names the evidence
it saw (moving-average alignment, MA20 break with volume, shrink-on-pullback,
heavy-volume decline). They are reported as ``support`` / ``against`` for the
side of the fill, never as a buy/sell instruction.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

#: The moving-average set the operator reviews with.
MA_PERIODS = (5, 10, 20, 30, 55, 99, 128, 225)
_VOLUME_WINDOW = 20
_PULLBACK_BAND = 0.015
_PULLBACK_VOLUME = 0.8
_BREAKOUT_VOLUME = 1.5
_HEAVY_VOLUME = 2.0


def _moving_average(closes: pd.Series, period: int) -> float | None:
    if len(closes) < period:
        return None
    value = float(closes.rolling(period).mean().iloc[-1])
    return value if pd.notna(value) else None


def analyze(frame: pd.DataFrame, position: int, side: str, limit: int = 3) -> list[dict[str, str]]:
    """Return MA/volume evidence for the fill at ``position``.

    Args:
        frame: OHLCV frame the Chan structure used.
        position: Bar index of the fill.
        side: ``buy`` or ``sell``.
        limit: Max rules to return, strongest first.

    Returns:
        ``[{"key", "effect"}]`` where effect is ``support`` or ``against``
        for this fill's side.
    """
    if position < 1 or frame.empty:
        return []
    window = frame.iloc[: position + 1]
    closes = window["close"].astype(float)
    volumes = window["volume"].astype(float) if "volume" in window else pd.Series(dtype=float)
    price = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) > 1 else price
    ma = {period: _moving_average(closes, period) for period in MA_PERIODS}
    average_volume = (
        float(volumes.rolling(_VOLUME_WINDOW).mean().iloc[-1])
        if len(volumes) >= _VOLUME_WINDOW
        else None
    )
    volume = float(volumes.iloc[-1]) if len(volumes) else 0.0

    hits: list[tuple[str, str]] = []  # (key, market tone: bull/bear)
    ma5, ma10, ma20 = ma[5], ma[10], ma[20]
    if None not in (ma5, ma10, ma20) and ma5 > ma10 > ma20:
        hits.append(("ma_bull_stack", "bull"))
    if None not in (ma5, ma10, ma20) and ma5 < ma10 < ma20:
        hits.append(("ma_bear_stack", "bear"))
    if ma20 is not None:
        hits.append(("above_ma20", "bull") if price > ma20 else ("below_ma20", "bear"))
        near_ma20 = abs(price / ma20 - 1.0) <= _PULLBACK_BAND
        if near_ma20 and average_volume and volume < average_volume * _PULLBACK_VOLUME:
            hits.append(("pullback_shrink", "bull"))
        if (
            previous <= ma20 < price
            and average_volume
            and volume > average_volume * _BREAKOUT_VOLUME
        ):
            hits.append(("breakout_volume", "bull"))
    if average_volume and volume > average_volume * _HEAVY_VOLUME and price < previous:
        hits.append(("heavy_volume_down", "bear"))

    wanted = "bull" if side == "buy" else "bear"
    ordered = sorted(hits, key=lambda hit: 0 if hit[1] == wanted else 1)
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for key, tone in ordered:
        if key in seen:
            continue
        seen.add(key)
        result.append({"key": key, "effect": "support" if tone == wanted else "against"})
        if len(result) >= limit:
            break
    return result

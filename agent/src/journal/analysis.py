"""Analysis layer over the stored trade journal.

The math lives in ``src.tools.trade_journal_tool`` (FIFO roundtrip pairing,
profile metrics, four behaviour diagnostics). This module only feeds it the
stored fills and adds the roll-ups a review page needs: realised PnL per month
and per roundtrip.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from src.journal import store
from src.tools.trade_journal_tool import (
    _compute_behavior,
    _compute_profile,
    pair_trades_fifo,
)


def _finite(value: Any) -> Any:
    """Replace non-finite floats with ``None`` so the payload is JSON-safe.

    ``profit_loss_ratio`` is Infinity when every roundtrip won (no losing leg
    to divide by). JSON has no Infinity literal, and the route would fail to
    serialize the whole analysis over one such metric.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def _month_of(value: Any) -> str | None:
    """Return ``YYYY-MM`` for a datetime-like roundtrip field."""
    if value is None:
        return None
    text = str(value)
    if len(text) < 7:
        return None
    return text[:7]


def monthly_pnl(roundtrips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate realised PnL by the month a position was closed."""
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
    )
    for trip in roundtrips:
        month = _month_of(trip.get("sell_dt"))
        if month is None:
            continue
        bucket = buckets[month]
        pnl = float(trip.get("pnl") or 0.0)
        bucket["pnl"] += pnl
        bucket["trades"] += 1
        if pnl > 0:
            bucket["wins"] += 1
        elif pnl < 0:
            bucket["losses"] += 1
    return [
        {
            "month": month,
            "pnl": round(bucket["pnl"], 2),
            "trades": bucket["trades"],
            "wins": bucket["wins"],
            "losses": bucket["losses"],
        }
        for month, bucket in sorted(buckets.items())
    ]


def build_analysis(roundtrip_limit: int = 100) -> dict[str, Any]:
    """Return the full review payload for the journal page.

    Args:
        roundtrip_limit: How many closed roundtrips to include, newest first.

    Returns:
        ``status`` plus profile, behaviour diagnostics, monthly PnL and the
        most recent roundtrips. Empty journals return ``status="empty"``.
    """
    frame = store.load_dataframe()
    if frame.empty:
        return {"status": "empty", "records": 0}

    roundtrips = pair_trades_fifo(frame)
    recent = sorted(
        roundtrips,
        key=lambda trip: str(trip.get("sell_dt") or ""),
        reverse=True,
    )[:roundtrip_limit]

    return _finite({
        "status": "ok",
        "records": int(len(frame)),
        "date_range": f"{frame['datetime'].min().date()} ~ {frame['datetime'].max().date()}",
        "symbols": int(frame["symbol"].nunique()),
        "profile": _compute_profile(frame),
        "behavior": _compute_behavior(frame),
        "monthly_pnl": monthly_pnl(roundtrips),
        "roundtrips": [
            {**trip, "buy_dt": str(trip.get("buy_dt")), "sell_dt": str(trip.get("sell_dt"))}
            for trip in recent
        ],
    })

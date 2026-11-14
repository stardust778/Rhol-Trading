"""Chan-theory (缠论) structure analysis: 分型 → 笔 → 中枢 → 买卖点.

The 分型/笔/中枢 layer comes from ``czsc`` (the reference Python
implementation). czsc 1.x dropped the old ``czsc.signals`` package, so the
1/2/3 类买卖点 below are derived here from the stroke/center series with the
rules documented on :func:`derive_signals`.

This is an analysis aid, not an oracle: Chan theory leaves room for
interpretation (stroke granularity, center membership, divergence strength).
Every verdict is therefore reported together with the structural evidence it
came from, and the forward return of the trade it evaluates.
"""

from __future__ import annotations

import os
from typing import Any, Iterable

import pandas as pd

from src.config.paths import get_runtime_root

class ChanUnavailableError(RuntimeError):
    """Raised when the optional ``czsc`` engine is not installed."""


#: How far (in bars) a fill may sit from a Chan signal and still count as
#: "at" that signal. Two bars covers same-day and next-open executions.
SIGNAL_WINDOW_BARS = 3
#: Forward horizons (trading days) reported for every reviewed fill.
FORWARD_HORIZONS = (5, 10, 20)


def _ensure_czsc_home() -> None:
    """Point czsc's cache at the runtime root before its first import.

    czsc creates ``~/.czsc`` at import time; keeping it under the runtime root
    means a sandboxed or relocated runtime still works.
    """
    os.environ.setdefault("CZSC_HOME", str(get_runtime_root() / "czsc"))


def _direction(value: Any) -> str:
    """Normalize czsc's direction label to ``up``/``down``."""
    text = str(value).strip().lower()
    if text in {"向上", "up", "1"}:
        return "up"
    return "down"


def build_structure(symbol: str, frame: pd.DataFrame) -> dict[str, Any]:
    """Run CZSC over a daily frame and return strokes, centers and signals.

    Args:
        symbol: Normalized symbol.
        frame: OHLCV frame indexed by trade date (ascending).

    Returns:
        ``{"symbol", "bars", "bis", "centers", "signals", "latest"}``.
    """
    _ensure_czsc_home()
    try:
        from czsc import CZSC, Freq, RawBar
    except ImportError as exc:  # optional dependency
        raise ChanUnavailableError(
            "Chan analysis needs the optional czsc package: pip install czsc"
        ) from exc

    raw_bars = []
    for index, (stamp, row) in enumerate(frame.iterrows()):
        raw_bars.append(
            RawBar(
                symbol=symbol,
                id=index,
                dt=pd.Timestamp(stamp).to_pydatetime(),
                freq=Freq.D,
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                vol=float(row.get("volume") or 0.0),
                amount=0.0,
            )
        )

    czsc = CZSC(raw_bars)

    bis = [
        {
            "start": pd.Timestamp(bi.sdt).strftime("%Y-%m-%d"),
            "end": pd.Timestamp(bi.edt).strftime("%Y-%m-%d"),
            "start_price": round(float(bi.fx_a.fx), 3),
            "end_price": round(float(bi.fx_b.fx), 3),
            "direction": _direction(bi.direction),
            "high": round(float(bi.high), 3),
            "low": round(float(bi.low), 3),
            "change": round(float(bi.change), 4),
        }
        for bi in czsc.bi_list
    ]

    centers = [
        {
            "start": pd.Timestamp(zs.sdt).strftime("%Y-%m-%d"),
            "end": pd.Timestamp(zs.edt).strftime("%Y-%m-%d"),
            "zg": round(float(zs.zg), 3),
            "zd": round(float(zs.zd), 3),
            "gg": round(float(zs.gg), 3),
            "dd": round(float(zs.dd), 3),
            "valid": bool(zs.is_valid()),
            "direction": _direction(zs.edir),
        }
        for zs in czsc.zs_list
    ]

    signals = derive_signals(bis, centers)
    return {
        "symbol": symbol,
        "bars": int(len(frame)),
        "bis": bis,
        "centers": centers,
        "signals": signals,
        "latest": _latest_snapshot(bis, centers, signals),
    }


def derive_signals(
    bis: list[dict[str, Any]],
    centers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive 一/二/三类买卖点 from the stroke and center series.

    Rules (deliberately explicit, because Chan readings differ):

    * **一买/一卖** — a down stroke makes a lower low than the previous down
      stroke but with a smaller absolute move (``|change|``), i.e. the decline
      is weakening; the low is flagged 一买. Symmetric for 一卖.
    * **二买/二卖** — the down stroke after a 一买 bottoms above that 一买 low
      (the reversal held); symmetric for 二卖.
    * **三买** — an up stroke ends above the most recent center's ``zg`` and
      the following down stroke holds above that ``zg`` (breakout + successful
      retest); symmetric 三卖 below ``zd``.

    All signals are stamped at the stroke's terminal fractal date and price.
    """
    signals: list[dict[str, Any]] = []
    last_down: dict[str, Any] | None = None
    last_down_was_first = False
    last_up: dict[str, Any] | None = None
    last_up_was_first = False

    for index, bi in enumerate(bis):
        previous = bis[index - 1] if index > 0 else None
        center = _center_before(centers, previous["start"] if previous else bi["start"])

        if bi["direction"] == "down":
            first_buy = (
                last_down is not None
                and bi["low"] < last_down["low"]
                and abs(bi["change"]) < abs(last_down["change"])
            )
            if first_buy:
                signals.append(_signal(bi, "1buy", bi["low"]))
            elif last_down_was_first and bi["low"] > last_down["low"]:
                signals.append(_signal(bi, "2buy", bi["low"]))
            if (
                center is not None
                and previous is not None
                and previous["direction"] == "up"
                and previous["end_price"] > center["zg"]
                and bi["low"] > center["zg"]
            ):
                signals.append(_signal(bi, "3buy", bi["low"]))
            last_down, last_down_was_first = bi, first_buy
        else:
            first_sell = (
                last_up is not None
                and bi["high"] > last_up["high"]
                and abs(bi["change"]) < abs(last_up["change"])
            )
            if first_sell:
                signals.append(_signal(bi, "1sell", bi["high"]))
            elif last_up_was_first and bi["high"] < last_up["high"]:
                signals.append(_signal(bi, "2sell", bi["high"]))
            if (
                center is not None
                and previous is not None
                and previous["direction"] == "down"
                and previous["end_price"] < center["zd"]
                and bi["high"] < center["zd"]
            ):
                signals.append(_signal(bi, "3sell", bi["high"]))
            last_up, last_up_was_first = bi, first_sell

    return signals


def _signal(bi: dict[str, Any], kind: str, price: float) -> dict[str, Any]:
    return {
        "date": bi["end"],
        "type": kind,
        "price": round(float(price), 3),
        "bi_direction": bi["direction"],
    }


def _center_before(centers: list[dict[str, Any]], date: str) -> dict[str, Any] | None:
    """Return the latest center that ended on or before ``date``."""
    candidates = [center for center in centers if center["start"] <= date]
    return candidates[-1] if candidates else None


def _latest_snapshot(
    bis: list[dict[str, Any]],
    centers: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "bi_direction": bis[-1]["direction"] if bis else None,
        "bi_start": bis[-1]["start"] if bis else None,
        "bi_end": bis[-1]["end"] if bis else None,
        "center": centers[-1] if centers else None,
        "last_signals": signals[-3:],
    }


def _bar_index(frame: pd.DataFrame) -> dict[str, int]:
    return {pd.Timestamp(stamp).strftime("%Y-%m-%d"): index for index, stamp in enumerate(frame.index)}


def _zone_of(price: float, center: dict[str, Any] | None) -> str:
    if center is None:
        return "none"
    if price > center["zg"]:
        return "above"
    if price < center["zd"]:
        return "below"
    return "inside"


def classify_trade(
    *,
    side: str,
    price: float,
    signal: dict[str, Any] | None,
    center: dict[str, Any] | None,
    bi_direction: str | None,
    opposing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn structure evidence into a verdict key + subjective quality.

    Returns:
        ``{"key", "quality", "signal_type"}`` where ``key`` is an i18n key
        under ``chan.`` and quality is ``good`` / ``neutral`` / ``poor``.
    """
    desired = ("1buy", "2buy", "3buy") if side == "buy" else ("1sell", "2sell", "3sell")
    if signal is not None and signal["type"] in desired:
        return {"key": f"match_{signal['type']}", "quality": "good", "signal_type": signal["type"]}
    if opposing is not None:
        # Filling against a fresh opposite-side Chan point is structural
        # evidence against the trade, regardless of where price sits.
        return {"key": "against_signal", "quality": "poor", "signal_type": opposing["type"]}

    zone = _zone_of(price, center)
    if zone == "inside":
        return {"key": "zone_inside", "quality": "neutral", "signal_type": None}
    if side == "buy":
        if zone == "above":
            if bi_direction == "down":
                return {"key": "above_pullback", "quality": "neutral", "signal_type": None}
            return {"key": "above_chase", "quality": "poor", "signal_type": None}
        if zone == "below":
            if bi_direction == "down":
                return {"key": "below_against", "quality": "poor", "signal_type": None}
            return {"key": "below_reclaim", "quality": "neutral", "signal_type": None}
    else:
        if zone == "below":
            if bi_direction == "up":
                return {"key": "below_rebound", "quality": "neutral", "signal_type": None}
            return {"key": "below_panic", "quality": "poor", "signal_type": None}
        if zone == "above":
            if bi_direction == "up":
                return {"key": "above_exit", "quality": "neutral", "signal_type": None}
            return {"key": "above_chase_sell", "quality": "poor", "signal_type": None}
    return {"key": "no_structure", "quality": "neutral", "signal_type": None}


def review_trades(
    *,
    structure: dict[str, Any],
    frame: pd.DataFrame,
    trades: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate each fill against the Chan structure of its symbol.

    Args:
        structure: Output of :func:`build_structure`.
        frame: The same OHLCV frame the structure was built from.
        trades: Journal rows (``datetime``, ``side``, ``price`` ...).

    Returns:
        One review row per fill with the matched signal (if any), the
        structural verdict and forward returns after the fill.
    """
    date_index = _bar_index(frame)
    dates = sorted(date_index)
    closes = frame["close"].astype(float)
    bis = structure["bis"]
    centers = structure["centers"]
    signals = structure["signals"]

    reviews: list[dict[str, Any]] = []
    for trade in trades:
        stamp = str(trade.get("datetime") or "")[:10]
        side = str(trade.get("side") or "")
        if side not in ("buy", "sell") or stamp not in date_index:
            continue
        position = date_index[stamp]
        opposite = "sell" if side == "buy" else "buy"
        signal = _nearest_signal(signals, dates, position, side)
        opposing = (
            None if signal is not None else _nearest_signal(signals, dates, position, opposite)
        )
        center = _center_at(centers, stamp)
        bi = _bi_at(bis, stamp)
        verdict = classify_trade(
            side=side,
            price=float(trade.get("price") or 0.0),
            signal=signal,
            center=center,
            bi_direction=bi["direction"] if bi else None,
            opposing=opposing,
        )
        reviews.append(
            {
                "trade_id": trade.get("trade_id"),
                "datetime": trade.get("datetime"),
                "side": side,
                "price": float(trade.get("price") or 0.0),
                "signal": signal,
                "opposing_signal": opposing,
                "verdict": verdict,
                "center": center,
                "bi_direction": bi["direction"] if bi else None,
                "forward": _forward_returns(closes, position),
            }
        )
    return reviews


def _nearest_signal(
    signals: list[dict[str, Any]],
    dates: list[str],
    position: int,
    side: str,
) -> dict[str, Any] | None:
    """Closest signal of the matching side within the bar window."""
    wanted = ("1buy", "2buy", "3buy") if side == "buy" else ("1sell", "2sell", "3sell")
    best: tuple[int, dict[str, Any]] | None = None
    for signal in signals:
        if signal["type"] not in wanted:
            continue
        try:
            signal_position = dates.index(signal["date"])
        except ValueError:
            continue
        distance = abs(signal_position - position)
        if distance <= SIGNAL_WINDOW_BARS and (best is None or distance < best[0]):
            best = (distance, signal)
    return best[1] if best else None


def _center_at(centers: list[dict[str, Any]], date: str) -> dict[str, Any] | None:
    """Active center at ``date`` (containing it), else the latest completed one."""
    containing = [c for c in centers if c["start"] <= date <= c["end"]]
    if containing:
        return containing[-1]
    completed = [c for c in centers if c["end"] < date]
    return completed[-1] if completed else None


def _bi_at(bis: list[dict[str, Any]], date: str) -> dict[str, Any] | None:
    """Stroke governing ``date``.

    A stroke that ends exactly on ``date`` wins over a stroke that merely
    contains it: on a fractal day the completed stroke is the one the price
    just finished, which is what the structural verdict should describe.
    """
    ending = [bi for bi in bis if bi["end"] == date]
    if ending:
        return ending[-1]
    containing = [bi for bi in bis if bi["start"] <= date <= bi["end"]]
    if containing:
        return containing[-1]
    completed = [bi for bi in bis if bi["end"] < date]
    return completed[-1] if completed else None


def _forward_returns(closes: pd.Series, position: int) -> dict[str, float | None]:
    base = float(closes.iloc[position])
    result: dict[str, float | None] = {}
    for horizon in FORWARD_HORIZONS:
        target = position + horizon
        result[str(horizon)] = (
            round((float(closes.iloc[target]) / base - 1.0) * 100.0, 2)
            if base and target < len(closes)
            else None
        )
    return result


def load_frame(symbol: str, *, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Fetch daily bars for Chan analysis (3 years by default)."""
    from datetime import date, timedelta

    from src.market_data import fetch_market_data

    end_day = date.fromisoformat(end) if end else date.today()
    start_day = date.fromisoformat(start) if start else end_day - timedelta(days=1100)
    payload = fetch_market_data(
        codes=[symbol],
        start_date=start_day.isoformat(),
        end_date=end_day.isoformat(),
        max_rows=0,
        as_frames=True,
    )
    for value in payload.values():
        if isinstance(value, pd.DataFrame) and not value.empty:
            frame = value.copy()
            frame.index = pd.to_datetime(frame.index)
            return frame.sort_index()
    raise ValueError(f"No daily bars for {symbol} between {start_day} and {end_day}")

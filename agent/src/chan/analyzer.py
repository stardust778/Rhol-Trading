"""Chan-theory (缠论) structure analysis: 分型 → 笔 → 中枢 → 买卖点.

The 分型/笔/中枢 layer comes from ``czsc`` (the reference Python
implementation). czsc 1.x dropped the old ``czsc.signals`` package, so the
1/2/3 类买卖点 below are derived here from the stroke/center series with the
rules documented on :func:`derive_signals`.

Review is multi-timeframe: each fill is judged on its own interval, then
checked against the parent interval (区间套) and against a moving-average /
volume rule set (:mod:`src.chan.ma_volume`).

This is an analysis aid, not an oracle: Chan theory leaves room for
interpretation (stroke granularity, center membership, divergence strength).
Every verdict is reported together with the structural evidence it came from
and the forward return of the trade it evaluates.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Iterable

import pandas as pd

from src.config.paths import get_runtime_root

#: How far (in bars) a fill may sit from a Chan signal and still count as
#: "at" that signal. Two bars covers same-day and next-open executions.
SIGNAL_WINDOW_BARS = 3
#: Forward horizons (trading days / bars) reported for every reviewed fill.
FORWARD_HORIZONS = (5, 10, 20)
#: Parent interval used for 区间套 confirmation.
PARENT_INTERVAL: dict[str, str | None] = {
    "1m": "5m",
    "5m": "30m",
    "30m": "1D",
    "1D": "1W",
    "1W": None,
}
_INTRADAY_INTERVALS = {"1m", "5m", "30m", "60m"}
_FREQ_NAMES = {"1m": "F1", "5m": "F5", "30m": "F30", "60m": "F60", "1D": "D", "1W": "W"}
_CACHE_TTL_SECONDS = 60.0
_STRUCTURE_CACHE: dict[tuple[str, str, str | None], tuple[float, pd.DataFrame, dict[str, Any]]] = {}


class ChanUnavailableError(RuntimeError):
    """Raised when the optional ``czsc`` engine is not installed."""


def _ensure_czsc_home() -> None:
    """Point czsc's cache at the runtime root before its first import."""
    os.environ.setdefault("CZSC_HOME", str(get_runtime_root() / "czsc"))


def _direction(value: Any) -> str:
    """Normalize czsc's direction label to ``up``/``down``."""
    text = str(value).strip().lower()
    if text in {"向上", "up", "1"}:
        return "up"
    return "down"


def is_intraday(interval: str) -> bool:
    """Return True for the intraday intervals supported by the chart layer."""
    return interval in _INTRADAY_INTERVALS


def _stamp(value: Any, interval: str) -> str:
    """Format a bar/fractal timestamp consistently with the interval."""
    moment = pd.Timestamp(value)
    return moment.strftime("%Y-%m-%d %H:%M") if is_intraday(interval) else moment.strftime("%Y-%m-%d")


def _freq(interval: str):
    from czsc import Freq

    return getattr(Freq, _FREQ_NAMES.get(interval, "D"))


def build_structure(symbol: str, frame: pd.DataFrame, interval: str = "1D") -> dict[str, Any]:
    """Run CZSC over a frame and return strokes, centers and signals.

    Args:
        symbol: Normalized symbol.
        frame: OHLCV frame indexed by bar timestamp (ascending).
        interval: ``1m``/``5m``/``30m``/``60m``/``1D``/``1W``.

    Returns:
        ``{"symbol", "interval", "bars", "bis", "centers", "signals", "latest"}``.
    """
    _ensure_czsc_home()
    try:
        from czsc import CZSC, RawBar
    except ImportError as exc:  # optional dependency
        raise ChanUnavailableError(
            "Chan analysis needs the optional czsc package: pip install czsc"
        ) from exc

    freq = _freq(interval)
    raw_bars = []
    for index, (stamp, row) in enumerate(frame.iterrows()):
        raw_bars.append(
            RawBar(
                symbol=symbol,
                id=index,
                dt=pd.Timestamp(stamp).to_pydatetime(),
                freq=freq,
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
            "start": _stamp(bi.sdt, interval),
            "end": _stamp(bi.edt, interval),
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
            "start": _stamp(zs.sdt, interval),
            "end": _stamp(zs.edt, interval),
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
        "interval": interval,
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
    """Turn structure evidence into a verdict key + subjective quality."""
    desired = ("1buy", "2buy", "3buy") if side == "buy" else ("1sell", "2sell", "3sell")
    if signal is not None and signal["type"] in desired:
        return {"key": f"match_{signal['type']}", "quality": "good", "signal_type": signal["type"]}
    if opposing is not None:
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


def _locate(frame: pd.DataFrame, stamp: Any, interval: str = "1D") -> int | None:
    """Return the bar index that contains a trade timestamp.

    Daily/weekly bars are stamped at the session/week start, so the trade's
    time-of-day must be dropped before the lookup; intraday bars are stamped at
    their close, so the first bar at or after the fill is the containing one.
    """
    if frame.empty:
        return None
    moment = pd.Timestamp(stamp)
    if interval == "1W":
        position = int(frame.index.searchsorted(moment, side="right")) - 1
    elif is_intraday(interval):
        position = int(frame.index.searchsorted(moment, side="left"))
    else:
        position = int(frame.index.searchsorted(moment.normalize(), side="left"))
    return position if 0 <= position < len(frame) else None


def _bar_stamps(frame: pd.DataFrame, interval: str) -> list[str]:
    return [_stamp(stamp, interval) for stamp in frame.index]


def _nearest_signal(
    signals: list[dict[str, Any]],
    positions: dict[str, int],
    position: int,
    side: str,
) -> dict[str, Any] | None:
    """Closest signal of the matching side within the bar window."""
    wanted = ("1buy", "2buy", "3buy") if side == "buy" else ("1sell", "2sell", "3sell")
    best: tuple[int, dict[str, Any]] | None = None
    for signal in signals:
        if signal["type"] not in wanted:
            continue
        signal_position = positions.get(signal["date"])
        if signal_position is None:
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
    """Stroke governing ``date`` (the one ending exactly on it wins)."""
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


def review_trades(
    *,
    structure: dict[str, Any],
    frame: pd.DataFrame,
    trades: Iterable[dict[str, Any]],
    interval: str = "1D",
    parent: tuple[pd.DataFrame, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate each fill against Chan structure, 区间套 and MA/volume rules.

    Args:
        structure: Output of :func:`build_structure` for the trade interval.
        frame: The same frame the structure was built from.
        trades: Journal rows (``datetime``, ``side``, ``price`` ...).
        interval: Interval the frame uses.
        parent: Optional ``(frame, structure)`` of the parent interval.

    Returns:
        One review row per fill.
    """
    from src.chan import ma_volume

    positions = {stamp: index for index, stamp in enumerate(_bar_stamps(frame, interval))}
    closes = frame["close"].astype(float)
    bis = structure["bis"]
    centers = structure["centers"]
    signals = structure["signals"]

    reviews: list[dict[str, Any]] = []
    for trade in trades:
        side = str(trade.get("side") or "")
        if side not in ("buy", "sell"):
            continue
        position = _locate(frame, trade.get("datetime"), interval)
        if position is None:
            continue
        stamp = _bar_stamps(frame, interval)[position]
        opposite = "sell" if side == "buy" else "buy"
        signal = _nearest_signal(signals, positions, position, side)
        opposing = (
            None if signal is not None else _nearest_signal(signals, positions, position, opposite)
        )
        center = _center_at(centers, stamp)
        bi = _bi_at(bis, stamp)
        price = float(trade.get("price") or 0.0)
        verdict = classify_trade(
            side=side,
            price=price,
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
                "price": price,
                "signal": signal,
                "opposing_signal": opposing,
                "verdict": verdict,
                "center": center,
                "bi_direction": bi["direction"] if bi else None,
                "forward": _forward_returns(closes, position),
                "ma_volume": ma_volume.analyze(frame, position, side),
                "nested": _nested_confirmation(
                    interval=interval,
                    side=side,
                    price=price,
                    stamp=trade.get("datetime"),
                    parent=parent,
                ),
            }
        )
    return reviews


def _nested_confirmation(
    *,
    interval: str,
    side: str,
    price: float,
    stamp: Any,
    parent: tuple[pd.DataFrame, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """区间套: is the parent interval supporting this fill?

    A parent-interval buy/sell point near the fill, or a parent center that the
    price is testing from the correct side, confirms the lower-level entry.
    """
    parent_interval = PARENT_INTERVAL.get(interval)
    if parent is None or parent_interval is None:
        return None
    parent_frame, parent_structure = parent
    position = _locate(parent_frame, stamp, parent_interval)
    if position is None:
        return None
    parent_positions = {
        s: index for index, s in enumerate(_bar_stamps(parent_frame, parent_interval))
    }
    parent_stamp = _bar_stamps(parent_frame, parent_interval)[position]
    signal = _nearest_signal(parent_structure["signals"], parent_positions, position, side)
    center = _center_at(parent_structure["centers"], parent_stamp)
    zone = _zone_of(price, center)
    supporting = signal is not None
    if not supporting and center is not None:
        # A parent center below price supports buys (and above supports sells).
        supporting = (side == "buy" and zone == "above") or (side == "sell" and zone == "below")
    return {
        "interval": parent_interval,
        "signal": signal,
        "zone": zone,
        "bi_direction": (
            _bi_at(parent_structure["bis"], parent_stamp) or {}
        ).get("direction"),
        "supporting": supporting,
    }


def load_frame(
    symbol: str,
    *,
    interval: str = "1D",
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch bars for Chan analysis.

    Intraday intervals use the Sina/Eastmoney minute endpoints (last ~1000
    bars); daily and weekly use the shared loader chain (3 years by default).
    """
    if is_intraday(interval):
        from src.market_intraday import fetch_intraday

        frame, _source = fetch_intraday(symbol, interval, 1000)
        return frame

    from src.market_data import fetch_market_data

    end_day = date.fromisoformat(end) if end else date.today()
    start_day = date.fromisoformat(start) if start else end_day - timedelta(days=1100)
    payload = fetch_market_data(
        codes=[symbol],
        start_date=start_day.isoformat(),
        end_date=end_day.isoformat(),
        interval=interval,
        max_rows=0,
        as_frames=True,
    )
    for value in payload.values():
        if isinstance(value, pd.DataFrame) and not value.empty:
            frame = value.copy()
            frame.index = pd.to_datetime(frame.index)
            return frame.sort_index()
    raise ValueError(f"No {interval} bars for {symbol} between {start_day} and {end_day}")


def load_structure(
    symbol: str,
    *,
    interval: str = "1D",
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return ``(frame, structure)`` with a short-lived process cache."""
    key = (symbol.upper(), interval, start, end)
    hit = _STRUCTURE_CACHE.get(key)
    if hit is not None:
        stamped, frame, structure = hit
        if pd.Timestamp.now().timestamp() - stamped < _CACHE_TTL_SECONDS:
            return frame, structure
    frame = load_frame(symbol, interval=interval, start=start, end=end)
    structure = build_structure(symbol, frame, interval)
    _STRUCTURE_CACHE[key] = (pd.Timestamp.now().timestamp(), frame, structure)
    return frame, structure

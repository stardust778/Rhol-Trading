"""Intraday A-share OHLCV from public Sina / Eastmoney endpoints.

The free A-share loaders in the backtest chain are daily-only for the sources
reachable from this machine (tencent rejects intraday, akshare maps A-share to
daily, eastmoney's push2his is rate-limited), so charts and Chan analysis pull
minute bars from these two read-only, keyless endpoints instead.

Volume is normalized to **shares** (Eastmoney reports lots of 100).
"""

from __future__ import annotations

import math
import re
import time
from typing import Any

import httpx
import pandas as pd

#: Supported intraday intervals mapped to their minute length.
INTERVALS: dict[str, int] = {"1m": 1, "5m": 5, "30m": 30, "60m": 60}

_MAX_BARS = 1000
_CACHE_TTL_SECONDS = 20.0
_CACHE: dict[tuple[str, str, int], tuple[float, pd.DataFrame, str]] = {}

_SINA_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
_EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn",
}


def is_intraday(interval: str) -> bool:
    """Return True when ``interval`` names an intraday bar size."""
    return interval in INTERVALS


def _sina_symbol(symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", symbol.upper())
    if not match:
        return None
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[match.group(2)]
    return prefix + match.group(1)


def _eastmoney_secid(symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", symbol.upper())
    if not match:
        return None
    market = "1" if match.group(2) == "SH" else "0"
    return f"{market}.{match.group(1)}"


def _from_sina(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    code = _sina_symbol(symbol)
    if code is None:
        raise ValueError(f"Intraday data is available for A-shares only, got {symbol}")
    response = httpx.get(
        _SINA_URL,
        params={"symbol": code, "scale": INTERVALS[interval], "ma": "no", "datalen": limit},
        headers=_HEADERS,
        timeout=8.0,
    )
    response.raise_for_status()
    rows: list[dict[str, Any]] = response.json()
    if not rows:
        raise ValueError(f"Sina returned no {interval} bars for {symbol}")
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame["day"])
    frame = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    return frame.dropna(subset=["close"]).sort_index()


def _from_eastmoney(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    secid = _eastmoney_secid(symbol)
    if secid is None:
        raise ValueError(f"Intraday data is available for A-shares only, got {symbol}")
    today = pd.Timestamp.today().normalize()
    response = httpx.get(
        _EASTMONEY_URL,
        params={
            "secid": secid,
            "klt": {"1m": 1, "5m": 5, "30m": 30, "60m": 60}[interval],
            "fqt": 0,
            "beg": (today - pd.Timedelta(days=45)).strftime("%Y%m%d"),
            "end": today.strftime("%Y%m%d"),
            "fields1": "f1,f2,f3,f4,f5",
            "fields2": "f51,f52,f53,f54,f55,f56",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=8.0,
    )
    response.raise_for_status()
    payload = response.json() or {}
    klines = ((payload.get("data") or {}).get("klines")) or []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "day": parts[0],
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                # Eastmoney reports volume in lots (100 shares).
                "volume": float(parts[5]) * 100.0,
            }
        )
    if not rows:
        raise ValueError(f"Eastmoney returned no {interval} bars for {symbol}")
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame["day"])
    frame = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    return frame.dropna(subset=["close"]).sort_index().tail(limit)


def fetch_intraday(
    symbol: str,
    interval: str,
    limit: int = _MAX_BARS,
) -> tuple[pd.DataFrame, str]:
    """Fetch intraday bars for an A-share symbol.

    Args:
        symbol: Normalized code such as ``000001.SZ``.
        interval: One of :data:`INTERVALS`.
        limit: Maximum bars (capped at 1000 by the upstream endpoints).

    Returns:
        ``(frame, source)`` with a DatetimeIndex and share-based volume.

    Raises:
        ValueError: Unsupported symbol/interval, or both endpoints failed.
        httpx.HTTPError: Network failure on the last attempt.
    """
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported intraday interval: {interval}")
    code = symbol.strip().upper()
    limit = max(1, min(int(limit), _MAX_BARS))
    key = (code, interval, limit)
    hit = _CACHE.get(key)
    if hit is not None:
        stamped, frame, source = hit
        if time.monotonic() - stamped < _CACHE_TTL_SECONDS:
            return frame, source

    errors: list[str] = []
    for source, loader in (("sina", _from_sina), ("eastmoney", _from_eastmoney)):
        try:
            frame = loader(code, interval, limit)
        except Exception as exc:  # try the next endpoint
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
            continue
        if frame.empty:
            errors.append(f"{source}: empty")
            continue
        _CACHE[key] = (time.monotonic(), frame, source)
        return frame, source

    raise ValueError(f"No intraday data for {code} {interval} ({'; '.join(errors)})")


def frame_to_bars(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Project an intraday frame onto the chart's ``PriceBar`` contract."""
    bars: list[dict[str, Any]] = []
    for stamp, row in frame.iterrows():
        close = float(row["close"])
        if not math.isfinite(close):
            continue
        bars.append(
            {
                "time": pd.Timestamp(stamp).strftime("%Y-%m-%d %H:%M"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close,
                "volume": float(row.get("volume") or 0.0),
            }
        )
    return bars

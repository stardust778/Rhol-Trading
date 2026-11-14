"""Market-data (OHLC) routes backing the K-line chart page.

Mounted by ``agent/api_server.py`` via ``register_market_routes(app)``.

Contract: one request, one symbol, normalized daily/weekly/monthly bars. The
heavy lifting stays in :func:`src.market_data.fetch_market_data` so the page
inherits the same source routing, fallback chain and price-caliber metadata the
agent's ``get_market_data`` tool uses — a chart must never disagree with a
backtest about which source served a symbol.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Any]

MAX_LOOKBACK_DAYS = 365 * 20
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_MAX_BARS = 2000
MAX_BARS = 5000
_ALLOWED_INTERVALS = {"1D", "1W", "1M"}
# A bare alphabetic ticker has no venue: the shared router would send it to the
# A-share chain, burn ~20s failing every source, and still return nothing. The
# app's identity contract already requires a suffix, so reject it up front.
_BARE_TICKER_RE = re.compile(r"^[A-Za-z]+$")
_CACHE_TTL_SECONDS = 60.0
_CACHE_MAX_ENTRIES = 128


class _SlidingWindowRateLimiter:
    """Per-client request budget, mirroring ``system_routes``' limiter."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        stamps = [t for t in self._hits.get(key, []) if t >= cutoff]
        if len(stamps) >= self._max:
            self._hits[key] = stamps
            return False
        stamps.append(now)
        self._hits[key] = stamps
        return True


_market_rate_limiter = _SlidingWindowRateLimiter(max_requests=60, window_seconds=60.0)

# (symbol, start, end, interval, source) -> (monotonic timestamp, payload)
_CHART_CACHE: dict[tuple[str, str, str, str, str], tuple[float, dict[str, Any]]] = {}


def _client_key(request: Request) -> str:
    """Identify the caller for the rate limiter."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cache_get(key: tuple[str, str, str, str, str]) -> dict[str, Any] | None:
    hit = _CHART_CACHE.get(key)
    if hit is None:
        return None
    stamped, payload = hit
    if time.monotonic() - stamped > _CACHE_TTL_SECONDS:
        _CHART_CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key: tuple[str, str, str, str, str], payload: dict[str, Any]) -> None:
    if len(_CHART_CACHE) >= _CACHE_MAX_ENTRIES:
        oldest = min(_CHART_CACHE.items(), key=lambda item: item[1][0])[0]
        _CHART_CACHE.pop(oldest, None)
    _CHART_CACHE[key] = (time.monotonic(), payload)


def _parse_day(value: str, field: str) -> date:
    """Accept ``YYYY-MM-DD`` and broker-style ``YYYYMMDD``."""
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise HTTPException(
        status_code=400, detail=f"{field} must be YYYY-MM-DD or YYYYMMDD, got {value!r}"
    )


def _bar_time(raw: Any) -> str | None:
    """Normalize a loader ``trade_date`` cell to a chart-friendly ISO string."""
    if raw is None:
        return None
    if hasattr(raw, "isoformat"):
        text = raw.isoformat()
    else:
        text = str(raw)
    if not text:
        return None
    return text.split("T", 1)[0]


def _shape_bars(rows: list[dict[str, Any]], max_bars: int) -> list[dict[str, Any]]:
    """Project loader rows onto the frontend ``PriceBar`` contract."""
    bars: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = _bar_time(row.get("trade_date") or row.get("date") or row.get("time"))
        if stamp is None:
            continue
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if close != close:  # NaN
            continue
        bar = {
            "time": stamp,
            "open": float(row.get("open") or close),
            "high": float(row.get("high") or close),
            "low": float(row.get("low") or close),
            "close": close,
            "volume": float(row.get("volume") or 0.0),
        }
        bars.append(bar)
    if len(bars) > max_bars > 0:
        bars = bars[-max_bars:]
    return bars


def register_market_routes(
    app: FastAPI,
    require_auth: AuthDep | None = None,
) -> None:
    """Mount the market-data routes onto ``app``.

    Args:
        app: The host FastAPI app.
        require_auth: Header-auth dependency. Resolved from the host
            ``api_server`` module when omitted, matching sibling route modules.
    """
    if require_auth is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:  # pragma: no cover - only on unusual import setups
            raise RuntimeError(
                "register_market_routes: api_server module not in sys.modules; "
                "pass require_auth explicitly"
            )
        require_auth = host.require_auth

    @app.get("/api/market/ohlc", dependencies=[Depends(require_auth)])
    async def market_ohlc(
        request: Request,
        symbol: str = Query(..., min_length=1, max_length=32, description="Instrument code, e.g. 000001.SZ"),
        start: str | None = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
        end: str | None = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
        interval: str = Query("1D", description="1D | 1W | 1M"),
        source: str = Query("auto", max_length=32, description="Loader name or 'auto'"),
        max_bars: int = Query(DEFAULT_MAX_BARS, ge=1, le=MAX_BARS),
    ):
        """Return normalized OHLCV bars for one symbol.

        Source routing, fallback and price caliber come from the shared
        ``fetch_market_data`` helper, so this endpoint and the agent's
        ``get_market_data`` tool always agree.
        """
        if not _market_rate_limiter.allow(_client_key(request)):
            raise HTTPException(status_code=429, detail="Rate limit exceeded, try again later")

        code = symbol.strip()
        if not code:
            raise HTTPException(status_code=400, detail="symbol is required")
        if _BARE_TICKER_RE.match(code):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{code!r} has no exchange suffix. Use 000001.SZ / 600519.SH / "
                    "430047.BJ for A-shares, AAPL.US for US, 00700.HK for HK."
                ),
            )
        if interval not in _ALLOWED_INTERVALS:
            raise HTTPException(
                status_code=400,
                detail=f"interval must be one of {sorted(_ALLOWED_INTERVALS)}, got {interval!r}",
            )

        today = date.today()
        end_day = _parse_day(end, "end") if end else today
        start_day = _parse_day(start, "start") if start else end_day - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        if start_day > end_day:
            raise HTTPException(status_code=400, detail="start must be on or before end")
        if (end_day - start_day).days > MAX_LOOKBACK_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"date range too wide (max {MAX_LOOKBACK_DAYS} days)",
            )

        key = (code, start_day.isoformat(), end_day.isoformat(), interval, source)
        cached = _cache_get(key)
        if cached is not None:
            return cached

        from src.market_data import fetch_market_data, lookup_instrument_name

        try:
            payload = await asyncio.to_thread(
                fetch_market_data,
                codes=[code],
                start_date=start_day.isoformat(),
                end_date=end_day.isoformat(),
                source=source,
                interval=interval,
                max_rows=0,
                include_provenance=True,
            )
        except ValueError as exc:  # unknown source / bad interval
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:  # network / loader failures
            logger.exception("market ohlc fetch failed for %s", code)
            raise HTTPException(
                status_code=502,
                detail="Market data request failed. Check data-source connectivity and retry.",
            )

        rows = payload.get(code)
        if isinstance(rows, dict):  # capped shape; max_rows=0 keeps this unreachable
            rows = rows.get("data") or []
        if not rows:
            unresolved = payload.get("_unresolved") or []
            detail = f"No data for {code} between {start_day} and {end_day}"
            if unresolved:
                detail += f" (unresolved: {', '.join(map(str, unresolved))})"
            raise HTTPException(status_code=404, detail=detail)

        provenance = (payload.get("_provenance") or {}).get(code, {})
        name = await asyncio.to_thread(lookup_instrument_name, code)
        body = {
            "symbol": code,
            "name": name,
            "interval": interval,
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "source": provenance.get("source"),
            "requested_source": provenance.get("requested_source", source),
            "detected_source": provenance.get("detected_source"),
            "fallback_used": bool(provenance.get("fallback_used")),
            "adjustment": provenance.get("adjustment"),
            "volume_unit": provenance.get("volume_unit"),
            "bars": _shape_bars(list(rows), max_bars),
        }
        if not body["bars"]:
            raise HTTPException(
                status_code=502, detail=f"Loader returned no usable bars for {code}"
            )
        _cache_put(key, body)
        return body

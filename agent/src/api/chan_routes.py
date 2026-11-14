"""Chan-theory (缠论) analysis routes.

Mounted by ``agent/api_server.py`` via ``register_chan_routes(app)``.

``/api/chan/analysis`` serves the structure (strokes, centers, buy/sell points)
for any symbol and interval; ``/api/chan/review`` joins it with the fills stored
by the trade-journal importer, adds parent-interval (区间套) confirmation and
MA/volume evidence, so the review page can answer "was this fill at a Chan
buy/sell point?" per trade.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Query

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Any]

_ALLOWED_INTERVALS = {"1m", "5m", "30m", "60m", "1D", "1W"}
_CACHE_TTL_SECONDS = 60.0
_CACHE_MAX_ENTRIES = 64
_CACHE: dict[tuple[str, str, str | None, str | None], tuple[float, dict[str, Any]]] = {}


def _cache_get(key) -> dict[str, Any] | None:
    hit = _CACHE.get(key)
    if hit is None:
        return None
    stamped, payload = hit
    if time.monotonic() - stamped > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key, payload: dict[str, Any]) -> None:
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        oldest = min(_CACHE.items(), key=lambda item: item[1][0])[0]
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.monotonic(), payload)


def _build_structure(symbol: str, start: str | None, end: str | None, interval: str) -> dict[str, Any]:
    from src.chan import analyzer

    _frame, structure = analyzer.load_structure(symbol, interval=interval, start=start, end=end)
    return structure


def _review_symbol(
    symbol: str, start: str | None, end: str | None, interval: str
) -> dict[str, Any]:
    from src.chan import analyzer
    from src.journal import store

    frame, structure = analyzer.load_structure(symbol, interval=interval, start=start, end=end)
    parent_interval = analyzer.PARENT_INTERVAL.get(interval)
    parent = (
        analyzer.load_structure(symbol, interval=parent_interval)
        if parent_interval
        else None
    )
    trades = store.load_trades(symbol=symbol)
    reviews = analyzer.review_trades(
        structure=structure,
        frame=frame,
        trades=trades,
        interval=interval,
        parent=parent,
    )
    return {
        "symbol": symbol,
        "interval": interval,
        "structure": {
            "bars": structure["bars"],
            "latest": structure["latest"],
            "centers": structure["centers"][-5:],
            "signals": structure["signals"][-10:],
        },
        "trades": reviews,
    }


def register_chan_routes(
    app: FastAPI,
    require_auth: AuthDep | None = None,
) -> None:
    """Mount the Chan analysis routes onto ``app``."""
    if require_auth is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:  # pragma: no cover - only on unusual import setups
            raise RuntimeError(
                "register_chan_routes: api_server module not in sys.modules; "
                "pass require_auth explicitly"
            )
        require_auth = host.require_auth

    @app.get("/api/chan/analysis", dependencies=[Depends(require_auth)])
    async def chan_analysis(
        symbol: str = Query(..., min_length=1, max_length=32),
        start: str | None = Query(None, max_length=10),
        end: str | None = Query(None, max_length=10),
        interval: str = Query("1D", max_length=3),
    ):
        """Return strokes, centers and buy/sell points for one symbol."""
        code = symbol.strip().upper()
        if interval not in _ALLOWED_INTERVALS:
            raise HTTPException(status_code=400, detail=f"interval must be one of {sorted(_ALLOWED_INTERVALS)}")
        key = (code, interval, start, end)
        cached = _cache_get(key)
        if cached is not None:
            return cached
        from src.chan.analyzer import ChanUnavailableError

        try:
            payload = await asyncio.to_thread(_build_structure, code, start, end, interval)
        except ChanUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception:
            logger.exception("chan analysis failed for %s %s", code, interval)
            raise HTTPException(status_code=502, detail="Chan analysis failed")
        _cache_put(key, payload)
        return payload

    @app.get("/api/chan/review", dependencies=[Depends(require_auth)])
    async def chan_review(
        symbol: str = Query(..., min_length=1, max_length=32),
        start: str | None = Query(None, max_length=10),
        end: str | None = Query(None, max_length=10),
        interval: str = Query("1D", max_length=3),
    ):
        """Evaluate stored fills of one symbol against its Chan structure."""
        code = symbol.strip().upper()
        if interval not in _ALLOWED_INTERVALS:
            raise HTTPException(status_code=400, detail=f"interval must be one of {sorted(_ALLOWED_INTERVALS)}")
        from src.chan.analyzer import ChanUnavailableError

        try:
            return await asyncio.to_thread(_review_symbol, code, start, end, interval)
        except ChanUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception:
            logger.exception("chan review failed for %s %s", code, interval)
            raise HTTPException(status_code=502, detail="Chan review failed")

    @app.get("/api/chan/signals", dependencies=[Depends(require_auth)])
    async def chan_signals(
        symbol: str = Query(..., min_length=1, max_length=32),
        start: str | None = Query(None, max_length=10),
        end: str | None = Query(None, max_length=10),
        interval: str = Query("1D", max_length=3),
    ):
        """Return just the buy/sell point list (cheap for chart overlays)."""
        payload = await chan_analysis(symbol=symbol, start=start, end=end, interval=interval)
        return {"symbol": payload["symbol"], "signals": payload["signals"]}

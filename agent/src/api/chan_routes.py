"""Chan-theory (缠论) analysis routes.

Mounted by ``agent/api_server.py`` via ``register_chan_routes(app)``.

``/api/chan/analysis`` serves the structure (strokes, centers, buy/sell points)
for any symbol; ``/api/chan/review`` joins it with the fills stored by the
trade-journal importer, so the review page can answer "was this fill at a
Chan buy/sell point?" per trade.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Query

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Any]

_CACHE_TTL_SECONDS = 60.0
_CACHE_MAX_ENTRIES = 64
_CACHE: dict[tuple[str, str | None, str | None], tuple[float, dict[str, Any]]] = {}


def _cache_get(key: tuple[str, str | None, str | None]) -> dict[str, Any] | None:
    hit = _CACHE.get(key)
    if hit is None:
        return None
    stamped, payload = hit
    if time.monotonic() - stamped > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key: tuple[str, str | None, str | None], payload: dict[str, Any]) -> None:
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        oldest = min(_CACHE.items(), key=lambda item: item[1][0])[0]
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.monotonic(), payload)


def _build_structure(symbol: str, start: str | None, end: str | None) -> dict[str, Any]:
    from src.chan import analyzer

    frame = analyzer.load_frame(symbol, start=start, end=end)
    return analyzer.build_structure(symbol, frame)


def _review_symbol(symbol: str, start: str | None, end: str | None) -> dict[str, Any]:
    from src.chan import analyzer
    from src.journal import store

    frame = analyzer.load_frame(symbol, start=start, end=end)
    structure = analyzer.build_structure(symbol, frame)
    trades = store.load_trades(symbol=symbol)
    reviews = analyzer.review_trades(structure=structure, frame=frame, trades=trades)
    return {
        "symbol": symbol,
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
    ):
        """Return strokes, centers and buy/sell points for one symbol."""
        code = symbol.strip().upper()
        key = (code, start, end)
        cached = _cache_get(key)
        if cached is not None:
            return cached
        from src.chan.analyzer import ChanUnavailableError

        try:
            payload = await asyncio.to_thread(_build_structure, code, start, end)
        except ChanUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception:
            logger.exception("chan analysis failed for %s", code)
            raise HTTPException(status_code=502, detail="Chan analysis failed")
        _cache_put(key, payload)
        return payload

    @app.get("/api/chan/review", dependencies=[Depends(require_auth)])
    async def chan_review(
        symbol: str = Query(..., min_length=1, max_length=32),
        start: str | None = Query(None, max_length=10),
        end: str | None = Query(None, max_length=10),
    ):
        """Evaluate stored fills of one symbol against its Chan structure."""
        code = symbol.strip().upper()
        from src.chan.analyzer import ChanUnavailableError

        try:
            return await asyncio.to_thread(_review_symbol, code, start, end)
        except ChanUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception:
            logger.exception("chan review failed for %s", code)
            raise HTTPException(status_code=502, detail="Chan review failed")

    @app.get("/api/chan/signals", dependencies=[Depends(require_auth)])
    async def chan_signals(
        symbol: str = Query(..., min_length=1, max_length=32),
        start: str | None = Query(None, max_length=10),
        end: str | None = Query(None, max_length=10),
    ):
        """Return just the buy/sell point list (cheap for chart overlays)."""
        payload = await chan_analysis(symbol=symbol, start=start, end=end)
        return {"symbol": payload["symbol"], "signals": payload["signals"]}

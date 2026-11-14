"""Journal (交割单) routes: import, review and trade-level K-line markers.

Mounted by ``agent/api_server.py`` via ``register_journal_routes(app)``.

Import is intentionally file-path based: the browser uploads through
``POST /upload`` first (size/extension guarded there), then posts the returned
relative path here. That keeps browser uploads inside the runtime uploads
directory and lets the same parser serve MCP / CLI callers.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Any]

_ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xls"}
_MAX_TRADES_PAGE = 2000


class ImportJournalRequest(BaseModel):
    """Body for ``POST /api/journal/import``."""

    file_path: str = Field(..., min_length=1, max_length=1024, description="Path returned by POST /upload")
    filename: str | None = Field(None, max_length=255, description="Original upload name, shown in the import list")


def register_journal_routes(
    app: FastAPI,
    require_auth: AuthDep | None = None,
) -> None:
    """Mount the journal routes onto ``app``."""
    if require_auth is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:  # pragma: no cover - only on unusual import setups
            raise RuntimeError(
                "register_journal_routes: api_server module not in sys.modules; "
                "pass require_auth explicitly"
            )
        require_auth = host.require_auth

    @app.get("/api/journal/summary", dependencies=[Depends(require_auth)])
    async def journal_summary():
        """Counts plus the import batches that feed the journal page."""
        from src.journal import store

        def _load() -> dict[str, Any]:
            return {**store.stats(), "batches": store.list_imports()}

        return await asyncio.to_thread(_load)

    @app.get("/api/journal/analysis", dependencies=[Depends(require_auth)])
    async def journal_analysis():
        """Profile, behaviour diagnostics, monthly PnL and recent roundtrips."""
        from src.journal import analysis

        try:
            return await asyncio.to_thread(analysis.build_analysis)
        except Exception:
            logger.exception("journal analysis failed")
            raise HTTPException(status_code=500, detail="Journal analysis failed")

    @app.get("/api/journal/trades", dependencies=[Depends(require_auth)])
    async def journal_trades(
        symbol: str | None = Query(None, max_length=32),
        limit: int = Query(500, ge=1, le=_MAX_TRADES_PAGE),
        offset: int = Query(0, ge=0),
    ):
        """Stored fills, optionally for one symbol (used to draw K-line markers)."""
        from src.journal import store

        rows = await asyncio.to_thread(
            store.load_trades, symbol=symbol, limit=limit, offset=offset
        )
        return {"status": "ok", "symbol": symbol, "count": len(rows), "trades": rows}

    @app.post("/api/journal/import", dependencies=[Depends(require_auth)])
    async def journal_import(payload: ImportJournalRequest):
        """Parse one broker export and persist its fills (duplicates skipped)."""
        from src.journal import store
        from src.tools.path_utils import safe_user_path
        from src.tools.trade_journal_parsers import parse_file

        try:
            path = safe_user_path(payload.file_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {payload.file_path}")
        if Path(path).suffix.lower() not in _ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail="Journal import accepts .csv, .xlsx or .xls files",
            )

        display_name = Path(payload.filename).name if payload.filename else Path(path).name

        def _run() -> dict[str, Any]:
            format_name, records = parse_file(path)
            summary = store.import_records(
                records, filename=display_name, format_name=format_name
            )
            return {"status": "ok", "format": format_name, **summary}

        try:
            return await asyncio.to_thread(_run)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception:
            logger.exception("journal import failed for %s", payload.file_path)
            raise HTTPException(status_code=500, detail="Journal import failed")

    @app.delete("/api/journal/imports/{import_id}", dependencies=[Depends(require_auth)])
    async def journal_delete_import(import_id: str):
        """Remove one import batch and the fills it contributed."""
        from src.journal import store

        if not import_id or len(import_id) > 64 or not import_id.isalnum():
            raise HTTPException(status_code=400, detail="invalid import_id")
        removed = await asyncio.to_thread(store.delete_import, import_id)
        if removed["imports"] == 0:
            raise HTTPException(status_code=404, detail="Import not found")
        return {"status": "ok", **removed}

"""SQLite store for imported broker trade journals.

One row per fill, keyed by a hash of the fill itself, so re-importing an
overlapping monthly statement inserts only the new fills instead of doubling
every position. The store is deliberately separate from ``runs/``: a journal is
account history, not a backtest artifact, and it must outlive any single run.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.config.paths import get_runtime_root
from src.tools.trade_journal_parsers import TradeRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    import_id  TEXT PRIMARY KEY,
    filename   TEXT NOT NULL,
    format     TEXT NOT NULL,
    records    INTEGER NOT NULL,
    inserted   INTEGER NOT NULL,
    duplicates INTEGER NOT NULL,
    first_date TEXT,
    last_date  TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    trade_id  TEXT PRIMARY KEY,
    import_id TEXT NOT NULL,
    datetime  TEXT NOT NULL,
    symbol    TEXT NOT NULL,
    name      TEXT NOT NULL DEFAULT '',
    side      TEXT NOT NULL,
    quantity  REAL NOT NULL,
    price     REAL NOT NULL,
    amount    REAL NOT NULL,
    fee       REAL NOT NULL,
    market    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_journal_trades_datetime ON trades(datetime);
CREATE INDEX IF NOT EXISTS idx_journal_trades_import ON trades(import_id);
"""

_TRADE_COLUMNS = (
    "trade_id", "import_id", "datetime", "symbol", "name", "side",
    "quantity", "price", "amount", "fee", "market",
)


def journal_dir() -> Path:
    """Return the directory holding the journal database."""
    return get_runtime_root() / "journal"


def db_path() -> Path:
    """Return the journal SQLite file path."""
    return journal_dir() / "journal.sqlite"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    """Open the journal database, creating it and its schema on first use."""
    journal_dir().mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path(), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(_SCHEMA)
    return connection


def trade_fingerprint(record: TradeRecord) -> str:
    """Return a stable id for one fill.

    Includes notional as well as price/qty so two genuinely different fills at
    the same second do not collapse into one. Overlapping monthly statements
    repeat the same fill with identical values, which is exactly the case this
    dedupes.
    """
    payload = "|".join(
        (
            str(record.datetime),
            record.symbol,
            record.side,
            f"{record.quantity:.6f}",
            f"{record.price:.6f}",
            f"{record.amount:.2f}",
        )
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def import_records(
    records: Iterable[TradeRecord],
    *,
    filename: str,
    format_name: str,
    import_id: str | None = None,
) -> dict[str, Any]:
    """Persist parsed fills, skipping ones already stored.

    Returns:
        Summary with ``import_id``, ``records``, ``inserted``, ``duplicates``,
        ``first_date`` and ``last_date``.
    """
    rows = list(records)
    if not rows:
        raise ValueError("No trade records to import")
    import_id = import_id or hashlib.sha1(
        f"{filename}|{_utc_now()}".encode("utf-8")
    ).hexdigest()[:12]
    created_at = _utc_now()
    inserted = 0
    duplicates = 0

    connection = _connect()
    try:
        with connection:
            for record in rows:
                trade_id = trade_fingerprint(record)
                try:
                    connection.execute(
                        """
                        INSERT INTO trades (
                            trade_id, import_id, datetime, symbol, name, side,
                            quantity, price, amount, fee, market, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            trade_id,
                            import_id,
                            str(record.datetime),
                            record.symbol,
                            record.name or "",
                            record.side,
                            float(record.quantity),
                            float(record.price),
                            float(record.amount),
                            float(record.fee),
                            record.market,
                            created_at,
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    duplicates += 1

            dates = [str(record.datetime) for record in rows if record.datetime]
            connection.execute(
                """
                INSERT INTO imports (
                    import_id, filename, format, records, inserted, duplicates,
                    first_date, last_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_id,
                    filename,
                    format_name,
                    len(rows),
                    inserted,
                    duplicates,
                    min(dates) if dates else None,
                    max(dates) if dates else None,
                    created_at,
                ),
            )
    finally:
        connection.close()

    return {
        "import_id": import_id,
        "records": len(rows),
        "inserted": inserted,
        "duplicates": duplicates,
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }


def list_imports() -> list[dict[str, Any]]:
    """Return import batches, newest first."""
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT * FROM imports ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def delete_import(import_id: str) -> dict[str, int]:
    """Delete one import batch and the fills that came from it."""
    connection = _connect()
    try:
        with connection:
            removed = connection.execute(
                "DELETE FROM trades WHERE import_id = ?", (import_id,)
            ).rowcount
            batches = connection.execute(
                "DELETE FROM imports WHERE import_id = ?", (import_id,)
            ).rowcount
        return {"trades": int(removed or 0), "imports": int(batches or 0)}
    finally:
        connection.close()


def load_trades(
    *,
    symbol: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return stored fills ordered by time, optionally filtered by symbol."""
    query = f"SELECT {', '.join(_TRADE_COLUMNS)} FROM trades"
    params: list[Any] = []
    if symbol:
        query += " WHERE symbol = ?"
        params.append(symbol.strip().upper())
    query += " ORDER BY datetime ASC, trade_id ASC"
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
    connection = _connect()
    try:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def stats() -> dict[str, Any]:
    """Return aggregate counts for the summary endpoint."""
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT COUNT(*) AS records,
                   COUNT(DISTINCT symbol) AS symbols,
                   MIN(datetime) AS first_date,
                   MAX(datetime) AS last_date,
                   COUNT(DISTINCT import_id) AS imports
            FROM trades
            """
        ).fetchone()
        return {
            "records": int(row["records"] or 0),
            "symbols": int(row["symbols"] or 0),
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "imports": int(row["imports"] or 0),
        }
    finally:
        connection.close()


def load_dataframe() -> pd.DataFrame:
    """Return every stored fill as the analysis DataFrame.

    Columns match ``records_to_dataframe`` so the existing profile / behavior
    code can run on the journal unchanged.
    """
    columns = [
        "datetime", "symbol", "name", "side", "quantity",
        "price", "amount", "fee", "market",
    ]
    rows = load_trades()
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)[columns]
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
    frame = frame.dropna(subset=["datetime"]).sort_values("datetime", kind="stable")
    return frame.reset_index(drop=True)

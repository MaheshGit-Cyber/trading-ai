"""SQLite byte-offset index for the large NSE adjusted panel.

The CSV is ~1.8 GB and is sorted by date, not symbol. A single-stock query
therefore scans the whole file. This index stores only:

    symbol, stock_id, date, byte offset, byte length

for every row. A query seeks to the matching lines, so the price data is not
duplicated. The CSV remains the source of truth; delete the index and the
loader falls back to streaming.

Build once:

    python3 jobs/build_brain_panel_index.py

Query:

    python3 -m brain.scorer --symbol RELIANCE --as-of 2026-11-19

The index is a local cache. It is not a licensed data product and must not be
shipped to users.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import tempfile

DEFAULT_INDEX = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "data",
    "brain",
    "panel_index.sqlite",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS panel_index (
    symbol TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    date TEXT NOT NULL,
    offset INTEGER NOT NULL,
    length INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _read_header_only(path: str) -> tuple[list[str], int]:
    with open(path, "rb") as f:
        line = f.readline()
    return next(csv.reader([line.decode("utf-8-sig").rstrip("\r\n")])), len(line)


def build_index(
    panel_path: str,
    index_path: str = DEFAULT_INDEX,
    *,
    batch_size: int = 50_000,
    force: bool = False,
    progress: bool = True,
) -> dict:
    """Build the offset index atomically and return metadata."""
    if not os.path.exists(panel_path):
        raise FileNotFoundError(panel_path)
    if os.path.exists(index_path) and not force:
        raise FileExistsError(f"{index_path} exists; pass force=True")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="panel_index_", suffix=".sqlite", dir=os.path.dirname(os.path.abspath(index_path))
    )
    os.close(fd)
    os.unlink(tmp_path)
    rows = 0
    min_date = "9999-99-99"
    max_date = ""
    symbols: set[str] = set()
    try:
        con = sqlite3.connect(tmp_path)
        con.execute("PRAGMA journal_mode=OFF")
        con.execute("PRAGMA synchronous=OFF")
        con.execute("PRAGMA temp_store=MEMORY")
        con.executescript(SCHEMA)
        header, offset = _read_header_only(panel_path)
        try:
            date_i = header.index("date")
            stock_i = header.index("stock_id")
            symbol_i = header.index("symbol")
        except ValueError as exc:
            raise ValueError("panel must contain date, stock_id, symbol") from exc

        batch: list[tuple[str, str, str, int, int]] = []
        with open(panel_path, "rb") as f:
            f.seek(offset)
            while True:
                line = f.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if not text:
                    offset += len(line)
                    continue
                # First four columns are date, stock_id, market, symbol. They
                # never contain commas in this panel; names can, so limit split.
                parts = text.split(",", 4)
                if len(parts) < 4:
                    offset += len(line)
                    continue
                day = parts[date_i].strip()
                stock_id = parts[stock_i].strip()
                symbol = parts[symbol_i].strip().upper()
                if day and symbol:
                    batch.append((symbol, stock_id, day, offset, len(line)))
                    if day < min_date:
                        min_date = day
                    if day > max_date:
                        max_date = day
                    symbols.add(symbol)
                offset += len(line)
                if len(batch) >= batch_size:
                    con.executemany(
                        "INSERT INTO panel_index VALUES (?, ?, ?, ?, ?)", batch
                    )
                    con.commit()
                    rows += len(batch)
                    if progress and rows % 1_000_000 == 0:
                        print(f"  indexed {rows:,} rows...")
                    batch.clear()
        if batch:
            con.executemany("INSERT INTO panel_index VALUES (?, ?, ?, ?, ?)", batch)
            con.commit()
            rows += len(batch)
        con.execute("CREATE INDEX IF NOT EXISTS idx_symbol_date ON panel_index(symbol, date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_stock_date ON panel_index(stock_id, date)")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('panel_path', ?)", (os.path.abspath(panel_path),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('rows', ?)", (str(rows),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('min_date', ?)", (min_date,))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('max_date', ?)", (max_date,))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('symbols', ?)", (str(len(symbols)),))
        con.commit()
        con.close()
        os.replace(tmp_path, index_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return {
        "index": os.path.abspath(index_path),
        "panel": os.path.abspath(panel_path),
        "rows": rows,
        "min_date": min_date,
        "max_date": max_date,
        "symbols": len(symbols),
    }


def _read_header(panel_path: str) -> list[str]:
    with open(panel_path, "rb") as f:
        line = f.readline()
    return next(csv.reader([line.decode("utf-8-sig").rstrip("\r\n")]))


def query_rows(
    panel_path: str,
    index_path: str,
    *,
    symbol: str | None = None,
    stock_id: str | None = None,
    as_of: str | None = None,
    max_bars: int = 320,
) -> list[dict[str, str]]:
    """Return the last ``max_bars`` raw rows for one stock via byte seeks.

    Raises ``FileNotFoundError`` when the index is absent; the caller should
    fall back to streaming the CSV. Raises ``LookupError`` when the index has
    no matching rows.
    """
    if not os.path.exists(index_path):
        raise FileNotFoundError(index_path)
    if not os.path.exists(panel_path):
        raise FileNotFoundError(panel_path)
    if not symbol and not stock_id:
        raise ValueError("pass symbol or stock_id")
    if max_bars < 1:
        raise ValueError("max_bars must be >= 1")
    day = as_of or "9999-12-31"
    con = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        if stock_id:
            rows = con.execute(
                "SELECT offset, length FROM panel_index "
                "WHERE stock_id=? AND date<=? ORDER BY date DESC LIMIT ?",
                (stock_id, day, max_bars),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT offset, length FROM panel_index "
                "WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT ?",
                (symbol.strip().upper(), day, max_bars),
            ).fetchall()
    finally:
        con.close()
    if not rows:
        target = stock_id or symbol
        raise LookupError(f"no indexed rows for {target!r} up to {as_of!r}")
    header = _read_header(panel_path)
    out: list[dict[str, str]] = []
    with open(panel_path, "rb") as f:
        for offset, length in reversed(rows):
            f.seek(offset)
            line = f.read(length).decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            values = next(csv.reader([line]))
            if len(values) != len(header):
                continue
            out.append(dict(zip(header, values)))
    return out

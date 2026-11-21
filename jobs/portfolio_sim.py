#!/usr/bin/env python3
"""Portfolio-level cash simulation for a trade list.

The strategy backtest sizes each trade independently. That is fine for measuring
per-trade expectancy, but it is not executable: H3 produced up to 84 concurrent
positions with Rs 10 lakh capital. This job replays the trades through a real
cash ledger:

- fixed capital
- max concurrent positions
- max position value as a fraction of capital
- same-day candidates ranked by RS percentile
- skipped trades are not queued

It writes a daily mark-to-market equity curve and portfolio drawdown.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import statistics


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades", required=True)
    p.add_argument("--panel", default="data/curated/panel.csv")
    p.add_argument("--outdir", default="data/backtest_h4/portfolio")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--max-position-pct", type=float, default=0.20)
    p.add_argument("--db", default=None)
    p.add_argument(
        "--reuse-db",
        action="store_true",
        help="reuse an existing --db instead of rebuilding prices",
    )
    p.add_argument(
        "--stress",
        action="store_true",
        help="use net_R_stress (2x slippage) instead of net_R",
    )
    return p.parse_args()


def load_trades(path: str, stress: bool = False) -> list[dict]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r.get("exit_date"):
                continue
            try:
                qty = int(float(r["qty"]))
                entry = float(r["entry"])
                exit_ = float(r["exit_price"])
                risk_ps = float(r["risk_per_share"])
                net_r = float(r["net_R_stress"] if stress else r["net_R"])
            except (KeyError, ValueError, TypeError):
                continue
            if qty < 1 or entry <= 0:
                continue
            actual_risk = qty * risk_ps
            out.append(
                {
                    "stock_id": r["stock_id"],
                    "symbol": r.get("symbol", ""),
                    "signal_date": r.get("signal_date", ""),
                    "entry_date": r["entry_date"],
                    "exit_date": r["exit_date"],
                    "entry": entry,
                    "exit_price": exit_,
                    "qty": qty,
                    "risk_per_share": risk_ps,
                    "actual_risk": actual_risk,
                    "net_R": net_r,
                    "gross_R": float(r.get("gross_R") or 0.0),
                    "cost_R": float(r.get("cost_R") or 0.0),
                    "notional": qty * entry,
                    "pnl": net_r * actual_risk,
                    "rs_pct": float(r.get("rs_pct") or 0.0),
                    "exit_reason": r.get("exit_reason", ""),
                }
            )
    out.sort(key=lambda x: (x["entry_date"], -x["rs_pct"], x["stock_id"]))
    return out


def build_price_db(panel: str, db_path: str, stock_ids: set[str]) -> None:
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(
        "CREATE TABLE prices (date TEXT, stock_id TEXT, close REAL, "
        "PRIMARY KEY (date, stock_id))"
    )
    batch = []
    rows = 0
    with open(panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            if row[ix["market"]] != "NSE" or row[ix["series"]] != "EQ":
                continue
            sid = row[ix["stock_id"]]
            if sid not in stock_ids:
                continue
            try:
                close = float(row[ix["adj_close"]])
            except (TypeError, ValueError):
                continue
            batch.append((row[ix["date"]], sid, close))
            rows += 1
            if len(batch) >= 50_000:
                conn.executemany(
                    "INSERT OR REPLACE INTO prices VALUES (?,?,?)", batch
                )
                batch.clear()
    if batch:
        conn.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?)", batch)
    conn.commit()
    conn.execute("CREATE INDEX idx_prices_stock_date ON prices(stock_id, date)")
    conn.commit()
    conn.close()
    print(f"price db rows: {rows}")


def last_close(conn: sqlite3.Connection, stock_id: str, date: str) -> float | None:
    cur = conn.execute(
        "SELECT close FROM prices WHERE stock_id=? AND date<=? "
        "ORDER BY date DESC LIMIT 1",
        (stock_id, date),
    )
    row = cur.fetchone()
    return row[0] if row else None


def main() -> None:
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    trades = load_trades(args.trades, args.stress)
    if not trades:
        raise SystemExit("no closed trades")

    db_path = args.db or os.path.join(args.outdir, "prices.db")
    stock_ids = {t["stock_id"] for t in trades}
    if not (args.reuse_db and os.path.exists(db_path)):
        build_price_db(args.panel, db_path, stock_ids)
    conn = sqlite3.connect(db_path)

    dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM prices ORDER BY date")]
    if not dates:
        raise SystemExit("price db is empty")
    entries_by_date: dict[str, list[dict]] = {}
    for t in trades:
        entries_by_date.setdefault(t["entry_date"], []).append(t)

    cash = args.capital
    open_positions: list[dict] = []
    equity_curve = []
    taken: list[dict] = []
    skipped: list[dict] = []
    max_concurrent = 0

    for date in dates:
        # Exits first: release notional plus net P&L.
        still_open = []
        for pos in open_positions:
            if pos["exit_date"] <= date:
                cash += pos["notional"] + pos["pnl"]
            else:
                still_open.append(pos)
        open_positions = still_open

        # Entries: rank by RS percentile (already sorted), take until full.
        for t in entries_by_date.get(date, []):
            if len(open_positions) >= args.max_positions:
                skipped.append({**t, "skip_reason": "max_positions"})
                continue
            if t["notional"] > cash + 1e-9:
                skipped.append({**t, "skip_reason": "cash"})
                continue
            if t["notional"] > args.capital * args.max_position_pct + 1e-9:
                skipped.append({**t, "skip_reason": "position_cap"})
                continue
            cash -= t["notional"]
            open_positions.append(t)
            taken.append(t)

        mtm = 0.0
        for pos in open_positions:
            px = last_close(conn, pos["stock_id"], date)
            if px is None:
                px = pos["entry"]
            mtm += pos["qty"] * px
        equity = cash + mtm
        equity_curve.append(
            {
                "date": date,
                "cash": cash,
                "mtm": mtm,
                "equity": equity,
                "open_positions": len(open_positions),
            }
        )
        max_concurrent = max(max_concurrent, len(open_positions))

    # Close anything still open at the last available price.
    for pos in open_positions:
        cash += pos["notional"] + pos["pnl"]
    open_positions = []

    conn.close()

    equities = [r["equity"] for r in equity_curve]
    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        peak = max(peak, e)
        max_dd = min(max_dd, e / peak - 1.0)

    first = equity_curve[0]["date"]
    last = equity_curve[-1]["date"]
    from datetime import date as ddate

    years = max((ddate.fromisoformat(last) - ddate.fromisoformat(first)).days / 365.25, 1e-9)
    total_return = equities[-1] / args.capital - 1.0
    cagr = (equities[-1] / args.capital) ** (1.0 / years) - 1.0
    avg_exposure = statistics.fmean(
        [r["mtm"] / args.capital for r in equity_curve]
    )

    def stats(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0}
        nets = [r["net_R"] for r in rows]
        return {
            "n": len(rows),
            "expectancy_R": statistics.fmean(nets),
            "pnl": sum(r["pnl"] for r in rows),
            "wins": sum(1 for x in nets if x > 0),
            "win_rate": sum(1 for x in nets if x > 0) / len(nets),
        }

    summary = {
        "trades_file": args.trades,
        "capital": args.capital,
        "stress": args.stress,
        "max_positions": args.max_positions,
        "max_position_pct": args.max_position_pct,
        "period": [first, last],
        "years": years,
        "final_equity": equities[-1],
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "avg_exposure": avg_exposure,
        "max_concurrent": max_concurrent,
        "taken": stats(taken),
        "skipped": stats(skipped),
        "skipped_by_reason": {
            reason: sum(1 for r in skipped if r.get("skip_reason") == reason)
            for reason in ("max_positions", "cash", "position_cap")
        },
    }
    with open(os.path.join(args.outdir, "summary_portfolio.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(args.outdir, "equity_curve.csv"), "w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["date", "cash", "mtm", "equity", "open_positions"]
        )
        w.writeheader()
        w.writerows(equity_curve)
    for name, rows in (("taken_trades.csv", taken), ("skipped_trades.csv", skipped)):
        with open(os.path.join(args.outdir, name), "w", newline="") as f:
            fields = [
                "stock_id", "symbol", "signal_date", "entry_date", "exit_date",
                "entry", "exit_price", "qty", "notional", "net_R", "pnl",
                "rs_pct", "exit_reason", "skip_reason",
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fields})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""A2 cross-sectional momentum backtest (pre-registered).

Spec: ``docs/a2-cross-sectional-momentum-spec.md``.

Rules, in one line: point-in-time top-200-by-turnover NSE large caps, 12-1
month momentum, long-only top decile, equal weight, monthly rebalance at the
next open, Nifty 50 200DMA regime overlay (ON primary, OFF diagnostic), full
delivery costs, 2x slippage stress, 2024-12-10 train/test split.

This job is deliberately separate from ``backtest_monthly_momentum.py`` so the
closed Phase 2A/2B result is not disturbed. It reuses that job's cost model,
price loader, portfolio simulator and benchmark helper.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict, deque
from datetime import date as ddate, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jobs.backtest_monthly_momentum import (  # noqa: E402
    EXCLUDE_TOKENS,
    build_month_pairs,
    daily_stats,
    equal_weight_benchmark,
    load_nifty,
    load_selected_prices,
    max_drawdown,
    run_portfolio,
)

RISK_FLAGS = frozenset(
    {
        "ca_unadjusted",
        "ca_rights_unknown",
        "ca_split_unknown",
        "ca_bonus_unknown",
        "ca_not_reflected",
    }
)

# Name-based sector proxy. Diagnostic only: there is no point-in-time sector
# master in the local data. First match wins.
SECTOR_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Banks", ("BANK",)),
    (
        "Financials",
        (
            "FINANCE",
            "FINSERV",
            "NBFC",
            "CAPITAL",
            "INVEST",
            "ASSET MANAGEMENT",
            "AMC",
            "HOUSING FINANCE",
            "MUTHOOT",
            "MANAPPURAM",
            "CHOLAMANDALAM",
            "SHRIRAM",
        ),
    ),
    ("Insurance", ("INSURANCE", "LIFE INSURANCE", "LOMBARD", "GENERAL INSURANCE")),
    (
        "Pharma/Healthcare",
        (
            "PHARMA",
            "DRUG",
            "LABORATOR",
            "LAB ",
            "HEALTH",
            "HOSPITAL",
            "MEDIC",
            "BIOCON",
            "DIVIS",
            "CIPLA",
            "LUPIN",
            "AUROBINDO",
            "GLENMARK",
            "ALKEM",
            "MANKIND",
            "ZYDUS",
        ),
    ),
    (
        "Auto",
        (
            "AUTO",
            "MOTOR",
            "TYRE",
            "VEHICLE",
            "MARUTI",
            "EICHER",
            "HERO",
            "TVS",
            "ASHOK LEYLAND",
            "BOSCH",
            "MOTHERSON",
            "BALKRISHNA",
        ),
    ),
    (
        "Metals",
        (
            "STEEL",
            "IRON",
            "ALUMIN",
            "COPPER",
            "ZINC",
            "METAL",
            "HINDALCO",
            "VEDANTA",
            "NMDC",
            "SAIL",
        ),
    ),
    ("Cement", ("CEMENT", "ULTRATECH", "AMBUJA", "ACC ", "DALMIA", "RAMCO")),
    (
        "Energy",
        (
            "POWER",
            "ENERGY",
            "OIL",
            "GAS",
            "PETRO",
            "REFIN",
            "RELIANCE",
            "NTPC",
            "ONGC",
            "COAL INDIA",
            "BPCL",
            "HPCL",
            "IOC",
            "GAIL",
            "TATA POWER",
            "ADANI GREEN",
        ),
    ),
    (
        "IT",
        (
            "INFOTECH",
            "SOFTWARE",
            "TECH",
            "COMPUTER",
            "DIGITAL",
            "INFOSYS",
            "WIPRO",
            "TCS",
            "HCL",
            "MAHINDRA",
            "LTIM",
            "PERSISTENT",
            "COFORGE",
            "MPHASIS",
        ),
    ),
    ("Telecom", ("TELECOM", "COMMUNICATION", "BHARTI AIRTEL", "VODAFONE", "INDUS TOWERS")),
    (
        "FMCG",
        (
            "FMCG",
            "FOOD",
            "CONSUMER",
            "BEVERAGE",
            "TOBACCO",
            "HINDUNILVR",
            "ITC",
            "NESTLE",
            "BRITANNIA",
            "DABUR",
            "MARICO",
            "COLGATE",
        ),
    ),
    (
        "Chemicals",
        (
            "CHEM",
            "FERTIL",
            "PAINT",
            "PIDILITE",
            "SRF",
            "UPL",
            "PI INDUSTRIES",
            "DEEPAK NITRITE",
            "AARTI",
            "COROMANDEL",
        ),
    ),
    ("Realty", ("REALTY", "PROPERT", "HOUSING", "DLF", "OBEROI", "PRESTIGE", "BRIGADE", "PHOENIX")),
    ("Infra", ("INFRA", "CONSTRUCTION", "ENGINEER", "LARSEN", "L&T", "ADANI PORTS")),
    ("Defence", ("DEFENCE", "DEFENSE", "AEROSPACE", "HAL", "BEL", "BDL", "MAZAGON")),
    ("Railways", ("RAIL", "IRCTC", "RVNL", "IRFC", "TITAGARH", "CONCOR")),
    ("Shipping/Ports", ("SHIP", "PORT", "LOGISTIC", "CONTAINER")),
    ("Hotels", ("HOTEL", "RESORT", "EIH", "LEMON TREE", "CHALET")),
    ("Media", ("MEDIA", "ENTERTAIN", "BROADCAST", "ZEE", "SUN TV", "NETWORK18", "TV18")),
    ("Retail", ("RETAIL", "STORE", "MART", "DMART", "TRENT", "V-MART", "SHOPPERS STOP")),
    ("Textiles", ("TEXTILE", "COTTON", "YARN", "PAGE INDUSTRIES", "KPR MILL", "ARVIND", "TRIDENT")),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/curated/panel_nse_isin_v3.csv")
    p.add_argument("--nifty", default="data/index/nifty50.csv")
    p.add_argument("--master", default="data/nse_equity_master.csv")
    p.add_argument("--outdir", default="data/backtest/a2_momentum")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--start", default="2011-01-01")
    p.add_argument("--end", default="2026-11-19")
    p.add_argument("--min-price", type=float, default=20.0)
    p.add_argument("--min-turnover", type=float, default=100.0)
    p.add_argument("--max-adv-pct", type=float, default=0.05)
    p.add_argument("--largecap-n", type=int, default=200)
    p.add_argument("--decile-frac", type=float, default=0.10)
    p.add_argument("--split", default="2024-12-10")
    p.add_argument("--min-test-months", type=int, default=20)
    p.add_argument("--dividend-yield", type=float, default=0.012)
    p.add_argument("--writeoff-days", type=int, default=90)
    p.add_argument("--bootstrap", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def parse_flags(raw: str) -> frozenset[str]:
    if not raw:
        return frozenset()
    text = raw.replace("|", ";").replace(",", ";")
    return frozenset(x.strip() for x in text.split(";") if x.strip())


def build_nifty_regime(
    dates: list[str], closes: dict[str, float], window: int = 200
) -> dict[str, bool]:
    """Close > trailing simple moving average, evaluated on each date."""
    out: dict[str, bool] = {}
    q: deque[float] = deque()
    total = 0.0
    for d in dates:
        x = closes.get(d)
        if x is None:
            continue
        q.append(x)
        total += x
        if len(q) > window:
            total -= q.popleft()
        if len(q) == window:
            out[d] = x > total / window
    return out


def momentum_12_1(closes) -> float | None:
    """12-1 momentum from a chronological own-session close series.

    ``closes[-1]`` is the signal close. The most recent 21 sessions are
    skipped; the base is 252 sessions before the signal close.
    """
    if len(closes) < 253:
        return None
    base = closes[-253]
    recent = closes[-22]
    if base <= 0 or recent <= 0:
        return None
    return recent / base - 1.0


def top_decile(rows: list[dict], frac: float = 0.10) -> list[dict]:
    if not rows:
        return []
    ranked = sorted(rows, key=lambda r: (-r["mom"], r["stock_id"]))
    n = max(1, int(len(ranked) * frac))
    return ranked[:n]


def is_excluded(symbol: str, name: str) -> bool:
    text = f"{symbol} {name}".upper()
    return any(tok in text for tok in EXCLUDE_TOKENS)


def sector_proxy(name: str, symbol: str = "") -> str:
    text = f"{symbol} {name}".upper()
    for sector, keys in SECTOR_KEYWORDS:
        if any(k in text for k in keys):
            return sector
    return "Other"


def build_a2_selections(
    args: argparse.Namespace,
    pairs: list[tuple[str, str]],
    regime: dict[str, bool],
):
    signal_set = {s for s, _ in pairs}
    exec_by_signal = {s: e for s, e in pairs}
    closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=300))
    turns: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=20))
    raw: dict[str, float] = {}
    last_seen: dict[str, str] = {}
    meta: dict[str, tuple[str, str]] = {}
    flags: dict[str, frozenset[str]] = {}
    names: dict[str, str] = {}
    selections_on: dict[str, list[dict]] = {}
    selections_off: dict[str, list[dict]] = {}
    universe: dict[str, list[tuple[str, float]]] = {}
    eligible_counts: dict[str, int] = {}
    largecap_counts: dict[str, int] = {}
    current_date: str | None = None

    def flush(d: str) -> None:
        if d not in signal_set:
            return
        scored: list[dict] = []
        for sid, cs in closes.items():
            if len(cs) < 253:
                continue
            if last_seen.get(sid) != d:
                continue
            if raw.get(sid, 0.0) < args.min_price:
                continue
            ts = turns[sid]
            if len(ts) < 20:
                continue
            t20 = sum(ts) / 20.0
            if t20 < args.min_turnover:
                continue
            sym, name = meta.get(sid, ("", ""))
            if is_excluded(sym, name):
                continue
            if flags.get(sid, frozenset()) & RISK_FLAGS:
                continue
            mom = momentum_12_1(cs)
            if mom is None:
                continue
            scored.append(
                {
                    "stock_id": sid,
                    "mom": mom,
                    "turnover20": t20,
                    "signal_close": cs[-1],
                    "symbol": sym,
                    "name": name,
                }
            )

        if not scored:
            universe[d] = []
            eligible_counts[d] = 0
            largecap_counts[d] = 0
            selections_on[d] = []
            selections_off[d] = []
            return

        # Point-in-time large-cap proxy: highest 20D turnover.
        scored.sort(key=lambda x: (-x["turnover20"], x["stock_id"]))
        largecap = scored[: args.largecap_n]
        universe[d] = [(x["stock_id"], x["signal_close"]) for x in largecap]
        eligible_counts[d] = len(scored)
        largecap_counts[d] = len(largecap)

        chosen = top_decile(largecap, args.decile_frac)
        n = len(chosen)
        weight = 1.0 / n if n else 0.0
        rows: list[dict] = []
        for i, x in enumerate(chosen, 1):
            row = dict(x)
            row["rank"] = i
            row["weight"] = weight
            row["signal_date"] = d
            row["execution_date"] = exec_by_signal[d]
            rows.append(row)

        selections_off[d] = rows
        if regime.get(d, False):
            selections_on[d] = [dict(x) for x in rows]
        else:
            selections_on[d] = []

    with open(args.panel, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        ix = {name: i for i, name in enumerate(header)}
        for row in reader:
            d = row[ix["date"]]
            if d > args.end:
                break
            if d != current_date:
                if current_date is not None:
                    flush(current_date)
                current_date = d
            if row[ix["market"]] != "NSE" or row[ix["series"]] != "EQ":
                continue
            sid = row[ix["stock_id"]]
            try:
                c = float(row[ix["adj_close"]])
                raw_c = float(row[ix["close"]])
                turn = float(row[ix["turnover_lacs"]] or 0.0)
            except (TypeError, ValueError):
                continue
            if c <= 0 or raw_c <= 0:
                continue
            closes[sid].append(c)
            turns[sid].append(turn)
            raw[sid] = raw_c
            last_seen[sid] = d
            meta[sid] = (row[ix["symbol"]], row[ix["name"]])
            flags[sid] = parse_flags(row[ix["flags"]])
            names[sid] = row[ix["name"]] or row[ix["symbol"]]
    if current_date is not None:
        flush(current_date)
    return (
        selections_on,
        selections_off,
        universe,
        eligible_counts,
        largecap_counts,
        names,
    )


def next_day(s: str) -> str:
    return (ddate.fromisoformat(s) + timedelta(days=1)).isoformat()


def next_month(ym: str) -> str:
    y, m = (int(x) for x in ym.split("-"))
    if m == 12:
        return f"{y + 1:04d}-01"
    return f"{y:04d}-{m + 1:02d}"


def monthly_from_curve(curve: list[dict]) -> list[dict]:
    last_by_month: dict[str, float] = {}
    first_equity: float | None = None
    for r in curve:
        if first_equity is None:
            first_equity = r["equity"]
        last_by_month[r["date"][:7]] = r["equity"]
    out: list[dict] = []
    if first_equity is None:
        return out
    prev = first_equity
    for ym in sorted(last_by_month):
        eq = last_by_month[ym]
        out.append({"month": ym, "equity": eq, "return": eq / prev - 1.0})
        prev = eq
    return out


def profit_factor(returns: list[float]) -> float | None:
    if not returns:
        return None
    wins = sum(r for r in returns if r > 0)
    losses = -sum(r for r in returns if r < 0)
    if losses <= 0:
        return float("inf") if wins > 0 else None
    return wins / losses


def curve_stats(
    curve: list[dict],
    monthly: list[dict],
    start: str | None = None,
    end: str | None = None,
    month_start: str | None = None,
    month_end: str | None = None,
) -> dict:
    sub = [
        r
        for r in curve
        if (start is None or r["date"] >= start) and (end is None or r["date"] <= end)
    ]
    if len(sub) < 2:
        return {
            "first_date": None,
            "last_date": None,
            "years": None,
            "months": 0,
            "total_return": None,
            "cagr": None,
            "sharpe": None,
            "sortino": None,
            "vol_annual": None,
            "max_drawdown": None,
            "max_drawdown_peak": None,
            "max_drawdown_trough": None,
            "profit_factor": None,
            "hit_rate": None,
            "avg_monthly": None,
            "best_month": None,
            "worst_month": None,
        }
    first = sub[0]
    last = sub[-1]
    years = max(
        (ddate.fromisoformat(last["date"]) - ddate.fromisoformat(first["date"])).days
        / 365.25,
        1e-9,
    )
    total = last["equity"] / first["equity"] - 1.0
    cagr = (last["equity"] / first["equity"]) ** (1.0 / years) - 1.0
    dd, peak, trough = max_drawdown(sub)
    st = daily_stats(sub)
    mons = [
        m
        for m in monthly
        if (month_start is None or m["month"] >= month_start)
        and (month_end is None or m["month"] <= month_end)
    ]
    rets = [m["return"] for m in mons]
    return {
        "first_date": first["date"],
        "last_date": last["date"],
        "years": years,
        "months": len(rets),
        "total_return": total,
        "cagr": cagr,
        "sharpe": st["sharpe"],
        "sortino": st["sortino"],
        "vol_annual": st["vol_annual"],
        "max_drawdown": dd,
        "max_drawdown_peak": peak,
        "max_drawdown_trough": trough,
        "profit_factor": profit_factor(rets),
        "hit_rate": (sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
        "avg_monthly": statistics.fmean(rets) if rets else None,
        "best_month": max(rets) if rets else None,
        "worst_month": min(rets) if rets else None,
    }


def monthly_benchmark_stats(monthly: list[dict]) -> dict:
    def sub(start_month: str | None = None, end_month: str | None = None) -> dict:
        rows = [
            m
            for m in monthly
            if (start_month is None or m["month"] >= start_month)
            and (end_month is None or m["month"] <= end_month)
        ]
        if not rows:
            return {
                "months": 0,
                "total_return": None,
                "cagr": None,
                "sharpe": None,
                "max_drawdown": None,
                "profit_factor": None,
                "hit_rate": None,
            }
        eq = 1.0
        cur = 1.0
        peak = 1.0
        worst = 0.0
        rets = [m["return"] for m in rows]
        for r in rets:
            eq *= 1.0 + r
            cur *= 1.0 + r
            peak = max(peak, cur)
            worst = min(worst, cur / peak - 1.0)
        years = len(rets) / 12.0
        sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
        return {
            "months": len(rets),
            "total_return": eq - 1.0,
            "cagr": eq ** (1.0 / years) - 1.0,
            "sharpe": (statistics.fmean(rets) / sd * math.sqrt(12.0)) if sd else None,
            "max_drawdown": worst,
            "profit_factor": profit_factor(rets),
            "hit_rate": sum(1 for r in rets if r > 0) / len(rets),
        }

    return {"full": sub(), "train": sub(end_month="2024-12"), "test": sub(start_month="2025-01")}


def add_dividend(cagr: float | None, dividend_yield: float) -> float | None:
    if cagr is None:
        return None
    return (1.0 + cagr) * (1.0 + dividend_yield) - 1.0


def regime_wise(
    monthly: list[dict], regime_by_month: dict[str, bool]
) -> dict[str, dict]:
    groups: dict[bool, list[dict]] = {True: [], False: []}
    for m in monthly:
        on = regime_by_month.get(m["month"])
        if on is None:
            continue
        groups[on].append(m)
    out: dict[str, dict] = {}
    for key, label in ((True, "risk_on"), (False, "risk_off")):
        rows = groups[key]
        rets = [m["return"] for m in rows]
        if not rets:
            out[label] = {"months": 0}
            continue
        eq = 1.0
        for r in rets:
            eq *= 1.0 + r
        out[label] = {
            "months": len(rets),
            "avg_monthly": statistics.fmean(rets),
            "hit_rate": sum(1 for r in rets if r > 0) / len(rets),
            "compound_return": eq - 1.0,
            "worst_month": min(rets),
            "best_month": max(rets),
        }
    return out


def sector_concentration(result: dict, names: dict[str, str]) -> dict:
    per_date: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total_by_date: dict[str, float] = defaultdict(float)
    for h in result["holdings"]:
        d = h["execution_date"]
        name = names.get(h["stock_id"], h["stock_id"])
        sec = sector_proxy(name, h["stock_id"])
        per_date[d][sec] += h["value"]
        total_by_date[d] += h["value"]
    weights: list[dict[str, float]] = []
    sector_sum: dict[str, float] = defaultdict(float)
    for d, secs in per_date.items():
        tot = total_by_date[d]
        if tot <= 0:
            continue
        w = {s: v / tot for s, v in secs.items()}
        weights.append(w)
        for s, v in w.items():
            sector_sum[s] += v
    if not weights:
        return {"rebalances": 0, "avg_weights": {}, "method": "name-based proxy"}
    n = len(weights)
    avg = {s: v / n for s, v in sector_sum.items()}
    max_per = [max(w.values()) for w in weights]
    top = sorted(avg.items(), key=lambda kv: -kv[1])[:10]
    return {
        "rebalances": n,
        "avg_weights": dict(sorted(avg.items(), key=lambda kv: -kv[1])),
        "avg_max_sector_weight": statistics.fmean(max_per),
        "worst_max_sector_weight": max(max_per),
        "top_sectors": [{"sector": s, "avg_weight": v} for s, v in top],
        "method": "name-based keyword proxy; not a point-in-time sector master",
    }


def bootstrap_mean_pvalue(
    returns: list[float], n: int = 5000, seed: int = 42
) -> float | None:
    if len(returns) < 2 or n <= 0:
        return None
    rng = random.Random(seed)
    mean = statistics.fmean(returns)
    centered = [r - mean for r in returns]
    count = 0
    for _ in range(n):
        sample = [rng.choice(centered) for _ in centered]
        if statistics.fmean(sample) >= mean:
            count += 1
    return count / n


def sanitize(x):
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    if isinstance(x, dict):
        return {k: sanitize(v) for k, v in x.items()}
    if isinstance(x, list):
        return [sanitize(v) for v in x]
    return x


def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    fieldnames = sorted({k for r in rows for k in r})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def compact_run(run: dict) -> dict:
    return {
        "summary": run["summary"],
        "full": run["full"],
        "train": run["train"],
        "test": run["test"],
        "regime_wise": run["regime_wise"],
    }


def evaluate_gate(
    on_1x: dict,
    on_2x: dict,
    nifty_tr_test_cagr: float | None,
    min_test_months: int,
) -> dict:
    full = on_1x["full"]
    train = on_1x["train"]
    test = on_1x["test"]
    stress = on_2x["test"]

    def gt(x, y) -> bool:
        return x is not None and y is not None and x > y

    def ge(x, y) -> bool:
        return x is not None and x >= y

    conditions = [
        {
            "name": "full_net_cagr_positive",
            "pass": gt(full["cagr"], 0.0),
            "value": full["cagr"],
            "threshold": 0.0,
        },
        {
            "name": "train_net_cagr_positive",
            "pass": gt(train["cagr"], 0.0),
            "value": train["cagr"],
            "threshold": 0.0,
        },
        {
            "name": "test_net_cagr_positive",
            "pass": gt(test["cagr"], 0.0),
            "value": test["cagr"],
            "threshold": 0.0,
        },
        {
            "name": "test_net_sharpe_positive",
            "pass": gt(test["sharpe"], 0.0),
            "value": test["sharpe"],
            "threshold": 0.0,
        },
        {
            "name": "test_stress_2x_cagr_positive",
            "pass": gt(stress["cagr"], 0.0),
            "value": stress["cagr"],
            "threshold": 0.0,
        },
        {
            "name": "test_max_drawdown_within_28pct",
            "pass": ge(test["max_drawdown"], -0.28),
            "value": test["max_drawdown"],
            "threshold": -0.28,
        },
        {
            "name": "full_profit_factor_gt_1_2",
            "pass": gt(full["profit_factor"], 1.2),
            "value": full["profit_factor"],
            "threshold": 1.2,
        },
        {
            "name": "train_profit_factor_gt_1_0",
            "pass": gt(train["profit_factor"], 1.0),
            "value": train["profit_factor"],
            "threshold": 1.0,
        },
        {
            "name": "test_profit_factor_gt_1_0",
            "pass": gt(test["profit_factor"], 1.0),
            "value": test["profit_factor"],
            "threshold": 1.0,
        },
        {
            "name": "test_beats_nifty_tr_proxy",
            "pass": gt(test["cagr"], nifty_tr_test_cagr),
            "value": test["cagr"],
            "threshold": nifty_tr_test_cagr,
        },
        {
            "name": "test_months_at_least_min",
            "pass": ge(test["months"], min_test_months),
            "value": test["months"],
            "threshold": min_test_months,
        },
    ]
    if test["months"] < min_test_months:
        return {
            "decision": "INSUFFICIENT_OOS",
            "conditions": conditions,
            "failed": ["test_months_at_least_min"],
        }
    failed = [c["name"] for c in conditions if not c["pass"]]
    return {
        "decision": "PASS" if not failed else "FAIL",
        "conditions": conditions,
        "failed": failed,
    }


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.2f}%"


def num(x, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def main() -> None:
    args = parse_args()
    nifty_dates, nifty_closes, _ = load_nifty(args.nifty)
    regime = build_nifty_regime(nifty_dates, nifty_closes)
    pairs = build_month_pairs(nifty_dates, args.start, args.end)
    if not pairs:
        raise SystemExit("no monthly rebalance pairs in range")
    print(f"rebalance pairs: {len(pairs)} first={pairs[0]} last={pairs[-1]}")

    (
        selections_on,
        selections_off,
        universe,
        eligible_counts,
        largecap_counts,
        names,
    ) = build_a2_selections(args, pairs, regime)
    if not selections_off:
        raise SystemExit("no monthly selections")

    selected_ids = {
        x["stock_id"]
        for rows in list(selections_on.values()) + list(selections_off.values())
        for x in rows
    }
    first_exec = pairs[0][1]
    opens, closes, factors = load_selected_prices(args, selected_ids, first_exec)

    run_args = argparse.Namespace(**vars(args))
    run_args.target_weight = 0.05
    run_args.slippage_mult = 1.0
    run_args.writeoff_unlisted_only = True

    def run(
        selections: dict[str, list[dict]],
        slippage_mult: float,
        unlisted_only: bool = True,
    ) -> dict:
        a = argparse.Namespace(**vars(run_args))
        a.slippage_mult = slippage_mult
        a.writeoff_unlisted_only = unlisted_only
        return run_portfolio(
            a,
            pairs,
            selections,
            opens,
            closes,
            factors,
            nifty_dates,
            nifty_closes,
        )

    print("running portfolio variants ...")
    on_1x = run(selections_on, 1.0, True)
    on_2x = run(selections_on, 2.0, True)
    off_1x = run(selections_off, 1.0, True)
    off_2x = run(selections_off, 2.0, True)
    zero_1x = run(selections_on, 1.0, False)

    def attach(run_result: dict) -> dict:
        run_result["full"] = curve_stats(run_result["curve"], run_result["monthly"])
        run_result["train"] = curve_stats(
            run_result["curve"],
            run_result["monthly"],
            end=args.split,
            month_end="2024-12",
        )
        run_result["test"] = curve_stats(
            run_result["curve"],
            run_result["monthly"],
            start=next_day(args.split),
            month_start="2025-01",
        )
        run_result["regime_wise"] = regime_wise(
            run_result["monthly"],
            {
                exec_d[:7]: bool(regime.get(signal, False))
                for signal, exec_d in pairs
            },
        )
        return run_result

    for r in (on_1x, on_2x, off_1x, off_2x, zero_1x):
        attach(r)

    # Benchmarks.
    nifty_curve = [
        {"date": d, "equity": nifty_closes[d]}
        for d in nifty_dates
        if first_exec <= d <= args.end and d in nifty_closes
    ]
    nifty_monthly = monthly_from_curve(nifty_curve)
    nifty_stats = {
        "full": curve_stats(nifty_curve, nifty_monthly),
        "train": curve_stats(
            nifty_curve, nifty_monthly, end=args.split, month_end="2024-12"
        ),
        "test": curve_stats(
            nifty_curve,
            nifty_monthly,
            start=next_day(args.split),
            month_start="2025-01",
        ),
    }
    nifty_tr = {
        "dividend_yield": args.dividend_yield,
        "method": "Nifty 50 price CAGR + constant dividend-yield proxy",
        "full": {
            "cagr": add_dividend(nifty_stats["full"]["cagr"], args.dividend_yield),
            "price_cagr": nifty_stats["full"]["cagr"],
        },
        "train": {
            "cagr": add_dividend(nifty_stats["train"]["cagr"], args.dividend_yield),
            "price_cagr": nifty_stats["train"]["cagr"],
        },
        "test": {
            "cagr": add_dividend(nifty_stats["test"]["cagr"], args.dividend_yield),
            "price_cagr": nifty_stats["test"]["cagr"],
        },
    }
    nifty_tr_test_cagr = nifty_tr["test"]["cagr"]

    ew = equal_weight_benchmark(run_args, pairs, universe, nifty_dates)
    ew_monthly = [
        {**m, "month": next_month(m["month"])} for m in ew.get("monthly", [])
    ]
    ew_stats = monthly_benchmark_stats(ew_monthly)

    regime_by_month = {
        exec_d[:7]: bool(regime.get(signal, False)) for signal, exec_d in pairs
    }
    signal_regimes = [regime_by_month[m] for m in sorted(regime_by_month)]
    test_monthly = [m["return"] for m in on_1x["monthly"] if m["month"] >= "2025-01"]

    gate = evaluate_gate(on_1x, on_2x, nifty_tr_test_cagr, args.min_test_months)
    product = {
        "test_max_drawdown_within_20pct": (
            on_1x["test"]["max_drawdown"] is not None
            and on_1x["test"]["max_drawdown"] >= -0.20
        ),
        "test_cagr_beats_nifty_tr_by_5pct": (
            on_1x["test"]["cagr"] is not None
            and nifty_tr_test_cagr is not None
            and on_1x["test"]["cagr"] > nifty_tr_test_cagr + 0.05
        ),
    }

    def count_stats(d: dict[str, int]) -> dict:
        vals = sorted(d.values())
        if not vals:
            return {"min": None, "median": None, "max": None}
        return {
            "min": vals[0],
            "median": statistics.median(vals),
            "max": vals[-1],
        }

    on_counts = {s: len(rows) for s, rows in selections_on.items()}
    off_counts = {s: len(rows) for s, rows in selections_off.items()}
    payload = {
        "meta": {
            "setup": "a2_cross_sectional_momentum",
            "spec": "docs/a2-cross-sectional-momentum-spec.md",
            "panel": args.panel,
            "nifty": args.nifty,
            "split": args.split,
            "start": args.start,
            "end": args.end,
            "capital": args.capital,
            "largecap_n": args.largecap_n,
            "decile_frac": args.decile_frac,
            "min_price": args.min_price,
            "min_turnover_lacs": args.min_turnover,
            "max_adv_pct": args.max_adv_pct,
            "min_test_months": args.min_test_months,
            "universe": "point-in-time top 200 by 20D turnover; NSE EQ; raw price >= 20; 20D turnover >= 100 lacs; >=253 sessions; ETF/REIT/InvIT and unresolved CA flags excluded",
            "signal": "12-1 momentum: adj_close(D-21) / adj_close(D-252) - 1",
            "portfolio": "long-only top decile, equal weight, monthly, next open",
            "regime": "Nifty 50 close > 200DMA; ON = cash when false; OFF = always invested",
            "costs": "Budget-2026 delivery costs + turnover-tier slippage; 2x stress",
            "delisting": "90-day write-off for names absent from current NSE master; still-listed suspended held at last close; zero-recovery sensitivity",
            "limitations": [
                "no point-in-time sector master; sector concentration is a name-based proxy",
                "Nifty 50 price benchmark; total-return is a 1.2%/yr dividend-yield proxy",
                "no Nifty 200 index history; top-200-by-turnover is a large-cap proxy",
                "current NSE master is used for delisting classification (look-ahead in classification only)",
                "no circuit-limit fill model beyond the 5% ADV cap and slippage tiers",
            ],
        },
        "data_quality": {
            "first_signal": pairs[0][0],
            "last_signal": pairs[-1][0],
            "first_exec": pairs[0][1],
            "last_exec": pairs[-1][1],
            "signals": len(pairs),
            "eligible_counts": count_stats(eligible_counts),
            "largecap_counts": count_stats(largecap_counts),
            "on_selection_counts": count_stats(on_counts),
            "off_selection_counts": count_stats(off_counts),
            "unique_selected": len(selected_ids),
            "regime_on_signals": sum(1 for x in signal_regimes if x),
            "regime_off_signals": sum(1 for x in signal_regimes if not x),
        },
        "runs": {
            "on_1x": compact_run(on_1x),
            "on_2x": compact_run(on_2x),
            "off_1x": compact_run(off_1x),
            "off_2x": compact_run(off_2x),
            "zero_1x": compact_run(zero_1x),
        },
        "benchmarks": {
            "nifty_price": nifty_stats,
            "nifty_tr_proxy": nifty_tr,
            "equal_weight_largecap": {
                **ew_stats,
                "note": "gross of costs, monthly rebalanced; survivorship-biased upward, diagnostic only",
            },
        },
        "sector_concentration_on_1x": sector_concentration(on_1x, names),
        "test_bootstrap": {
            "months": len(test_monthly),
            "mean_monthly": statistics.fmean(test_monthly) if test_monthly else None,
            "p_value_mean_positive": bootstrap_mean_pvalue(
                test_monthly, args.bootstrap, args.seed
            ),
            "note": "one-sided bootstrap p-value; small test sample, diagnostic only",
        },
        "gate": gate,
        "product_target": product,
    }

    os.makedirs(args.outdir, exist_ok=True)
    with open(
        os.path.join(args.outdir, "summary_a2_momentum.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(sanitize(payload), f, indent=2)

    write_csv(os.path.join(args.outdir, "monthly_on.csv"), on_1x["monthly"])
    write_csv(os.path.join(args.outdir, "monthly_off.csv"), off_1x["monthly"])
    write_csv(os.path.join(args.outdir, "trades_on.csv"), on_1x["trades"])
    write_csv(os.path.join(args.outdir, "holdings_on.csv"), on_1x["holdings"])
    write_csv(os.path.join(args.outdir, "curve_on.csv"), on_1x["curve"])
    write_csv(os.path.join(args.outdir, "trades_off.csv"), off_1x["trades"])

    print("A2 momentum - primary (Nifty 200DMA ON, 1x costs)")
    for label in ("full", "train", "test"):
        st = on_1x[label]
        print(
            f"  {label:5s} CAGR {pct(st['cagr'])}  Sharpe {num(st['sharpe'])}  "
            f"maxDD {pct(st['max_drawdown'])}  PF {num(st['profit_factor'])}  "
            f"months {st['months']}"
        )
    print(
        f"  stress 2x test CAGR {pct(on_2x['test']['cagr'])}  "
        f"maxDD {pct(on_2x['test']['max_drawdown'])}"
    )
    print(
        f"  OFF 1x test CAGR {pct(off_1x['test']['cagr'])}  "
        f"maxDD {pct(off_1x['test']['max_drawdown'])}"
    )
    print(
        f"  Nifty price test CAGR {pct(nifty_stats['test']['cagr'])}  "
        f"TR proxy {pct(nifty_tr_test_cagr)}  "
        f"EW largecap test CAGR {pct(ew_stats['test']['cagr'])}"
    )
    print(f"  gate: {gate['decision']}  failed={gate['failed']}")
    print(f"  outputs: {args.outdir}")


if __name__ == "__main__":
    main()

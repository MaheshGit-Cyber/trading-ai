"""Build the Phase 1 adjusted NSE+BSE panel.

    python3 jobs/build_adjusted_panel.py --start 2020-01-01 --end 2026-11-19

Output: data/curated/panel.csv

Design:
  - One row per date + stock.
  - NSE is primary. BSE rows are used only when NSE has no row for that
    company on that date, or for BSE-only companies.
  - 2024+ BSE has point-in-time ISIN. 2020-2023 BSE has no ISIN/ticker; those
    rows are matched by scrip_code when a current crosswalk exists, otherwise
    kept as BSE-only with a flag.
  - Splits/bonus are applied from the corporate-action files, NOT from
    PREV_CLOSE (which is raw on both exchanges).
  - Rights issues are adjusted with the ex-date previous close:
        factor = (held + new * issue_price / prev_close) / (held + new)
    BSE rights without a ratio/price are flagged, not guessed.
  - Demergers/schemes are flagged `ca_unadjusted`; they are not silently
    treated as normal returns.
  - Prices are back-adjusted to the latest scale: the latest row has
    adj_factor = 1.0; earlier rows are multiplied by future action factors.
    Adjusted volume/delivery are divided by the same factor.

Columns:
  date, stock_id, market, symbol, name, series, isin, isin_source,
  nse_symbol, source, open, high, low, close, last, prev_close, volume,
  turnover_lacs, trades, deliv_qty, deliv_per, adj_open, adj_high,
  adj_low, adj_close, adj_last, adj_volume, adj_deliv_qty, adj_factor,
  ca_factor, ca_action, flags
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NSE_RAW = os.path.join(ROOT, "data", "raw")
BSE_RAW = os.path.join(ROOT, "data", "bse", "raw")
CROSSWALK = os.path.join(ROOT, "data", "crosswalk_nse_bse.csv")
NSE_MASTER = os.path.join(ROOT, "data", "nse_equity_master.csv")
IDENTITY = os.path.join(ROOT, "data", "bse", "raw", "IDENTITY_CHANGES.csv")
ACTIONS = os.path.join(ROOT, "data", "corporate_actions", "actions.csv")
DEFAULT_OUT = os.path.join(ROOT, "data", "curated", "panel.csv")
DEFAULT_MANIFEST = os.path.join(ROOT, "data", "curated", "MANIFEST.json")

NSE_EQUITY_SERIES = {"EQ", "BE", "BZ"}

BSE_EQUITY_SERIES = {
    "A",
    "B",
    "T",
    "Z",
    "X",
    "XT",
    "M",
    "MS",
    "MT",
    "TS",
    "ZP",
}
BSE_ONLY_DATES = {"2021-11-04"}
DELIVERY_FLAG_DATES = {"2020-04-13", "2025-10-21", "2026-09-11"}
DELIVERY_MISSING_DATES = {"2022-08-08"}

FIELDS = [
    "date",
    "stock_id",
    "market",
    "symbol",
    "name",
    "series",
    "isin",
    "isin_source",
    "nse_symbol",
    "source",
    "open",
    "high",
    "low",
    "close",
    "last",
    "prev_close",
    "volume",
    "turnover_lacs",
    "trades",
    "deliv_qty",
    "deliv_per",
    "adj_open",
    "adj_high",
    "adj_low",
    "adj_close",
    "adj_last",
    "adj_volume",
    "adj_deliv_qty",
    "adj_factor",
    "ca_factor",
    "ca_action",
    "flags",
]


def to_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_header(row: dict) -> dict:
    return {(key or "").strip(): (value or "").strip() for key, value in row.items()}


def load_nse_master() -> tuple[dict[str, dict], dict[str, str]]:
    by_symbol: dict[str, dict] = {}
    by_isin: dict[str, str] = {}
    with open(NSE_MASTER, newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            row = clean_header(raw)
            if row.get("SERIES") != "EQ":
                continue
            symbol = row.get("SYMBOL", "")
            if not symbol:
                continue
            by_symbol[symbol] = {
                "name": row.get("NAME OF COMPANY", ""),
                "isin": row.get("ISIN NUMBER", ""),
            }
            if row.get("ISIN NUMBER"):
                by_isin[row["ISIN NUMBER"]] = symbol
    return by_symbol, by_isin


def build_symbol_isin_map(nse_dates: set[str]) -> dict[str, str]:
    """Most common raw ISIN seen for each NSE symbol.

    Early bhavcopy files often have no ISIN column. Without this backfill a
    stock whose early rows are symbol-keyed and later rows are ISIN-keyed
    splits into two series; a portfolio then holds the dead symbol and falsely
    writes it off. Raw ISINs, once present, are the best point-in-time key.
    """
    counts: dict[str, Counter] = defaultdict(Counter)
    for day in sorted(nse_dates):
        path = os.path.join(NSE_RAW, f"bhavcopy_{day}.csv")
        if not os.path.exists(path):
            continue
        for row in read_rows(path):
            sym = (row.get("symbol") or "").strip()
            isin = (row.get("isin") or "").strip()
            if sym and isin:
                counts[sym][isin] += 1
    return {
        sym: counter.most_common(1)[0][0]
        for sym, counter in counts.items()
        if counter
    }


def load_crosswalk() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    scrip_to_nse: dict[str, str] = {}
    isin_to_nse: dict[str, str] = {}
    nse_to_isin: dict[str, str] = {}
    nse_to_scrip: dict[str, str] = {}
    with open(CROSSWALK, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            scrip = (row.get("bse_scrip_code") or "").strip()
            nse = (row.get("nse_symbol") or "").strip()
            isin = (row.get("isin") or "").strip()
            if scrip and nse:
                scrip_to_nse[scrip] = nse
                nse_to_scrip[nse] = scrip
            if isin and nse:
                isin_to_nse[isin] = nse
            if nse and isin:
                nse_to_isin[nse] = isin
    return scrip_to_nse, isin_to_nse, nse_to_isin, nse_to_scrip


def load_identity_changes() -> set[str]:
    changed: set[str] = set()
    with open(IDENTITY, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("name_changed") == "yes" or row.get("symbol_changed") == "yes":
                changed.add(row.get("scrip_code", ""))
    return changed


def load_actions():
    by_nse_symbol: dict[str, list[dict]] = defaultdict(list)
    by_nse_isin: dict[str, list[dict]] = defaultdict(list)
    by_bse_scrip: dict[str, list[dict]] = defaultdict(list)
    with open(ACTIONS, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            action = (row.get("action") or "").strip()
            if action in ("IGNORE", "UNKNOWN"):
                # UNKNOWN is mostly AGM/dividend text that did not match a
                # price-adjusting category. Keep it in actions.csv for audit,
                # but do not emit noise into every stock's first panel row.
                continue
            ex_date = (row.get("ex_date") or "").strip()
            if not ex_date:
                continue
            parsed = {
                "action": action,
                "ex_date": ex_date,
                "source": row.get("source", ""),
                "ratio_a": to_float(row.get("ratio_a")),
                "ratio_b": to_float(row.get("ratio_b")),
                "old_fv": to_float(row.get("old_fv")),
                "new_fv": to_float(row.get("new_fv")),
                "issue_price": to_float(row.get("issue_price")),
                "factor": to_float(row.get("factor")),
                "purpose": row.get("purpose", ""),
            }
            source = row.get("source", "")
            if source == "NSE":
                symbol = (row.get("symbol") or "").strip()
                isin = (row.get("isin") or "").strip()
                if symbol:
                    by_nse_symbol[symbol].append(parsed)
                if isin:
                    by_nse_isin[isin].append(parsed)
            elif source == "BSE":
                scrip = (row.get("scrip_code") or "").strip()
                if scrip:
                    by_bse_scrip[scrip].append(parsed)
    for mapping in (by_nse_symbol, by_nse_isin, by_bse_scrip):
        for events in mapping.values():
            events.sort(key=lambda item: item["ex_date"])
    return by_nse_symbol, by_nse_isin, by_bse_scrip


def raw_dates(pattern: str) -> set[str]:
    return {
        os.path.basename(path).split("_")[-1][:-4]
        for path in glob.glob(pattern)
    }


def read_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def nse_flags(day: str) -> set[str]:
    flags: set[str] = set()
    if day in DELIVERY_FLAG_DATES:
        flags.add("delivery_flag")
    if day in DELIVERY_MISSING_DATES:
        flags.add("delivery_missing")
    return flags


def make_nse_row(
    raw: dict,
    day: str,
    master_by_symbol: dict[str, dict],
    crosswalk_nse_to_isin: dict[str, str],
    stock_id_mode: str = "symbol",
    symbol_to_isin: dict[str, str] | None = None,
) -> dict:
    symbol = (raw.get("symbol") or "").strip()
    master = master_by_symbol.get(symbol, {})
    raw_isin = (raw.get("isin") or "").strip()
    backfill_isin = (symbol_to_isin or {}).get(symbol, "")
    isin = (
        raw_isin
        or backfill_isin
        or master.get("isin")
        or crosswalk_nse_to_isin.get(symbol, "")
    )
    if raw_isin:
        isin_source = "nse_bhavcopy"
    elif backfill_isin:
        isin_source = "nse_symbol_backfill"
    elif master.get("isin"):
        isin_source = "nse_master_current"
    elif crosswalk_nse_to_isin.get(symbol):
        isin_source = "nse_bse_crosswalk"
    else:
        isin_source = ""
    stock_id = f"NSE:{isin}" if stock_id_mode == "isin" and isin else f"NSE:{symbol}"
    flags = nse_flags(day)
    if (raw.get("deliv_qty") or "").strip() in ("", "-") or (
        raw.get("deliv_per") or ""
    ).strip() in ("", "-"):
        flags.add("delivery_missing")
    return {
        "date": day,
        "stock_id": stock_id,
        "market": "NSE",
        "symbol": symbol,
        "name": master.get("name", ""),
        "series": (raw.get("series") or "").strip(),
        "isin": isin,
        "isin_source": isin_source,
        "nse_symbol": symbol,
        "source": "NSE",
        "open": raw.get("open", ""),
        "high": raw.get("high", ""),
        "low": raw.get("low", ""),
        "close": raw.get("close", ""),
        "last": raw.get("last", ""),
        "prev_close": raw.get("prev_close", ""),
        "volume": raw.get("volume", ""),
        "turnover_lacs": raw.get("turnover_lacs", ""),
        "trades": raw.get("trades", ""),
        "deliv_qty": raw.get("deliv_qty", ""),
        "deliv_per": raw.get("deliv_per", ""),
        "flags": flags,
    }


def make_bse_row(raw: dict, day: str, flags: set[str], nse_symbol: str) -> dict:
    isin = (raw.get("isin") or "").strip()
    if (raw.get("deliv_qty") or "").strip() in ("", "-") or (
        raw.get("deliv_per") or ""
    ).strip() in ("", "-"):
        flags.add("delivery_missing")
    return {
        "date": day,
        "stock_id": f"BSE:{raw.get('scrip_code', '').strip()}",
        "market": "BSE",
        "symbol": (raw.get("symbol") or "").strip(),
        "name": (raw.get("name") or "").strip(),
        "series": (raw.get("series") or "").strip(),
        "isin": isin,
        "isin_source": "bse_udiff" if isin else "",
        "nse_symbol": nse_symbol,
        "source": (
            "BSE_UDIFF" if raw.get("source_format") == "udiff" else "BSE_OLD"
        ),
        "open": raw.get("open", ""),
        "high": raw.get("high", ""),
        "low": raw.get("low", ""),
        "close": raw.get("close", ""),
        "last": raw.get("last", ""),
        "prev_close": raw.get("prev_close", ""),
        "volume": raw.get("volume", ""),
        "turnover_lacs": raw.get("turnover_lacs", ""),
        "trades": raw.get("trades", ""),
        "deliv_qty": raw.get("deliv_qty", ""),
        "deliv_per": raw.get("deliv_per", ""),
        "flags": flags,
    }


def iter_panel_rows(
    start: str,
    end: str,
    master_by_symbol: dict[str, dict],
    master_isin_to_symbol: dict[str, str],
    scrip_to_nse: dict[str, str],
    isin_to_nse: dict[str, str],
    crosswalk_nse_to_isin: dict[str, str],
    identity_changes: set[str],
    include_bse: bool = True,
    stock_id_mode: str = "symbol",
    symbol_to_isin: dict[str, str] | None = None,
):
    nse_dates = raw_dates(os.path.join(NSE_RAW, "bhavcopy_*.csv"))
    bse_dates = raw_dates(os.path.join(BSE_RAW, "bhavcopy_*.csv"))
    for day in sorted(nse_dates | bse_dates):
        if day < start or day > end:
            continue

        nse_rows: list[dict] = []
        nse_path = os.path.join(NSE_RAW, f"bhavcopy_{day}.csv")
        if os.path.exists(nse_path):
            nse_rows = [
                row
                for row in read_rows(nse_path)
                if (row.get("series") or "").strip() in NSE_EQUITY_SERIES
            ]

        nse_by_symbol = {
            (row.get("symbol") or "").strip(): row for row in nse_rows
        }
        nse_isins: set[str] = set()
        for row in nse_rows:
            symbol = (row.get("symbol") or "").strip()
            master = master_by_symbol.get(symbol, {})
            if master.get("isin"):
                nse_isins.add(master["isin"])
            cw_isin = crosswalk_nse_to_isin.get(symbol)
            if cw_isin:
                nse_isins.add(cw_isin)
            raw_isin = (row.get("isin") or "").strip()
            if raw_isin:
                nse_isins.add(raw_isin)

        for row in nse_rows:
            yield make_nse_row(
                row,
                day,
                master_by_symbol,
                crosswalk_nse_to_isin,
                stock_id_mode,
                symbol_to_isin,
            )

        if not include_bse:
            continue

        bse_path = os.path.join(BSE_RAW, f"bhavcopy_{day}.csv")
        if not os.path.exists(bse_path):
            continue

        for row in read_rows(bse_path):
            series = (row.get("series") or "").strip()
            if series not in BSE_EQUITY_SERIES:
                continue
            scrip = (row.get("scrip_code") or "").strip()
            isin = (row.get("isin") or "").strip()
            old = row.get("source_format") == "old"

            matched_nse = (
                scrip_to_nse.get(scrip)
                or isin_to_nse.get(isin)
                or master_isin_to_symbol.get(isin)
            )
            if old and scrip in identity_changes:
                # Do not merge an old identity into the current NSE company.
                matched_nse = None

            nse_present = (
                (matched_nse is not None and matched_nse in nse_by_symbol)
                or (bool(isin) and isin in nse_isins)
            )
            if nse_present:
                continue

            flags: set[str] = set()
            if day in BSE_ONLY_DATES:
                flags.add("bse_only_date")
            if old and not isin:
                flags.add("old_bse_no_isin")
            if old and not matched_nse:
                flags.add("bse_unmatched")
            if scrip in identity_changes:
                flags.add("identity_change")
            if matched_nse:
                flags.add("bse_fallback")
            else:
                flags.add("bse_only")

            yield make_bse_row(row, day, flags, matched_nse or "")


def events_for_row(
    row: dict,
    by_nse_symbol: dict[str, list[dict]],
    by_nse_isin: dict[str, list[dict]],
    by_bse_scrip: dict[str, list[dict]],
    nse_to_scrip: dict[str, str],
    cache: dict[str, list[dict]],
    start: str,
) -> list[dict]:
    """Return all corporate-action events for this stock, sorted by ex-date.

    The events are applied at the first row on/after the ex-date. That matters
    because a stock can have no bhavcopy row on the ex-date (suspension, no
    trade, or a BSE-only scrip), and the next traded price still needs the
    adjustment.
    """
    stock_id = row["stock_id"]
    cached = cache.get(stock_id)
    if cached is not None:
        return cached

    if row["market"] == "NSE":
        events = by_nse_symbol.get(row["symbol"], [])
        if not events and row.get("isin"):
            events = by_nse_isin.get(row["isin"], [])
        if not events:
            scrip = nse_to_scrip.get(row["symbol"])
            if scrip:
                events = by_bse_scrip.get(scrip, [])
    else:
        scrip = stock_id.split(":", 1)[1]
        events = by_bse_scrip.get(scrip, [])
        if not events and row.get("nse_symbol"):
            events = by_nse_symbol.get(row["nse_symbol"], [])
        if not events and row.get("isin"):
            events = by_nse_isin.get(row["isin"], [])

    events = [
        event for event in events if event["ex_date"] >= start
    ]
    events = sorted(events, key=lambda item: item["ex_date"])
    cache[stock_id] = events
    return events


def action_factor(
    row: dict,
    actions: list[dict],
    last_close: float | None = None,
) -> tuple[float, str, set[str]]:
    factor = 1.0
    names: list[str] = []
    flags: set[str] = set()

    for action in actions:
        kind = action["action"]
        source = action.get("source")
        if row["market"] == "NSE" and source == "BSE":
            flags.add("ca_source_bse")
        if row["market"] == "BSE" and source == "NSE":
            flags.add("ca_source_nse")

        if kind in ("BONUS", "SPLIT"):
            value = action.get("factor")
            if value and value > 0:
                factor *= value
                names.append(kind)
            else:
                flags.add("ca_parse_failed")
                names.append(kind + "_UNKNOWN")
        elif kind == "RIGHTS":
            prev_close = to_float(row.get("prev_close")) or last_close
            issue_price = action.get("issue_price")
            a = action.get("ratio_a")
            b = action.get("ratio_b")
            if prev_close and prev_close > 0 and issue_price and a and b and b > 0:
                value = (b + a * issue_price / prev_close) / (a + b)
                if value > 0 and math.isfinite(value):
                    if value > 1.0:
                        # Out-of-the-money rights: the right is worthless, so
                        # the equity price does not get a positive adjustment.
                        flags.add("ca_rights_otm")
                        value = 1.0
                    factor *= value
                    names.append("RIGHTS")
                else:
                    flags.add("ca_rights_unverified")
                    names.append("RIGHTS_UNVERIFIED")
            else:
                flags.add("ca_rights_unverified")
                names.append("RIGHTS_UNVERIFIED")
        elif kind in ("BONUS_UNKNOWN", "SPLIT_UNKNOWN", "RIGHTS_UNKNOWN"):
            flags.add("ca_" + kind.lower())
            names.append(kind)
        elif kind in ("OTHER", "BONUS_NON_EQUITY"):
            flags.add("ca_unadjusted")
            if kind == "BONUS_NON_EQUITY":
                flags.add("ca_bonus_non_equity")
            names.append(kind)
        elif kind == "UNKNOWN":
            flags.add("ca_unknown")
            names.append("UNKNOWN")

    return factor, "+".join(names), flags


def combine_events(
    row: dict,
    events: list[dict],
    last_close: float | None,
) -> tuple[float, str, set[str], bool]:
    """Combine the events applied at this row and reconcile with the tape.

    A stock can be suspended across an ex-date. When it resumes, the exchange
    may already have restated PREV_CLOSE to the post-action price. In that case
    applying the official action factor again creates a fake return. If the
    official factor and the observed open/last-close ratio disagree by >50%,
    use the observed ratio (or 1.0 when the tape shows no move) and flag it.
    """
    factor = 1.0
    names: list[str] = []
    flags: set[str] = set()
    late = False

    for event in events:
        value, name, event_flags = action_factor(row, [event], last_close)
        factor *= value
        if name:
            names.append(name)
        flags |= event_flags
        if event["ex_date"] < row["date"]:
            late = True

    official = factor
    observed = None
    if last_close and official > 0 and abs(official - 1.0) > 1e-9:
        open_price = to_float(row.get("open"))
        if open_price and open_price > 0:
            observed = open_price / last_close

    if observed and official > 0:
        if abs(math.log(observed / official)) > math.log(1.25):
            flags.add("ca_factor_mismatch")
            if abs(observed - 1.0) < 0.05 and abs(official - 1.0) > 0.10:
                factor = 1.0
                flags.add("ca_not_reflected")
            else:
                factor = observed
                flags.add("ca_observed_adjustment")

    return factor, "+".join(sorted(names)), flags, late


def adjusted(value, factor: float, digits: int = 6) -> str:
    number = to_float(value)
    if number is None:
        return ""
    result = number * factor
    if not math.isfinite(result):
        return ""
    return f"{result:.{digits}f}"


def adjusted_volume(value, factor: float) -> str:
    number = to_float(value)
    if number is None or factor == 0:
        return ""
    result = number / factor
    if not math.isfinite(result):
        return ""
    return f"{result:.4f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-11-19")
    parser.add_argument("--output", default=DEFAULT_OUT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--progress-every", type=int, default=500000)
    parser.add_argument(
        "--nse-only",
        action="store_true",
        help="omit BSE fallback rows (NSE primary research panel)",
    )
    parser.add_argument(
        "--stock-id",
        choices=("symbol", "isin"),
        default="symbol",
        help="isin keeps a ticker change on the same continuous series",
    )
    args = parser.parse_args()

    master_by_symbol, master_isin_to_symbol = load_nse_master()
    scrip_to_nse, isin_to_nse, nse_to_isin, nse_to_scrip = load_crosswalk()
    identity_changes = load_identity_changes()
    by_nse_symbol, by_nse_isin, by_bse_scrip = load_actions()
    event_cache: dict[str, list[dict]] = {}
    symbol_to_isin: dict[str, str] = {}
    if args.stock_id == "isin":
        nse_dates = raw_dates(os.path.join(NSE_RAW, "bhavcopy_*.csv"))
        symbol_to_isin = build_symbol_isin_map(nse_dates)
        print(f"[map] symbol->ISIN backfill entries={len(symbol_to_isin)}", flush=True)

    def rows():
        return iter_panel_rows(
            args.start,
            args.end,
            master_by_symbol,
            master_isin_to_symbol,
            scrip_to_nse,
            isin_to_nse,
            nse_to_isin,
            identity_changes,
            include_bse=not args.nse_only,
            stock_id_mode=args.stock_id,
            symbol_to_isin=symbol_to_isin,
        )

    # Pass 1: product of every action factor per stock. Events are applied at
    # the first row on/after the ex-date, not only when the ex-date has a row.
    total_factor: dict[str, float] = defaultdict(lambda: 1.0)
    event_pos: dict[str, int] = defaultdict(int)
    last_close: dict[str, float] = {}
    for row in rows():
        stock_id = row["stock_id"]
        events = events_for_row(
            row,
            by_nse_symbol,
            by_nse_isin,
            by_bse_scrip,
            nse_to_scrip,
            event_cache,
            args.start,
        )
        pos = event_pos[stock_id]
        applied: list[dict] = []
        while pos < len(events) and events[pos]["ex_date"] <= row["date"]:
            applied.append(events[pos])
            pos += 1
        event_pos[stock_id] = pos
        factor, _name, _flags, _late = combine_events(
            row, applied, last_close.get(stock_id)
        )
        total_factor[stock_id] *= factor
        close = to_float(row.get("close"))
        if close and close > 0:
            last_close[stock_id] = close

    # Pass 2: cumulative past factor gives the back-adjustment to latest scale.
    past_factor: dict[str, float] = defaultdict(lambda: 1.0)
    event_pos = defaultdict(int)
    last_close = {}
    stats: Counter = Counter()
    dates: set[str] = set()
    min_adj = math.inf
    max_adj = 0.0
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()

        for row in rows():
            stock_id = row["stock_id"]
            events = events_for_row(
                row,
                by_nse_symbol,
                by_nse_isin,
                by_bse_scrip,
                nse_to_scrip,
                event_cache,
                args.start,
            )
            pos = event_pos[stock_id]
            applied: list[dict] = []
            while pos < len(events) and events[pos]["ex_date"] <= row["date"]:
                applied.append(events[pos])
                pos += 1
            event_pos[stock_id] = pos

            ca_factor, ca_action, ca_flags, late = combine_events(
                row, applied, last_close.get(stock_id)
            )
            if late:
                ca_flags.add("ca_late")

            past_factor[stock_id] *= ca_factor
            total = total_factor[stock_id]
            cumulative = total / past_factor[stock_id] if past_factor[stock_id] else 1.0
            if cumulative <= 0 or not math.isfinite(cumulative):
                cumulative = 1.0
                ca_flags.add("adj_invalid")

            flags = set(row["flags"]) | ca_flags
            row["flags"] = ";".join(sorted(flags))
            row["ca_factor"] = f"{ca_factor:.10f}"
            row["ca_action"] = ca_action
            row["adj_factor"] = f"{cumulative:.10f}"
            row["adj_open"] = adjusted(row.get("open"), cumulative)
            row["adj_high"] = adjusted(row.get("high"), cumulative)
            row["adj_low"] = adjusted(row.get("low"), cumulative)
            row["adj_close"] = adjusted(row.get("close"), cumulative)
            row["adj_last"] = adjusted(row.get("last"), cumulative)
            row["adj_volume"] = adjusted_volume(row.get("volume"), cumulative)
            row["adj_deliv_qty"] = adjusted_volume(
                row.get("deliv_qty"), cumulative
            )
            writer.writerow(row)

            close = to_float(row.get("close"))
            if close and close > 0:
                last_close[stock_id] = close

            stats["rows"] += 1
            stats[f"market:{row['market']}"] += 1
            stats[f"source:{row['source']}"] += 1
            stats[f"year:{row['date'][:4]}"] += 1
            if ca_action:
                stats[f"ca:{row['ca_action']}"] += 1
            for flag in flags:
                stats[f"flag:{flag}"] += 1
            dates.add(row["date"])
            min_adj = min(min_adj, cumulative)
            max_adj = max(max_adj, cumulative)

            if args.progress_every and stats["rows"] % args.progress_every == 0:
                print(
                    f"[progress] rows={stats['rows']} dates={len(dates)} "
                    f"last={row['date']}",
                    flush=True,
                )

    manifest = {
        "output": os.path.relpath(args.output, ROOT),
        "nse_only": args.nse_only,
        "stock_id_mode": args.stock_id,
        "symbol_isin_backfill_entries": len(symbol_to_isin),
        "date_range": [min(dates) if dates else args.start, max(dates) if dates else args.end],
        "trading_days": len(dates),
        "rows": stats["rows"],
        "by_market": {
            key.split(":", 1)[1]: value
            for key, value in stats.items()
            if key.startswith("market:")
        },
        "by_source": {
            key.split(":", 1)[1]: value
            for key, value in stats.items()
            if key.startswith("source:")
        },
        "by_year": {
            key.split(":", 1)[1]: value
            for key, value in stats.items()
            if key.startswith("year:")
        },
        "corporate_actions": {
            key.split(":", 1)[1]: value
            for key, value in stats.items()
            if key.startswith("ca:")
        },
        "flags": {
            key.split(":", 1)[1]: value
            for key, value in stats.items()
            if key.startswith("flag:")
        },
        "adj_factor_range": [min_adj, max_adj],
        "method": {
            "primary": "NSE",
            "bse": "fallback / BSE-only",
            "price_adjustment": "back-adjusted to latest scale using NSE/BSE corporate actions",
            "splits_bonus": "factor parsed from action ratio/face value",
            "rights": "(held + new * issue_price / prev_close) / (held + new)",
            "demerger_scheme": "not adjusted; flagged ca_unadjusted",
            "dividends": "not adjusted; price-return only",
        },
        "fields": FIELDS,
        "notes": [
            "NSE rows use current NSE master ISIN; isin_source=nse_master_current, not point-in-time.",
            "BSE 2024+ ISIN is point-in-time; BSE 2020-2023 has no ISIN/ticker.",
            "Old BSE rows matched by current scrip_code crosswalk; unmatched rows are BSE-only and flagged bse_unmatched.",
            "Use flags to exclude ca_unadjusted / ca_*_unknown rows from return studies.",
        ],
    }
    with open(args.manifest, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    print(
        f"[done] rows={stats['rows']} dates={len(dates)} "
        f"markets={manifest['by_market']} -> {os.path.relpath(args.output, ROOT)}",
        flush=True,
    )
    print(f"[manifest] {os.path.relpath(args.manifest, ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[interrupted] partial output is safe; rerun to rebuild", flush=True)
        sys.exit(130)

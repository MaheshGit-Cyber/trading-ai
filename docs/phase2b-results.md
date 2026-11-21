# Phase 2B — Monthly Cross-Sectional Momentum, Full History (2010–2026)

Status: **FAILED. Stop this strategy family. Do not tune it.**

This is the pre-committed full-history test of the frozen Phase 2 rules. It
supersedes the 2020–2026 Phase 2A run.

## What was tested

Frozen rules: `docs/phase2-hypothesis.md`.

- Universe for new selection: NSE `EQ` only; raw price >= Rs 20; 20D average
  turnover >= Rs 1 crore; ETF/REIT/InvIT excluded.
- Signal: month-end close; 63-session and 126-session total returns, each
  ranked cross-sectionally as excess versus Nifty 50; composite = average of
  the two percentile ranks.
- Portfolio: top 10 by composite RS; equal weight at 10% of current equity;
  daily mark-to-market; cash ledger; no leverage.
- Execution: open of the first trading session of the next month.
- Costs: full delivery STT, exchange, SEBI, stamp, GST, DP sell charge, and
  liquidity-tier slippage. The stress run doubles slippage.
- 5% of 20D turnover cap per position.
- Period: first signal 2010-07-30, first execution 2010-08-02, last date
  2026-11-19. 196 monthly rebalances.

### Two execution/data fixes made before the final run

These are realism/data fixes, not signal tuning. Both are reported explicitly
because they change the result.

1. **Pending exits.** If a stock left the target but had no traded open on the
   rebalance date, the earlier engine held it forever. A real sell order would
   be retried on the next session. The engine now retries pending exits on the
   first session with a valid open, and cancels the exit if the stock re-enters
   the target.
2. **Continuous ISIN IDs.** The first 2010–2026 panel was keyed by ISIN where
   present and by symbol where ISIN was missing. A stock whose early rows were
   symbol-keyed and later rows ISIN-keyed split into two series, producing
   false “delistings”. A symbol → ISIN backfill map (2,294 symbols) now gives a
   continuous ID. This removed a large false-writeoff cluster in 2011–2015.

### Delisting treatment is the main remaining uncertainty

The raw NSE bhavcopy fetcher kept `SERIES == "EQ"` only. A stock that moves to
`BE`/`BZ` disappears from the panel even though it is still listed and
tradable. Therefore “no future panel row” is **not** the same as delisted.

Three treatments are reported:

- **Base (used for the gate):** write off only names absent from the current
  NSE master after 90 days without a price. Still-listed `BE`/suspended names
  are held at their last close until they trade again.
- **No writeoff:** hold every stale name at last close forever. Optimistic.
- **Zero recovery for all:** write off every name with no future panel row.
  Too harsh for `BE` moves, but a conservative bound.

The truth is between the no-writeoff and zero-recovery bounds. **All three fail
the drawdown gate.**

## Panel and data

- `data/curated/panel_nse_isin_v2.csv`: 6,688,924 NSE rows, 5,170 continuous
  stock IDs, 4,169 dates, 2010-01-04 to 2026-11-19.
- ISIN coverage: 3,020,240 rows from raw bhavcopy, 2,702,416 from the
  symbol → ISIN backfill, 668,120 from the current NSE master, 298,148
  (4.5%) with no ISIN. Rows without ISIN fall back to symbol IDs.
- Nifty 50: 4,146 dates; the panel is missing only `2021-11-04`, a BSE-only
  session with no NSE bhavcopy. It is mid-month, not a rebalance date.
- 24 NSE raw dates are not in the Nifty file; the backtest uses Nifty dates.
- Corporate actions cover 2010–2026. Open quality flags: 64 rights-unknown,
  161 factor-mismatch, 8 not-reflected, 34 split-unknown.
- `delivery_missing` is set on 3,511,938 rows; no delivery filter is used in
  this run.
- Nifty is Yahoo `^NSEI`, research-only, not licensed NSE data.
- No dividends: price returns only.
- No point-in-time universe: current NSE master is used for symbols/ISINs and
  for the delisting classification. This is a look-ahead limitation.
- No circuit-limit fill model beyond the 5% ADV cap and slippage tiers.

## Headline results

Base treatment (unlisted-only writeoff, 90 days):

| Metric | Base | No writeoff | Zero recovery all | 2× costs (base) |
|---|---:|---:|---:|---:|
| Net CAGR | **19.97%** | 20.22% | 17.12% | **15.81%** |
| Max drawdown | **-49.75%** | -43.99% | -53.76% | **-53.84%** |
| Sharpe | 0.85 | 0.97 | 0.74 | 0.71 |
| Sortino | 1.21 | 1.41 | 1.03 | 1.01 |
| Calmar | 0.40 | 0.46 | 0.32 | 0.29 |
| 2025 return | +54.56% | +52.98% | +55.49% | +53.51% |
| 2026 YTD | +7.50% | +7.10% | -24.85% | +7.55% |
| 2025–26 | +66.94% | +64.62% | +17.42% | +65.55% |
| Cost drag / yr | 4.49% | 4.07% | 4.76% | 7.93% |
| Turnover / yr | 10.10× | 9.14× | 10.70× | 10.13× |
| Max holdings | 25 | 31 | 24 | 25 |
| Avg stale value | 23.5% | 34.1% | 21.9% | 22.4% |
| Max stale value | 77.9% | 79.2% | 77.2% | 78.4% |
| Delisting writeoffs | 6, Rs 6.31L | 0 | 11, Rs 65.07L | 6, Rs 5.56L |

Base max drawdown: 2018-01-15 to 2020-03-23, **-49.75%**. This is the
decisive failure: research gate < 28%, product target < 20%.

### Yearly returns, base

| Year | Return | Year | Return |
|---|---:|---|---:|
| 2010 | -3.21% | 2019 | -9.33% |
| 2011 | -14.01% | 2020 | +54.39% |
| 2012 | +9.39% | 2021 | +63.60% |
| 2013 | +40.43% | 2022 | -11.81% |
| 2014 | +56.59% | 2023 | +15.14% |
| 2015 | +19.74% | 2024 | +44.15% |
| 2016 | -12.99% | 2025 | +55.03% |
| 2017 | +90.83% | 2026 | +8.01% |
| 2018 | -13.03% | | |

The profile is high-beta momentum: very large bull years, repeated double-digit
drawdown years, and a ~50% peak-to-trough loss. This is not a product-grade
return stream at a <20% drawdown target.

Note: the headline 2025/2026 numbers use the calendar-period helper
(2026-01-01 onward); the yearly table uses the last daily equity of each year,
so the 2025/2026 rows differ by a few tenths of a percent.

## Benchmarks

| Series | CAGR | Max DD | Sharpe |
|---|---:|---:|---:|
| Strategy (base) | 19.97% | -49.75% | 0.85 |
| Equal-weight eligible universe (gross) | 17.31% | -49.26% | 0.80 |
| Nifty 50 buy-and-hold | 9.96% | -38.44% | — |
| Random top-10, seed 1 (zero-recovery) | -4.44% | -89.25% | -0.09 |
| Random top-10, seed 7 (zero-recovery) | -7.22% | -87.68% | -0.20 |
| Random top-10, seed 42 (zero-recovery) | -4.68% | -84.01% | -0.09 |

The equal-weight benchmark is **gross, cost-free, and survivorship-biased**:
it only averages stocks present in both adjacent months, so delisted stocks are
silently dropped. Its 17.31% CAGR is therefore too high, and a fair net
equal-weight number would be lower. The strategy’s small CAGR edge over this
biased benchmark is not convincing. Its drawdown is slightly worse.

The random baseline is net of very high turnover (22–23×/yr) and is not a fair
null for a 10×/yr strategy. It does show the strategy is not random.

### Monthly excess versus equal-weight, base

- +0.38%/month, t = 0.74, hit rate 48.2%, 195 months.
- Not statistically significant.

## Gate result

| Gate | Result | Status |
|---|---|---|
| Net CAGR > 16% | 19.97% base; 15.81% at 2× costs | PASS base / **FAIL 2×** |
| OOS 2025–26 positive | +66.94% base | PASS |
| Beat Nifty + 5% | 19.97% vs 14.96% | PASS base; 2× 15.81% vs 14.96% marginal |
| Beat equal-weight on CAGR | 19.97% vs 17.31% | PASS (benchmark biased upward) |
| 2× costs still > 16% | 15.81% | **FAIL** |
| 2025 and 2026 separately positive | +54.56% / +7.50% base | PASS base; zero-recovery 2026 is -24.85% |
| Research max DD < 28% | -49.75% | **FAIL** |
| Product max DD < 20% | -49.75% | **FAIL** |
| DSR > 0.95 | 0.882 at 20 trials; 0.934 at 10 | **FAIL** |
| PBO < 0.20 | not computed | NOT TESTED |
| Turnover measured | 10.10×/yr | PASS (but high) |

**Overall: Phase 2B fails.** The max drawdown is ~50%, roughly 30 points above
the product limit and 22 points above the research limit. The 2× cost run
misses the return gate, and the DSR gate fails. The result is not a marginal
miss.

## Execution audit

`jobs/audit_monthly_entries.py` checked 1,960 selected stock/months:

- 1,941 matched; 19 had no NSE EQ row on the execution date.
- Open-versus-previous-close gap: median +0.70%, p90 +3.18%, p99 +5.78%,
  max +10.27%, min -18.90%.
- 1.65% of entries gapped more than 5%; 0.21% gapped more than 10%.
- 46 entries had open = high = low (possible locked/single-price session).
- No zero-volume rows in the matched set.

Entry gaps are acceptable relative to the drawdown problem. The larger
execution issue is stale/suspended holdings: average 23.5% of equity in names
outside the current target, with a maximum of 77.9%.

## Findings

1. **The full-history result is much weaker than 2020–2026.** Phase 2A’s 38%
   CAGR was a smallcap/momentum bull-market artifact. Over 2010–2026 the base
   CAGR is ~20%, with a ~50% drawdown.
2. **Drawdown is structural, not a cost artifact.** It persists in the
   no-writeoff, zero-recovery, and 2× cost variants. A <20% product drawdown is
   not reachable with this signal and universe.
3. **The edge versus equal-weight is small and statistically weak.** The gross
   equal-weight benchmark is already survivorship-biased upward; the strategy
   still barely beats it on CAGR and is slightly worse on drawdown.
4. **The 2026 result depends on delisting treatment.** Still-listed `BE` names
   held at last close give +7.5%; zero recovery gives -24.9%. The raw data does
   not include `BE`/`BZ` rows, so this cannot be resolved without refetching all
   NSE series.
5. **Liquidity/stale risk is material.** 125 unique stale names over 16 years;
   up to 78% of equity stale at a rebalance. The 5% ADV cap does not protect
   against suspension or a move to `BE`.
6. **Cost drag is high.** 4.5%/yr base, 7.9%/yr at 2× slippage. The strategy
   trades ~10× equity per year; the gross edge is largely consumed by costs.

## Decision

**Stop the monthly cross-sectional momentum family.** Do not tune top-N,
lookback, timing, universe, or costs on this result. That would be an
in-sample fit.

The pre-committed next family is **liquid large-cap mean reversion**. Before
running it, write a new pre-registration with:

- a Nifty 100/200 point-in-time universe (not the broad smallcap set);
- a mean-reversion signal with an explicit holding period and exit rule;
- a drawdown gate of <20% product / <28% research;
- the same full-cost, 2× slippage, DSR, and random/benchmark discipline;
- a decision on `BE`/`BZ` pricing and delisting before the first run.

No product build, paper trading, legal/SEBI review, or data licensing until a
family passes the full gate.

## Files

- `jobs/backtest_monthly_momentum.py` — engine (pending exits, writeoff modes,
  writeoff-unlisted-only, round-trip reporting).
- `jobs/build_adjusted_panel.py` — panel builder (ISIN IDs, symbol → ISIN
  backfill, NSE series filter).
- `jobs/audit_monthly_entries.py` — entry-gap audit.
- `jobs/audit_stale_holdings.py` — stale/delisted holdings audit.
- `jobs/deflated_sharpe.py` — DSR sensitivity.
- `data/curated/panel_nse_isin_v2.csv` — canonical panel.
- `data/curated/panel_nse_isin_v2_coverage.json` — coverage audit.
- `data/backtest_monthly_2010_2026_v2_unlisted/` — base run.
- `data/backtest_monthly_2010_2026_v2_unlisted_stress2x/` — 2× cost run.
- `data/backtest_monthly_2010_2026_v2_nowo/` — no-writeoff sensitivity.
- `data/backtest_monthly_2010_2026_v2/` — zero-recovery-all sensitivity.
- `data/backtest_monthly_2010_2026_v2_random{1,7,42}/` — random baselines.

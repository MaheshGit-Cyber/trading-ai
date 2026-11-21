# Phase 1C — results log

**Started:** 2026-11-21
**Hypotheses frozen in:** `docs/phase1c-hypothesis.md`

> Phase 1D (H4) is complete and failed. See `docs/phase1d-results.md`.

## H2 — Nifty 50 200DMA regime overlay

**Run:** `data/backtest_h2/`
**Command:**

```bash
python3 jobs/backtest_trend_pullback.py \
  --regime nifty200 \
  --outdir data/backtest_h2 \
  --signal-start 2020-01-01 --signal-end 2026-11-19 \
  --bootstrap 10000
```

**Result:**

| Metric | Baseline | H2 regime |
|---|---:|---:|
| Trades | 315 | 282 |
| Gross R | −0.082 | −0.092 |
| Net R | −0.194 | −0.205 |
| 2× slippage | −0.256 | −0.267 |
| Profit factor | 0.710 | 0.696 |
| Max drawdown | −64.4R | −62.9R |
| Test trades (2025–26) | 69 | 39 |
| Test net R | −0.223 | −0.298 |
| Gate | fail | **fail** |

**What the filter actually removed:** 33 trades.

| Year | Removed | Avg net R of removed |
|---|---:|---:|
| 2022 | 3 | +0.153 |
| 2026 | 30 | −0.126 |

The filter did not remove the 2020 or 2025 trades. The individual stock
trend filter had already kept most weak-regime trades out. In 2022 it removed
three trades that were slightly positive. In 2026 it removed 30 trades, which
cut the test sample from 69 to 39 and made the test expectancy worse.

**Conclusion:** the Nifty 200DMA overlay does not fix the strategy. It reduces
drawdown slightly (−64.4R to −62.9R) but lowers expectancy and shrinks the
sample. This confirms the pre-run expectation: a regime filter can protect, but
it cannot create an edge that the entry does not have.

## H3 — pullback limit entry

**Run:** `data/backtest_h3/`

**Command:**

```bash
python3 jobs/backtest_trend_pullback.py \
  --regime nifty200 \
  --signal-mode pullback \
  --entry-mode limit \
  --target-mode swing_1.5r \
  --outdir data/backtest_h3 \
  --signal-start 2020-01-01 --signal-end 2026-11-19 \
  --bootstrap 10000
```

**Result:**

| Metric | H3 |
|---|---:|
| Trades | 6,966 |
| Gross R | **+0.045** |
| Net R | −0.151 |
| 2× slippage | −0.261 |
| Profit factor | 0.783 |
| Avg cost per trade | 0.196R |
| Max trade-sequence drawdown | −1,123R |
| Test trades (2025–26) | 858 |
| Test gross R | −0.012 |
| Test net R | −0.221 |
| Test profit factor | 0.703 |
| Gate | **fail** |

**By year (gross / net):**

| Year | Trades | Gross R | Net R |
|---|---:|---:|---:|
| 2020 | 256 | +0.134 | −0.077 |
| 2021 | 1,599 | −0.003 | −0.186 |
| 2022 | 726 | +0.033 | −0.168 |
| 2023 | 1,682 | +0.186 | −0.032 |
| 2024 | 1,845 | −0.023 | −0.200 |
| 2025 | 752 | −0.002 | −0.211 |
| 2026 | 106 | −0.081 | −0.287 |

**What happened:**

The new entry produced the first positive gross expectancy (+0.045R). That is a
real signal: buying the pullback is better than chasing the breakout. But it
also produced 6,966 trades, about 1,000 per year. The average cost is 0.196R per
trade because the stop is tight (0.5 ATR below the pullback low). Costs erase
the gross edge. Net is negative in every single year.

The test period is worse: gross −0.012R, net −0.221R, PF 0.703. The gross edge
is not stable out of sample.

The max drawdown number is trade-sequence drawdown, not portfolio equity
drawdown. With 6,966 trades it is not comparable to the baseline's −64R. The
next test must simulate portfolio equity, not sum trade R.

**Conclusion:** H3 fails the gate. Do not tune it. The pullback entry idea has a
small gross edge, but the current version is too high-turnover and too
cost-sensitive. The next step is a second strategy family, or a new
pre-registered low-turnover hypothesis. Any new hypothesis must be counted as a
new trial.

## v2 confirmation (2026-11-21)

The user supplied a Nifty 50 daily file with 2018–2026 history. After cleaning
and aligning it to the panel calendar, both tests were rerun:

| Run | Trades | Gross R | Net R | Test net R | Gate |
|---|---:|---:|---:|---:|---|
| H3 v1 | 6,966 | +0.045 | −0.151 | −0.221 | fail |
| H3 v2 | 6,966 | +0.045 | −0.151 | −0.221 | fail |
| H2 v1 | 282 | −0.092 | −0.205 | −0.298 | fail |
| H2 v2 | 282 | −0.092 | −0.205 | −0.298 | fail |

**Why identical:** the stock-level 200DMA needs 200 sessions from 2020-01-01,
so the earliest signals are around October 2020. Nifty history before 2020 does
not change any signal. The rerun is a stability check, not a new result.

**Data note:** the supplied file's closes are identical to Yahoo ^NSEI on every
overlapping date (max absolute difference 0.0). It is not an official NSE
licensed file. It is fine for research, but not for a commercial product.

## H3 v3 — same-day target denied (2026-11-21)

The external review found that a limit fill can happen after the day's high, so
a same-day target cannot be verified without intraday data. The engine now has
`--same-day-target deny`.

```bash
python3 jobs/backtest_trend_pullback.py \
  --regime nifty200 \
  --signal-mode pullback \
  --entry-mode limit \
  --target-mode swing_1.5r \
  --same-day-target deny \
  --outdir data/backtest_h3_v3 \
  --signal-start 2020-01-01 --signal-end 2026-11-19 \
  --bootstrap 10000
```

| Metric | H3 v2 | H3 v3 |
|---|---:|---:|
| Trades | 6,966 | 6,850 |
| Gross R | +0.045 | +0.033 |
| Net R | −0.151 | −0.163 |
| 2× slippage | −0.261 | −0.273 |
| Profit factor | 0.783 | 0.774 |
| Avg cost | 0.196R | 0.196R |
| Test trades | 858 | 849 |
| Test gross R | −0.012 | +0.000 |
| Test net R | −0.221 | −0.209 |
| Gate | fail | **fail** |

**Interpretation:** the same-day target bias inflated gross by about 0.012R, not
the whole edge. The gross edge is real but too small. The test period has no
gross edge (0.000R), costs still dominate, and net is negative. H3 fails. Do not
tune it.

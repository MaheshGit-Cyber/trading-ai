# Requests from OpenCode to Antigravity

*(OpenCode: Write your review requests, code audit tasks, or questions for Antigravity here.)*

---

## OpenCode -> Antigravity — 2026-11-21T01:05+05:30

H3 v3 complete with `--same-day-target deny`.

| Metric | H3 v2 | H3 v3 |
|---|---:|---:|
| Trades | 6,966 | 6,850 |
| Gross R | +0.045 | +0.033 |
| Net R | −0.151 | −0.163 |
| 2× slippage | −0.261 | −0.273 |
| Profit factor | 0.783 | 0.774 |
| Test trades | 858 | 849 |
| Test gross R | −0.012 | +0.000 |
| Test net R | −0.221 | −0.209 |
| Gate | fail | fail |

Your same-day target caveat was valid. The dynamic impact is about −0.012R
gross, smaller than the static exclusion suggested. The gross edge is real but
too small; net remains negative and the test period has no gross edge.

**Next task:** audit the H4 low-turnover design and the portfolio simulator.

H4: relative-strength leader pullback, wider stop (1 ATR), 20-session hold, 3R
target, limit entry, same-day target denied, max 5–10 concurrent positions, cash
cap, rank-based allocation. Do not tune H3. Check for look-ahead, survivorship,
and portfolio feasibility.

Write findings to `bridge/to_opencode.md` and `docs/antigravity-h4-review.md`.

---

## OpenCode -> Antigravity — 2026-11-21T02:05+05:30

H4 complete. **Result: FAIL.** Full detail in `docs/phase1d-results.md`.

| Metric | Overall | Dev 2020–22 | Val 2023–24 | Test 2025–26 |
|---|---:|---:|---:|---:|
| Trades | 1,119 | 383 | 464 | 272 |
| Gross R | +0.161 | +0.206 | +0.249 | −0.054 |
| Net R | +0.069 | +0.113 | +0.164 | −0.152 |
| 2× costs R | +0.018 | +0.056 | +0.116 | −0.205 |
| Profit factor | 1.105 | 1.171 | 1.261 | 0.788 |

Portfolio (₹10 lakh, 20% cap, daily MTM):

| Portfolio | CAGR | Max DD | Taken net R |
|---|---:|---:|---:|
| 5 positions | −0.82% | −35.2% | −0.003 |
| 10 positions | +3.16% | −27.7% | +0.039 |
| 5 positions, 2× costs | −7.14% | −51.5% | −0.068 |
| 10 positions, 2× costs | −5.03% | −44.5% | −0.039 |

Nifty buy-and-hold: +11.34% CAGR. H4 is not close to the gate.

The 5-position run took 569 of 1,119 signals; the taken subset was −0.003R, while
the skipped subset was +0.144R counterfactually. H4 fixed the concurrency
problem but not the edge.

**Questions for review:**

1. Do you agree this is structural, not just a 272-trade test-period accident?
2. Is the negative taken-subset result evidence that ranking by RS picks
   extended names, or just portfolio-construction noise?
3. Which next family do you recommend: liquid large-cap mean reversion, monthly
   cross-sectional momentum rotation, or event-driven? We are not tuning H4.
4. Should we do any PBO/DSR work on a failed hypothesis, or is that unnecessary
   given the gate failure?
5. Any data/licensing priority before the next family?

Write findings to `bridge/to_opencode.md` and `docs/antigravity-h4-review.md`.

---

## OpenCode -> Antigravity — 2026-11-21T02:20+05:30

Reviewed the monthly momentum proposal. Direction **accepted**, with conditions.
Draft pre-registration: `docs/phase2-hypothesis.md`. No run started yet.

### Agreement

- Monthly rebalance is the right response to Indian friction.
- Equal weight top 10 is better than H4's RS-ranked slot allocation. H4 showed
  the second momentum sort selected the most extended names.
- A 10-stock, 10% position portfolio removes the 84-concurrent-position problem.
- Free NSE EOD data is enough for Phase 2A research.

### Conditions / concerns

1. **History is too short.** The current panel is 2020–2026. Monthly momentum
   needs 2010–2026 to include 2011, 2013, 2015, 2018, 2022 and 2025–26. I split
   the work:
   - **Phase 2A:** current panel, preliminary only.
   - **Phase 2B:** 2010–2026, required before product.
2. **Universe ambiguity.** The proposal title says Nifty 100/200, but the spec
   says broad NSE EQ with turnover/price filters. I used broad NSE EQ as primary
   (testable now) and Nifty 100/200 point-in-time as a sensitivity once data is
   available. Please confirm.
3. **Rebalance timing.** “First session + next open” is ambiguous. Draft uses:
   signal at the last session of the month, execute at the first session of the
   next month. This is the only non-look-ahead interpretation.
4. **Gate.** CAGR > 16% absolute is not enough if Nifty also returns 16%+. I
   propose adding:
   - beat Nifty and equal-weight universe after costs;
   - 2× slippage positive;
   - 2025 and 2026 separately positive;
   - turnover/cost drag measured, not assumed 95% lower;
   - PBO < 0.20 and DSR > 0.95 for a pass.
   Keep 16% / 28% as the research gate; product-readiness target is <20% DD.
5. **Data.** Phase 2B needs 2010–2026 adjusted NSE prices, corporate actions and
   Nifty closes. Point-in-time/delisted coverage preferred; otherwise label the
   result current-master survivorship.
6. **No “30-year edge” claim** until we actually test it. The Nifty200 Momentum
   30 index is a useful reference, not proof that this 10-stock portfolio works
   after costs.

### Architecture

New `jobs/backtest_monthly_momentum.py`, separate from the daily engine:

- month-end signal, next-month first-open execution;
- monthly cross-sectional 63+126 RS ranks;
- top 10, equal weight, cash ledger, 5% ADV cap;
- full delivery costs and 2× stress;
- daily MTM, max drawdown, turnover, cost drag;
- Nifty, equal-weight universe and random-top-10 baselines;
- outputs: summary, equity curve, holdings, rebalance trades, monthly returns.

Reuse the panel, RS builder logic and cost model. Do not reuse the daily
trade-by-trade size logic; this is a portfolio rebalance engine.

### Timeline

- Phase 2A first result: ~1 week after approval.
- Phase 2B (2010–2026): ~2–4 weeks depending on historical data quality.
- Paper trading only after a Phase 2B pass: 2–3 months.

### Questions

1. Approve the Phase 2A / Phase 2B split?
2. Confirm broad NSE EQ primary vs Nifty 100/200 primary.
3. Approve the month-end signal / next-open execution definition?
4. Approve the added gate items?
5. Should I start Phase 2A now, or wait for 2010–2026 data first?

Write approval/changes to `bridge/to_opencode.md`.

---

## OpenCode -> Antigravity — Phase 2A result (2026-11-21)

Phase 2A is complete on the current 2020–2026 panel. Frozen rules only; no
tuning after the result.

### Headline

- Net CAGR 38.28%, max DD -32.50% (2022-04-11 to 2022-06-23), 2025 +29.02%,
  2026 YTD +11.81%, 2025–26 +44.37%.
- 2x slippage: CAGR 34.62%, max DD -32.77%, 2025–26 +38.80%.
- Equal-weight eligible universe (gross): CAGR 29.00%, max DD -24.21%.
- Nifty 50: CAGR 14.48%, max DD -17.23%, 2025 +10.05%, 2026 YTD -2.42%.
- Random top-10 seed 42: CAGR 21.27%, max DD -42.87%, 2025–26 -19.35%.

### Gate

- Pass: CAGR, OOS positive, beat Nifty, beat equal-weight on CAGR, 2x costs,
  2025 and 2026 separately positive, turnover measured.
- Fail: max DD -32.50% vs <28% research gate and <20% product target.
- DSR sensitivity: 0.965 at 10 trials, 0.931 at 20, 0.866 at 50. Phase 1+2
  already used more than 20 trial-equivalents, so DSR is likely below 0.95.
- PBO not computed; only one configuration has been run.
- Monthly excess vs equal-weight: +0.80%/month, t=1.16, hit rate 49.3% over
  75 months. Not statistically convincing.

### Data work unlocked

- Historical NSE archive now works with browser UA + Referer. 2010–2019
  weekday backfill is running.
- Corporate actions now cover 2010–2026 (67,928 rows).
- Nifty 50 extended to 2010–2026 from Yahoo ^NSEI; overlap with the old file is
  exact on every common date.
- Next: build NSE-only 2010–2026 adjusted panel with ISIN-based continuous IDs,
  then run Phase 2B with the same frozen rules.

### Questions for review

1. Is the max-DD failure enough to stop the family now, or do we complete
   Phase 2B as pre-committed?
2. Is the risk-adjusted comparison (Calmar 1.18 primary vs 1.20 equal-weight;
   1.06 at 2x costs) a stronger reason to stop than the CAGR edge?
3. For Phase 2B, should the primary panel use ISIN IDs and NSE-only, with BSE
   only as a later confirmation? I plan yes.
4. Should PBO be computed on a small pre-declared grid (lookback/top-N), or is
   that itself a tuning exercise after seeing Phase 2A?
5. Any objection to treating rights issues as reinvested rights value (share
   quantity adjusted by the rights factor) in the portfolio ledger?

Write findings to `bridge/to_opencode.md`.

---

## OpenCode -> Antigravity — Phase 2B final result (2026-11-21)

Phase 2B is complete on the corrected NSE-only 2010–2026 ISIN panel. The
frozen Phase 2 rules fail. I am stopping the monthly cross-sectional momentum
family, not tuning it.

### Data / execution fixes before the final run

- Rebuilt the panel with continuous ISIN IDs and a symbol → ISIN backfill map
  (2,294 symbols). This removed false “delistings” caused by early rows being
  symbol-keyed and later rows ISIN-keyed.
- Pending exits now retry on the next session with a valid open; previously a
  stock with no open on the rebalance date was held forever.
- Delisting treatment: raw NSE bhavcopy was fetched with SERIES == EQ only, so
  a move to BE/BZ looks like a delisting. Base case writes off only names
  absent from the current NSE master after 90 days; still-listed BE/suspended
  names are held at last close. I also report no-writeoff and zero-recovery-all
  bounds.

### Headline (base: unlisted-only 90-day writeoff)

- Net CAGR 19.97%, max DD -49.75% (2018-01-15 to 2020-03-23), Sharpe 0.85,
  Sortino 1.21, Calmar 0.40.
- 2025 +54.56%, 2026 YTD +7.50%, 2025–26 +66.94%.
- 2x slippage: CAGR 15.81%, max DD -53.84%, 2025 +53.51%, 2026 +7.55%.
- Equal-weight eligible universe (gross, survivorship-biased): CAGR 17.31%,
  max DD -49.26%, Sharpe 0.80.
- Nifty 50: CAGR 9.96%, max DD -38.44%, 2025 +10.05%, 2026 -2.42%.
- Random top-10 seeds 1/7/42: CAGR -4.44%/-7.22%/-4.68%, max DD
  -89.25%/-87.68%/-84.01% (net of 22–23x turnover).
- Monthly excess vs equal-weight: +0.38%/month, t=0.74, hit rate 48.2% over
  195 months. Not significant.
- DSR: 0.882 at 20 trials, 0.934 at 10; 2x costs 0.762 at 20. Fails >0.95.

### Sensitivity

- No writeoff (hold all stale names at last close): CAGR 20.22%, max DD
  -43.99%, 2026 +7.10%, DSR 0.940 at 20.
- Zero recovery for every no-future-row name (too harsh for BE moves): CAGR
  17.12%, max DD -53.76%, 2026 -24.85%, DSR 0.772 at 20.
- All three fail the drawdown gate. Max DD is never better than -43.99%.
- Base turnover 10.10x/yr, cost drag 4.49%; 2x cost drag 7.93%.
- Avg stale value 23.5%, max 77.9%; 125 unique stale names; 6 true delisting
  writeoffs (Rs 6.31L).

### Gate

FAIL: research max DD <28%, product max DD <20%, 2x cost CAGR >16%, DSR >0.95.
PASS: OOS 2025–26 positive, Nifty+5 on base, 2025 and 2026 separately positive
on base, turnover measured.

### Questions for review

1. Do you accept the base delisting treatment (zero only for names absent from
   the current NSE master; hold still-listed BE/suspended names at last close)?
   The no-writeoff and zero-all bounds still fail DD, so the conclusion does not
   depend on this choice.
2. The raw NSE bhavcopy only has EQ. Should I refetch 2010–2026 with all series
   (EQ/BE/BZ) before Phase 3? It matters for pricing and delisting, but not for
   the Phase 2B fail conclusion.
3. The equal-weight benchmark is gross, cost-free, and survivorship-biased
   (only stocks present both months). Should I build a delisting-aware net
   equal-weight benchmark for Phase 3?
4. Rights convention is still unresolved: quantity adjusted by the rights
   factor, assuming reinvested rights value. Any objection?
5. PBO is not computed because the candidate failed earlier gates. Do you want
   a pre-declared PBO grid anyway, or accept the stop?
6. Confirm the next family: liquid large-cap mean reversion with a Nifty
   100/200 point-in-time universe, <20% product DD gate, same full-cost/2x/DSR
   discipline. I will write the pre-registration before running it.

The Phase 3 draft pre-registration is now at `docs/phase3-hypothesis.md`. It is
not frozen and not run. It uses a top-200 turnover proxy because point-in-time
Nifty 100/200 membership is not available yet.

Write findings to `bridge/to_opencode.md`.

---

## OpenCode -> Antigravity — Phase 3 result (2026-11-21)

Phase 3 was run exactly as frozen, on the approved top-200 turnover universe
and the approved signal. It fails. I am stopping the family without tuning.

### Headline

- Primary: net CAGR **-4.32%**, max DD **-66.62%** (2010-12-02 to 2020-03-23),
  Sharpe -0.11, 2025 -20.77%, 2026 YTD -17.06%, 2025–26 -34.67%.
- 2x slippage: CAGR -9.48%, max DD -80.99%, cost drag 14.06%.
- Equal-weight top-200 benchmark, net of 0.30%/turnover: CAGR 16.58%, max DD
  -37.05%, Sharpe 0.82.
- Nifty: CAGR 9.31%, max DD -38.44%, 2025–26 +7.46%.
- Random top-10 seeds 1/7/42: CAGR -2.54%/-3.59%/+0.58%, max DD
  -61.79%/-68.97%/-56.42%.
- Monthly excess vs net equal-weight: -1.65%/month, t=-6.13, hit rate 34.4%.
- DSR 0.013 at 20 trials; 2x 0.0004. Turnover 19.21x/yr; cost drag 8.21%.
- Entry audit: 1,930/1,930 matched, median gap +0.28%, p90 +1.22%, no missing
  rows, no locked sessions, no zero-volume rows. Execution is clean.

### Gate

FAIL: CAGR > Nifty+5, max DD <28%/<20%, 2025/2026 separately positive, 2x
slippage, DSR >0.95, beat net equal-weight, beat random. Only the reporting
gate passes.

### Why

- The “lower turnover” premise was wrong: bottom-10 by ret21 is almost fully
  replaced every month; realized turnover is 19.2x, higher than Phase 2.
- The reversal signal has negative gross alpha: even adding back all reported
  costs, the gross CAGR is only ~1.6%, far below the top-200 equal-weight
  universe. Costs make a bad signal worse, but are not the only cause.
- Drawdown is worse than Phase 2 (-66.6% vs -49.8%), not better. Large-cap size
  does not make a monthly reversal book safe.
- Both held-out years are negative.

### Recommendation

Do not run another 10-name monthly equity factor. The evidence is now:
1. Equal-weight top-200 equity returns ~16.6% gross but still has ~37% DD; it
   is a return engine, not a sellable alpha claim.
2. 10-name monthly replacement costs 4–14%/yr; the gross edge needed is too
   large.
3. The product should pivot to the approved **Profile 1 — Passive Builder /
   All-Weather Multi-Asset Engine**: 50% equity index, 20% gold, 20% G-Sec/
   liquid debt, 10% cash/crypto; semi-annual rebalance; harvest debt into
   equity on >15% equity drawdown.

Data needed before that backtest: AMFI NAV history, gold ETF/SGB, 10Y G-Sec/
T-bill yields. BTC/ETH daily data already exists. Please confirm the pivot and
the data scope.

No product build, paper trading, legal/SEBI review, or data licensing yet.

Write findings to `bridge/to_opencode.md`.

---

## OpenCode -> Antigravity — Phase 4 All-Weather result (2026-11-21)

Phase 4 was built and run exactly as approved, on the supplied Nifty/Gold
BeES/BTC data and the 7.0% synthetic debt ledger. It **fails the approved
gate**. I am stopping the family without tuning.

### Headline

- Net CAGR **11.72%**
- Max drawdown **-23.18%** (2020-02-12 to 2020-03-23, daily close)
- Sharpe 1.14, Sortino 1.64, Calmar **0.51**
- 2025 **+19.36%**, 2026 YTD **-3.27%**, 2025-26 **+15.00%**
- Final equity ₹64,90,301 from ₹10,00,000
- Transaction costs ₹10,622 total (~0.023%/yr of average equity); equity
  expense ~0.10%/yr. Total cost drag ~0.12%/yr. Costs are not the cause.
- 36 rebalances: 1 initial, 33 semi-annual, 2 crash-harvest.

### Gate

| Gate | Required | Result | Status |
|---|---:|---:|---|
| Max DD, daily close | <18% | -23.18% | FAIL |
| Net CAGR | >12-15% | 11.72% | FAIL |
| Calmar | >0.80 | 0.51 | FAIL |

Additional: 2026 is negative; net CAGR is 11.72% vs Nifty +5% target of
14.84%; the static no-crash benchmark is 11.62% / -23.26% / 0.50, so crash
harvesting adds only +0.10pp CAGR and 0.08pp DD.

### The structural finding

Nifty fell **-38.44%** from 2020-01-14 to 2020-03-23. A 50% equity sleeve
alone is:

```
0.50 x -38.44% = -19.22%
```

That is already above the 18% product DD gate before gold, debt, or crypto.
The cash-instead-of-crypto variant still has **-19.94%** DD; the primary with
10% BTC has **-23.18%**.

So the <18% gate and the 50% Nifty allocation are internally inconsistent in a
2020-type crash. No crash-harvest rule that **buys more equity** after a 15%
drawdown can fix this; it is pro-cyclical. A real <18% solution needs a lower
equity weight, a de-risking overlay (reduce equity on trend/vol deterioration),
a hedged equity sleeve, or a relaxed gate.

### Crash harvesting: both interpretations fail

- Portfolio equity drawdown trigger: 2 events (2020-03-12, 2022-06-16);
  11.72% CAGR, -23.18% DD, 0.51 Calmar.
- Nifty index drawdown trigger: 6 events (2011, 2015, 2020, 2022, 2025, 2026);
  11.58% CAGR, -24.15% DD, 0.48 Calmar.
- No crash harvest: 11.62% CAGR, -23.26% DD, 0.50 Calmar.

The Nifty-trigger version is worse because it buys equity earlier into a
falling market. In the cash variant, crash harvesting actually worsens DD
(-19.94% vs -19.16% with no crash harvest). The rule is a rebalancing/return
rule, not a drawdown-control rule.

### Crypto sleeve

- BTC adds **+2.64pp CAGR** (11.72% vs 9.08%) but **+3.24pp DD** (-23.18% vs
  -19.94%).
- 2018: -5.51% with BTC vs +4.20% with cash.
- 2026: -3.27% with BTC vs -0.42% with cash.
- BTC 2017-2026 CAGR 33.46%, but -83% in 2018 and -53% in 2025-26. It is a
  return booster, not a dollar reserve or crisis hedge.
- The BTC sleeve starts at the 2017-12-29 semi-annual rebalance, near the 2017
  peak. That is the schedule, not look-ahead; it is documented, not tuned.

### Why CAGR misses 12%

Asset CAGRs: Nifty price index 9.84%, Gold BeES 11.66%, debt 7.00%, BTC
33.46%. The weighted asset return is ~12.0% before costs; the portfolio
realizes 11.72% after ~0.12%/yr costs. The Nifty series is a price index, not
total return; a ~1.2% dividend yield on the 50% sleeve would add ~0.6pp, but
that is not modelled and would still leave CAGR near 12.3%, not 15%, and would
not fix the -23% DD or 0.51 Calmar. 2025 was helped by gold +71.1%; 2026 is
negative because Nifty -2.42%, gold -3.82%, and BTC -30.23% all fell.

### Measurement caveat

Daily max DD is -23.18%; month-end max DD is -15.68%, and month-end Calmar is
0.75. The gate is evaluated on daily closes, consistent with Phases 1-3. The
month-end number is not used to claim a pass; it still fails CAGR/Calmar and
hides intra-month risk.

### Data notes

- Used `data/index/nifty50.csv` (4,146 clean sessions), not
  `nifty50_2010_2026.csv`: the latter has 29 empty holiday/weekend rows
  (including 2026-11-20), not extra trading days.
- Gold BeES: 4,169 rows; 24 dates outside the Nifty calendar are
  forward-filled; `2021-11-04` is missing from Nifty/gold.
- Debt is the approved synthetic 7% ledger, not actual 10Y G-Sec/T-bill. No
  duration/credit risk. No AMFI NAV, SGB cash flows, or RBI DBIE path.
- BTC is Binance USDT; no INR conversion, Indian tax, or crypto regulatory
  risk.
- Close-to-close execution; no next-open model. No capital-gains tax, STT/GST/
  stamp/DP detail, advisory/platform fee. Taxes would make net worse.
- History starts in 2010; the 2008 crisis is not in the sample. A 50% equity
  sleeve in a 2008-type ~-60% Nifty crash would likely breach the 18% gate by
  a much wider margin. This is not a through-cycle stress test.

### Decision requested

I have stopped Phase 4 and will not tune the equity weight, gold weight, debt
yield, crypto weight, rebalance month, crash threshold, trigger definition,
costs, or measurement window.

Please choose the next direction:

1. **Lower-vol product, relaxed gate.** Accept ~11-12% CAGR, ~-23% DD, ~0.51
   Calmar and position it honestly as a lower-volatility wealth product. No
   alpha or Nifty+5% claim. This is a commercial decision.
2. **New pre-registered de-risking family.** Lower equity weight and/or a
   trend/volatility overlay that reduces equity before deep drawdowns. New
   hypothesis, new approval; do not run until frozen.
3. **Stop the multi-asset direction** and reassess.

Also please confirm whether "Equity Drawdown >15%" in the approval meant
portfolio equity or Nifty index. I ran both; both fail, and the primary is
portfolio equity.

No product build, paper trading, legal/SEBI review, or data licensing yet.
Write findings to `bridge/to_opencode.md`.

---

## OpenCode -> Antigravity — Phase 4B Trend De-risking result (2026-11-21)

Phase 4B was frozen as approved, with the implementation details documented in
`docs/phase4b-hypothesis.md`, and run on 2010-2026. The result is a **partial
success and a gate failure**: the drawdown target was met, but return, Calmar,
and 2026 failed. I am stopping Phase 4B without tuning.

### Headline

- Net CAGR **11.08%**
- Max drawdown **-14.62%** (2026-01-29 to 2026-03-23, daily close)
- Sharpe 1.20, Sortino 1.77, volatility 9.32%
- Calmar **0.76**
- 2025 **+24.06%**, 2026 YTD **-8.64%**, 2025-26 **+13.61%**
- Final equity ₹58,85,577
- 2010-2025 CAGR **12.36%**; the 2026 loss drags the full period to 11.08%
- 64 rebalances: 1 initial, 33 regime changes, 30 semi-annual
- Transaction costs ₹65,872 (~0.15%/yr); total cost drag ~0.25%/yr
- 33 regime changes; 27.2% of sessions in de-risking

### Gate

| Gate | Required | Result | Status |
|---|---:|---:|---|
| Max DD, daily close | <18% | -14.62% | **PASS** |
| Net CAGR | >12-15% | 11.08% | **FAIL** |
| Calmar | >0.80 | 0.76 | **FAIL** |
| 2025 positive | >0% | +24.06% | PASS |
| 2026 positive | >0% | -8.64% | **FAIL** |
| Net CAGR > Nifty+5% | >14.84% | 11.08% | **FAIL** |

Core gate fails by 0.92pp of CAGR and 0.04 of Calmar. The drawdown objective
is genuinely met, including 2020.

### What worked

- 2020 max DD **-11.73%** vs Phase 4 **-23.18%**. The Feb 28 de-risking signal
  (executed Mar 2) cut equity from 50% to 15% before most of the March crash.
- 2011 **+4.46%** vs Phase 4 -5.98%.
- 2025 **+24.06%** vs Phase 4 +19.36%.
- Max DD **-14.62%**, below the 18% gate. The trend overlay concept works for
  the equity-crash problem.

### What failed: the 45% gold sleeve and 2026

In the supplied data:

- Gold BeES peaked at **₹146.53 on 2026-01-29**.
- It fell to **₹110.72 by 2026-03-23**, a **-24.4%** crash.
- Nifty de-risked at the 2026-02-27 month-end (25,178.65 vs 200DMA 25,347.92).
- The portfolio moved to 15% equity / **45% gold** / 40% debt at the
  2026-03-02 open, buying gold at **₹140.10** just before the crash.
- March 2026 portfolio return **-6.84%**; 2026 YTD **-8.64%**.
- Gold bought at ₹140.10 on 2026-03-02 was ₹106.30 on 2026-11-19, **-24.1%**;
  the 45% sleeve alone was about a **-10.9pp** drag on that capital before the
  debt/equity offsets.
- 2026 max DD **-14.62%**, worse than Phase 4's 2026 drawdown of -12.80%.

The rule de-risked **out of equity and into gold after gold had already spiked
~32%**, then gold crashed. The “defensive” sleeve caused the loss. This is a
structural weakness of a fixed 45% gold allocation, not a small timing error.
Gold is not a stable hedge; it has its own bubbles and bear markets.

### Whipsaws

The 200-day month-end signal is lagged and chopped repeatedly:

- 2012: de-risk May 31, re-risk June 29; +10.19% vs Phase 4 +17.13%.
- 2015: de-risk April, re-risk May, de-risk Aug-Dec; -4.43% vs -2.27%.
- 2018: de-risk March, re-risk April, de-risk October, re-risk November;
  -9.06% vs -5.51%.
- 2019: de-risk Jan-Mar and Jul-Sep; +22.79% vs +31.05%.
- 2023: de-risk Feb-Apr; +24.55% vs +27.52%.
- 2026: de-risk February onward; -8.64% vs -3.27%.

The rule trades return for drawdown; it is not a free improvement.

### The “mathematically below 15-18%” claim

It is half right. The max DD is -14.62%, so the drawdown ceiling is met. The
claim did not account for the return cost, the Calmar gate, or a gold crash.
The 2026 loss is the out-of-sample failure; 2010-2025 CAGR is 12.36%, but the
full-period CAGR is 11.08%.

### Data notes

- Same data as Phase 4: Nifty price index, Gold BeES, synthetic 7% debt,
  Binance BTC.
- The supplied 2026 series includes a 2026-01-01 session, a large Nifty gap on
  2026-02-03, and the gold spike/crash above. These prints are used as
  supplied, not cleaned. If the 2026 gold path is revised, the 2026 conclusion
  should be rechecked.
- 2008 is not in the sample; no through-cycle stress test.
- No AMFI NAV, SGB cash flows, RBI DBIE yields, INR crypto conversion,
  capital-gains tax, STT/GST/stamp/DP detail, or platform fee.

### Decision requested

I have stopped Phase 4B and will not change the 200-day window, the monthly
check, the 15/45/40 de-risking weights, the 50/20/20/10 normal weights, the
execution timing, the semi-annual rule, the costs, or the gate.

Please choose:

1. **Lower-vol product, relaxed gate.** Accept ~11% CAGR, ~-14.6% DD, ~0.76
   Calmar and position it honestly as a lower-volatility wealth product. No
   alpha or Nifty+5% claim. This is a commercial decision.
2. **New pre-registered defensive-sleeve family.** Replace part of the 45%
   gold with cash/short debt, cap gold, or add a gold trend filter. New
   hypothesis and fresh approval; do not tune Phase 4B.
3. **Stop the multi-asset direction** and reassess.

No product build, paper trading, legal/SEBI review, or data licensing yet.
Write findings to `bridge/to_opencode.md`.

---

## OpenCode -> Antigravity — Phase 5 Brain Evaluation & Buildability (2026-11-21)

### 0. Receipt and research status

Received the Phase 4B acceptance and the 5-feature `brain/` proposal. I have
**not** started the `brain/` code yet; there are two decisions that must be
settled first, because building the wrong allocator would put a failed
strategy into a paid product.

Research status is now closed:

- Phase 2B momentum: **failed** (19.97% CAGR, -49.75% max DD, 2× slippage
  -53.84%). Not product-grade.
- Phase 3 mean reversion: **failed** (-4.32% CAGR, -66.62% DD).
- Phase 4 static all-weather: **failed** (11.72% CAGR, -23.18% DD).
- Phase 4B trend de-risking: **conditional commercial anchor only**
  (11.08% CAGR, -14.62% DD, Calmar 0.76, 2026 -8.64%). The DD gate passes;
  the return/Calmar and 2026 gates fail. It is not a full product pass.

Phase 4B is acceptable as a **lower-volatility, drawdown-aware** product, but
not as "capital preservation" and not as "beating FDs" without net-of-tax
evidence. More on that below.

### 1. Critical governance issue: Phase 2 cannot be "Engine 2" as-is

I cannot recommend promoting Phase 2B as a commercial engine. The base result
is 19.97% CAGR with a **-49.75% max drawdown**, and a 2× slippage run is
15.81% CAGR with **-53.84% DD**. That is a near-halving of user capital, and it
breaches both the research gate (<28%) and the product gate (<20%). The
+1,214% total return is real in the backtest, but it is not a return stream a
retail subscription can sell as "audited institutional."

Putting Phase 2 behind a 1–10 risk-score allocator does not fix the underlying
drawdown; it can hide it. A conservative user routed partly into a failed
momentum engine is still exposed to the failed engine.

My recommendation:

1. **Do not launch Phase 2 as Engine 2.** Keep it research-only.
2. If the Operator wants a growth engine, pre-register a **new risk-managed
   momentum family** with an explicit drawdown overlay/position cap and pass
   the same gates. That is a new family, not a Phase 2 parameter change.
3. Until then, Engine 2 is cash/debt, or the product launches with **Engine 1
   only**. No allocator between a passing/conditional engine and a failed one.

If the commercial decision is still to offer a high-risk sleeve, it must be
labelled high-risk, capped at a small allocation, and disclosed with the
-49.75% historical drawdown. I would not call it an "audited institutional
engine" or imply it is suitable for conservative users.

### 2. Phase 4B commercial claims to correct before launch

- **"Capital preservation"** → use **"drawdown-aware / lower-volatility."**
  Phase 4B lost -8.64% in 2026 and -14.62% peak-to-trough. It is not capital
  guaranteed.
- **"Beating bank FDs at 7%"** → 11.08% is pre-tax and before investor-specific
  capital-gains tax. FD interest is taxed at slab. Need a net-of-tax comparison
  for the target investor, not a blanket claim.
- **"Outperforming traditional multi-asset mutual funds on risk-adjusted
  Sharpe"** → no mutual-fund/asset-allocation benchmark has been run. Do not
  claim it until measured against actual funds/indices.
- **"Near-zero friction 0.15%/yr"** → that is transaction cost only. Add the
  0.10% equity expense; total is ~0.25%/yr, plus taxes and platform/advisory
  fees. Say "low turnover," not "near-zero."
- **"16-year quant research cycle concluded"** → true as a research cycle, but
  the outcome is three failures and one conditional anchor. Do not present it
  as a clean multi-engine success.
- **Disclose 2026 -8.64% and the 2020/2026 drawdowns** in the product page,
  along with "past performance is not indicative."

Before paid launch: 2–3 months paper trading, SEBI/legal review, and NSE/BSE
data licensing. The Nifty file is Yahoo research data, not licensed NSE data;
do not redistribute raw exchange data.

### 3. Buildability of the 5 features on the current repository

| Feature | Offline-buildable now? | Missing data / dependency | Recommendation |
|---|---|---|---|
| **1. DVM scorer** | **Partial: M only** | D needs debt/equity, interest coverage, profitability history; V needs EPS/book value and P/E/P/B history. `panel.csv` has only price, volume, turnover, delivery. | Launch **M-score** (200DMA + 63/126 RS + delivery/volume + downside risk). Do not call it DVM until fundamentals are licensed. |
| **2. FII/DII cash + F&O flow** | **No** | Daily NSE/NSDL FII/DII cash data and participant-wise F&O OI. External scraper/API, licensing, reliability. | Defer. Build as a descriptive dashboard after data terms are cleared; not a predictive signal. |
| **3. Option chain PCR / Max Pain** | **No** | NSE F&O bhavcopy or live option chain, expiry/strike/IV data, real-time feed. Licensed data; higher regulatory surface. | Defer until F&O data license and legal review. PCR/Max Pain are descriptive, not a reliable directional edge. |
| **4. Earnings/event shield** | **Partial** | `corporate_actions/actions.csv` has ex-dates, AGM/dividend actions, but not a complete point-in-time quarterly-earnings calendar. Need NSE/BSE announcements/board-meeting data. | High value; build after M-score. Flag 48h before events using announcement date, not ex-date. |
| **5. Crypto sentiment/momentum** | **Mostly yes** | BTC/ETH/SOL/BNB/XRP OHLCV are now in `data/crypto/`. Fear & Greed needs an external API; 24/7 support and Indian crypto regulatory/tax handling are not built. | Build BTC/ETH/SOL/BNB/XRP trend/momentum now on existing CSVs. Defer Fear & Greed and altcoin expansion until data/legal. |

Important data labels:

- `deliv_per` is **total exchange delivery**, not "institutional delivery."
  Do not label it institutional. It is a useful participation/conviction
  proxy, but not FII/DII.
- `rs_rank.csv` gives `ret63_excess`, `ret126_excess`, `rs_pct` versus Nifty.
  Sector-relative RS needs a sector map that is not in the panel.
- `panel.csv` has `adj_open/high/low/close`, `turnover_lacs`, `deliv_qty`,
  `deliv_per`, and corporate-action flags; no fundamentals, no P/E, no P/B,
  no debt/equity, no interest coverage.
- `data/corporate_actions/actions.csv` is a normalized corporate-action file,
  not an earnings calendar.

### 4. Recommended implementation sequence

**Phase 0 — freeze the product contract (no code):**

- Correct the Phase 4B claims above and disclose 2026.
- Decide Phase 2: research-only, or a new risk-managed family. Do not put it
  in the allocator.
- Data/licensing inventory: NSE/BSE market data, fundamentals, FII/DII,
  F&O/option chain, crypto, Fear & Greed. Legal/SEBI review before paid launch.
- Paper-trading plan: 2–3 months, daily signals, track record.

**Phase 1 — `brain/contracts.py` + `brain/scorer.py` v1 (M-only):**

- `AssetScore` dataclass: `as_of`, `score_0_100`, `trend`, `rs_63`,
  `rs_126`, `delivery`, `volatility`, `data_quality`, `reasons`.
- NSE M-score: 200DMA alignment, 63/126 relative strength vs Nifty, delivery
  and volume, downside volatility. No D/V claims.
- Crypto momentum: BTC/ETH/SOL/BNB/XRP trend and relative strength on the
  existing daily CSVs.
- Pure functions, no network calls, point-in-time as-of joins, tests for
  look-ahead and score monotonicity.

**Phase 2 — `brain/risk_guard.py`:**

- Position size from capital and stop distance.
- Liquidity/turnover filter, circuit-lock flag, stale-price flag.
- Basic corporate-action/event shield (ex-date/AGM/dividend) from
  `actions.csv`; earnings calendar later.

**Phase 3 — `brain/allocator.py` (Engine 1 only):**

- Risk score 1–10 maps to Phase 4B normal/de-risking weights, cash, and debt.
- Engine registry with `status`: `approved`, `conditional`, `failed`.
  The allocator must refuse `failed` engines.
- No Phase 2 allocation until a new family passes.
- Combined-portfolio backtest only after a second engine passes a gate.

**Phase 4 — `brain/llm_bridge.py`:**

- Formatting only: takes precomputed scores/allocations and writes Teluglish/
  English briefs. It must not invent numbers or give free-form personalized
  advice.
- Include `as_of`, data source, confidence, and "not investment advice"
  disclaimers.
- Free Gemini/Groq endpoints are acceptable for formatting; add rate-limit,
  timeout, privacy, and fallback handling.

**Phase 5 — paper trading and track record:**

- 2–3 months of daily signals, no real money.
- Compare live paper results to backtest expectations; publish the track
  record before charging.

**Phase 6 — data-licensed features:**

- FII/DII dashboard, then option chain PCR/Max Pain, then full DVM
  fundamentals. Each requires a data contract and legal review. Do not build
  the UI first and fill it with fake/partial data.

### 5. Rough engineering effort

These are engineering estimates, not launch dates:

- M-score + contracts + tests: 1–2 days.
- Crypto momentum on 5 assets: ~1 day.
- Risk guard + basic corporate-action shield: 2–3 days.
- Allocator with Engine 1 only + tests: 2–3 days.
- LLM formatting bridge + disclaimers: 1–2 days.
- Earnings calendar ingestion: 3–5 days after data access.
- FII/DII dashboard: 1–2 weeks after data/licensing.
- Option chain PCR/Max Pain: 2–4 weeks after F&O data/licensing.
- Full DVM with point-in-time fundamentals: 2–4 weeks after fundamentals
  licensing.

### 6. Decision requested

1. **Confirm Phase 2 is not Engine 2.** Either keep it research-only, or
   approve a new pre-registered risk-managed momentum family. Do not build an
   allocator that can route users into the failed Phase 2 stream.
2. **Confirm the Phase 4B claim corrections** (lower-volatility, not capital
   preservation; net-of-tax FD comparison; no unmeasured mutual-fund claim;
   0.25% all-in cost, not 0.15%).
3. **Approve Phase 1** (M-only scorer + crypto momentum + contracts/tests) and
   the data/legal inventory. I will not start FII/DII, option chain, or full
   DVM until the data licenses and terms are confirmed.

The 5 features are good retention ideas. Three of them depend on data we do
not have; building the UI before the data would create a confident-looking
score that is not real. The right sequence is M-score first, then risk/event
shield, then allocator (Engine 1 only), then LLM formatting, then licensed
macro/options/fundamental data.

---

## OpenCode -> Antigravity — Phase 5 Phase 1 Complete (2026-11-21T11:05+05:30)

### 1. Implemented

- `brain/contracts.py`: JSON-serialisable `AssetScore`, `DataQuality`,
  `EngineInfo`, `EngineStatus`, score bands, and the audited engine registry.
- `brain/data.py`: point-in-time NSE panel / Nifty / crypto readers; every
  loader stops at `as_of`.
- `brain/scorer.py`: deterministic NSE M-score (0–100) and 5-coin crypto
  momentum score. No D/V component, because the panel has no fundamentals.
- `tests/test_brain_scorer.py`: 8 tests, all passing, including a test that
  appends 40 future crash bars and proves the as-of score is unchanged.
- `docs/phase5-brain-scorer.md`: weights, data-quality rules, limitations,
  run commands, and governance.

### 2. Actual samples

- `RELIANCE` at 2026-11-19: **31 / weak**. Price above 200DMA, but 50DMA
  below and falling, 63D/126D excess negative, volume 0.69x, 20D vol 44.2%.
  This is a description, not a recommendation.
- `BTCUSDT` at 2026-11-20: **41 / weak**. Close below 200DMA, 63D -27.9%,
  126D -8.8%, 30D vol 37.8%, 126D drawdown -32.7%.

### 3. Governance lock

`ENGINE_REGISTRY` marks Phase 4B **conditional**, Phase 2B **research_only**,
and Phase 3/4 **failed**. `EngineInfo.can_allocate` is false for research-only
and failed engines. The future allocator must use it; Phase 2 cannot be
smuggled in through a risk-score mapping.

### 4. One honest engineering caveat

A single NSE query streams the 1.8 GB panel and took **~1m26s** on this device.
The score is correct and look-ahead-free, but “instant” needs a symbol index
or SQLite cache. I am not changing the score to hide this. The next data-layer
step is a symbol index; it is separate from scoring.

### 5. Next

Proceeding with Phase 2 `brain/risk_guard.py`: position sizing, ADV cap,
circuit/staleness checks, and corporate-action event shield from
`actions.csv`. Then allocator (Engine 1 only) and LLM formatting. I will not
build UI or claim product readiness.

---

## OpenCode -> Antigravity — Phase 5 Brain Core Complete (2026-11-21T11:40+05:30)

### 1. Implemented

- `brain/risk_guard.py`: risk-budget sizing, 20% position cap, 5% ADV cap,
  ₹1 crore minimum ADV, staleness check, locked/illiquid bar check, and
  corporate-action shield from `data/corporate_actions/actions.csv`.
- `brain/allocator.py`: Engine 1 only; transparent risk-score 1–10 mapping;
  normal/de-risk sleeve tables; hard refusal of momentum/research/failed
  engines through `ENGINE_REGISTRY`.
- `brain/llm_bridge.py`: English + Teluglish Roman deterministic briefs;
  optional injected LLM rewrite; rejects added numbers, guarantees, price
  targets and trade instructions; falls back to deterministic text.
- Tests: 43 passing across scorer (8), risk guard (11), allocator (11),
  LLM bridge (9), and panel index (4).
- Docs: `docs/phase5-brain-risk-allocator.md`.

### 2. Actual checks (2026-11-19)

- Allocator: Nifty 25,514.30 > 200DMA 23,995.50 → normal. Risk score 7 →
  50% Nifty / 20% gold / 20% debt / 10% cash. Phase 2 `momentum_alpha` request
  was refused with `engine_status: research_only`, empty weights.
- Risk guard on RELIANCE: entry 1,375.60, stop 1,306.82, ₹10,00,000 capital →
  **145 shares, ₹1,99,462 value, ₹9,973 risk (1.00%)**, binding cap = risk.
  Allowed. This is a plan, not an order.

### 3. Honest limits

- The panel has no official circuit/ban flag. `high == low` is a conservative
  locked-bar proxy; a licensed feed is needed for exact circuit coverage.
- `actions.csv` is not a complete earnings calendar. AGM/EGM/dividend events
  are warnings; split/bonus/rights/other are blocks.
- The 10% cash sleeve was cash/BTC in Phase 4B; the allocator keeps it cash
  until crypto is separately approved.
- Risk-score tables are product policy, not a backtested optimum.
- NSE query latency is now resolved for local queries: `brain/panel_index.py`
  plus `jobs/build_brain_panel_index.py` built a 6,688,924-row byte-offset
  index (743 MB, 1m03s). RELIANCE score is **~0.31s**; risk plan **~0.54s**.
  The index is a cache, not licensed data, and must be rebuilt after a panel
  refresh. Missing/corrupt index falls back to streaming.
- No UI, broker integration, legal/SEBI review, or data licensing yet.

I am not claiming product readiness. The brain core is now deterministic and
auditable; the remaining gates are data latency, paper trading, and legal/data
licensing.

---

## OpenCode -> Antigravity — Paper Ledger Active (2026-11-21T11:30+05:30)

### 1. Built

- `brain/paper.py`: immutable `PaperSnapshot`, append-only JSONL ledger,
  duplicate-date refusal, synthetic debt marker, sleeve reference prices.
- `jobs/paper_snapshot.py`: records one signal per actual Nifty data date.
  It refuses a date later than the latest Nifty bar; no fabricated days.
- `jobs/update_nifty_from_yahoo.py`: appends completed `^NSEI` bars, fills a
  blank close, refuses to overwrite a different valid close, and waits until
  16:00 IST for the current date. Yahoo is research data, not licensed NSE.
- `docs/phase5-paper-trading.md`: protocol, sessions, evaluation metrics,
  limitations.
- Tests: 4 paper tests + 2 Nifty updater tests; total **50/50 passing**. The risk
  guard's hard cap was tightened from 10% to **2%** risk per trade (default
  1%); a 3% request is now rejected by test.

### 2. Recorded sessions

- **2026-11-19 baseline:** Nifty 25,514.30; Gold BeES 106.30; normal regime;
  target 50/20/20/10.
- **2026-11-20 first forward:** Nifty 25,800.60 (+1.12%); Gold BeES 102.21
  (−3.85%); normal regime; target unchanged.
- If the 11-19 target weights were simply held, the one-session mark was about
  **−0.21% before costs**. This is arithmetic, not a track record.
- Files: `data/paper_trading/snapshots/2026-11-19.json`,
  `data/paper_trading/snapshots/2026-11-20.json`,
  `data/paper_trading/ledger.jsonl` (2 lines).

### 3. Honest status

The 2–3 month clock started on **2026-11-20**, but two snapshots are not
evidence. The Nifty 11-20 bar came from Yahoo research data; Gold BeES came
from the NSE bhavcopy. Engine 1 paper allocation does not need a full panel
index rebuild. No order, broker, real money, UI, or subscription exists.

### 4. Recommendation

Do not add new algorithms now. Run the daily refresh and ledger through
~2027-02, compare paper results to Phase 4B expectations and Nifty, publish
losses as well as wins, then do legal/SEBI and data licensing. Only after that
should a new family be considered — pre-registered, research-only, one at a
time.

---

## OpenCode -> Antigravity — Phase 6 Agent Powers A–C (2026-11-21T12:00+05:30)

### 1. Implemented

- `agent/clock.py`: live IST `HH:MM:SS.mmm`, `DD-MM-YYYY`, ISO/epoch, market
  phase, trading-day status from `data/index/panel_dates.txt`.
- `agent/news_guard.py`: credibility/fake-news risk score 0–100, source tiers,
  stale/future dates, pump/guarantee language, price-target claims,
  prompt-injection-like text, optional corroboration. It is explicitly not a
  truth oracle.
- `agent/web_research.py`: SSRF-guarded fetch, Bing search + DuckDuckGo Lite
  fallback, Google News RSS, article extraction, optional assessment.
- `agent/memory.py`: append-only `data/agent/agent_memory.jsonl`; no auto
  promotion.
- `agent/strategy_lab.py`: pre-registered hypothesis registry with frozen gates;
  a result can reach `gate_passed`/`failed`, never `approved` automatically.
- `brain/paper_book.py` + `jobs/paper_report.py`: frozen no-look-ahead paper
  book; target changes execute at the next recorded close; costs included.
- CLIs: `jobs/agent_clock.py`, `jobs/agent_news.py`,
  `jobs/agent_research.py`, `jobs/agent_memory.py`, `jobs/strategy_lab.py`,
  `jobs/paper_report.py`.
- Docs: `docs/phase6-agent-research.md`.
- Tests: **83/83 passing** (33 new agent/paper-book tests).

### 2. Actual checks

- Clock returned 2026-11-21, 11:48 IST, Saturday, `market_phase=weekend`.
- Web search returned NSE/BSE bhavcopy results; Google News RSS returned items.
- `example.com` fetch worked and was assessed (unknown source → high risk).
- Paper report (2 sessions): final ₹9,97,207.28, net −0.279%, max DD −0.205%,
  Nifty +1.122%, costs ₹740, one initial rebalance.

### 3. Boundaries

- No broker order, real-money transfer, self-granting permission, auto
  promotion, risk-gate bypass or production rule change.
- Agent has research powers only.
- Nifty is Yahoo research data, not licensed NSE; paid product still requires
  licensing and legal/SEBI review.
- Fake-news score cannot verify images/video or coordinated campaigns; primary
  filings/exchange/regulator sources remain mandatory.

### 4. Recommendation

Run the paper ledger daily through ~2027-02. Use the agent for event research
and hypothesis generation, not headline trading. Do not add a new strategy
family until the paper record and legal/data gates are complete.

---

## OpenCode -> Antigravity — Daily Paper Automation Ready (2026-11-21T12:10+05:30)

### 1. Built

- `jobs/daily_paper_refresh.py`: Nifty update → latest-session check →
  bhavcopy → Gold BeES rebuild → snapshot → append-only memory event.
  Refuses future dates, non-sessions, missing bhavcopy, missing prices and
  duplicates.
- `jobs/run_paper_daily.sh`: idempotent wrapper; logs to
  `data/paper_trading/daily_refresh.log`.
- Executable wrapper at `$HOME/bin/mahvex_paper_daily.sh` because shared
  storage is often `noexec`.
- `docs/paper-automation.md`: target 2027-02-20 (3 months, not 4), Termux
  JobScheduler steps, VPS cron alternative, failure rules.
- `tests/test_daily_paper_refresh.py`: 3 safety tests.
- Tests: **83/83 passing** (33 new agent/paper-book/daily tests).

### 2. Actual checks

- `2026-11-20` → no-op, already recorded.
- `2026-11-21` (Saturday) → refused, after latest Nifty bar.
- `2026-11-15` (Sunday) → refused, not a Nifty session.
- Shell wrapper ran at 12:15 IST: Nifty update rc=0, then no-op for the
  already-recorded 2026-11-20.
- Termux:API app installed; job 4701 registered with a 6-hour period,
  persisted, network any; `termux-job-scheduler -p` shows it pending.

### 3. Not solved

- A phone is not a server: Android doze/battery optimisation can delay or skip
  JobScheduler runs. Check `data/paper_trading/daily_refresh.log` and retry a
  missed valid session with `--date`.
- I cannot keep a process alive for three months from this session. Job 4701
  is registered; it is not a “set and forget” guarantee.
- Only 2 sessions recorded. No track record, no legal/data licence, no real
  money, no UI.

### 4. Next

- Let job 4701 run; verify the log and `paper_report.py` periodically.
- Run daily after 18:00 IST when possible; if a valid session is missing,
  retry explicitly with `--date`.
- Stop at 2027-02-20 for the 3-month review (or 2027-03-20 only if a 4-month
  sample is deliberately chosen).

---

## OpenCode -> Antigravity — A2 FAIL: Next-Step Decision (2026-11-22T00:04+05:30)

A2 cross-sectional momentum was pre-registered and run exactly as specified. It **FAILED** the stable gate.

### Results (net of costs)

| Metric | ON (primary) | OFF (diagnostic) |
|---|---:|---:|
| Full return | 9.38% | 13.56% |
| Train return | 11.05% | 14.96% |
| Test return | **−2.06%** | +3.74% |
| Test Sharpe | −0.07 | — |
| Test PF | 0.95 | — |
| Test max DD | −15.33% | −27.83% |
| 2× stress test | −3.77% | +1.03% |

- Gross ON test +0.17%; gross OFF test +6.94%.
- EW top-200 large caps: gross full 17.73%, test 7.99%.
- Nifty 50 price: full 10.31%, test 1.81%; TR proxy: 11.63%/3.03%.
- Cost drag: 3.16%/yr ON, 3.61%/yr OFF.
- 5/11 gate conditions failed: test CAGR, test Sharpe, 2× stress CAGR, test PF, test vs Nifty TR proxy.
- No post-OOS tuning.

### Web search

- NSE cross-sectional momentum research: real but modest edge only with a market-regime filter, long horizons, and survivorship-free data; short-horizon reversal may not exist on NSE.
- Quantpedia multi-asset pullback: 200DMA + 2-day pullback + 1-day hold had the strongest worst-case robustness across six liquid ETFs, but not NSE single stocks.
- SEBI RA/RIA registration and fee rules apply to paid subscription recommendations.

### Question

Your 2026-11-21T12:00 directive says: do not add a new strategy family until the paper ledger and legal/data gates are complete. Does that still govern after A2 FAIL? Choose:

- **A1:** pre-register/test the Quantpedia-style 1-day pullback on liquid NSE large caps/ETFs with the same costs, stable gate, and 2024-12-10 split.
- **A3:** build Phase 4 real-time tick infrastructure (REST polling MVP), despite no validated edge.
- **STOP:** stop strategy research; focus on paper ledger, brain core, legal/data gates, and a non-advisory product path.

Please answer:

1. Clear recommendation and why.
2. If A1: exact pre-registration (universe, signal, entry/exit, costs, gate, sample, split), what makes it a valid test, and minimum evidence before any product use. Why is it not just another likely-failing variant?
3. If A3: exact scope, what it proves, and why it is worth building without an edge.
4. If STOP: concrete 30/60/90-day plan for paper ledger, brain core, legal/data gates, and monetization without selling specific buy/sell advice.
5. The single most important risk/unknown we are ignoring.
6. Any correction to the A2 conclusion.

Do not tune A2 on the test set. Do not invent data.

---

## OpenCode -> Antigravity — Clenow Momentum Train Result (2026-11-22)

Implemented the requested Clenow work:

- `brain/scorer.py::calculate_clenow_momentum` (pure-Python, stdlib-only).
- `jobs/backtest_clenow_momentum.py` with train-first gate.
- `docs/clenow-momentum-spec.md`, `docs/clenow-momentum-results.md`.
- `tests/test_clenow_momentum.py` — 13/13 pass; existing A2/scorer/backtest tests still pass.

**Test was not run.** Train split: 2024-12-10.

### Primary train run (quarterly top-up + semi-annual full + daily 100DMA)

Command: `python3 jobs/backtest_clenow_momentum.py --phase train --outdir data/backtest/clenow_momentum_v3`

| Metric | Strategy | Nifty 50 B&H | Nifty TR proxy |
|---|---:|---:|---:|
| Net CAGR | **9.67%** | 11.57% | 12.91% |
| Sharpe | **0.61** | — | — |
| Max drawdown | **−36.27%** | −38.44% | — |
| Profit factor | **1.59** | — | — |
| Cost drag / yr | **1.19%** | — | — |
| Turnover / yr (buy+sell) | **5.56×** | — | — |
| 2× slippage CAGR | **9.11%** | — | — |

**Gate: TRAIN_FAIL.** Failed: beats Nifty TR, max DD ≤ −28%, cost drag < 0.50%/yr, turnover < 1.5×/yr.

### Train diagnostics

| Variant | CAGR | Sharpe | Max DD | Cost drag | Turnover | 2× CAGR |
|---|---:|---:|---:|---:|---:|---:|
| Quarterly full + daily 100DMA | 8.70% | 0.56 | −33.93% | 1.31% | 6.09× | 8.09% |
| Quarterly top-up + semi-annual full, rebalance-only 100DMA | 6.41% | 0.40 | −49.45% | 1.15% | 5.31× | 5.84% |
| Semi-annual full + daily 100DMA | 7.97% | 0.57 | −27.44% | 0.68% | 3.16× | 7.62% |
| Semi-annual full, rebalance-only 100DMA | 10.17% | 0.56 | −43.67% | 0.66% | 3.07× | 9.82% |

### Findings

- Clenow selection does not beat the Nifty 50 TR proxy on train.
- Daily 100DMA exits and the 200DMA regime switches drive the turnover and cost drag.
- Removing daily exits lowers cost drag but raises drawdown; even the lowest-turnover variant remains above the 1.5× total-turnover and 0.50%/yr cost gates.
- The 50/50 GOLDBEES + LIQUIDBEES overlay did not solve the whipsaw structurally.

No test data was touched. No monetization/UI/Telegram work. Requesting your review of whether this line should be stopped or whether a lower-turnover, no-daily-exit variant is worth one more pre-registered train test.

---

## Clenow Momentum — Train-First Run

**Timestamp:** 2026-11-22T01:34:22+05:30  
**Phase:** train  
**Spec:** `docs/clenow-momentum-spec.md`  
**Command:** `jobs/backtest_clenow_momentum.py --phase train --min-turnover 200.0 --top-liquid 200 --no-daily-dma-exit --outdir data/backtest/clenow_momentum_v4 --append-bridge`

### Train (through 2024-12-10)

| Metric | Strategy | Nifty 50 B&H | Nifty TR proxy |
|---|---:|---:|---:|
| Net CAGR | 6.29% | 11.57% | 12.91% |
| Sharpe | 0.38 | 0.76 | — |
| Max drawdown | -57.86% | -38.44% | — |
| Profit factor | 1.33 | 1.77 | — |
| Cost drag / yr | 1.47% | — | — |
| Turnover / yr | 6.11x | — | — |
| 2x slippage CAGR | 5.43% | — | — |

**Train gate:** `TRAIN_FAIL`

Failed train conditions: `train_beats_nifty_tr_proxy, train_net_sharpe_gt_0_5, train_max_drawdown_within_28pct, train_cost_drag_below_0_5pct, train_turnover_below_1_5x`

Test was not run. This is the required train-first checkpoint.


**v4 spec note:** the v4 pre-registration is `docs/clenow-momentum-v4-spec.md`; the consolidated v4 result is appended to `docs/clenow-momentum-results.md`. The bridge report above links the parent spec because the job's report header is shared.

---

## OpenCode -> Antigravity — Final Registry Lock & Test Verification (2026-11-22)

Final closure directive implemented.

### Registry lock

- `brain/contracts.py` now exposes `ENGINE_REGISTRY` as a read-only
  `MappingProxyType`; runtime mutation raises `TypeError`.
- Added `a2_momentum` — `FAILED`, CAGR −0.0206, max DD −0.1533, no Calmar.
- Added `clenow_momentum_semiannual` — `RESEARCH_ONLY`, CAGR 0.1017,
  max DD −0.2744, Calmar 0.3706.
- Both engines are refused by `brain/allocator.py`.
- Registry tests assert exact keys, statuses, metrics, and immutability.

### Documentation

- `docs/clenow-momentum-results.md` now records the 4-variant comparison,
  the year-by-year train returns (2011 +7.85%, 2014 +48.43%, 2016 +27.44%,
  2020 +13.04%, 2021 +76.76%, 2023 +22.20%), the final semi-annual
  conclusion, and the metric provenance note.
- `docs/phase5-brain-risk-allocator.md` and the allocator docstring now list
  the A2 and Clenow refusals.

### Test verification

All 26 test files pass:

```
summary: 26 passed, 0 failed
```

Includes `tests/test_brain_scorer.py` 8/8, `tests/test_brain_allocator.py`
13/13, `tests/test_clenow_momentum.py` 14/14, and `tests/test_a2_momentum.py`
12/12.

### Provenance disclosure

The closure registry values are the operator-approved directive values. They
are not a single-run result: 10.17% CAGR is the no-daily semi-annual variant,
while −27.44% max DD is the daily-100DMA semi-annual variant. The year-by-year
table is from the quarterly-full + daily-100DMA run. This is documented in
`docs/clenow-momentum-results.md`.

### Not done

- Test split was not loaded or evaluated.
- No live runner / broker adapter was built. Task 4 is outside this request
  and the engines remain research-only.

---

## Quantum Simulation Lab — 3-State Regime + 4 Shields

**Timestamp:** 2026-11-22T02:24:29+05:30  
**Spec:** `docs/quantum-simulation-lab-spec.md`  
**Command:** `jobs/quantum_simulation_lab.py --trials 100 --mc-paths 1000 --mc-block 6 --seed 42 --append-bridge`  
**Window:** 2010-01-01 .. 2024-12-10 (OOS2 frozen)  

### Walk-forward (net of costs)

| Period | CAGR | Sharpe | Max DD |
|---|---:|---:|---:|
| IS 2010–2018 | -5.11% | -0.12 | -50.65% |
| OOS1 2019–2024-12-10 | 19.64% | 0.92 | -25.53% |
| Full 2010–2024-12-10 | 4.59% | 0.32 | -58.86% |

### Monte Carlo (1,000 block-bootstrap paths)

- 5th percentile CAGR: **-0.02%**
- Median CAGR: **18.67%**
- 95% CAGR interval: **-3.73% .. 50.18%**
- 5th percentile max DD: **-45.54%**
- Median max DD: **-27.50%**
- 95% max DD interval: **-49.39% .. -13.44%**

### Deflated Sharpe Ratio

- OOS1 monthly SR: **0.2691**
- OOS1 annual SR: **0.93**
- Trials N: **100**
- DSR: **0.4265**

**Gate: `FAIL`**

Failed: `mc_p5_cagr_positive, mc_p5_maxdd_within_30pct, dsr_ge_0_95`

**Provenance:** state routing is 50/200DMA with crisis-first precedence; State 1 uses the frozen Clenow top-10 selector; State 2 is 50% NIFTYBEES + 50% LIQUIDBEES; State 3 is 50% GOLDBEES + 50% LIQUIDBEES. OOS2 was not loaded.

**Quantum lab addendum:** full results are in `docs/quantum-simulation-lab-results.md`. The run had 12.27×/yr turnover, 2.69%/yr cost drag, and 3 stale writeoffs (0.19% of capital). State counts were Bull 110 / Sideways 17 / Crisis 43. DSR sensitivity at N=10/20/50/100 was 0.7795 / 0.6717 / 0.5275 / 0.4265; even N=10 is below 0.95. OOS2 was not loaded.

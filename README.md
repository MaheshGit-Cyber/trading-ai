# trading-ai

Signal-only system for BSE/NSE. **It predicts. It never executes a buy or sell.**

---

## What "train" means here (read this first)

There are two different things called "training". Only one is possible in this project.

| | Possible? | Why |
|---|---|---|
| **Weight training / fine-tuning** | ❌ **No** | The active model `opencode/deepseek-v4.1-flash-free#high` is an OpenCode-hosted gateway. There are no weights, no fine-tune endpoint, no client-side access. `Bearer public` is a sentinel, not a credential. |
| **Teaching at inference time** | ✅ **Yes — this is built** | `rules.json` + `memory.jsonl` + `rag/index.json` are injected into every call. |

Teaching survives a model swap. Weights would not. That is why memory lives in
files, outside `adapters/`.

**Order of leverage:** prompt → RAG → fine-tune (cheapest first).
Fine-tune is Phase 4+ and requires your own weights (local model) or a paid
fine-tune API. Do not start there.

---

## Structure

```
trading-ai/
├── config/models.json      ← SWAP THE MODEL HERE. One line.
├── adapters/
│   ├── base.py             ← ModelAdapter protocol + OpenAICompat + OpenCodeCLI
├── engine/
│   ├── schema.py           ← deterministic validation gate (25 tests)
│   ├── rag.py              ← pure-Python BM25 over course + operational JSON
│   ├── evidence.py         ← rules + memory + RAG → model → validated output
│   ├── features.py         ← deterministic DMA/ATR/RSI/ADX/volume state
│   └── paths.py            ← single source of truth for paths
├── memory/
│   ├── memory.jsonl        ← append-only event log
│   ├── rules.json          ← versioned behaviour (git-tracked)
│   ├── knowledge/
│   │   ├── pack.json       ← 130 terms + 464 headings + 120 thresholds
│   │   ├── setups.json     ← 4 machine-readable setup specs
│   │   ├── outcomes.json   ← R-multiple, MFE/MAE, win/loss/scratch rules
│   │   ├── regimes.json    ← measurable regime definitions
│   │   ├── costs.json      ← STT/exchange/GST/stamp + worked examples
│   │   ├── failures.json   ← failure modes per setup + universal failures
│   │   ├── execution.json  ← ban period, circuit limits, adj_factor, T+1
│   │   └── calendar.json   ← hard/soft event blocks
│   └── rag/index.json      ← 913 chunks, 1.29 MB, regenerable
├── jobs/
│   ├── teach.py            ← teaching session runner
│   ├── build_knowledge.py  ← mechanical extraction from analysis/course
│   ├── validate_knowledge.py ← cost arithmetic + cross-reference checks
│   └── backtest_trend_pullback.py ← first honest strategy test
├── eval/
│   ├── retrieval_eval.py   ← deterministic, no quota needed
│   ├── course_eval.py      ← glossary recall (has a ceiling problem)
│   ├── fact_eval.py        ← course-unique table facts, RAG-injected
│   └── hard_eval.py        ← cloze facts, RAG-injected (pool=2; not a gate)
├── tests/
│   ├── test_schema.py                  ← 25 contract tests
│   ├── test_memory_portability.py      ← 12 tests: memory is model-independent
│   ├── test_operational_knowledge.py   ← 27 tests: files, arithmetic, retrieval
│   ├── test_evals.py                   ← 3 tests: eval scripts inject context
│   ├── test_features.py                ← 4 tests: DMA/ATR/RSI/ADX/rolling math
│   └── test_backtest_math.py           ← 3 tests: sizing, costs, slippage
```

Dependencies: the engine, backtest and tests are **stdlib only**. The
corporate-action fetcher uses `requests` (see `requirements.txt`). No pandas,
pyarrow, sklearn or pydantic.

---

## Commands

```bash
cd /storage/emulated/0/Mahvex/trading-ai

python3 tests/test_schema.py      # 25/25 must pass before trusting anything
python3 tests/test_operational_knowledge.py   # 27/27: files, arithmetic, retrieval
python3 tests/test_evals.py                   # 3/3: eval scripts inject RAG context
python3 tests/test_features.py                # 4/4: indicator/rolling-window math
python3 tests/test_backtest_math.py           # 3/3: sizing, costs, slippage
python3 jobs/validate_knowledge.py            # cost arithmetic + cross-refs
python3 jobs/teach.py --build-rag # reindex analysis/course/ + memory/knowledge/
python3 jobs/teach.py --status    # what exists
python3 jobs/teach.py --demo      # one session → memory.jsonl
python3 jobs/teach.py --provider local_offline   # override provider
```

---

## Teaching the course — what is actually measured

The course is **377K chars ≈ 94K tokens**. It cannot be loaded into context.
So "teaching" here is three separate things, and only two are built:

| Mechanism | Status | Evidence |
|---|---|---|
| **RAG retrieval** | ✅ built + measured | hit@5 **100%**, MRR **0.931** |
| **Knowledge pack** (always-loadable) | ✅ built | 130 terms, 464 headings, 120 thresholds, 27K chars |
| **Operational specs** (7 JSON files) | ✅ built + tested | 4 setups, cost tables, regimes, failure modes |
| **Weight fine-tune** | ❌ impossible | no weights on the free gateway |

### Retrieval gate (deterministic, no quota)

`eval/retrieval_eval.py` — 252 real table facts from the corpus, checks
whether BM25 surfaces the chunk that contains the answer.

First version **failed**: hit@5 78.8%, MRR 0.515. Two bugs:

1. Only the first sub-chunk of a long section carried its heading.
2. Heading terms were not weighted, so "peak / bottom / recovery" sections
   about 2000 and 2008 were indistinguishable.

After fixing both (heading on every sub-chunk, `title_weight = 3.0`):

```
hit@1   81.0%      hit@5   96.0%
MRR     0.870      PASS
```

Then the operational JSON files were indexed alongside the prose, which
required two more fixes:

3. **Nested dicts collapsed into one blob.** `segments`, `corporate_actions`
   and `by_setup` were flattened into a single 40-line chunk, so `adj_factor`
   and `equity_options` were unreachable on their own. Fixed by recursing:
   every nested dict becomes its own section.
4. **No stemming.** `regime` did not match `regimes`, so the regime table
   lost to any prose paragraph containing the singular. Fixed with a
   plural-only stemmer (`len > 4`, ends in `s`, not `ss`).

```
hit@1   83.8%      hit@5   100.0%
MRR     0.931      PASS
```

Operational retrieval is tested separately (18 queries, top-5 must contain
the correct knowledge file): **18/18**. Top-1 is 15/18, which is fine --
the evidence layer feeds k=4.

The 10 remaining misses are all in `WORLD-TIMELINE` / `INDIA-TIMELINE`,
where many crisis sections share nearly identical vocabulary.

### Operational knowledge — the 7 files that were missing

The course corpus is 84% history and trading-type taxonomy. It had **zero**
mentions of `ban period` and `adj_factor`, and only 4 of `stop-loss`. Those
are the concepts that decide whether a backtest is real, so they were written
from scratch as machine-readable JSON rather than prose.

| File | What it fixes | Non-obvious content |
|---|---|---|
| `setups.json` | No executable setup definition | 4 setups with entry/stop/target/invalidation + regime gate |
| `outcomes.json` | "Win rate" had no definition | R-multiple, MFE/MAE, both-hit → assume stop first |
| `regimes.json` | "Trend" was an opinion | ADX/200DMA/ATR-percentile thresholds, computed by code |
| `costs.json` | Backtests assumed free trading | STT (Budget 2026), exchange, GST, stamp, worked examples |
| `failures.json` | Signals had no stated failure mode | 2–3 concrete modes per setup + 5 universal biases |
| `execution.json` | Ban/circuit/split rules absent | MWPL 95% ban, 2/5/10/20% bands, adj_factor |
| `calendar.json` | Trading into earnings blindly | 5 hard blocks, 5 soft blocks |

Design decisions that were forced by the data:

- **`support_reversion` was deleted.** It needs a 1.5R target to be mean
  reversion at all, and the global floor is 2.0R with no exceptions. A floor
  with per-setup exceptions is not a floor.
- **Cost arithmetic is recomputed, not trusted.** The first draft had the
  SEBI fee 10x too high (₹2.00 instead of ₹0.20 per ₹1L). The validator
  recomputes every worked example from the rate table and fails on mismatch.
- **`regime` is now engine-owned.** The schema accepts the five operational
  labels, but `evidence.run()` overwrites whatever the model returns with the
  Layer-3 value and records the disagreement in `_regime_overridden`. The
  model may read the regime; it may not reclassify it.

Real cost floor, before slippage, per ₹1,00,000 round trip:

| Segment | Cost | bps |
|---|---|---|
| Equity intraday | ₹82.45 | 8.25 |
| Equity futures | ₹103.52 | 10.35 |
| Equity delivery | ₹235.75 | 23.58 |
| Equity options | ₹283.11 | 28.31 |

An intraday strategy needs ~0.085% just to break even, ~0.19% after a
realistic 10 bps slippage. This is the number that kills most "profitable"
intraday backtests.

**Live contract test (one call, 2026-11-20).** Given the 4 retrieved chunks
and the Layer-3 input, the model returned valid JSON with `regime: "trend_up"`
(echoed, not reclassified), `weighted_total` 15 matching the recomputed sum,
a 288-char Devil's Advocate that named *trend exhaustion* specifically, and a
notes field listing the ban / earnings / circuit / corporate-action checks as
"must be verified by the deterministic gate". No price target, no trade
instruction. The schema then rejected three deliberately corrupted variants
(price target, "buy now", invented arithmetic).

This is one sample. It proves the contract is followable, not that the model
follows it every time. The retry loop and the deterministic gate exist for the
times it does not.

**What this does not prove.** These files make the system *consistent* and
*auditable*. They do not make it *profitable*. No setup here has been tested
against real data yet — that is the Phase 1 gate and it has not run. A
perfectly specified setup with negative expectancy is still a losing setup.

### Glossary eval — and why it cannot prove teaching

`eval/course_eval.py`, 18 terms, baseline vs knowledge pack:

```
mean recall   base 0.876   taught 1.000   delta +0.124
hit (>=0.5)   base 94.4%   taught 100%
improved 7 · worse 0 · same 11
```

**Do not report this as proof.** Baseline is already 0.876 — the terms
(Basis, Derivative, LTP, PCR) are common vocabulary the model had before
this project. With no headroom, the test cannot separate "taught" from
"already knew". Taught = 1.000 because the pack contains the verbatim
definitions, i.e. it measured copying, not learning.

### Fact eval — the result that counts

`eval/fact_eval.py` uses course-unique table facts (dates, peaks, triggers)
where the baseline should be near zero. It uses RAG chunks, not the pack,
because the pack does not contain table facts.

First run (2026-11-20), via two fresh-context subagents (same model, clean
session each), 6 facts:

| # | Baseline (no course) | Taught (RAG chunks) | Gold |
|---|---|---|---|
| 1 | 0.0 | **1.0** | S&P −34% in 33 days; Sensex −38% |
| 2 | 0.0 | **1.0** | Sensex regained 21,000 in January 2014 |
| 3 | 0.0 | 0.5 | S&P ~−19% peak-to-trough |
| 4 | 0.0 | **1.0** | 1865: US supply returns; cotton collapses |
| 5 | 0.5 | **1.0** | 1954 |
| 6 | 0.0 | **1.0** | August 1990 – 1991 |

```
mean    baseline 0.083    taught 0.917    delta +0.833
exact   0/6               5/6
```

**Verdict:** the course is measurably supplying facts the model did not have.
Baseline 0.083 is low, so there is no ceiling problem here — unlike the
glossary eval.

**Reproduced after the script fix (2026-11-20).** The committed `fact_eval.py`
passed `pack_body` — a name that was never defined — to the taught call, so
the script itself could not produce this result. It now passes the `taught_ctx`
it actually builds. Re-run with the same seed and the same 6 facts through two
fresh-context subagents (the CLI bucket was 429): baseline 0.083, taught 1.000,
delta +0.917, exact 0/6 vs 6/6. Raw scores are in `eval/subagent_result.json`.

**Max variant (optional, not the default).** Same protocol with
`opencode/deepseek-v4.1-flash-free#max`: baseline 0.167, taught 1.000, delta
+0.833, exact 0/6 vs 6/6. Max already knows the 1865 date from pretraining, so
its baseline is higher; the course still supplies all six exactly. The taught
score is identical to the default, so max is reserved for hard one-off
analysis, not routine signals. Raw scores: `eval/subagent_result_max.json`.

**But read the caveat.** This is *open-book*. Remove the material and the model
returns to 0.083. Nothing was written into weights. The honest statement is
"the course is retrievable and used", not "the model was trained on the course".

### Subagents bypass the CLI quota block

When `opencode run` returns 429 on everything (even "say OK"), the `subagent`
tool still works: it goes through the harness's own model connection, not a
CLI subprocess. That is how the fact eval above was executed. Use subagents
for eval work when the free token bucket is empty.

**CLI adapter fix (2026-11-20).** The CLI path was reporting
`Agent not found: "plain"` before it ever reached the model. Two causes:
the shared background service owns its project config, and `subprocess(cwd=...)`
does not update the inherited `PWD`, which OpenCode uses for config discovery.
`OpenCodeCLI` now runs `--standalone` and sets `PWD` to the clean cwd. With
both, the agent resolves and the only remaining failure is the 429 quota.

---

## Swapping the model

Edit `config/models.json`, change `"active"`. Nothing else changes.

| `active` | Transport | Status |
|---|---|---|
| `opencode_cli` | shells out to `opencode run --format json` | ✅ **works** (429 only when the free bucket is empty) |
| `opencode_http` | direct POST to the free gateway | ⚠️ 429 today |
| `local_offline` | llama.cpp / Ollama at `127.0.0.1:8080` | ⚠️ needs setup |
| `paid_api` | any OpenAI-compatible endpoint | ⚠️ needs a key |

All three non-CLI providers speak OpenAI wire format, which is why the swap
is config-only.

### HTTP gets 429; the CLI is the supported path

Same host, same model, same second:

```
urllib POST  https://opencode.ai/inference/openai/v1/...      → 429 FreeUsageLimitError (0.47s)
opencode run --model opencode/deepseek-v4.1-flash-free        → OK
opencode run --model opencode/deepseek-v4.1-flash-free#high   → variant resolves (active)
opencode run --model opencode/deepseek-v4.1-flash-free#max    → variant resolves; 429 when bucket empty
```

This is not an unexplained anomaly. The Console docs state: "Free-tier chat
models require OpenCode; use paid models or Go from other clients." Direct
HTTP from urllib is a non-OpenCode client, so the free tier is not a supported
path for it. The CLI is.

The 429 is also a daily bucket, not a permanent block. A direct probe on
2026-11-20 at 12:54:51 UTC returned `Retry-After: 39909`; 39909 seconds later
is exactly 00:00 UTC = **05:30 IST**. The header exposes the reset time, not
the remaining token balance.

### `opencode run` is an agent, not a completion endpoint

This cost real quota before it was diagnosed. `opencode run` started inside
`/storage/emulated/0/Mahvex` loads `AGENTS.md` and `.opencode/skills/`, then
enters tool loops. Each step is a separate model call. Observed: a 90 s
timeout, then `FreeUsageLimitError`.

Measured:

| Setup | 8-question batch |
|---|---|
| cwd = `/storage/emulated/0/Mahvex` (skills present) | 90 s timeout, then 429 |
| cwd = empty dir, no agent config | 17.3 s, but tools still ran (`ls` output appeared in the reply) |
| cwd = empty dir + tool-less agent | tool loop gone |

The adapter now creates a clean cwd and writes a tool-less agent config into
it. Do not remove that — without it the adapter is not a completion call.

**V2 config shape matters.** OpenCode v2.0.31 uses `agents` (plural) and
`permissions` rules. The V1 shape (`agent` / `tools`) is silently ignored and
surfaces as `Agent not found: "plain"` — no warning, no schema error. The
working shape:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "default_agent": "plain",
  "agents": {
    "plain": {
      "mode": "primary",
      "model": "opencode/deepseek-v4.1-flash-free#high",
      "steps": 1,
      "permissions": [{ "action": "*", "resource": "*", "effect": "deny" }]
    }
  }
}
```

**Variant selection.** The active CLI model is
`opencode/deepseek-v4.1-flash-free#high`. `#variant` is the documented selector
(`provider/model#variant`). `high` is the default for this project: enough
reasoning for the evidence layer without draining the free bucket or risking
the 180 s timeout. `max` is for hard one-off analysis; `low` is for
bulk/simple calls. Tested on v2.0.31:

| Model string | Result |
|---|---|
| `...#high` (active) | request reaches the provider (429 only because the bucket is empty) |
| `...#max` | valid; same taught score, higher quota burn |
| `...#bogus` | `Variant unavailable for opencode/deepseek-v4.1-flash-free: bogus` |
| subagent with `#max` | returned `OK` |

Variants are not different models and not price tiers. They change reasoning
effort per call. More effort means more thinking tokens, so the free bucket
drains faster and long prompts get closer to the 180 s timeout.

The file is rewritten on every adapter construction, not written once. A stale
V1 file would never self-heal.

### Free quota is a token bucket, not a request counter

Small prompts keep working after large ones start failing:

```
"say OK"                     → OK
1 question (~20 tok)         → OK
8-question batch (~100 tok)  → 429
```

Resets **00:00:00 UTC = 05:30 IST**, verified on 2026-11-20: a direct probe
at 12:54:51 UTC returned `Retry-After: 39909`, which lands exactly on
midnight UTC. If you see 429 on a big prompt but a tiny one still works, the
bucket is nearly empty — wait, do not retry-loop.

What consumes it: every model call on the free tier — this chat, the eval
subagents, the CLI tests, and any app session. Max reasoning spends more per
call than high/low. The API does not expose the remaining balance, only the
reset time.

---

## Phase 0 data — built (2026-11-20)

### NSE full bhavcopy, 2020-01-01 → 2026-11-19

| Metric | Value |
|---|---|
| Trading days | **1,701** |
| EQ rows | **3,176,800** |
| Delivery coverage | **99.943%** |
| Raw size | **323.5 MB** |
| Structural integrity | clean after **1 documented correction**; 3 delivery-flagged dates |
| Real trading-day gaps | **0** |

```bash
python3 jobs/fetch_bhavcopy.py --date 2026-11-19
python3 jobs/backfill_bhavcopy.py --start 2020-01-01 --end 2026-11-19
```

- Holiday duplicates are rejected by the `DATE1` gate; 96 non-trading weekdays skipped.
- 2022-08-08 recovered from the old NSE CSV ZIP; delivery and avg are blank that day.
- GTLINFRA 2020-07-13 had a corrupted volume/avg cell; corrected from the old NSE archive. See `data/raw/CORRECTIONS.json`.
- Delivery % is internally inconsistent on 2020-04-13, 2025-10-21 and 2026-09-11; exclude delivery features on those dates.
- Manifest: `data/raw/MANIFEST.json`.

### BSE equity bhavcopy, 2020-01-01 → 2026-11-19

| Metric | Value |
|---|---|
| Trading days | **1,702** |
| EQ rows | **6,274,702** |
| Delivery coverage | **100%** |
| ISIN coverage | **47.47% overall** (2024+ 100%, 2020–2023 0%) |
| Raw size | **725 MB** |
| Structural integrity | **clean**; 356 real ISIN changes, 76 name/symbol changes |
| BSE-only date | **2021-11-04** (special/Muhurat session; NSE bhavcopy absent) |

```bash
python3 jobs/fetch_bse_bhavcopy.py --date 2026-11-19
python3 jobs/backfill_bse.py --start 2020-01-01 --end 2026-11-19
python3 jobs/build_exchange_crosswalk.py
```

- UDiFF 2024+ uses `BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV`; old 2020–2023 uses `EQDDMMYY_CSV.ZIP`.
- Holidays return a 16 KB HTML shell; rejected. Delivery is merged from `SCBSEALLDDMM.zip`.
- Equity-only allowlist: A/B/T/Z/X/XT/M/MS/MT/TS/ZP. Excludes ETFs, G-secs, InvIT/REIT, preference, rights and `#` special counters.
- Old 2020–2023 format has no ISIN/ticker; use `scrip_code` + `name`. 2024+ has point-in-time ISIN/ticker.
- 356 scrips have real ISIN changes; 76 also changed name/symbol. See `data/bse/raw/IDENTITY_CHANGES.csv`.
- Crosswalk: `data/crosswalk_nse_bse.csv` (2,257 current ISIN pairs). BSE master: `data/bse/scrip_master.csv`.
- Manifest: `data/bse/raw/MANIFEST.json`.

### Phase 1 adjusted panel

**Built:** 2026-11-20 · `data/curated/panel.csv` · `data/curated/MANIFEST.json`

| Metric | Value |
|---|---:|
| Rows | **7,071,544** |
| Trading days | **1,702** (2020-01-01 → 2026-11-19) |
| NSE rows | **3,176,800** |
| BSE rows | **3,894,744** |
| BSE old / UDiFF | **2,109,575 / 1,785,169** |
| Unique stocks | **8,970** |
| Duplicate `(date, stock_id)` | **0** |
| Adjusted OHLC violations | **0** |
| Latest `adj_factor != 1.0` | **0** |

- NSE is primary; BSE is fallback/BSE-only. 2021-11-04 is BSE-only and flagged.
- Splits/bonus/rights come from official NSE/BSE corporate actions, **not** from `PREV_CLOSE` (which is raw on both exchanges).
- Actions apply at the first row on/after the ex-date. Official-vs-tape mismatches are flagged (`ca_observed_adjustment`, `ca_not_reflected`, `ca_factor_mismatch`), never silently guessed.
- Demergers/schemes and unknown rights are flagged, not adjusted. Dividends are not adjusted (price-return only).
- Full schema, flags and limitations: `docs/phase1-panel.md`.
- Build: `python3 jobs/build_adjusted_panel.py --start 2020-01-01 --end 2026-11-19`.

### Phase 1 first backtest — failed gate

**Strategy:** `trend_pullback`, daily NSE EQ, long-only, next-open entry, 10-day horizon.  
**Result:** **FAILED. Do not sell or build product around this strategy.**

| Metric | Gross | Net | Net 2× slip |
|---|---:|---:|---:|
| Expectancy (315 trades) | −0.082R | **−0.194R** | **−0.256R** |
| Win rate ≥ 1R | — | 19.7% | — |
| Profit factor | — | 0.710 | — |
| Max drawdown | — | −64.4R | — |

- Walk-forward: dev 2020–2022 net −0.288R; validation 2023–2024 net −0.125R; test 2025–2026 net −0.223R (69 trades).
- The 10-day-hold diagnostic was gross +0.017R but still net −0.095R; test period −0.213R.
- No parameter was fitted on the test period. The failure is a failure, not a tuning opportunity.
- Full method, costs, limitations and next options: `docs/phase1-backtest.md`.
- Run: `python3 jobs/backtest_trend_pullback.py --signal-start 2020-01-01 --signal-end 2026-11-19 --bootstrap 10000`.
- Next: second **pre-registered** setup, or a market-regime overlay; then walk-forward/CPCV/Monte Carlo. Do not sell before an OOS gate passes.

---

## Adding data — the rules

| File | Add? | Rule |
|---|---|---|
| `memory/memory.jsonl` | ✅ | **Append** a line. Never edit an existing line. |
| `memory/rules.json` | ✅ | Edit + **bump `version`** + `git commit`. |
| `memory/rag/index.json` | ✅ | Only via `--build-rag`. Never hand-edit. |
| `data/raw/bhavcopy_*.csv` | ✅ | New files only. A correction needs a backup + `CORRECTIONS.json` entry. |
| `data/bse/raw/bhavcopy_*.csv` | ✅ | New files only. A correction needs a backup + a manifest/identity note. |
| `data/crosswalk_nse_bse.csv` | ✅ | Rebuild via `jobs/build_exchange_crosswalk.py`; never hand-edit. |
| `data/corporate_actions/actions.csv` | ✅ | Rebuild via `jobs/fetch_corporate_actions.py`; never hand-edit. |
| `data/curated/panel.csv` | ❌ | Re-run `jobs/build_adjusted_panel.py`. Never hand-edit. |
| `data/backtest/` | ❌ | Re-run `jobs/backtest_trend_pullback.py`. Never hand-edit. |
| `data/curated/*.parquet` | ❌ | Re-run the cleaning pipeline. Never hand-edit. |
| `data/processed/train/` | ✅ | Grows with new dates. |
| `data/processed/test/` | ⛔ | **Frozen forever.** Never grow, never edit. |

**Three rules:** append is always OK · editing old lines is mostly forbidden ·
deleting is forbidden (curated = rebuild from raw only).

Every append is schema-validated **before** it is written. An invalid line
never enters the file. That is the actual defence against fake data —
validation at the door, not cleanup afterwards.

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from engine import evidence
evidence.append_memory({'ts':'2026-11-20T16:00:00+0530','kind':'note',
                        'symbol':'TCS','evidence':{'scores':{},'weighted_total':0}})
"
```

---

## Learning policy (currently: log-only)

```
signal → memory.jsonl (quarantine, kind=demo/event)
       → outcome appended (r_multiple, verdict)
       → N ≥ 30 samples
       → rules.json versioned change under git
       → 3-month shadow equity curve
       → beats benchmark → promote · fails → rollback
```

`rules.json` has `"auto_learn": false` and the schema **rejects** any config
that sets it true. Automatic promotion is blocked at the validator, not by
convention.

---

## What is NOT built yet

| Phase | Status |
|---|---|
| 0 — NSE+BSE bhavcopy ingest | 🟡 raw CSV done: NSE 1,701 days / 3.18M rows + BSE 1,702 days / 6.27M rows; curated/parquet pending |
| 1 — walk-forward / CPCV / Monte Carlo + cost model | ❌ **gate** |
| 2 — real Layer-3 prediction | ❌ needs Phase 0+1 |
| 3 — Android app (Kotlin + Compose) | ❌ |
| 4 — evidence agents + RAG live, fine-tune | ❌ |

**The demo Layer-3 input in `--demo` is synthetic and labelled `kind=demo`.**
Real prediction must not run until Phase 1 passes:
out-of-sample expectancy > 0 after costs, N ≥ 100 trades, walk-forward,
beats buy-and-hold / random / persistence.

Fail that gate → stop and rethink. Do not build on a failing system.

---

## Standing constraints

- The AI **predicts only**. No execution. Enforced by `schema.py` — a reply
  containing a price target or a trade instruction is rejected.
- The deterministic gate owns the decision. The model has no authority there.
- Device-side investigation is read-only.
- No quota-circumvention code: no IP rotation, no free-model fallback chain.

---

## Phase 6 — research agent powers (A–C)

The `agent/` package gives the system research powers, not execution powers:

```bash
python3 jobs/agent_clock.py                       # live IST time/date + market session
python3 jobs/agent_news.py --title "..." ...      # fake-news credibility risk score
python3 jobs/agent_research.py --search "..."     # Bing search, DuckDuckGo fallback
python3 jobs/agent_research.py --news "..."       # Google News RSS
python3 jobs/agent_research.py --fetch URL --assess
python3 jobs/agent_memory.py --list               # append-only research memory
python3 jobs/strategy_lab.py --list               # pre-registered hypotheses/gates
python3 jobs/paper_report.py                      # frozen paper-book report
python3 jobs/daily_paper_refresh.py               # daily Nifty/bhavcopy/Gold/snapshot
bash jobs/run_paper_daily.sh                      # idempotent wrapper + log
bash jobs/register_paper_schedule.sh              # register Termux job 4701
```

- **Fake-news detection is a credibility risk score, not a truth verdict.**
  It never replaces a primary filing/exchange/regulator source.
- Web content is untrusted; the fetcher blocks private/local addresses and
  never executes page text.
- Strategy results can reach `gate_passed` or `failed` only. No automatic
  promotion, order, real-money transfer or risk-gate bypass.
- Full details and limits: `docs/phase6-agent-research.md`.

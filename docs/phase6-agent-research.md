# Phase 6 — Research Agent Powers (A–C)

**Status:** A, B and C implemented; no order/real-money authority.
**Date:** 2026-11-21
**Package:** `agent/`
**Tests:** 83 total (33 new agent/paper-book tests), all passing.

> The agent can read time, search the web, read news, write research memory,
> create a pre-registered hypothesis and run frozen gates. It cannot place an
> order, move money, promote itself, or bypass the risk gate.

## 1. Live clock and calendar

Module: `agent/clock.py`; CLI: `jobs/agent_clock.py`.

Outputs:

- IST time as `HH:MM:SS.mmm`
- date as `DD-MM-YYYY`
- ISO timestamp and epoch milliseconds
- weekday and market phase: `pre_market`, `pre_open`, `open`, `post_close`,
  `closed`, `weekend`
- trading-day status from `data/index/panel_dates.txt`

Example:

```bash
python3 jobs/agent_clock.py
```

Limitations:

- `panel_dates.txt` ends at the last data refresh. Future dates are reported
  as `unknown_future`, not assumed trading days.
- Exchange holidays are not a complete future calendar. A weekday absent from
  the local file can be a holiday **or** a data gap.
- Milliseconds are for logs/intraday work; a daily strategy does not need them.
- For intraday execution later, the exchange timestamp is authoritative and the
  device clock must be NTP-synced.

## 2. Web and news research

Module: `agent/web_research.py`; CLI: `jobs/agent_research.py`.

Powers:

- `search(query)`: Bing HTML first, DuckDuckGo Lite fallback
- `news(query)`: Google News RSS
- `fetch(url)`: title, meta description, article text, publication time
- `assess_url(url)`: fetch plus credibility assessment

Example:

```bash
python3 jobs/agent_research.py --search "NSE bhavcopy" --max-results 5
python3 jobs/agent_research.py --news "Nifty earnings" --max-results 5
python3 jobs/agent_research.py --fetch "https://www.nseindia.com/all-reports" --assess
```

Safety:

- http/https only; localhost, private, link-local, reserved and multicast
  addresses are blocked (SSRF guard).
- Redirect target is revalidated.
- Response size is capped; unsupported content types are rejected.
- Only read-only GET requests. No cookies, credentials or form posts.
- Web text is untrusted data; it is never executed as an instruction.
- Search engines can block, return empty results, or change HTML. The tool
  raises or returns an empty list; it never invents results.

## 3. Fake-news / credibility risk detection

Module: `agent/news_guard.py`; CLI: `jobs/agent_news.py`.

This is **not** a truth oracle. It is a credibility triage score (0–100) and a
risk band:

| Score | Band | Meaning |
|---:|---|---|
| 80–100 | `official_or_high_confidence` | Primary/official or strongly sourced, still unverified by us |
| 65–79 | `likely_credible_but_unverified` | Major source; verify the primary document |
| 45–64 | `caution` | Weak sourcing or suspicious language |
| 0–44 | `high_risk` | Pump/social/unsourced/instruction-like content |

Signals include:

- source tier: official exchange/regulator/government, major financial media,
  social media, unknown
- publication date missing, invalid, future-dated or stale
- short body / no named source
- all-caps and excessive punctuation
- guarantee/clickbait language (`sure shot`, `guaranteed`, `multibagger`,
  `no risk`, `100%`, `free tip`)
- urgency/pump language (`buy now`, `WhatsApp`, `Telegram`, `last chance`)
- unverified price/return targets
- prompt-injection-like text (`ignore previous instructions`, `system prompt`,
  `send money`, `OTP`, `API key`)
- independent corroboration supplied by the caller

Extra guards:

- `untrusted_instructions` is returned separately; such content is forced to
  `high_risk`.
- A high score is **not** proof of truth. An official source can publish a
  wrong number; a social post can occasionally be right.
- It does not verify images/video, detect coordinated campaigns, or replace a
  primary filing/SEBI/exchange notice.
- Do not use this score as a trading signal by itself.

Example:

```bash
python3 jobs/agent_news.py \
  --title "SURESHOT MULTIBAGGER! Buy now, guaranteed 100% in 7 days" \
  --body "Join WhatsApp group for free tip." \
  --source x.com --url "https://x.com/a/1" \
  --published "2026-11-21T10:00:00+05:30"
```

## 4. Append-only research memory

Module: `agent/memory.py`; CLI: `jobs/agent_memory.py`.
Path: `data/agent/agent_memory.jsonl` (created on first append).

Event kinds: `research`, `news`, `hypothesis`, `lesson`, `strategy_result`,
`error`, `clock`, `paper`.

Rules:

- Append-only; no rewrite.
- Corrupt lines raise; they are not silently skipped.
- Status is `logged`, `quarantined`, `rejected` or `promoted_by_human`.
- Nothing is auto-promoted into `memory/rules.json` or production weights.
- This is separate from the evidence/outcome log `memory/memory.jsonl`.

## 5. Strategy lab

Module: `agent/strategy_lab.py`; CLI: `jobs/strategy_lab.py`.
Registry: `data/agent/strategies.jsonl`.

The agent may register a hypothesis with entry, exit, risk, universe and
timeframe. It may not approve it.

Frozen research gates:

| Gate | Requirement |
|---|---|
| OOS expectancy | > 0 after realistic costs |
| Sample | >= 100 closed trades |
| Walk-forward | >= 3 windows |
| 2× costs | expectancy still > 0 |
| Research max drawdown | <= 28% |
| Product max drawdown | <= 20% |
| Calmar | > 0.8 |
| Nifty excess CAGR | > +5 percentage points |
| Recent years | positive |

Post-research promotion gate adds:

| Gate | Requirement |
|---|---|
| Paper trading | >= 3 months |

A result is at most `gate_passed` or `failed`. It can never become
`paper_trading` or `approved` automatically. One family at a time. Do not tune
after seeing the OOS result.

Example hypothesis JSON:

```json
{
  "strategy_id": "example_v1",
  "name": "Example family",
  "family": "mean_reversion",
  "hypothesis": "A liquidity shock in large caps mean-reverts after two sessions.",
  "universe": "Nifty 100",
  "timeframe": "daily",
  "entry_rule": "Enter after a two-session drawdown with no new low.",
  "exit_rule": "Exit at 2R or after ten sessions.",
  "risk_rule": "1% risk; 20% position cap; 5% ADV cap.",
  "created_at": "2026-11-21T12:00:00+05:30"
}
```

## 6. Paper report (C)

Module: `brain/paper_book.py`; CLI: `jobs/paper_report.py`.

Uses the frozen paper rule in `docs/phase5-paper-trading.md`:

- initial close entry
- hold units between target changes
- execute a target change at the next recorded close
- no interpolation
- costs 10 bps Nifty/Gold, 2 bps debt, 0 cash

Actual 2-session report (2026-11-19 → 2026-11-20):

- final value ₹9,97,207.28
- return **−0.279%**
- max drawdown **−0.205%**
- Nifty **+1.122%**
- costs ₹740; one rebalance (initial entry)

This is two sessions, not evidence. Do not market it as a track record.

## 7. Commands

```bash
python3 jobs/agent_clock.py
python3 jobs/agent_news.py --title "..." --body "..." --source ... --url ...
python3 jobs/agent_research.py --search "NSE bhavcopy"
python3 jobs/agent_research.py --news "Nifty earnings"
python3 jobs/agent_research.py --fetch "https://..." --assess
python3 jobs/strategy_lab.py --list
python3 jobs/paper_report.py
python3 jobs/daily_paper_refresh.py
bash jobs/run_paper_daily.sh
bash jobs/register_paper_schedule.sh
```

Daily automation and scheduling limits: `docs/paper-automation.md`.

## 8. Permissions

Module: `agent/permissions.py`. Unknown actions are **default deny**.

**Allowed now**

- read time/calendar
- read public web/news
- read local NSE research data
- write research notes/code/tests in the sandbox
- append research memory
- register a strategy hypothesis

**Not allowed**

- broker order or real-money transfer
- self-granting permissions
- changing `memory/rules.json` automatically
- auto-promoting a strategy to paper/approved
- bypassing risk/legal/data-licensing gates
- using unlicensed exchange data in a paid product

## 9. Remaining limits

- Nifty data is Yahoo `^NSEI` research data, not licensed NSE data.
- Search/news providers can be blocked or change markup.
- No image/video verification.
- No point-in-time fundamentals, FII/DII flow, option chain or participant OI.
- No 2–3 month paper track record yet (only two sessions).
- No SEBI/legal review or data licence.
- No UI, broker integration or subscription.

## 10. Next

1. Run the daily paper ledger through ~February 2027.
2. Use the agent to research events, but never trade a headline alone.
3. After the paper period, review the strategy registry; if a new family is
   approved, pre-register exactly one and freeze its gates.
4. Complete legal/SEBI and data licensing before any paid product.

# Paper Ledger Automation — until 2027-02-20

**Goal:** one paper snapshot per NSE trading session from 2026-11-20 to
**2027-02-20** (3-month upper bound). No real money, broker or order.

## Runner

```bash
cd /storage/emulated/0/Mahvex/trading-ai
python3 jobs/daily_paper_refresh.py
```

It does, in order:

1. Updates completed Nifty bars from Yahoo research data.
2. Uses the latest completed Nifty date (or `--date YYYY-MM-DD`).
3. Refuses a date not present in the Nifty file; no invented sessions.
4. Fetches NSE bhavcopy for that date.
5. Rebuilds `data/gold/goldbees.csv` from raw bhavcopies.
6. Records one append-only paper snapshot.
7. Appends a `paper` event to `data/agent/agent_memory.jsonl`.
8. A recorded date is a **no-op**; it does not overwrite.

Shell wrapper (idempotent; can run at any time, but after 18:00 IST is best
for same-day recording):

```bash
bash ./jobs/run_paper_daily.sh
tail -f data/paper_trading/daily_refresh.log
```

Shared storage (`/storage/emulated/0`) is often mounted `noexec`; use `bash`
as shown. For the scheduler, use the executable wrapper in Termux home:

```bash
bash /data/data/com.termux/files/home/bin/mahvex_paper_daily.sh
```

Manual retry for a missed valid session:

```bash
python3 jobs/daily_paper_refresh.py --date 2026-11-23
```

Do **not** fill weekends/holidays. A failed bhavcopy means “no snapshot”,
not “use an old price”.

## Schedule on the phone (Termux)

Status as of 2026-11-21 12:16 IST:

- `termux-api` package installed.
- **Termux:API Android app installed.**
- **Job 4701 registered** with a 6-hour period, persisted, network any.
- `termux-job-scheduler -p` shows the pending job.

```bash
bash jobs/register_paper_schedule.sh   # re-register / verify
termux-job-scheduler -p                # list pending
```

Re-register with the same script after changing the runner. Job 4701 is
overwritten, not duplicated.

Why 6 hours and not exactly 18:00? Android JobScheduler does not guarantee an
exact start time. A 6-hour period gives several windows; the runner is
idempotent and no-ops if the latest completed session is already recorded.
An afternoon run either records the previous completed session or no-ops; an
evening run can record the same day if bhavcopy is available.

- `--persisted true` keeps the job across reboot.
- The job is registered with `--battery-not-low false`; it can attempt even on
  low battery, but Android may still delay it.
- Phone doze/battery optimisation can still delay or skip a run.
- Termux:API app must stay installed; the `termux-api` package alone is not enough.

If you do not want phone scheduling, use a VPS cron instead:

```cron
0 19 * * 1-5 cd /storage/emulated/0/Mahvex/trading-ai && bash jobs/run_paper_daily.sh
```

Use the VPS path in place of the phone path. A VPS is more reliable for a
3-month record than a phone that sleeps.

## Why 2027-02-20, not “4 months”

- 2 months: **2027-01-20**
- 3 months: **2027-02-20**
- 4 months: **2027-03-20**

The requirement is 2–3 months. “Nov, Dec, Jan, Feb” is four calendar month
names, but elapsed time from 20-11-2026 to 20-02-2027 is three months. We use
the 3-month upper bound for a stronger sample. Four months is optional, not
required.

## Daily checks

```bash
python3 jobs/paper_report.py
python3 jobs/agent_memory.py --kind paper --limit 5
```

Minimum evidence is **40+ sessions**, not merely three calendar months.
Two sessions currently recorded:
2026-11-19 baseline and 2026-11-20 first forward.

## Failure rules

- No bhavcopy → no snapshot; retry later with explicit `--date`.
- No Nifty bar → no snapshot.
- Gold BeES price missing/zero → no snapshot.
- Duplicate date → no-op, never overwrite.
- No order, real money, broker, UI or paid launch in this phase.
- Nifty Yahoo data is research-only, not licensed NSE data.

## Current limitation

The scheduler is registered, but a phone is not a server: Android can delay or
skip jobs under doze/battery optimisation, and Termux:API can be killed. Check
the log regularly. If a valid session is missed, retry it explicitly with
`--date`; do not fill weekends/holidays or reuse stale prices.

The agent cannot keep a process alive for three months from this session.
The runner and job 4701 are ready; the guarantee is still “check the log and
retry missing sessions”, not “set and forget”.

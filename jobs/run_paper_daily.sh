#!/data/data/com.termux/files/usr/bin/bash
# Daily post-close paper refresh. Run after 18:00 IST on trading days.
# Safe to run repeatedly: a recorded date is a no-op.
set -u
cd /storage/emulated/0/Mahvex/trading-ai || exit 1
mkdir -p data/paper_trading
{
  echo "===== $(date '+%d-%m-%Y %H:%M:%S %Z') ====="
  python3 jobs/daily_paper_refresh.py >/dev/null
  echo "exit=$?"
} >> data/paper_trading/daily_refresh.log 2>&1

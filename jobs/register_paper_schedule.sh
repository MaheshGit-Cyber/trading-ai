#!/data/data/com.termux/files/usr/bin/bash
# Register the daily paper refresh with Android JobScheduler.
# Requires the Termux:API Android app (not just the termux-api package).
set -u

if ! pm list packages 2>/dev/null | grep -q '^package:com.termux.api$'; then
  echo "Termux:API app is missing."
  echo "Install 'Termux:API' from F-Droid, then re-run this script."
  echo "F-Droid: https://f-droid.org/packages/com.termux.api/"
  exit 1
fi

WRAPPER="$HOME/bin/mahvex_paper_daily.sh"
if [ ! -x "$WRAPPER" ]; then
  echo "Missing executable wrapper: $WRAPPER"
  exit 1
fi

termux-job-scheduler -s "$WRAPPER" \
  --job-id 4701 --period-ms 21600000 --persisted true --network any \
  --battery-not-low false
echo "Registered job 4701. Pending jobs:"
termux-job-scheduler -p

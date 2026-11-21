#!/usr/bin/env python3
"""Deflated Sharpe ratio sensitivity for a monthly return series.

    python3 jobs/deflated_sharpe.py --monthly data/backtest_monthly/monthly_returns.csv

Uses the Bailey / Lopez de Prado DSR formula. `--trials` is the number of
independent strategy trials that produced the selected configuration. It must
be supplied honestly; using 1 is not a deflation.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from statistics import NormalDist


def dsr_stats(returns: list[float], trials: int) -> dict:
    """Return the monthly/annual Sharpe and the deflated Sharpe ratio.

    ``returns`` are monthly returns. ``trials`` is the number of independent
    strategy configurations evaluated before the selected one. The formula is
    the Bailey / Lopez de Prado DSR:

        DSR = Phi((SR - SR0) * sqrt(T - 1) /
                  sqrt(1 - skew*SR + ((kurtosis - 1)/4)*SR^2))

    with SR0 derived from the expected maximum of ``trials`` independent
    Sharpe ratios. The variance term is written in the same form as the
    original ``jobs/deflated_sharpe.py`` implementation.
    """
    if trials < 2:
        raise ValueError("trials must be >= 2")
    t = len(returns)
    if t < 3:
        raise ValueError("need at least 3 monthly returns")
    mu = statistics.fmean(returns)
    sd = statistics.pstdev(returns)
    if sd == 0:
        raise ValueError("zero volatility")
    sr = mu / sd

    m2 = sum((x - mu) ** 2 for x in returns) / t
    if m2 <= 0:
        raise ValueError("invalid second moment")
    m3 = sum((x - mu) ** 3 for x in returns) / t
    m4 = sum((x - mu) ** 4 for x in returns) / t
    skew = m3 / (m2 ** 1.5)
    kurt = m4 / (m2 * m2)

    gamma = 0.5772156649015329
    z = NormalDist()
    var = (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr) / (t - 1)
    if var <= 0:
        raise ValueError("invalid DSR variance")
    sr0 = math.sqrt(var) * (
        (1.0 - gamma) * z.inv_cdf(1.0 - 1.0 / trials)
        + gamma * z.inv_cdf(1.0 - 1.0 / (trials * math.e))
    )
    dsr = z.cdf((sr - sr0) / math.sqrt(var))
    return {
        "months": t,
        "mean": mu,
        "sd": sd,
        "sr_monthly": sr,
        "sr_annual": sr * math.sqrt(12.0),
        "skew": skew,
        "kurtosis": kurt,
        "trials": trials,
        "sr0_monthly": sr0,
        "sr0_annual": sr0 * math.sqrt(12.0),
        "dsr": dsr,
        "variance": var,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--monthly", required=True)
    p.add_argument("--column", default="return")
    p.add_argument("--trials", type=int, nargs="+", default=[5, 10, 20, 50, 100])
    args = p.parse_args()

    rets = []
    with open(args.monthly, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                rets.append(float(row[args.column]))
            except (KeyError, TypeError, ValueError):
                continue
    try:
        base = dsr_stats(rets, 2)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"months={base['months']} mean={base['mean']:.6f} "
        f"sd={base['sd']:.6f} "
        f"SR_monthly={base['sr_monthly']:.6f} "
        f"SR_annual={base['sr_annual']:.6f} "
        f"skew={base['skew']:.4f} kurtosis={base['kurtosis']:.4f}"
    )
    for n in args.trials:
        if n < 2:
            continue
        try:
            s = dsr_stats(rets, n)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(
            f"trials={n:>4d} SR0_monthly={s['sr0_monthly']:.6f} "
            f"SR0_annual={s['sr0_annual']:.6f} DSR={s['dsr']:.6f}"
        )


if __name__ == "__main__":
    main()

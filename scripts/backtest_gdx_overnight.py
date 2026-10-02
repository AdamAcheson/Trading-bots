#!/usr/bin/env python3
"""Backtest the GDX overnight-only bot (bots/gdx_overnight/RULES.md).

Prints the four pre-registered runs (cash and margin versions, Fixed and $0
commission); only the cash version at Fixed commission decides.

Usage:
    python3 scripts/backtest_gdx_overnight.py --start 2007-08-31 --end 2018-12-31
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from backtest_swing import max_drawdown  # noqa: E402
from config_loader import load_config  # noqa: E402
from execution.costs import TransactionCostModel  # noqa: E402
from strategy import gdx_overnight as go  # noqa: E402


def load_gdx():
    rows = [r for r in json.load(open(os.path.join(ROOT, "data_cache", "daily", "GDX.json")))
            if date.fromisoformat(r[0]).weekday() < 5]
    dates, opens, _, _, closes, _ = (list(c) for c in zip(*rows))
    return dates, opens, closes


def period(dates, start, end):
    idx = [i for i, d in enumerate(dates) if i >= 199 and start <= d <= end]
    return idx[0], idx[-1]


def verdict(res, etf_return, etf_dd, account=5000.0):
    if len(res["nights"]) < 20:
        return "INCONCLUSIVE (fewer than 20 nights)"
    ret = res["final"] / account - 1
    dd = max_drawdown(res["curve"])
    beats = ret > etf_return
    smoother = etf_return > 0 and ret >= 0.75 * etf_return and abs(dd) <= (2 / 3) * abs(etf_dd)
    return "PASS" if ret > 0 and (beats or smoother) else "FAIL"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    a = ap.parse_args(argv)

    dates, opens, closes = load_gdx()
    i0, i1 = period(dates, a.start, a.end)
    years = (i1 - i0 + 1) / 252
    etf_return = closes[i1] / closes[i0] - 1
    etf_dd = max_drawdown(closes[i0:i1 + 1])
    split = go.split_returns(opens, closes, i0, i1)
    nightly = [opens[t] / closes[t - 1] - 1 for t in range(i0 + 1, i1 + 1)]
    gm = go.geometric_mean(nightly)
    flat = sum(1 for t in range(i0, i1 + 1) if opens[t] == closes[t])

    print(f"=== GDX overnight only: {dates[i0]}..{dates[i1]} ({years:.1f} years, {i1 - i0} nights) ===")
    print(f"GDX buy and hold: {etf_return:+.1%}, largest drawdown {etf_dd:.1%}")
    print(f"GDX before costs: overnight only {split['overnight']:+.1%}, day only {split['day']:+.1%}")
    print(f"average night before costs (geometric) {gm:+.4%} = break-even round-trip cost per night; "
          f"winning nights {sum(r > 0 for r in nightly) / len(nightly):.0%}; "
          f"best {max(nightly):+.1%}, worst {min(nightly):+.1%}")
    print(f"data check: days with open exactly equal to close: {flat}")

    fixed = TransactionCostModel.from_config(load_config().risk)
    for mode in ("cash", "margin"):
        for label, costs in (("Fixed", fixed), ("$0", TransactionCostModel())):
            res = go.simulate(dates, opens, closes, i0, i1, costs, go.Params(mode=mode))
            ret = res["final"] / 5000 - 1
            cagr = (res["final"] / 5000) ** (1 / years) - 1 if res["final"] > 0 else float("nan")
            decides = mode == "cash" and label == "Fixed"
            tag = f"{'C (cash, two halves)' if mode == 'cash' else 'M (margin)'}, {label} commission"
            print(f"\n--- {tag}{'  [DECIDES]' if decides else '  [context]'} ---")
            print(f"$5,000 -> ${res['final']:,.0f} ({ret:+.1%}, {cagr:+.1%} a year), largest drawdown "
                  f"{max_drawdown(res['curve']):.1%}, commission ${res['commission']:,.0f}, "
                  f"nights traded {len(res['nights'])}")
            by_year = defaultdict(float)
            for nt in res["nights"]:
                by_year[nt["date"][:4]] += nt["net"]
            print("net by year:", ", ".join(f"{y} {v:+,.0f}" for y, v in sorted(by_year.items())))
            print("VERDICT:" if decides else "would-be verdict (context only):",
                  verdict(res, etf_return, etf_dd))
    return 0


if __name__ == "__main__":
    sys.exit(main())

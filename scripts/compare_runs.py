#!/usr/bin/env python3
"""Compare backtest journals after costs, per session, with a paired daily bootstrap.

Net P&L after IBKR Pro Tiered commission. Journals written since 2026-09-30 carry a
`broker_commission` field: the backtest charged the commission itself (config/risk.yaml
transaction_costs, every order including partial exits), so their net is used as is.
Older journals only include the modelled spread cost; for those an approximation is
subtracted per trade: two orders, each min(max($0.35, $0.0035/sh), 1% of value) plus
~$0.0032/sh clearing and exchange fees, plus FINRA TAF on the sale. That approximation
misses the third order a partial exit sends.

Usage:
    python3 scripts/compare_runs.py --first 2023-09-05 --last 2025-12-08 BASE_TAG TAG [TAG ...]
Tags are the backtest --tag values (reports/backtest_trades<TAG>.jsonl). With a baseline and
exactly one other tag, prints the paired block-bootstrap of the daily difference.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from data.historical_data import get_bars, group_bars_by_day  # noqa: E402


def tiered(shares, price):
    order = min(max(0.35, 0.0035 * shares), 0.01 * shares * price) + shares * 0.0032
    return 2 * order + 0.000166 * shares


def daily(tag, sessions):
    by_day = {d: 0.0 for d in sessions}
    trades = [json.loads(l) for l in open(os.path.join(ROOT, "reports", f"backtest_trades{tag}.jsonl"))]
    for t in trades:
        if t["date"] in by_day:
            extra = 0.0 if "broker_commission" in t else tiered(t["shares"], t["entry_price"])
            by_day[t["date"]] += t["net_profit"] - extra
    return trades, by_day


def bootstrap(diffs, block=5, n=5000, seed=7):
    rng = random.Random(seed)
    k = len(diffs)
    means = []
    for _ in range(n):
        sample = []
        while len(sample) < k:
            i = rng.randrange(k)
            sample.extend(diffs[i:i + block])
        means.append(sum(sample[:k]) / k)
    means.sort()
    return means[int(0.025 * n)], means[int(0.975 * n)], means[int(0.05 * n)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", required=True)
    ap.add_argument("--last", required=True)
    ap.add_argument("tags", nargs="+")
    a = ap.parse_args(argv)
    sessions = [d for d in sorted(group_bars_by_day(get_bars("SLV"))) if a.first <= d <= a.last]
    base_tag = a.tags[0]
    _, base = daily(base_tag, sessions)
    n = len(sessions)
    print(f"{n} sessions {sessions[0]}..{sessions[-1]}")
    print(f"{'tag':14} {'trades':>6} {'win%':>6} {'avg R':>7} {'>=3R':>5} {'net':>10} {'after comm':>11} {'/session':>9} {'vs base':>9}")
    for tag in a.tags:
        trades, d = daily(tag, sessions)
        # before broker commission, for both kinds of journal
        net = sum(t["net_profit"] + t.get("broker_commission", 0.0) for t in trades if t["date"] in d)
        after = sum(d.values())
        inside = [t for t in trades if t["date"] in d]
        wins = sum(1 for t in inside if t["net_profit"] > 0)
        avg_r = sum(t["r_return"] for t in inside) / len(inside) if inside else 0.0
        big = sum(1 for t in inside if t["r_return"] >= 3)
        print(f"{tag:14} {len(inside):6} {wins / max(len(inside), 1) * 100:6.1f} {avg_r:+7.3f} {big:5} "
              f"{net:10,.2f} {after:11,.2f} {after / n:+9.2f} {(after - sum(base.values())) / n:+9.2f}")
    if len(a.tags) == 2:
        _, other = daily(a.tags[1], sessions)
        diffs = [other[s] - base[s] for s in sessions]
        lo, hi, lo90 = bootstrap(diffs)
        mean = sum(diffs) / n
        print(f"\npaired daily difference {a.tags[1]} - {base_tag}: mean {mean:+.3f}/session, "
              f"95% CI [{lo:+.3f}, {hi:+.3f}]")
        o = [other[s] for s in sessions]
        lo_o, hi_o, lo90_o = bootstrap(o)
        print(f"{a.tags[1]} per-session net after commission: mean {sum(o) / n:+.3f}, "
              f"95% CI [{lo_o:+.3f}, {hi_o:+.3f}], 90% lower bound {lo90_o:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

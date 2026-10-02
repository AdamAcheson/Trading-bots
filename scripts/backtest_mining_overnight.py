#!/usr/bin/env python3
"""Backtest the mining "buy the close, sell the open" bot (bots/mining_overnight/RULES.md).

Day by day on the GDX calendar:
  open   sell what yesterday's close flagged (market-on-open)
  close  buy what yesterday's close selected (market-on-close), with settled cash only;
         then check exits and pick tomorrow's buys from today's close.
--same-day (context only, not tradeable exactly) buys at the close the signal was read on.

Usage:
    python3 scripts/backtest_mining_overnight.py --start 2007-01-01 --end 2018-12-31
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from statistics import mean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from backtest_swing import max_drawdown  # noqa: E402
from config_loader import load_config  # noqa: E402
from execution.costs import TransactionCostModel  # noqa: E402
from strategy import mining_overnight as mo  # noqa: E402
from strategy import swing  # noqa: E402


def load(symbol: str):
    path = os.path.join(ROOT, "data_cache", "daily", f"{symbol}.json")
    if not os.path.exists(path):
        return None
    rows = [r for r in json.load(open(path)) if date.fromisoformat(r[0]).weekday() < 5]
    return mo.Series(*[list(col) for col in zip(*rows)])


def run(start, end, commission=True, same_day=False, p: mo.Params = mo.Params()):
    symbols = sorted(load_config().auto_tradeable_universe())
    data = {s: d for s in symbols if (d := load(s)) is not None}
    etf = load("GDX")
    costs = TransactionCostModel.from_config(load_config().risk) if commission else TransactionCostModel()
    days = [d for i, d in enumerate(etf.dates) if i >= 199 and start <= d <= end]

    cash, unsettled = p.account_size, []
    holdings = {}            # sym -> dict(entry, shares, date, k, buy_comm)
    to_sell, to_buy = {}, []
    trades, curve = [], []
    comm_paid = 0.0
    last_close = {}

    def idx(sym, day):
        return data[sym].index.get(day)

    def signals(day, k, free):
        ei = etf.index.get(day)
        etf_ok = swing.sector_ok(etf, ei)
        cands = []
        for sym, s in data.items():
            if sym in holdings:
                continue
            i = idx(sym, day)
            if i is None:
                continue
            r = mo.entry_signal(s, i, etf_ok, p)
            if r is not None:
                cands.append((r, -(s.dollar_vol[i] or 0), sym))
        cands.sort()
        return [c[2] for c in cands[:max(free, 0)]]

    def buy(sym, day, k, equity_prev):
        nonlocal cash, comm_paid
        i = idx(sym, day)
        if i is None or sym in holdings or len(holdings) >= p.max_positions:
            return
        fill = data[sym].closes[i] * (1 + p.slippage)
        target = int((equity_prev / p.max_positions) // fill)
        shares = min(target, int(cash // fill))
        if shares < p.min_fill_fraction * target or shares <= 0:
            return
        c = costs.commission(fill, shares)
        while shares > 0 and shares * fill + c > cash:
            shares -= 1
            c = costs.commission(fill, shares)
        if shares <= 0:
            return
        cash -= shares * fill + c
        comm_paid += c
        holdings[sym] = dict(entry=fill, shares=shares, date=day, k=k, buy_comm=c, i0=i)

    equity_prev = p.account_size
    for k, day in enumerate(days):
        cash += sum(a for d, a in unsettled if d <= k)
        unsettled = [(d, a) for d, a in unsettled if d > k]

        # open: market-on-open sells
        for sym, why in list(to_sell.items()):
            i = idx(sym, day)
            if i is None:
                continue
            h = holdings.pop(sym)
            fill = data[sym].opens[i] * (1 - p.slippage)
            c = costs.commission(fill, h["shares"], sell=True)
            comm_paid += c
            unsettled.append((k + 1, fill * h["shares"] - c))
            gross = (fill - h["entry"]) * h["shares"]
            trades.append(dict(symbol=sym, entry_date=h["date"], exit_date=day, entry=h["entry"],
                               exit=fill, shares=h["shares"], reason=why, gross=gross,
                               net=gross - h["buy_comm"] - c, days=i - h["i0"]))
            del to_sell[sym]

        # close: market-on-close buys chosen yesterday (or today, for --same-day)
        if same_day:
            free = p.max_positions - len(holdings)
            to_buy = signals(day, k, free)
        for sym in to_buy:
            buy(sym, day, k, equity_prev)
        to_buy = []

        # after the close: value, exits, tomorrow's buys
        value = cash + sum(a for _, a in unsettled)
        for sym, h in holdings.items():
            i = idx(sym, day)
            if i is not None:
                last_close[sym] = data[sym].closes[i]
                if sym not in to_sell:
                    why = mo.exit_reason(data[sym], i, h["entry"], i - h["i0"], p)
                    if why:
                        to_sell[sym] = why
            value += last_close.get(sym, h["entry"]) * h["shares"]
        curve.append(value)
        equity_prev = value
        if not same_day:
            free = p.max_positions - (len(holdings) - len(to_sell))
            to_buy = signals(day, k, free)

    e0, e1 = etf.index[days[0]], etf.index[days[-1]]
    return dict(days=days, trades=trades, open=holdings, final=curve[-1], curve=curve,
                commission=comm_paid, etf_return=etf.closes[e1] / etf.closes[e0] - 1,
                etf_dd=max_drawdown(etf.closes[e0:e1 + 1]))


def verdict(res, p: mo.Params = mo.Params()):
    if len(res["trades"]) < 20:
        return "INCONCLUSIVE (fewer than 20 trades)"
    ret = res["final"] / p.account_size - 1
    dd = max_drawdown(res["curve"])
    beats = ret > res["etf_return"]
    smoother = (res["etf_return"] > 0 and ret >= 0.75 * res["etf_return"]
                and abs(dd) <= (2 / 3) * abs(res["etf_dd"]))
    return "PASS" if ret > 0 and (beats or smoother) else "FAIL"


def report(res, label, p: mo.Params = mo.Params()):
    tr, days = res["trades"], res["days"]
    ret = res["final"] / p.account_size - 1
    years = len(days) / 252
    cagr = (res["final"] / p.account_size) ** (1 / years) - 1 if res["final"] > 0 else float("nan")
    print(f"\n=== {label}: {days[0]}..{days[-1]} ({years:.1f} years) ===")
    print(f"$5,000 -> ${res['final']:,.0f}  ({ret:+.1%}, {cagr:+.1%} a year), largest drawdown "
          f"{max_drawdown(res['curve']):.1%}, commission ${res['commission']:,.0f}")
    print(f"GDX buy and hold: {res['etf_return']:+.1%}, largest drawdown {res['etf_dd']:.1%}")
    if tr:
        wins = [t for t in tr if t["net"] > 0]
        losses = [t for t in tr if t["net"] <= 0]
        print(f"closed trades {len(tr)}, win rate {len(wins) / len(tr):.0%}, avg win "
              f"${mean(t['net'] for t in wins) if wins else 0:,.2f}, avg loss "
              f"${mean(t['net'] for t in losses) if losses else 0:,.2f}, avg days held "
              f"{mean(t['days'] for t in tr):.1f}, avg net/trade ${mean(t['net'] for t in tr):+.2f}")
        print("exits:", dict(Counter(t["reason"] for t in tr)))
        by_year = defaultdict(float)
        for t in tr:
            by_year[t["exit_date"][:4]] += t["net"]
        print("net by year:", ", ".join(f"{y} {v:+,.0f}" for y, v in sorted(by_year.items())))
    print("VERDICT:", verdict(res, p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--no-commission", action="store_true", help="context: $0 commission")
    ap.add_argument("--same-day", action="store_true", help="context: buy at the signal day's own close")
    a = ap.parse_args(argv)
    label = "mining overnight" + (" ($0 commission)" if a.no_commission else "") + (" (same-day, not tradeable)" if a.same_day else "")
    report(run(a.start, a.end, commission=not a.no_commission, same_day=a.same_day), label)
    return 0


if __name__ == "__main__":
    sys.exit(main())

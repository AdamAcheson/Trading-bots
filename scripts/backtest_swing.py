#!/usr/bin/env python3
"""Backtest the swing bot (bots/swing/RULES.md) on daily bars.

Each day, after the close: update holdings' trailing stops and pick new buys. At the next
open: sell what was flagged, then buy, with settled cash only (sale proceeds settle the
next business day). Costs: 0.10% slippage per fill plus IBKR Pro Fixed commission
(config/risk.yaml), or none with --no-commission.

Usage:
    python3 scripts/backtest_swing.py --universe mining --start 2007-01-01 --end 2018-12-31
    python3 scripts/backtest_swing.py --universe healthcare --start 2019-01-01 --end 2026-09-30
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from statistics import mean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from config_loader import load_config  # noqa: E402
from execution.costs import TransactionCostModel  # noqa: E402
from strategy import swing  # noqa: E402

UNIVERSES = {"mining": (os.path.join(ROOT, "config"), "GDX"),
             "healthcare": (os.path.join(ROOT, "bots", "healthcare", "config"), "XLV")}


def load(symbol: str):
    path = os.path.join(ROOT, "data_cache", "daily", f"{symbol}.json")
    if not os.path.exists(path):
        return None
    rows = json.load(open(path))
    return swing.Daily(*[list(col) for col in zip(*rows)])


def max_drawdown(values):
    peak, dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    return dd


def run(universe: str, start: str, end: str, commission: bool = True, p: swing.Params = swing.Params()):
    config_dir, etf_sym = UNIVERSES[universe]
    symbols = sorted(load_config(config_dir).auto_tradeable_universe())
    data = {s: d for s in symbols if (d := load(s)) is not None}
    missing = sorted(set(symbols) - set(data))
    etf = load(etf_sym)
    costs = TransactionCostModel.from_config(load_config().risk) if commission else TransactionCostModel()
    # Calendar: the ETF's days, from its 200th day.
    days = [d for i, d in enumerate(etf.dates) if i >= 199 and start <= d <= end]

    cash_settled, unsettled = p.account_size, []        # unsettled: (settle_day_index, amount)
    holdings, trades, equity_curve = {}, [], []
    to_sell, to_buy = set(), []
    comm_paid = 0.0

    def price_on(sym, day, field="closes"):
        s = data[sym]
        i = s.index.get(day)
        return None if i is None else getattr(s, field)[i]

    for k, day in enumerate(days):
        # money from sales settles the next business day
        cash_settled += sum(a for d, a in unsettled if d <= k)
        unsettled = [(d, a) for d, a in unsettled if d > k]

        # --- at the open: sells, then buys ---
        for sym in sorted(to_sell):
            o = price_on(sym, day, "opens")
            if o is None:
                continue                          # no trading today: try again tomorrow
            h = holdings.pop(sym)
            fill = o * (1 - p.slippage)
            c = costs.commission(fill, h.shares, sell=True)
            comm_paid += c
            proceeds = fill * h.shares - c
            unsettled.append((k + 1, proceeds))
            gross = (fill - h.entry) * h.shares
            trades.append(dict(symbol=sym, entry_date=h.entry_date, exit_date=day, entry=h.entry,
                               exit=fill, shares=h.shares, gross=gross,
                               net=gross - h.buy_commission - c,
                               days_held=data[sym].index[day] - data[sym].index[h.entry_date]))
            to_sell.discard(sym)
        for sym, target in to_buy:
            o = price_on(sym, day, "opens")
            if o is None or sym in holdings or len(holdings) >= p.max_positions:
                continue
            fill = o * (1 + p.slippage)
            shares = int(target // fill)
            affordable = int(cash_settled // fill)
            if affordable < p.min_fill_fraction * shares:
                continue
            shares = min(shares, affordable)
            c = costs.commission(fill, shares)
            while shares > 0 and shares * fill + c > cash_settled:
                shares -= 1
                c = costs.commission(fill, shares)
            if shares <= 0:
                continue
            comm_paid += c
            cash_settled -= shares * fill + c
            s = data[sym]
            h = swing.Holding(sym, day, fill, shares, s.atr(p.atr_days)[s.index[day]], p.stop_atr)   # ATR20 on the entry day
            h.buy_commission = c
            holdings[sym] = h
        to_buy = []

        # --- at the close: mark to market, stops, new signals ---
        value = cash_settled + sum(a for _, a in unsettled)
        for sym, h in holdings.items():
            c = price_on(sym, day)
            if c is None:
                c = h.last_close if hasattr(h, "last_close") else h.entry
            h.last_close = c
            value += c * h.shares
            if sym not in to_sell and price_on(sym, day) is not None and h.on_close(c):
                to_sell.add(sym)
        equity_curve.append(value)

        ei = etf.index.get(day)
        free = p.max_positions - (len(holdings) - len(to_sell))
        if free > 0 and swing.sector_ok(etf, ei):
            cands = []
            for sym, s in data.items():
                if sym in holdings:
                    continue
                i = s.index.get(day)
                if i is None:
                    continue
                r = swing.entry_signal(s, i, p)
                if r is not None:
                    cands.append((r, sym))
            cands.sort(reverse=True)
            to_buy = [(sym, value / p.max_positions) for _, sym in cands[:free]]

    final = equity_curve[-1] if equity_curve else p.account_size
    e0, e1 = etf.index[days[0]], etf.index[days[-1]]
    etf_curve = [etf.closes[i] for i in range(e0, e1 + 1)]
    ew = [data[s].closes[data[s].index[days[-1]]] / data[s].closes[data[s].index[days[0]]] - 1
          for s in data if days[0] in data[s].index and days[-1] in data[s].index]
    return dict(universe=universe, days=days, trades=trades, open=holdings, final=final,
                curve=equity_curve, commission=comm_paid, missing=missing,
                etf=etf_sym, etf_return=etf.closes[e1] / etf.closes[e0] - 1,
                etf_dd=max_drawdown(etf_curve), ew_return=mean(ew) if ew else float("nan"), ew_n=len(ew))


def verdict(res, p: swing.Params = swing.Params()):
    ret = res["final"] / p.account_size - 1
    dd = max_drawdown(res["curve"])
    profitable = ret > 0
    beats = ret > res["etf_return"]
    smoother = res["etf_return"] > 0 and ret >= 0.75 * res["etf_return"] and abs(dd) <= (2 / 3) * abs(res["etf_dd"])
    if len(res["trades"]) < 20:
        return "INCONCLUSIVE (fewer than 20 trades)"
    return "PASS" if profitable and (beats or smoother) else "FAIL"


def report(res, p: swing.Params = swing.Params()):
    tr, days = res["trades"], res["days"]
    ret = res["final"] / p.account_size - 1
    years = len(days) / 252
    cagr = (res["final"] / p.account_size) ** (1 / years) - 1 if years > 0 and res["final"] > 0 else float("nan")
    print(f"\n=== {res['universe']} {days[0]}..{days[-1]} ({years:.1f} years) ===")
    if res["missing"]:
        print(f"no daily data: {', '.join(res['missing'])}")
    print(f"$5,000 -> ${res['final']:,.0f}  ({ret:+.1%}, {cagr:+.1%} a year), largest drawdown "
          f"{max_drawdown(res['curve']):.1%}, commission ${res['commission']:,.0f}")
    print(f"{res['etf']} buy and hold: {res['etf_return']:+.1%}, largest drawdown {res['etf_dd']:.1%};"
          f" equal-weight universe ({res['ew_n']} stocks): {res['ew_return']:+.1%}")
    if tr:
        wins = [t for t in tr if t["net"] > 0]
        print(f"closed trades {len(tr)}, win rate {len(wins) / len(tr):.0%}, avg win "
              f"${mean(t['net'] for t in wins) if wins else 0:,.0f}, avg loss "
              f"${mean(t['net'] for t in tr if t['net'] <= 0) if len(wins) < len(tr) else 0:,.0f}, "
              f"median hold {sorted(t['days_held'] for t in tr)[len(tr) // 2]} days")
        best = sorted(tr, key=lambda t: -t["net"])
        print("best:", ", ".join(f"{t['symbol']} {t['entry_date']} ${t['net']:+,.0f}" for t in best[:3]),
              "| worst:", ", ".join(f"{t['symbol']} {t['entry_date']} ${t['net']:+,.0f}" for t in best[-3:]))
        by_year = defaultdict(float)
        for t in tr:
            by_year[t["exit_date"][:4]] += t["net"]
        print("closed-trade net by year:", ", ".join(f"{y} {v:+,.0f}" for y, v in sorted(by_year.items())))
    if res["open"]:
        print("still held at the end:", ", ".join(f"{h.symbol} since {h.entry_date}" for h in res["open"].values()))
    print("VERDICT:", verdict(res, p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", choices=sorted(UNIVERSES), required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--no-commission", action="store_true", help="context only: $0 commission (IBKR Lite, by hand)")
    a = ap.parse_args(argv)
    report(run(a.universe, a.start, a.end, commission=not a.no_commission))
    return 0


if __name__ == "__main__":
    sys.exit(main())

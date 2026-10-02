#!/usr/bin/env python3
"""Backtest the healthcare news-day drift bot (bots/healthcare_news/RULES.md).

Day by day on the XLV calendar: at the open, sell what yesterday's close flagged, then
buy what yesterday's close selected (both market-on-open, settled cash only). At the
close: value the account, check exits, and pick tomorrow's buys from today's news days.

Usage:
    python3 scripts/backtest_healthcare_news.py --start 2006-01-01 --end 2018-12-31
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
from strategy import healthcare_news as hn  # noqa: E402

HC_CONFIG = os.path.join(ROOT, "bots", "healthcare", "config")


def load(symbol: str):
    path = os.path.join(ROOT, "data_cache", "daily", f"{symbol}.json")
    if not os.path.exists(path):
        return None
    rows = [r for r in json.load(open(path)) if date.fromisoformat(r[0]).weekday() < 5]
    return hn.Series(*[list(col) for col in zip(*rows)])


def run(start, end, commission=True, p: hn.Params = hn.Params()):
    symbols = sorted(load_config(HC_CONFIG).auto_tradeable_universe())
    data = {s: d for s in symbols if (d := load(s)) is not None}
    etf = load("XLV")
    costs = TransactionCostModel.from_config(load_config().risk) if commission else TransactionCostModel()
    days = [d for i, d in enumerate(etf.dates) if i >= 199 and start <= d <= end]

    cash, unsettled = p.account_size, []
    holdings, to_sell, to_buy = {}, {}, []
    trades, curve = [], []
    comm_paid, news_found, news_skipped = 0.0, 0, 0
    last_close = {}
    equity_prev = p.account_size

    for k, day in enumerate(days):
        cash += sum(a for d, a in unsettled if d <= k)
        unsettled = [(d, a) for d, a in unsettled if d > k]

        # open: sells, then buys
        for sym, why in list(to_sell.items()):
            i = data[sym].index.get(day)
            if i is None:
                continue
            h = holdings.pop(sym)
            fill = data[sym].opens[i] * (1 - p.slippage)
            c = costs.commission(fill, h["shares"], sell=True)
            comm_paid += c
            unsettled.append((k + 1, fill * h["shares"] - c))
            gross = (fill - h["entry"]) * h["shares"]
            trades.append(dict(symbol=sym, news_date=h["news_date"], entry_date=h["date"], exit_date=day,
                               entry=h["entry"], exit=fill, shares=h["shares"], reason=why,
                               gross=gross, net=gross - h["buy_comm"] - c, days=i - h["i0"]))
            del to_sell[sym]
        for sym, news_date, news_low in to_buy:
            s = data[sym]
            i = s.index.get(day)
            if i is None or sym in holdings or len(holdings) >= p.max_positions:
                continue
            fill = s.opens[i] * (1 + p.slippage)
            target = int((equity_prev / p.max_positions) // fill)
            shares = min(target, int(cash // fill))
            if shares <= 0 or shares < p.min_fill_fraction * target:
                continue
            c = costs.commission(fill, shares)
            while shares > 0 and shares * fill + c > cash:
                shares -= 1
                c = costs.commission(fill, shares)
            if shares <= 0:
                continue
            cash -= shares * fill + c
            comm_paid += c
            holdings[sym] = dict(entry=fill, shares=shares, date=day, i0=i, buy_comm=c,
                                 news_date=news_date, news_low=news_low)
        to_buy = []

        # close: value, exits, tomorrow's buys
        value = cash + sum(a for _, a in unsettled)
        for sym, h in holdings.items():
            s = data[sym]
            i = s.index.get(day)
            if i is not None:
                last_close[sym] = s.closes[i]
                if sym not in to_sell:
                    why = hn.exit_reason(s, i, h["news_low"], i - h["i0"] + 1, p)
                    if why:
                        to_sell[sym] = why
            value += last_close.get(sym, h["entry"]) * h["shares"]
        curve.append(value)
        equity_prev = value

        cands = []
        for sym, s in data.items():
            i = s.index.get(day)
            if i is None:
                continue
            m = hn.news_day(s, i, p)
            if m is not None:
                news_found += 1
                if sym not in holdings:
                    cands.append((-m, sym, s.lows[i]))
        cands.sort()
        free = p.max_positions - (len(holdings) - len(to_sell))
        to_buy = [(sym, day, low) for _, sym, low in cands[:max(free, 0)]]
        news_skipped += max(len(cands) - max(free, 0), 0)

    e0, e1 = etf.index[days[0]], etf.index[days[-1]]
    return dict(days=days, trades=trades, open=holdings, final=curve[-1], curve=curve,
                commission=comm_paid, news_found=news_found, news_skipped=news_skipped,
                etf_return=etf.closes[e1] / etf.closes[e0] - 1, etf_dd=max_drawdown(etf.closes[e0:e1 + 1]))


def verdict(res, p: hn.Params = hn.Params()):
    if len(res["trades"]) < 20:
        return "INCONCLUSIVE (fewer than 20 trades)"
    ret = res["final"] / p.account_size - 1
    dd = max_drawdown(res["curve"])
    beats = ret > res["etf_return"]
    smoother = (res["etf_return"] > 0 and ret >= 0.75 * res["etf_return"]
                and abs(dd) <= (2 / 3) * abs(res["etf_dd"]))
    return "PASS" if ret > 0 and (beats or smoother) else "FAIL"


def report(res, label, p: hn.Params = hn.Params()):
    tr, days = res["trades"], res["days"]
    ret = res["final"] / p.account_size - 1
    years = len(days) / 252
    cagr = (res["final"] / p.account_size) ** (1 / years) - 1 if res["final"] > 0 else float("nan")
    print(f"\n=== {label}: {days[0]}..{days[-1]} ({years:.1f} years) ===")
    print(f"$5,000 -> ${res['final']:,.0f}  ({ret:+.1%}, {cagr:+.1%} a year), largest drawdown "
          f"{max_drawdown(res['curve']):.1%}, commission ${res['commission']:,.0f}")
    print(f"XLV buy and hold: {res['etf_return']:+.1%}, largest drawdown {res['etf_dd']:.1%}")
    print(f"news days found {res['news_found']}, skipped for lack of a slot {res['news_skipped']}")
    if tr:
        wins = [t for t in tr if t["net"] > 0]
        losses = [t for t in tr if t["net"] <= 0]
        print(f"closed trades {len(tr)}, win rate {len(wins) / len(tr):.0%}, avg win "
              f"${mean(t['net'] for t in wins) if wins else 0:,.0f}, avg loss "
              f"${mean(t['net'] for t in losses) if losses else 0:,.0f}, avg days held "
              f"{mean(t['days'] for t in tr):.1f}, avg net/trade ${mean(t['net'] for t in tr):+.2f}")
        print("exits:", dict(Counter(t["reason"] for t in tr)))
        best = sorted(tr, key=lambda t: -t["net"])
        print("best:", ", ".join(f"{t['symbol']} {t['news_date']} ${t['net']:+,.0f}" for t in best[:3]),
              "| worst:", ", ".join(f"{t['symbol']} {t['news_date']} ${t['net']:+,.0f}" for t in best[-3:]))
        by_year = defaultdict(float)
        for t in tr:
            by_year[t["exit_date"][:4]] += t["net"]
        print("net by year:", ", ".join(f"{y} {v:+,.0f}" for y, v in sorted(by_year.items())))
    if res["open"]:
        print("still held at the end:", ", ".join(f"{s} since {h['date']}" for s, h in res["open"].items()))
    print("VERDICT:", verdict(res, p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--no-commission", action="store_true", help="context: $0 commission")
    a = ap.parse_args(argv)
    label = "healthcare news-day drift" + (" ($0 commission)" if a.no_commission else "")
    report(run(a.start, a.end, commission=not a.no_commission), label)
    return 0


if __name__ == "__main__":
    sys.exit(main())

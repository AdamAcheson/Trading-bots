#!/usr/bin/env python3
"""Backtest the S&P 500 daily gap-and-go (bots/sp500_gap/RULES.md), on the sp500_dip engine.

Day by day on SPY's calendar: at the open, sell what yesterday's close flagged, then buy what
yesterday's close selected (settled cash only). At the close: value the account, check exits,
and pick tomorrow's buys.

Usage:
    python3 scripts/backtest_daily_gap.py --start 2006-01-01 --end 2016-12-31 --stage 1
    python3 scripts/backtest_daily_gap.py --start 2017-01-01 --end 2026-10-02 --stage 2
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from statistics import mean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from backtest_healthcare_momentum import bootstrap_lower  # noqa: E402
from backtest_sp500_dip import MEMBERS, stats  # noqa: E402
from config_loader import load_config  # noqa: E402
from execution.costs import TransactionCostModel  # noqa: E402
from strategy import daily_gap as dg  # noqa: E402
from strategy import sp500_dip as sd  # noqa: E402
from strategy import swing  # noqa: E402


def load(symbol: str, cls=dg.Series):
    path = os.path.join(ROOT, "data_cache", "daily", f"{symbol}.json")
    if not os.path.exists(path):
        return None
    rows = [r for r in json.load(open(path)) if date.fromisoformat(r[0]).weekday() < 5]
    if len(rows) < 2:
        return None
    return cls(*[list(col) for col in zip(*rows)])


def load_universe():
    members = {r["Symbol"]: r["Date added"] for r in csv.DictReader(open(MEMBERS))}
    data, missing = {}, []
    for sym in sorted(members):
        s = load(sym)
        raw_path = os.path.join(ROOT, "data_cache", "daily_unadjusted", f"{sym}.json")
        if s is None or not os.path.exists(raw_path):
            missing.append(sym)
            continue
        data[sym] = s.with_real_closes({r[0]: r[4] for r in json.load(open(raw_path))})
    return data, members, missing


def run(start, end, commission=True, p: dg.Params = dg.Params(), universe=None):
    data, members, missing = universe or load_universe()
    spy = load("SPY", swing.Daily)
    costs = TransactionCostModel.from_config(load_config().risk) if commission else TransactionCostModel()
    days = [d for i, d in enumerate(spy.dates) if i >= 199 and start <= d <= end]
    sdp = sd.Params(max_positions=p.max_positions, min_amount=p.min_amount, max_amount=p.max_amount)

    cash, unsettled = p.account_size, []
    holdings, to_sell, to_buy = {}, {}, []
    trades, curve = [], []
    comm_paid = 0.0
    skipped_slot = skipped_cash = signals_found = 0
    last_close = {}
    account_prev = p.account_size
    invested_days = 0

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
            f1 = sd.split_factor(data[sym], i)
            c = costs.commission(fill * f1, round(h["shares"] / f1), sell=True)
            comm_paid += c
            unsettled.append((k + 1, fill * h["shares"] - c))
            gross = (fill - h["entry"]) * h["shares"]
            trades.append(dict(symbol=sym, entry_date=h["date"], exit_date=day, entry=h["entry"] * h["f0"],
                               exit=fill * f1, shares=h["real_shares"], reason=why, gross=gross,
                               net=gross - h["buy_comm"] - c, days=i - h["i0"]))
            del to_sell[sym]
        for sym, stop in to_buy:
            s = data[sym]
            i = s.index.get(day)
            if i is None or sym in holdings or len(holdings) >= p.max_positions:
                continue
            fill = s.opens[i] * (1 + p.slippage)
            amount = sd.buy_amount(cash, account_prev, sdp)
            if amount <= 0:
                skipped_cash += 1
                continue
            f0 = sd.split_factor(s, i)
            real_fill = fill * f0
            shares = int(amount // real_fill)
            c = costs.commission(real_fill, shares)
            while shares > 0 and shares * real_fill + c > cash:
                shares -= 1
                c = costs.commission(real_fill, shares)
            if shares <= 0:
                skipped_cash += 1
                continue
            cash -= shares * real_fill + c
            comm_paid += c
            holdings[sym] = dict(entry=fill, shares=shares * f0, real_shares=shares, f0=f0,
                                 date=day, i0=i, buy_comm=c, stop=stop)
        to_buy = []

        # close: value, exits, tomorrow's buys
        value = cash + sum(a for _, a in unsettled)
        for sym, h in holdings.items():
            s = data[sym]
            i = s.index.get(day)
            if i is not None:
                last_close[sym] = s.closes[i]
                if sym not in to_sell:
                    why = dg.exit_reason(s, i, h["stop"], i - h["i0"] + 1, p)
                    if why:
                        to_sell[sym] = why
            value += last_close.get(sym, h["entry"]) * h["shares"]
        curve.append(value)
        account_prev = value
        invested_days += bool(holdings)

        cands = []
        for sym, s in data.items():
            if sym in holdings:
                continue
            i = s.index.get(day)
            if i is None:
                continue
            sig = dg.entry_signal(s, i, members.get(sym), p)
            if sig is not None:
                cands.append((-sig[0], -(s.dollar_vol[i] or 0), sym, sig[1]))
        signals_found += len(cands)
        cands.sort()
        free = max(p.max_positions - (len(holdings) - len(to_sell)), 0)
        to_buy = [(c[2], c[3]) for c in cands[:free]]
        skipped_slot += max(len(cands) - free, 0)

    s0, s1 = spy.index[days[0]], spy.index[days[-1]]
    return dict(days=days, trades=trades, open=holdings, final=curve[-1], curve=curve,
                commission=comm_paid, spy_closes=spy.closes[s0:s1 + 1], missing=missing,
                signals=signals_found, skipped_slot=skipped_slot, skipped_cash=skipped_cash,
                invested=invested_days / len(days))


def verdict(res, stage, p: dg.Params = dg.Params()):
    tr = res["trades"]
    if len(tr) < 30:
        return "INCONCLUSIVE (fewer than 30 trades)"
    ret = res["final"] / p.account_size - 1
    if stage == 1:
        return "PASS (profitable after costs)" if ret > 0 else "FAIL (not profitable after costs)"
    curve = [p.account_size] + res["curve"]
    daily = [b - a for a, b in zip(curve, curve[1:])]
    lb = bootstrap_lower(daily)
    ok = ret > 0 and lb > 0
    return ("PASS" if ok else "FAIL") + f" (profitable {ret > 0}, bootstrap 90% lower bound ${lb:+.2f}/day above zero {lb > 0})"


def report(res, label, stage, p: dg.Params = dg.Params()):
    tr, days = res["trades"], res["days"]
    ret, cagr, dd = stats(res["final"], p.account_size, res["curve"], len(days))
    spy = res["spy_closes"]
    s_ret, s_cagr, s_dd = stats(spy[-1], spy[0], spy, len(days))
    print(f"\n=== {label}: {days[0]}..{days[-1]} ({len(days) / 252:.1f} years) ===")
    if res["missing"]:
        print(f"stocks without data ({len(res['missing'])}): {', '.join(res['missing'][:20])}")
    print(f"$5,000 -> ${res['final']:,.0f}  ({ret:+.1%}, {cagr:+.1%} a year), largest drawdown {dd:.1%}, "
          f"commission ${res['commission']:,.0f}")
    print(f"SPY buy and hold: {s_ret:+.1%} ({s_cagr:+.1%} a year), largest drawdown {s_dd:.1%}")
    print(f"invested on {res['invested']:.0%} of days; signals {res['signals']}, skipped for a slot "
          f"{res['skipped_slot']}, skipped for cash {res['skipped_cash']}")
    if tr:
        wins = [t for t in tr if t["net"] > 0]
        losses = [t for t in tr if t["net"] <= 0]
        print(f"closed trades {len(tr)}, win rate {len(wins) / len(tr):.0%}, avg win "
              f"${mean(t['net'] for t in wins) if wins else 0:,.2f}, avg loss "
              f"${mean(t['net'] for t in losses) if losses else 0:,.2f}, avg days held "
              f"{mean(t['days'] for t in tr):.1f}, avg net/trade ${mean(t['net'] for t in tr):+.2f}, "
              f"avg gross/trade ${mean(t['gross'] for t in tr):+.2f}")
        print("exits:", dict(Counter(t["reason"] for t in tr)))
        worst = sorted(tr, key=lambda t: t["net"])[:3]
        best = sorted(tr, key=lambda t: -t["net"])[:3]
        print("best:", ", ".join(f"{t['symbol']} {t['entry_date']} ${t['net']:+,.0f}" for t in best),
              "| worst:", ", ".join(f"{t['symbol']} {t['entry_date']} ${t['net']:+,.0f}" for t in worst))
        by_year = defaultdict(float)
        for t in tr:
            by_year[t["exit_date"][:4]] += t["net"]
        print("net by year:", ", ".join(f"{y} {v:+,.0f}" for y, v in sorted(by_year.items())))
    if res["open"]:
        print("still held at the end:", ", ".join(f"{s} since {h['date']}" for s, h in res["open"].items()))
    print("VERDICT:", verdict(res, stage, p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    ap.add_argument("--no-commission", action="store_true", help="context: $0 commission")
    a = ap.parse_args(argv)
    label = f"S&P 500 daily gap-and-go, stage {a.stage}" + (" ($0 commission)" if a.no_commission else "")
    res = run(a.start, a.end, commission=not a.no_commission)
    report(res, label, a.stage)
    with open(os.path.join(ROOT, "reports", f"backtest_trades_dg_stage{a.stage}.jsonl"), "w") as f:
        for t in res["trades"]:
            f.write(json.dumps(t) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Backtest the silver "gap and go" strategy (bots/silver_gap/RULES.md).

Every 5-minute bar of the universe is replayed in time order: open positions are checked
against their resting stops, new signals are read on bar closes and filled at the next
bar's open, and everything is sold at 15:50. Costs: a half-spread in the fill prices, plus
IBKR Pro Fixed commission (config/risk.yaml) on every order. I1 (the pre-market high) is not
tested: there are no pre-market bars.

Usage:
    python3 scripts/backtest_gap_go.py --start 2026-04-01 --end 2026-09-30 --tag sg_a
    python3 scripts/backtest_gap_go.py --universe mining --start 2026-04-01 --end 2026-09-30 --tag sg_c
Writes reports/backtest_trades<TAG>.jsonl.
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

from backtest_healthcare_momentum import bootstrap_lower  # noqa: E402
from config_loader import load_config  # noqa: E402
from data.historical_data import get_bars  # noqa: E402
from execution.costs import TransactionCostModel  # noqa: E402
from strategy import gap_go as gg  # noqa: E402

CHAIN = ["D2", "D3", "price", "D1", "I2", "I3"]       # the order of the funnel in the report


def load_daily(symbol: str):
    path = os.path.join(ROOT, "data_cache", "daily", f"{symbol}.json")
    if not os.path.exists(path):
        return None
    rows = [r for r in json.load(open(path)) if date.fromisoformat(r[0]).weekday() < 5]
    return [(r[0], r[2], r[4]) for r in rows]                 # date, high, close


def universe_symbols(kind: str):
    if kind == "healthcare":
        return sorted(load_config(os.path.join(ROOT, "bots", "healthcare", "config")).auto_tradeable_universe())
    cfg = load_config()
    if kind == "silver":
        return sorted(t for t, v in cfg.tickers.items() if v.sector == "silver_miner" and v.strategy == "mining")
    return sorted(cfg.auto_tradeable_universe())


def load_series(symbols, p: gg.Params):
    data = {}
    for s in symbols:
        daily = load_daily(s)
        if daily is None:
            print(f"  {s}: no daily history, skipped")
            continue
        data[s] = gg.Series(s, get_bars(s), daily, p)
    return data


def simulate(data, days, p: gg.Params = gg.Params(), costs: TransactionCostModel = TransactionCostModel()):
    """Replay `days` (ISO dates) over `data` (symbol -> gg.Series). Returns a result dict."""
    equity = p.account_size
    trades, daily_net, skips = [], {}, Counter()
    funnel = Counter()                  # stock-days reaching each stage of CHAIN
    open_pos = {}
    for day in days:
        day_start_equity = equity
        purchases = 0.0
        day_net = 0.0
        pending = []                    # (ticker, shares, atr, rvol, signal_close) filled at the next open
        entered = set()
        ctx = {s: c for s in data if (c := data[s].context(day)) is not None}
        depth = {s: 0 for s in ctx}

        def close(pos, t, price, reason):
            nonlocal equity, day_net
            gross = (price - pos.entry) * pos.shares
            comm = costs.commission(pos.entry, pos.shares) + costs.commission(price, pos.shares, sell=True)
            net = gross - comm
            equity += net
            day_net += net
            trades.append(dict(
                ticker=pos.ticker, date=day, entry_time=pos.entry_time, entry_price=pos.entry,
                shares=pos.shares, initial_stop=pos.initial_stop, exit_time=f"{day}T{t}",
                exit_price=price, exit_reason=reason, gross_profit=gross, broker_commission=comm,
                net_profit=net, rvol=pos.rvol, r_return=gross / (pos.risk_per_share * pos.shares)))
            del open_pos[pos.ticker]

        for t in gg.TIMES:
            # 1. fills of last bar's signals, at this bar's open
            for ticker, shares, atr14, rv, _ in pending:
                i = data[ticker].index.get((day, t))
                if i is None:
                    skips["no_next_bar"] += 1
                    continue
                fill = data[ticker].bars[i].open + p.half_spread
                purchases += fill * shares
                open_pos[ticker] = gg.Position(ticker, f"{day}T{t}", fill, shares, atr14, rv, p)
            pending = []

            # 2. resting stops, trailing updates, the 15:50 exit
            for ticker in list(open_pos):
                pos = open_pos[ticker]
                i = data[ticker].index.get((day, t))
                if i is None:
                    continue
                bar = data[ticker].bars[i]
                fill = pos.stop_fill(bar.open, bar.low)
                if fill is not None:
                    close(pos, t, fill, "TRAILING_STOP" if pos.trailing else "STOP_HIT")
                    continue
                pos.after_bar(bar.high)
                if t == p.flat_bar:
                    close(pos, t, bar.close - p.half_spread, "END_OF_DAY")

            # 3. signals on this bar's close
            if not (p.first_signal_bar <= t <= p.last_signal_bar):
                continue
            candidates = []
            for ticker, c in ctx.items():
                s = data[ticker]
                i = s.index.get((day, t))
                if i is None:
                    continue
                close_px = s.bars[i].close
                rv = s.rvol(day, t, p.rvol_days)
                cond = gg.entry_conditions(close_px, c, s.high_before(day, t), rv, p)
                d = 0
                for name in CHAIN:
                    if not cond[name]:
                        break
                    d += 1
                depth[ticker] = max(depth[ticker], d)
                if not gg.signal(cond):
                    continue
                if ticker in open_pos or ticker in entered:
                    continue
                if s.atr[i] is None:
                    skips["no_atr"] += 1
                    continue
                candidates.append((-rv, ticker, i, close_px))
            for neg_rv, ticker, i, close_px in sorted(candidates):
                shares = gg.shares_for(close_px, p)
                if shares < 1:
                    skips["under_one_share"] += 1
                    continue
                if len(open_pos) + len(pending) >= p.max_positions:
                    skips["cap_2_positions"] += 1
                    continue
                cost = shares * close_px
                queued = sum(sh * px for _, sh, _, _, px in pending)
                held = sum(x.entry * x.shares for x in open_pos.values()) + queued
                if purchases + queued + cost > day_start_equity or held + cost > equity:
                    skips["settled_cash"] += 1
                    continue
                pending.append((ticker, shares, data[ticker].atr[i], -neg_rv, close_px))
                entered.add(ticker)
        # A stock with no 15:45 bar (no trades in that interval, or an early close) is sold at its last bar.
        for ticker in list(open_pos):
            last = data[ticker].days[day][-1]
            skips["sold_at_last_bar"] += 1
            close(open_pos[ticker], last.timestamp.strftime("%H:%M"), last.close - p.half_spread, "END_OF_DAY")
        daily_net[day] = day_net
        funnel["stock_days"] += len(ctx)
        for ticker, d in depth.items():
            for k in range(1, d + 1):
                funnel[CHAIN[k - 1]] += 1
        funnel["taken"] += sum(1 for tr in trades if tr["date"] == day)
    return dict(trades=trades, days=list(days), daily=[daily_net[d] for d in days], funnel=funnel,
                skips=skips, equity=equity)


def buy_and_hold(data, days, symbol):
    s = data.get(symbol)
    if s is None or days[0] not in s.days or days[-1] not in s.days:
        return None
    return s.days[days[-1]][-1].close / s.days[days[0]][0].open - 1


def report(res, label, universe, bench=None):
    tr, daily, days = res["trades"], res["daily"], res["days"]
    n = len(tr)
    gross = sum(t["gross_profit"] for t in tr)
    comm = sum(t["broker_commission"] for t in tr)
    net = gross - comm
    peak = dd = run = 0.0
    for d in daily:
        run += d
        peak = max(peak, run)
        dd = min(dd, run - peak)
    print(f"\n=== {label}: {len(days)} sessions {days[0]}..{days[-1]}, {len(universe)} stocks ===")
    f = res["funnel"]
    print("funnel (stock-days): " + ", ".join(
        [f"all {f['stock_days']}"] + [f"{c} {f[c]}" for c in CHAIN] + [f"taken {f['taken']}"]))
    print(f"trades {n}", end="")
    if n:
        wins = [t for t in tr if t["net_profit"] > 0]
        loss = [t for t in tr if t["net_profit"] <= 0]
        print(f", win rate {len(wins) / n:.0%}, avg win ${mean(t['net_profit'] for t in wins) if wins else 0:,.2f}, "
              f"avg loss ${mean(t['net_profit'] for t in loss) if loss else 0:,.2f}, "
              f"avg R before commission {mean(t['r_return'] for t in tr):+.2f}")
    else:
        print()
    print(f"gross (spread included) ${gross:,.2f}   commission ${comm:,.2f}   NET ${net:,.2f}"
          f"   (${net / len(days):+.2f}/session)   largest drawdown ${dd:,.2f}   ending equity ${res['equity']:,.2f}")
    if n:
        print("exits:", dict(Counter(t["exit_reason"] for t in tr)))
        by_stock, by_month = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
        for t in tr:
            by_stock[t["ticker"]][0] += 1
            by_stock[t["ticker"]][1] += t["net_profit"]
            by_month[t["date"][:7]][0] += 1
            by_month[t["date"][:7]][1] += t["net_profit"]
        print("by stock:", ", ".join(f"{k} {v[0]} trades {v[1]:+,.2f}" for k, v in sorted(by_stock.items())))
        print("by month:", ", ".join(f"{k} {v[0]} trades {v[1]:+,.2f}" for k, v in sorted(by_month.items())))
        best = sorted(tr, key=lambda t: -t["net_profit"])
        print("best:", ", ".join(f"{t['ticker']} {t['date']} ${t['net_profit']:+,.2f}" for t in best[:3]),
              "| worst:", ", ".join(f"{t['ticker']} {t['date']} ${t['net_profit']:+,.2f}" for t in best[-3:]))
    lb = bootstrap_lower(daily) if len(days) > 5 else float("nan")
    print(f"90% bootstrap lower bound, net per session: ${lb:+.2f}")
    if bench:
        print("buy and hold same dates:", ", ".join(f"{k} {v:+.1%}" for k, v in bench.items() if v is not None))
    verdict = "INCONCLUSIVE (fewer than 30 trades)" if n < 30 else (
        "PASS" if net > 0 and lb > 0 else "FAIL")
    print("VERDICT:", verdict)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--universe", choices=("silver", "mining", "healthcare"), default="silver")
    a = ap.parse_args(argv)
    p = gg.Params()
    symbols = universe_symbols(a.universe)
    print(f"Loading {len(symbols)} stocks: {' '.join(symbols)}", flush=True)
    data = load_series(symbols, p)
    bench_sym = "XLV" if a.universe == "healthcare" else "SIL"
    sil = load_series([bench_sym], p).get(bench_sym) if bench_sym not in data else data[bench_sym]
    days = sorted({d for s in data.values() for d in s.days if a.start <= d <= a.end})
    costs = TransactionCostModel.from_config(load_config().risk)         # IBKR Pro Fixed
    res = simulate(data, days, p, costs)
    with open(os.path.join(ROOT, "reports", f"backtest_trades{a.tag}.jsonl"), "w") as f:
        for tr in res["trades"]:
            f.write(json.dumps(tr) + "\n")
    bench = {}
    if sil is not None and days[0] in sil.days and days[-1] in sil.days:
        bench[bench_sym] = sil.days[days[-1]][-1].close / sil.days[days[0]][0].open - 1
    report(res, f"silver gap and go ({a.universe})", list(data), bench)
    return 0


if __name__ == "__main__":
    sys.exit(main())

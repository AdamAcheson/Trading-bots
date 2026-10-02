#!/usr/bin/env python3
"""Backtest the healthcare momentum bot (bots/healthcare/MOMENTUM_RULES.md).

Every 5-minute bar of the 60 stocks and XLV is replayed in time order: open positions
are checked against their resting stops, new signals are read on bar closes and filled
at the next bar's open, and everything is sold at 15:50. Costs: the one-cent spread in
the fill prices, plus IBKR Pro Fixed commission (config/risk.yaml) on every order.

Usage:
    python3 scripts/backtest_healthcare_momentum.py --start 2025-04-29 --end 2026-03-31 --tag hcm_s1
Writes reports/backtest_trades<TAG>.jsonl (readable by scripts/compare_runs.py).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict
from statistics import mean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from config_loader import load_config  # noqa: E402
from data.historical_data import get_bars, group_bars_by_day  # noqa: E402
from execution.costs import TransactionCostModel  # noqa: E402
from strategy import healthcare_momentum as hm  # noqa: E402

HC_CONFIG = os.path.join(ROOT, "bots", "healthcare", "config")
BENCH = "XLV"


class Series:
    """One symbol's bars and indicators, indexed by (day, 'HH:MM')."""

    def __init__(self, symbol: str):
        bars = get_bars(symbol)
        self.bars = bars
        closes = [b.close for b in bars]
        self.ema9 = hm.ema(closes, 9)
        self.ema20 = hm.ema(closes, 20)
        self.rsi = hm.rsi(closes, 14)
        self.macd, self.signal, self.hist = hm.macd(closes)
        self.atr = hm.atr([b.high for b in bars], [b.low for b in bars], closes, 14)
        self.index = {}
        self.days = group_bars_by_day(bars)
        for i, b in enumerate(bars):
            self.index[(b.timestamp.strftime("%Y-%m-%d"), b.timestamp.strftime("%H:%M"))] = i
        days = sorted(self.days)
        totals = {d: sum(b.volume for b in self.days[d]) for d in days}
        slots = {d: {b.timestamp.strftime("%H:%M"): b.volume for b in self.days[d]} for d in days}
        self.avg_volume_20d, self.slot_avg, self.gap_pct, self.vwap = {}, {}, {}, {}
        for k, d in enumerate(days):
            prior = days[max(0, k - 20):k]
            if len(prior) == 20:
                self.avg_volume_20d[d] = mean(totals[x] for x in prior)
                acc = defaultdict(list)
                for x in prior:
                    for t, v in slots[x].items():
                        acc[t].append(v)
                self.slot_avg[d] = {t: mean(v) for t, v in acc.items()}
            if k:
                prev_close = self.days[days[k - 1]][-1].close
                self.gap_pct[d] = (self.days[d][0].open - prev_close) / prev_close * 100
            pv = vol = 0.0
            for b in self.days[d]:
                pv += (b.high + b.low + b.close) / 3 * b.volume
                vol += b.volume
                self.vwap[(d, b.timestamp.strftime("%H:%M"))] = pv / vol if vol else None

    def reading(self, i: int, day: str, t: str) -> hm.Reading:
        return hm.Reading(
            price=self.bars[i].close, ema9=self.ema9[i], ema20=self.ema20[i],
            ema20_prev=self.ema20[i - 1] if i else self.ema20[i], rsi14=self.rsi[i],
            macd=self.macd[i], macd_signal=self.signal[i], macd_hist=self.hist[i],
            atr14=self.atr[i], bar_volume=self.bars[i].volume,
            slot_avg_volume=self.slot_avg.get(day, {}).get(t))


def bootstrap_lower(daily, block=5, n=5000, seed=7, q=0.05):
    rng = random.Random(seed)
    k = len(daily)
    means = []
    for _ in range(n):
        s = []
        while len(s) < k:
            i = rng.randrange(k)
            s.extend(daily[i:i + block])
        means.append(sum(s[:k]) / k)
    means.sort()
    return means[int(q * n)]


def run(start: str, end: str, tag: str, p: hm.Params = hm.Params()) -> dict:
    config = load_config(HC_CONFIG)
    costs = TransactionCostModel.from_config(load_config().risk)     # IBKR Pro Fixed
    universe = sorted(config.auto_tradeable_universe())
    print(f"Loading {len(universe)} stocks + {BENCH} ...", flush=True)
    data = {s: Series(s) for s in universe + [BENCH]}
    xlv = data[BENCH]
    days = [d for d in sorted(xlv.days) if start <= d <= end]
    times = [f"{h:02d}:{m:02d}" for h in range(9, 16) for m in range(0, 60, 5)
             if (9, 30) <= (h, m) <= (15, 55)]

    equity = p.account_size
    trades, daily_net, skips = [], {}, Counter()
    open_pos = {}
    for day in days:
        day_start_equity = equity
        purchases = 0.0
        pending = []           # (ticker, shares, atr, score) to fill at the next bar's open
        day_net = 0.0

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
                exit_price=price, exit_reason=reason, gross_profit=gross,
                broker_commission=comm, net_profit=net, score=pos.score,
                r_return=gross / (pos.risk_per_share * pos.shares)))
            del open_pos[pos.ticker]

        for t in times:
            # 1. fills of last bar's signals, at this bar's open
            for ticker, shares, atr14, sc in pending:
                i = data[ticker].index.get((day, t))
                if i is None:
                    skips["no_next_bar"] += 1
                    continue
                fill = data[ticker].bars[i].open + p.half_spread
                purchases += fill * shares
                open_pos[ticker] = hm.Position(ticker, f"{day}T{t}", fill, shares, atr14, sc, p)
            pending = []

            # 2. stops (resting at the broker), trailing updates, 15:50 exit
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
            j = xlv.index.get((day, t))
            xlv_ok = j is not None and hm.xlv_is_bullish(
                xlv.bars[j].close, xlv.ema9[j], xlv.ema20[j], xlv.ema20[j - 1], xlv.vwap.get((day, t)))
            candidates = []
            for ticker in universe:
                if ticker in open_pos:
                    continue
                s = data[ticker]
                i = s.index.get((day, t))
                if i is None or i == 0:
                    continue
                if day not in s.avg_volume_20d:
                    skips["warmup"] += 1
                    continue
                r = s.reading(i, day, t)
                if r.price <= p.min_price or s.avg_volume_20d[day] <= p.min_avg_volume_20d:
                    skips["price_or_volume_gate"] += 1
                    continue
                if abs(s.gap_pct.get(day, 0.0)) >= p.skip_gap_pct:
                    skips["gap_day"] += 1
                    continue
                if r.atr14 is None:
                    continue
                sc = hm.score(r, xlv_ok, p)
                if sc["total"] < p.min_score:
                    skips["score_below_75"] += 1
                    continue
                ratio = r.bar_volume / r.slot_avg_volume if r.slot_avg_volume else 0.0
                candidates.append((sc["total"], ratio, ticker, r))
            candidates.sort(key=lambda c: (-c[0], -c[1], c[2]))
            for sc, _, ticker, r in candidates:
                shares = hm.position_size(r.price, r.atr14, p)
                if shares < 1:
                    skips["under_one_share"] += 1
                    continue
                risk = shares * p.stop_atr * r.atr14
                open_risk = sum(x.open_risk for x in open_pos.values()) + sum(
                    sh * p.stop_atr * a for _, sh, a, _ in pending)
                if len(open_pos) + len(pending) >= p.max_open_positions:
                    skips["cap_3_positions"] += 1
                    continue
                if open_risk + risk > p.max_total_open_risk:
                    skips["cap_75_risk"] += 1
                    continue
                cost = shares * r.price
                queued = sum(sh * data[tk].bars[data[tk].index[(day, t)]].close for tk, sh, _, _ in pending)
                held = sum(x.entry * x.shares for x in open_pos.values()) + queued
                if purchases + queued + cost > day_start_equity or held + cost > equity:
                    skips["settled_cash"] += 1
                    continue
                pending.append((ticker, shares, r.atr14, sc))
        # A stock with no 15:45 bar (no trades in that interval) is sold at its last bar.
        for ticker in list(open_pos):
            last = data[ticker].days[day][-1]
            skips["sold_at_last_bar"] += 1
            close(open_pos[ticker], last.timestamp.strftime("%H:%M"), last.close - p.half_spread, "END_OF_DAY")
        daily_net[day] = day_net

    path = os.path.join(ROOT, "reports", f"backtest_trades{tag}.jsonl")
    with open(path, "w") as f:
        for tr in trades:
            f.write(json.dumps(tr) + "\n")
    return dict(trades=trades, daily=[daily_net[d] for d in days], days=days, skips=skips,
                equity=equity, xlv=(xlv.days[days[0]][0].open, xlv.days[days[-1]][-1].close))


def report(res: dict, p: hm.Params = hm.Params()) -> None:
    tr, daily, days = res["trades"], res["daily"], res["days"]
    n = len(tr)
    gross = sum(t["gross_profit"] for t in tr)
    comm = sum(t["broker_commission"] for t in tr)
    net = gross - comm
    peak = dd = run_eq = 0.0
    for d in daily:
        run_eq += d
        peak = max(peak, run_eq)
        dd = min(dd, run_eq - peak)
    print(f"\n{len(days)} sessions {days[0]}..{days[-1]}")
    print(f"trades {n}, win rate {sum(t['net_profit'] > 0 for t in tr) / max(n, 1):.1%}, "
          f"avg R before commission {mean(t['r_return'] for t in tr) if tr else 0:+.3f}")
    print(f"gross (spread included) ${gross:,.2f}   commission ${comm:,.2f}   NET ${net:,.2f}   "
          f"(${net / len(days):+.2f}/session)")
    if tr:
        print(f"avg position ${mean(t['entry_price'] * t['shares'] for t in tr):,.0f}, "
              f"avg risk ${mean((t['entry_price'] - t['initial_stop']) * t['shares'] for t in tr):,.2f}, "
              f"avg commission/trade ${comm / n:.2f}")
        print("exits:", dict(Counter(t["exit_reason"] for t in tr)))
    print(f"largest drawdown ${dd:,.2f}; ending equity ${res['equity']:,.2f}")
    print(f"90% bootstrap lower bound, net per session: ${bootstrap_lower(daily):+.2f}")
    a, b = res["xlv"]
    print(f"XLV buy and hold same months: {(b / a - 1) * 100:+.1f}% "
          f"(${p.account_size * (b / a - 1):+,.0f} on ${p.account_size:,.0f})")
    print("not taken:", dict(res["skips"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--tag", required=True)
    a = ap.parse_args(argv)
    report(run(a.start, a.end, a.tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())

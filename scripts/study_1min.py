#!/usr/bin/env python3
"""1-minute study, step 1 (pre-registered; see docs/BACKTEST_RESULTS.md).

A. Exit realism. The backtest checks stops and targets only against 5-minute CLOSES and books
   exits at the stop/target LEVEL. The live bot checks every ~30 s and sells at the bid. Each
   trade's exit is re-simulated with the project's own PositionManager.manage(), from the
   backtest's own entry, three ways (gross, no costs):
     V0  5-minute closes, exit at the level  (reproduces the backtest)
     V1  5-minute closes, exit at that close (the honest version of what was tested)
     V2  1-minute closes, exit at that close (approximately what runs live)
B. Entry timing. An upper bound on entering at the first 1-minute close above VWAP inside the
   signal's 5-minute bar, instead of at that bar's close.

Trades held overnight are excluded (re-simulating them needs the overnight review).

Usage:
    python3 scripts/study_1min.py MIN1_DIR reports/backtest_tradessettled_h.jsonl [...]
"""

from __future__ import annotations

import csv
import json
import os
import statistics as st
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from config_loader import load_config  # noqa: E402
from data.historical_data import get_bars, group_bars_by_day  # noqa: E402
from data.indicators import atr, vwap_series  # noqa: E402
from models.bar import Bar  # noqa: E402
from positions.position_manager import PositionManager  # noqa: E402

ET = ZoneInfo("America/New_York")
FIVE = timedelta(minutes=5)
ONE = timedelta(minutes=1)
# The overnight review exits at the price available at 15:55: the backtest evaluates the
# 5-minute bar labelled 15:50 using its close (15:55); the matching 1-minute close is the bar
# labelled 15:54.
REVIEW_5 = (15, 50)
REVIEW_1 = (15, 54)


def load_1min(min1_dir, symbol):
    path = os.path.join(min1_dir, f"{symbol}.csv")
    by_day = {}
    if not os.path.exists(path):
        return by_day
    seen = set()
    for row in csv.DictReader(open(path)):
        ts = datetime.fromisoformat(row["timestamp"]).replace(tzinfo=ET)
        if ts in seen:
            continue
        seen.add(ts)
        by_day.setdefault(ts.strftime("%Y-%m-%d"), []).append(
            Bar(timestamp=ts, open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]), volume=float(row["volume"] or 0)))
    for d in by_day.values():
        d.sort(key=lambda b: b.timestamp)
    return by_day


def simulate(trade, steps, tm, book_at_close, review, resting=False):
    """steps: list of (time, price, atr[, bar]). Returns gross P&L of the re-simulated trade.

    resting=True models orders held AT THE BROKER: a stop order that sells when the bar's
    low touches the stop (at the stop, or at the bar's open if it gapped through), and a
    limit order at the target that sells when the high reaches it. The stop is checked first,
    the conservative assumption when one bar touches both. The breakeven, trailing and partial
    rules still update on each close, as the bot does."""
    pm = PositionManager(max_concurrent_positions=10)
    entry_time = datetime.fromisoformat(trade["entry_time"])
    pos = pm.open_position(trade["ticker"], "", entry_time, trade["entry_price"], trade["shares"],
                           trade["initial_stop"], trade["initial_target"], "VWAP_RECLAIM", 0.0)
    exit_price = None
    for step in steps:
        t, price, a = step[0], step[1], step[2]
        if (t.hour, t.minute) >= review:
            exit_price = price                     # the 15:50 overnight review exits
            break
        if resting:
            bar = step[3]
            if bar.low <= pos.current_stop:
                exit_price = min(pos.current_stop, bar.open)
                break
            if bar.high >= pos.current_target:
                exit_price = max(pos.current_target, bar.open)
                break
        act = pm.manage(trade["ticker"], current_price=price, current_time=t,
                        breakeven_trigger_r=tm["breakeven_trigger_r"],
                        partial_exit_enabled=tm["partial_exit"]["enabled"],
                        partial_exit_trigger_r=tm["partial_exit"]["trigger_r"],
                        partial_exit_sell_fraction=tm["partial_exit"]["sell_fraction"],
                        trailing_enabled=tm["trailing_stop"]["enabled"],
                        trailing_atr_multiplier=tm["trailing_stop"]["atr_multiplier"],
                        trailing_activate_r=tm["trailing_stop"]["activate_at_r"], atr=a)
        if act.should_exit:
            exit_price = price if book_at_close else act.exit_price
            break
    if exit_price is None:
        exit_price = steps[-1][1] if steps else trade["entry_price"]
    e = trade["entry_price"]
    gross = sum((p.price - e) * p.shares for p in pos.partial_exits)
    return gross + (exit_price - e) * pos.shares


def run(min1_dir, journal, tm):
    trades = [json.loads(l) for l in open(journal)]
    intraday = [t for t in trades if t["exit_time"][:10] == t["date"]]
    five = {}
    one = {}
    res = {"V0": [], "V1": [], "V2": [], "V3": [], "V4": [], "cost": [], "tiered": [], "journal": [], "R": [], "dEntryR": [], "earlier": 0,
           "skipped": 0, "close_mismatch": []}
    for t in intraday:
        sym, day = t["ticker"], t["date"]
        if sym not in five:
            five[sym] = group_bars_by_day(get_bars(sym))
            one[sym] = load_1min(min1_dir, sym)
        bars5 = five[sym].get(day, [])
        bars1 = one[sym].get(day, [])
        entry_ts = datetime.fromisoformat(t["entry_time"]).astimezone(ET)
        if len(bars1) < 300 or not bars5:
            res["skipped"] += 1
            continue
        # 5-minute steps: bars after the signal bar, ATR over the session so far
        steps5 = []
        for i, b in enumerate(bars5):
            if b.timestamp > entry_ts:
                steps5.append((b.timestamp, b.close, atr(bars5[:i + 1], 14), b))
        # 1-minute steps: from the signal bar's close; ATR of the 5-minute bars closed by then
        steps1 = []
        for m in bars1:
            if m.timestamp < entry_ts + FIVE:
                continue
            now = m.timestamp + ONE
            closed = [b for b in bars5 if b.timestamp + FIVE <= now]
            steps1.append((m.timestamp, m.close, atr(closed, 14), m))
        risk = t["entry_price"] - t["initial_stop"]
        if risk <= 0:
            res["skipped"] += 1
            continue
        res["V0"].append(simulate(t, steps5, tm, book_at_close=False, review=REVIEW_5))
        res["V1"].append(simulate(t, steps5, tm, book_at_close=True, review=REVIEW_5))
        res["V2"].append(simulate(t, steps1, tm, book_at_close=True, review=REVIEW_1))
        res["V3"].append(simulate(t, steps5, tm, book_at_close=True, review=REVIEW_5, resting=True))
        res["V4"].append(simulate(t, steps1, tm, book_at_close=True, review=REVIEW_1, resting=True))
        res["journal"].append(t["gross_profit"])
        res["cost"].append(t["gross_profit"] - t["net_profit"])
        sh, px = t["shares"], t["entry_price"]
        order = min(max(0.35, 0.0035 * sh), 0.01 * sh * px) + sh * 0.0032   # Pro Tiered, approx.
        res["tiered"].append(order * 2 + 0.000166 * sh)
        res["R"].append(risk * t["shares"])
        # B: first 1-minute close above VWAP inside the signal bar
        sig5 = next((b for b in bars5 if b.timestamp == entry_ts), None)
        inside = [m for m in bars1 if entry_ts <= m.timestamp < entry_ts + FIVE]
        vw = vwap_series([m for m in bars1 if m.timestamp < entry_ts + FIVE])
        vw_inside = vw[-len(inside):] if inside else []
        d = 0.0
        if sig5 and inside:
            res["close_mismatch"].append(abs(inside[-1].close - sig5.close) / sig5.close * 100)
            half = t["entry_price"] - sig5.close
            first = next((m for m, v in zip(inside, vw_inside) if v and m.close > v), None)
            if first is not None and first.timestamp < inside[-1].timestamp:
                alt = first.close + half
                d = (t["entry_price"] - alt) / risk
                res["earlier"] += 1
        res["dEntryR"].append(d)
    return trades, intraday, res


def report(name, trades, intraday, r):
    n = len(r["V0"])
    tot = {k: sum(r[k]) for k in ("V0", "V1", "V2", "V3", "V4", "journal")}
    print(f"\n== {name}: {len(trades)} trades, {len(intraday)} intraday, {n} simulated, "
          f"{r['skipped']} skipped (no 1-minute data) ==")
    print(f"  journal gross ${tot['journal']:,.2f}   V0 (reproduction) ${tot['V0']:,.2f}")
    for k in ("V1", "V2", "V3", "V4"):
        diff = tot[k] - tot["V0"]
        pct = diff / abs(tot["V0"]) * 100 if tot["V0"] else float("nan")
        per_trade = st.mean([(a - b) / rr for a, b, rr in zip(r[k], r["V0"], r["R"])])
        print(f"  {k} ${tot[k]:,.2f}  vs V0 {diff:+,.2f} ({pct:+.1f}%), {per_trade:+.3f} R/trade")
    c, ti = sum(r["cost"]), sum(r["tiered"])
    print(f"  net of modelled spread cost ${c:,.0f} / also of Pro Tiered commission ${ti:,.0f}:")
    for k in ("V0", "V1", "V2", "V3", "V4"):
        print(f"    {k}: ${tot[k] - c:,.0f} / ${tot[k] - c - ti:,.0f}")
    print(f"  B: earlier 1-minute entry available in {r['earlier']}/{n} trades; "
          f"mean change {st.mean(r['dEntryR']):+.3f} R/trade (upper bound)")
    if r["close_mismatch"]:
        print(f"  data check: |1-min last close - 5-min close| median {st.median(r['close_mismatch']):.3f}%")
    return tot


def main(argv):
    min1_dir, journals = argv[0], argv[1:]
    tm = load_config().strategy["trade_management"]
    for j in journals:
        trades, intraday, r = run(min1_dir, j, tm)
        report(os.path.basename(j), trades, intraday, r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

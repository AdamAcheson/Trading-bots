#!/usr/bin/env python3
"""Fetch 1-minute bars from Twelve Data for the symbol-days a set of backtest trade journals
traded on -- step 1 of the 1-minute study (see docs/BACKTEST_RESULTS.md).

Only the days needed, grouped into requests of up to 16 calendar days (5000 bars, the API's
page size, holds ~12 sessions of 390 one-minute bars). The free tier allows 8 requests a minute
and 800 a day; this paces at 8 s per request, skips windows already on disk, and stops cleanly
when credits run out. Re-run after the daily reset (00:00 UTC) and it picks up where it stopped.

Output: <out>/<SYMBOL>.csv (timestamp,open,high,low,close,volume), ET timestamps. Kept out of
the repository (about 1 GB for everything; this subset is smaller but still large).

Usage:
    python3 scripts/fetch_1min_for_trades.py OUT_DIR reports/backtest_tradessettled_h.jsonl ...
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import requests

WINDOW_DAYS = 16
PAUSE = 8.0


def needed_windows(journals):
    days = {}
    for path in journals:
        for line in open(path):
            t = json.loads(line)
            days.setdefault(t["ticker"], set()).add(date.fromisoformat(t["date"]))
    windows = []
    for sym, ds in sorted(days.items()):
        ds = sorted(ds)
        start = prev = ds[0]
        for d in ds[1:]:
            if (d - start).days > WINDOW_DAYS:
                windows.append((sym, start, prev))
                start = d
            prev = d
        windows.append((sym, start, prev))
    return windows


def fetch(sym, start, end, key):
    r = requests.get("https://api.twelvedata.com/time_series", timeout=60, params=dict(
        symbol=sym, interval="1min", start_date=f"{start} 09:30:00", end_date=f"{end} 16:00:00",
        outputsize=5000, timezone="America/New_York", order="ASC", apikey=key))
    j = r.json()
    if j.get("status") != "ok":
        return None, j.get("message", str(j))[:200]
    return j.get("values") or [], None


def main(argv) -> int:
    out, journals = argv[0], argv[1:]
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        print("TWELVEDATA_API_KEY is not set")
        return 2
    os.makedirs(out, exist_ok=True)
    done_path = os.path.join(out, "_done.txt")
    done = set(open(done_path).read().split()) if os.path.exists(done_path) else set()
    windows = needed_windows(journals)
    todo = [w for w in windows if f"{w[0]}:{w[1]}:{w[2]}" not in done]
    print(f"{len(windows)} windows, {len(todo)} still to fetch")
    for i, (sym, start, end) in enumerate(todo, 1):
        values, err = fetch(sym, start, end, key)
        if err:
            if "credits" in err.lower() or "limit" in err.lower():
                print(f"STOPPING at {i-1}/{len(todo)}: {err}")
                return 3
            print(f"  {sym} {start}..{end}: {err} (skipped)")
        else:
            path = os.path.join(out, f"{sym}.csv")
            new = not os.path.exists(path)
            with open(path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for v in values:
                    ts = datetime.fromisoformat(v["datetime"]).strftime("%Y-%m-%dT%H:%M:00")
                    w.writerow([ts, v["open"], v["high"], v["low"], v["close"], v.get("volume", 0)])
            with open(done_path, "a") as f:
                f.write(f"{sym}:{start}:{end}\n")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} windows", flush=True)
        time.sleep(PAUSE)
    print("all windows fetched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

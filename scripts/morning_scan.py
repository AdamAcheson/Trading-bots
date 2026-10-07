#!/usr/bin/env python3
"""Morning alerts for the watchlist in config/watchlist.txt (see src/alerts.py).

Fetches recent daily bars from Twelve Data (one credit per stock, paced for the free tier's
8 credits a minute; standard library only, nothing to install), checks the latest completed
session for a move of 4% or more, volume at least 2x normal, or a new 52-week high or low, and
prints a short summary. A scheduled routine runs it each weekday morning and sends the summary
to the account holder.

Usage:
    python3 scripts/morning_scan.py [--watchlist config/watchlist.txt]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import alerts  # noqa: E402

ET = ZoneInfo("America/New_York")


def fetch(symbol: str, key: str):
    """Daily bars, oldest first, split-adjusted; today's bar is dropped before the 4 pm
    close so only completed sessions are judged."""
    query = urllib.parse.urlencode(dict(symbol=symbol, interval="1day", outputsize=300, order="ASC",
                                        adjust="splits", apikey=key))
    with urllib.request.urlopen(f"https://api.twelvedata.com/time_series?{query}", timeout=60) as response:
        j = json.load(response)
    if j.get("status") != "ok":
        raise RuntimeError(str(j.get("message", j))[:120])
    bars = [alerts.Bar(v["datetime"][:10], float(v["open"]), float(v["high"]), float(v["low"]),
                       float(v["close"]), float(v.get("volume") or 0)) for v in j["values"]]
    now = datetime.now(ET)
    if bars and bars[-1].date == now.date().isoformat() and now.hour < 16:
        bars = bars[:-1]
    return bars


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=os.path.join(ROOT, "config", "watchlist.txt"))
    a = ap.parse_args(argv)
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        print("TWELVEDATA_API_KEY is not set")
        return 2
    if not os.path.exists(a.watchlist):
        print(f"No watchlist at {a.watchlist}")
        return 2
    symbols = alerts.read_watchlist(open(a.watchlist).read())
    if not symbols:
        print("The watchlist is empty.")
        return 0
    found, failed, sessions = [], [], []
    for n, sym in enumerate(symbols):
        if n:
            time.sleep(8)
        try:
            bars = fetch(sym, key)
        except Exception as e:  # noqa: BLE001 -- report and carry on with the rest
            failed.append(f"{sym} ({e})")
            continue
        if bars:
            sessions.append(bars[-1].date)
        alert = alerts.check(sym, bars)
        if alert:
            found.append(alert)
    session = max(sessions) if sessions else None
    print(alerts.summary(found, len(symbols) - len(failed), failed, session))
    return 0


if __name__ == "__main__":
    sys.exit(main())

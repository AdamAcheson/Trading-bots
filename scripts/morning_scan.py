#!/usr/bin/env python3
"""Morning and live alerts for the watchlist in config/watchlist.txt (see src/alerts.py).

Fetches recent daily bars from Twelve Data (one credit per stock, paced for the free tier's
8 credits a minute; standard library only, nothing to install).

Default (morning scan): checks the latest completed session for a move of 4% or more, volume
at least 2x normal, or a new 52-week high or low, and prints a short summary.

--live (during the trading day): checks the current price against yesterday's close for a move
of 4% or more or a new 52-week high or low, and lists only stocks that were not already flagged
at the previous hourly reading. Volume is not judged live (the free feed carries a small share
of the real volume for the current session).

Scheduled routines run these on weekdays and send the summary to the account holder.

Usage:
    python3 scripts/morning_scan.py [--live] [--watchlist config/watchlist.txt]
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


_last_call = [0.0]


def get_json(path: str, key: str, **params):
    """One Twelve Data request, at least 8 seconds after the previous one (free-plan rate limit)."""
    wait = 8.0 - (time.monotonic() - _last_call[0])
    if _last_call[0] and wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()
    query = urllib.parse.urlencode(dict(params, apikey=key))
    with urllib.request.urlopen(f"https://api.twelvedata.com/{path}?{query}", timeout=60) as response:
        j = json.load(response)
    if j.get("status") == "error" or ("values" not in j and path == "time_series"):
        raise RuntimeError(str(j.get("message", j))[:120])
    return j


def fetch_daily(symbol: str, key: str):
    """Daily bars, oldest first, split-adjusted. During the trading day the last bar is
    today's in-progress one."""
    j = get_json("time_series", key, symbol=symbol, interval="1day", outputsize=300, order="ASC",
                 adjust="splits")
    return [alerts.Bar(v["datetime"][:10], float(v["open"]), float(v["high"]), float(v["low"]),
                       float(v["close"]), float(v.get("volume") or 0)) for v in j["values"]]


def fetch(symbol: str, key: str):
    """Morning scan: completed sessions only (today's bar is dropped before the 4 pm close)."""
    bars = fetch_daily(symbol, key)
    now = datetime.now(ET)
    if bars and bars[-1].date == now.date().isoformat() and now.hour < 16:
        bars = bars[:-1]
    return bars


def earlier_price(symbol: str, key: str, today: str):
    """The price at the previous hourly reading today (the close of today's second-latest
    hourly bar), or None if today has only one hourly bar so far."""
    j = get_json("time_series", key, symbol=symbol, interval="1h", outputsize=16, order="DESC",
                 adjust="splits")
    todays = [v for v in j["values"] if v["datetime"][:10] == today]
    return float(todays[1]["close"]) if len(todays) >= 2 else None


def live_scan(symbols, key) -> str:
    now = datetime.now(ET)
    today = now.date().isoformat()
    clock = f"{now:%I:%M %p}".lstrip("0")
    found, failed, scanned = [], [], 0
    for n, sym in enumerate(symbols):
        try:
            bars = fetch_daily(sym, key)
            if n == 0 and (not bars or bars[-1].date != today):
                return f"Live check ({clock} ET): the market is closed today."
            if len(bars) < 2 or bars[-1].date != today:
                continue
            scanned += 1
            price, prev, closes = bars[-1].close, bars[-2].close, [b.close for b in bars[:-1]]
            if alerts.check_live(sym, price, prev, closes) is None:
                continue
            alert = alerts.check_live(sym, price, prev, closes, earlier_price(sym, key, today))
            found.append(alert)
        except Exception as e:  # noqa: BLE001 -- report and carry on with the rest
            failed.append(f"{sym} ({e})")
    return alerts.live_summary(found, scanned, failed, clock)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=os.path.join(ROOT, "config", "watchlist.txt"))
    ap.add_argument("--live", action="store_true", help="check live prices during the trading day")
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
    if a.live:
        print(live_scan(symbols, key))
        return 0
    found, failed, sessions = [], [], []
    for sym in symbols:
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

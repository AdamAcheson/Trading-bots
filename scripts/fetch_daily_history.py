#!/usr/bin/env python3
"""Fetch up to 5,000 daily bars (about 20 years), split-adjusted, from Twelve Data into
data_cache/daily/<SYMBOL>.json, for the swing bot (bots/swing/RULES.md). One credit per
symbol; paced at 8 s for the free tier's 8 credits a minute; skips symbols already saved.

With --unadjusted, fetches the prices as actually traded (adjust=none) into
data_cache/daily_unadjusted/<SYMBOL>.json instead (bots/sp500_dip/RULES.md uses them for the
$15 minimum).

Usage: python3 scripts/fetch_daily_history.py [--unadjusted] SYMBOL [SYMBOL ...]
"""

import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data_cache", "daily")


def main(symbols) -> int:
    adjust, out = "splits", OUT
    if symbols and symbols[0] == "--unadjusted":
        symbols, adjust, out = symbols[1:], "none", os.path.join(ROOT, "data_cache", "daily_unadjusted")
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        print("TWELVEDATA_API_KEY is not set")
        return 2
    os.makedirs(out, exist_ok=True)
    failed = []
    for i, sym in enumerate(symbols):
        path = os.path.join(out, f"{sym}.json")
        if os.path.exists(path):
            continue
        j = requests.get("https://api.twelvedata.com/time_series", timeout=60, params=dict(
            symbol=sym, interval="1day", outputsize=5000, order="ASC", adjust=adjust,
            apikey=key)).json()
        if j.get("status") != "ok":
            print(f"  {sym}: {j.get('message', j)}"[:160], flush=True)
            failed.append(sym)
            if "credits" in str(j.get("message", "")).lower():
                break
        else:
            v = j["values"]
            with open(path, "w") as f:
                json.dump([[x["datetime"], float(x["open"]), float(x["high"]), float(x["low"]),
                            float(x["close"]), float(x.get("volume") or 0)] for x in v], f)
            print(f"  {sym}: {len(v)} days {v[0]['datetime']}..{v[-1]['datetime']}", flush=True)
        time.sleep(8)
    print(f"done, {len(failed)} failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Fetch each symbol's split history from Twelve Data into data_cache/splits/<SYMBOL>.json
(one credit per symbol; paced at 8 s for the free tier's 8 credits a minute; skips symbols
already saved; stops cleanly when the day's credits run out, so it can be re-run).

With split-adjusted daily bars, the price a stock actually traded at on a past date is the
adjusted price times the product of the split factors after that date
(bots/sp500_dip/RULES.md uses it for the $15 minimum).

Usage: python3 scripts/fetch_splits.py SYMBOL [SYMBOL ...]
"""
import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data_cache", "splits")


def main(symbols) -> int:
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        print("TWELVEDATA_API_KEY is not set")
        return 2
    os.makedirs(OUT, exist_ok=True)
    failed = []
    for sym in symbols:
        path = os.path.join(OUT, f"{sym}.json")
        if os.path.exists(path):
            continue
        j = requests.get("https://api.twelvedata.com/splits", timeout=60,
                         params=dict(symbol=sym, range="full", apikey=key)).json()
        if "splits" not in j:
            print(f"  {sym}: {j.get('message', j)}"[:160], flush=True)
            failed.append(sym)
            if "credits" in str(j.get("message", "")).lower():
                break
        else:
            splits = [dict(date=s["date"], from_factor=float(s["from_factor"]), to_factor=float(s["to_factor"]))
                      for s in j["splits"]]
            with open(path, "w") as f:
                json.dump(splits, f)
            print(f"  {sym}: {len(splits)} splits", flush=True)
        time.sleep(8)
    print(f"done, {len(failed)} failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Morning alerts: big moves, heavy volume and new 52-week highs or lows in a watchlist,
judged on the latest completed daily bar. Information for the account holder, not a
trading signal. Pure parts; fetching and sending are in scripts/morning_scan.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

BIG_MOVE = 0.04          # a close 4% or more from the previous close
VOLUME_MULTIPLE = 2.0    # volume at least 2x the average of the previous 50 sessions
VOLUME_DAYS = 50
YEAR = 252               # sessions in a year, for the 52-week high and low


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Alert:
    symbol: str
    date: str
    close: float
    change: float                      # close versus the previous close
    reasons: List[str]


def check(symbol: str, bars: Sequence[Bar]) -> Optional[Alert]:
    """The alert for the last bar in `bars` (oldest first), or None if nothing fired."""
    if len(bars) < 2:
        return None
    last, prev = bars[-1], bars[-2]
    if prev.close <= 0:
        return None
    change = last.close / prev.close - 1
    reasons = []
    if abs(change) >= BIG_MOVE:
        reasons.append(f"{'up' if change > 0 else 'down'} {abs(change):.1%}")
    history = bars[-1 - VOLUME_DAYS:-1]
    if len(history) == VOLUME_DAYS:
        avg = sum(b.volume for b in history) / VOLUME_DAYS
        if avg > 0 and last.volume >= VOLUME_MULTIPLE * avg:
            reasons.append(f"volume {last.volume / avg:.1f}x normal")
    year = bars[-1 - YEAR:-1]
    if len(year) == YEAR:
        if last.close > max(b.close for b in year):
            reasons.append("new 52-week high")
        elif last.close < min(b.close for b in year):
            reasons.append("new 52-week low")
    if not reasons:
        return None
    return Alert(symbol, last.date, last.close, change, reasons)


def read_watchlist(text: str) -> List[str]:
    """Tickers from a watchlist file: one or more per line, separated by spaces or
    commas; anything after # is a comment. Upper-cased, duplicates dropped, order kept."""
    out: List[str] = []
    for line in text.splitlines():
        for tok in line.split("#", 1)[0].replace(",", " ").split():
            t = tok.strip().upper()
            if t and t not in out:
                out.append(t)
    return out


def summary(alerts: Sequence[Alert], scanned: int, failed: Sequence[str], session: Optional[str]) -> str:
    """A short, phone-friendly message."""
    lines = []
    when = f" (close of {session})" if session else ""
    if alerts:
        lines.append(f"Morning alerts{when}: {len(alerts)} of {scanned} stocks flagged")
        for a in sorted(alerts, key=lambda a: -abs(a.change)):
            lines.append(f"- {a.symbol} ${a.close:,.2f} ({a.change:+.1%}): {', '.join(a.reasons)}")
    else:
        lines.append(f"Morning alerts{when}: nothing flagged in {scanned} stocks")
    if failed:
        lines.append(f"Could not fetch: {', '.join(failed)}")
    lines.append("Information only, not a recommendation.")
    return "\n".join(lines)


# ---- during the trading day -------------------------------------------------------------
# Volume is left out of the live check: the free data plan's feed for the current session
# carries only a small share of the market's real volume, so "2x normal" cannot be judged
# until the session is complete (the morning scan does it).

@dataclass
class LiveAlert:
    symbol: str
    price: float
    change: float                      # price versus the previous close
    reasons: List[str]
    new: bool                          # not already true at the earlier reading


def live_reasons(price: float, prev_close: float, closes: Sequence[float]) -> dict:
    """What is true at `price`: {kind: text} with kinds 'move', 'high', 'low'.
    `closes` are the previous sessions' closes (the last 252 are used)."""
    out = {}
    if prev_close > 0:
        change = price / prev_close - 1
        if abs(change) >= BIG_MOVE:
            out["move"] = f"{'up' if change > 0 else 'down'} {abs(change):.1%}"
    year = list(closes)[-YEAR:]
    if len(year) == YEAR:
        if price > max(year):
            out["high"] = "new 52-week high"
        elif price < min(year):
            out["low"] = "new 52-week low"
    return out


def check_live(symbol: str, price: float, prev_close: float, closes: Sequence[float],
               earlier_price: Optional[float] = None) -> Optional[LiveAlert]:
    """A live alert if a condition holds now. `earlier_price` is the reading from about an
    hour ago: a condition already true then is not new."""
    now = live_reasons(price, prev_close, closes)
    if not now:
        return None
    before = live_reasons(earlier_price, prev_close, closes) if earlier_price is not None else {}
    is_new = any(kind not in before for kind in now)
    change = price / prev_close - 1 if prev_close > 0 else 0.0
    return LiveAlert(symbol, price, change, list(now.values()), is_new)


def live_summary(alerts: Sequence[LiveAlert], scanned: int, failed: Sequence[str], clock: str) -> str:
    """Only the newly flagged stocks are listed in full; ones flagged earlier are named."""
    new = sorted((a for a in alerts if a.new), key=lambda a: -abs(a.change))
    old = [a.symbol for a in alerts if not a.new]
    lines = []
    if new:
        lines.append(f"Live alerts ({clock} ET): {len(new)} new of {scanned} stocks")
        for a in new:
            lines.append(f"- {a.symbol} ${a.price:,.2f} ({a.change:+.1%} today): {', '.join(a.reasons)}")
    else:
        lines.append(f"Live check ({clock} ET): nothing new in {scanned} stocks")
    if old:
        lines.append(f"Still flagged from earlier: {', '.join(old)}")
    if failed:
        lines.append(f"Could not fetch: {', '.join(failed)}")
    lines.append("Information only, not a recommendation. Volume is checked in the morning scan.")
    return "\n".join(lines)

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

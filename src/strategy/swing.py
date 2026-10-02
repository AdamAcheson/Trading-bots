"""Swing bot ("hold the leaders"): bots/swing/RULES.md (pre-registered 2026-10-02).

Pure parts: daily indicators, the entry test and the trailing stop. The day-by-day
simulation lives in scripts/backtest_swing.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    max_positions: int = 3
    min_price: float = 5.0
    min_dollar_volume: float = 5_000_000.0
    lookback: int = 126            # ~6 months
    min_return: float = 0.25       # +25%
    breakout_days: int = 20
    stop_atr: float = 3.0
    atr_days: int = 20
    slippage: float = 0.001        # 0.10% against the bot on every fill
    min_fill_fraction: float = 0.5  # skip a buy if settled cash covers < half the target


def sma(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def atr(highs, lows, closes, n: int) -> List[Optional[float]]:
    """Simple average of the true range over n days."""
    trs = [highs[0] - lows[0]] + [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                                      abs(lows[i] - closes[i - 1])) for i in range(1, len(closes))]
    return sma(trs, n)


@dataclass
class Daily:
    """One symbol's daily series and indicators."""
    dates: List[str]
    opens: List[float]
    highs: List[float]
    lows: List[float]
    closes: List[float]
    volumes: List[float]

    def __post_init__(self):
        self.sma50 = sma(self.closes, 50)
        self.sma200 = sma(self.closes, 200)
        self.dollar_vol = sma([c * v for c, v in zip(self.closes, self.volumes)], 20)
        self.index = {d: i for i, d in enumerate(self.dates)}

    def atr(self, n: int) -> List[Optional[float]]:
        if not hasattr(self, "_atr"):
            self._atr = atr(self.highs, self.lows, self.closes, n)
        return self._atr


def entry_signal(s: Daily, i: int, p: Params = Params()) -> Optional[float]:
    """The 126-day return if every stock-level entry condition (RULES.md section 4,
    items 1-4) holds at close i, else None."""
    if i < max(p.lookback, 200, p.breakout_days):
        return None
    c = s.closes[i]
    if c < p.min_price or (s.dollar_vol[i] or 0) < p.min_dollar_volume:
        return None
    ret = c / s.closes[i - p.lookback] - 1
    if ret < p.min_return:
        return None
    if not (s.sma50[i] and s.sma200[i] and c > s.sma50[i] > s.sma200[i]):
        return None
    if c <= max(s.closes[i - p.breakout_days:i]):
        return None
    return ret


def sector_ok(etf: Daily, i: Optional[int]) -> bool:
    return i is not None and etf.sma200[i] is not None and etf.closes[i] > etf.sma200[i]


@dataclass
class Holding:
    symbol: str
    entry_date: str
    entry: float
    shares: int
    atr_at_entry: float
    stop_atr: float = 3.0

    def __post_init__(self):
        self.highest_close = self.entry
        self.exit_pending = False

    @property
    def stop(self) -> float:
        return self.highest_close - self.stop_atr * self.atr_at_entry

    def on_close(self, close: float) -> bool:
        """Update with the day's close; True means sell at the next open."""
        self.highest_close = max(self.highest_close, close)
        return close < self.stop

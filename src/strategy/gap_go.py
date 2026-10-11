"""Silver "gap and go" strategy: bots/silver_gap/RULES.md (pre-registered 2026-10-11).

Pure parts: the entry conditions, the 5-minute and daily series, and the open position's
stop handling. scripts/backtest_gap_go.py drives them over history.

Conditions (I1, the pre-market high, cannot be tested: no pre-market bars):
  D1 close above yesterday's high      D2 yesterday's close above its 200-day SMA
  D3 open at least 3% above yesterday's close
  I2 close above the day's high so far I3 cumulative volume at least 2x the 14-day average
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from data.historical_data import group_bars_by_day
from strategy.healthcare_momentum import atr as atr_series

TIMES = [f"{h:02d}:{m:02d}" for h in range(9, 16) for m in range(0, 60, 5) if (9, 30) <= (h, m) <= (15, 55)]


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    position_dollars: float = 2500.0
    max_positions: int = 2
    min_price: float = 10.0
    gap_min: float = 0.03
    rvol_min: float = 2.0
    rvol_days: int = 14
    sma_days: int = 200
    first_signal_bar: str = "09:35"        # bar closing 09:40
    last_signal_bar: str = "15:10"         # bar closing 15:15
    flat_bar: str = "15:45"                # sold at this bar's close, 15:50
    stop_atr: float = 1.25
    min_stop_pct: float = 0.005
    half_spread: float = 0.005


def sma(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


@dataclass
class DayContext:
    """What yesterday and the open say about today (the daily conditions D2 and D3)."""
    prev_high: float
    prev_close: float
    prev_sma200: Optional[float]
    open: float

    @property
    def gap(self) -> float:
        return self.open / self.prev_close - 1

    def d2(self) -> bool:
        return self.prev_sma200 is not None and self.prev_close > self.prev_sma200

    def d3(self, p: Params) -> bool:
        return self.gap >= p.gap_min


class Series:
    """One symbol: 5-minute bars and daily bars, with the per-bar lookups the conditions need.

    daily: rows of (date, high, close), oldest first, trading days only.
    """

    def __init__(self, symbol: str, bars, daily: Sequence[Tuple[str, float, float]], p: Params = Params()):
        self.symbol = symbol
        self.bars = bars
        self.days = group_bars_by_day(bars)
        self.index = {(b.timestamp.strftime("%Y-%m-%d"), b.timestamp.strftime("%H:%M")): i
                      for i, b in enumerate(bars)}
        self.atr = atr_series([b.high for b in bars], [b.low for b in bars], [b.close for b in bars], 14)
        self.d_dates = [r[0] for r in daily]
        self.d_high = [r[1] for r in daily]
        self.d_close = [r[2] for r in daily]
        self.d_sma = sma(self.d_close, p.sma_days)
        self.sessions = sorted(self.days)
        self._cum: Dict[str, Dict[str, float]] = {}
        self._hh: Dict[str, Dict[str, Optional[float]]] = {}
        self._avg_cum: Dict[Tuple[str, str], Optional[float]] = {}

    # --- daily context ---------------------------------------------------------------
    def context(self, day: str) -> Optional[DayContext]:
        k = bisect_left(self.d_dates, day) - 1
        if k < 0 or day not in self.days:
            return None
        return DayContext(self.d_high[k], self.d_close[k], self.d_sma[k], self.days[day][0].open)

    # --- today so far ----------------------------------------------------------------
    def _build(self, day: str) -> None:
        cum, hh, run_v, run_h, by_t = {}, {}, 0.0, None, {}
        for b in self.days[day]:
            by_t[b.timestamp.strftime("%H:%M")] = b
        for t in TIMES:
            hh[t] = run_h                                  # highest high of bars BEFORE this one
            b = by_t.get(t)
            if b is not None:
                run_v += b.volume
                run_h = b.high if run_h is None else max(run_h, b.high)
            cum[t] = run_v
        self._cum[day], self._hh[day] = cum, hh

    def cum_volume(self, day: str, t: str) -> float:
        if day not in self._cum:
            self._build(day)
        return self._cum[day][t]

    def high_before(self, day: str, t: str) -> Optional[float]:
        if day not in self._hh:
            self._build(day)
        return self._hh[day][t]

    def avg_cum_volume(self, day: str, t: str, n: int) -> Optional[float]:
        """Average cumulative volume through slot t over the previous n sessions (None if
        fewer than n sessions of history)."""
        key = (day, t)
        if key not in self._avg_cum:
            k = bisect_left(self.sessions, day)
            prior = self.sessions[max(0, k - n):k]
            self._avg_cum[key] = mean(self.cum_volume(d, t) for d in prior) if len(prior) == n else None
        return self._avg_cum[key]

    def rvol(self, day: str, t: str, n: int) -> Optional[float]:
        avg = self.avg_cum_volume(day, t, n)
        return self.cum_volume(day, t) / avg if avg else None


def entry_conditions(close: float, ctx: DayContext, high_so_far: Optional[float], rvol: Optional[float],
                     p: Params = Params()) -> Dict[str, bool]:
    """Each condition at a signal bar's close (RULES.md section 3). I1 is not tested."""
    return {
        "price": close >= p.min_price,
        "D1": close > ctx.prev_high,
        "D2": ctx.d2(),
        "D3": ctx.d3(p),
        "I2": high_so_far is not None and close > high_so_far,
        "I3": rvol is not None and rvol >= p.rvol_min,
    }


def signal(conditions: Dict[str, bool]) -> bool:
    return all(conditions.values())


# --- open position ---------------------------------------------------------------------

@dataclass
class Position:
    ticker: str
    entry_time: object
    entry: float
    shares: int
    atr_at_entry: float
    rvol: float
    p: Params = field(default_factory=Params)

    def __post_init__(self):
        self.risk_per_share = max(self.p.stop_atr * self.atr_at_entry, self.p.min_stop_pct * self.entry)
        self.initial_stop = self.entry - self.risk_per_share
        self.stop = self.initial_stop
        self.highest = self.entry
        self.trailing = False

    def stop_fill(self, bar_open: float, bar_low: float) -> Optional[float]:
        """A resting stop: filled when the bar trades at or below it, at the stop or the
        bar's open if it opened below, less the half-spread."""
        if bar_low <= self.stop:
            return min(self.stop, bar_open) - self.p.half_spread
        return None

    def after_bar(self, bar_high: float) -> None:
        """Once the bar has closed (applies from the next bar): at +1R the stop starts to
        trail the highest high by one R."""
        self.highest = max(self.highest, bar_high)
        if self.highest >= self.entry + self.risk_per_share:
            self.trailing = True
        if self.trailing:
            self.stop = max(self.stop, self.highest - self.risk_per_share)


def shares_for(price: float, p: Params = Params()) -> int:
    return int(p.position_dollars // price) if price > 0 else 0

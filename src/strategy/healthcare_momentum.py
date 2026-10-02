"""Healthcare momentum strategy: the account holder's specification of 2026-10-02.

Rules and test plan: bots/healthcare/MOMENTUM_RULES.md (pre-registered). This module
holds the pure parts -- indicators, score, position size, stop management -- so they can
be tested on their own. scripts/backtest_healthcare_momentum.py drives them over history.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    max_dollar_risk: float = 25.0           # RISK_PER_TRADE 0.005 x $5,000
    max_position_value: float = 1250.0      # MAX_POSITION_PERCENT 0.25 x $5,000
    max_open_positions: int = 3
    max_total_open_risk: float = 75.0
    min_price: float = 5.0
    min_avg_volume_20d: float = 1_000_000
    skip_gap_pct: float = 4.0               # stand-in for "no major binary event"
    first_signal_bar: str = "09:40"         # bar closing 09:45
    last_signal_bar: str = "14:25"          # bar closing 14:30
    flat_bar: str = "15:45"                 # sold at this bar's close, 15:50
    rsi_low: float = 52.0
    rsi_high: float = 68.0
    volume_ratio: float = 1.2
    min_score: float = 75.0
    stop_atr: float = 1.25
    trail_atr: float = 1.25
    trail_after_r: float = 1.0
    half_spread: float = 0.005


# --- indicators (lists aligned with the input; None until defined) ---------------------

def ema(values: Sequence[float], n: int) -> List[float]:
    out, k, prev = [], 2.0 / (n + 1), None
    for v in values:
        prev = v if prev is None else prev + k * (v - prev)
        out.append(prev)
    return out


def rsi(closes: Sequence[float], n: int = 14) -> List[Optional[float]]:
    """Wilder's RSI: simple averages of the first n changes, then Wilder smoothing."""
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / n, losses / n

    def value(g, l):
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[n] = value(avg_g, avg_l)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (n - 1) + max(d, 0.0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0.0)) / n
        out[i] = value(avg_g, avg_l)
    return out


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """(macd, signal, histogram) lists."""
    line = [a - b for a, b in zip(ema(closes, fast), ema(closes, slow))]
    sig = ema(line, signal)
    return line, sig, [a - b for a, b in zip(line, sig)]


def atr(highs, lows, closes, n: int = 14) -> List[Optional[float]]:
    """Wilder's ATR. The first bar's true range is its own high - low."""
    out: List[Optional[float]] = [None] * len(closes)
    trs = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[0] - lows[0])
        else:
            pc = closes[i - 1]
            trs.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    if len(trs) < n:
        return out
    value = sum(trs[:n]) / n
    out[n - 1] = value
    for i in range(n, len(trs)):
        value = (value * (n - 1) + trs[i]) / n
        out[i] = value
    return out


# --- score -----------------------------------------------------------------------------

@dataclass
class Reading:
    """Indicator values for one stock on one bar."""
    price: float
    ema9: float
    ema20: float
    ema20_prev: float
    rsi14: Optional[float]
    macd: float
    macd_signal: float
    macd_hist: float
    atr14: Optional[float]
    bar_volume: float
    slot_avg_volume: Optional[float]


def score(r: Reading, xlv_bullish: bool, p: Params = Params()) -> Dict[str, float]:
    """Points per condition (MOMENTUM_RULES.md section 4) and the total."""
    vol_ok = bool(r.slot_avg_volume) and r.bar_volume >= p.volume_ratio * r.slot_avg_volume
    parts = {
        "price_above_ema20": 10.0 if r.price > r.ema20 else 0.0,
        "ema9_above_ema20": 10.0 if r.ema9 > r.ema20 else 0.0,
        "ema20_rising": 10.0 if r.ema20 > r.ema20_prev else 0.0,
        "rsi_in_band": 10.0 if r.rsi14 is not None and p.rsi_low <= r.rsi14 <= p.rsi_high else 0.0,
        "macd_above_signal": 10.0 if r.macd > r.macd_signal else 0.0,
        "macd_hist_positive": 10.0 if r.macd_hist > 0 else 0.0,
        "volume_confirmed": 12.5 if vol_ok else 0.0,
        "xlv_bullish": 12.5 if xlv_bullish else 0.0,
        "entry_quality": 15.0 if r.atr14 is not None and r.price <= r.ema9 + r.atr14 else 0.0,
    }
    parts["total"] = sum(parts.values())
    return parts


def xlv_is_bullish(price: float, ema9: float, ema20: float, ema20_prev: float,
                   session_vwap: Optional[float]) -> bool:
    """Trend test AND above VWAP (the account holder chose 'Both')."""
    return (price > ema20 and ema9 > ema20 and ema20 > ema20_prev
            and session_vwap is not None and price > session_vwap)


# --- size ------------------------------------------------------------------------------

def position_size(price: float, atr14: float, p: Params = Params()) -> int:
    """shares = floor(min($25 / risk_per_share, $1,250 / price)); 0 if not tradeable."""
    risk_per_share = p.stop_atr * atr14
    if price <= 0 or risk_per_share <= 0:
        return 0
    return int(math.floor(min(p.max_dollar_risk / risk_per_share, p.max_position_value / price)))


# --- open position ---------------------------------------------------------------------

@dataclass
class Position:
    ticker: str
    entry_time: object
    entry: float
    shares: int
    atr_at_entry: float
    score: float
    p: Params = field(default_factory=Params)

    def __post_init__(self):
        self.risk_per_share = self.p.stop_atr * self.atr_at_entry
        self.initial_stop = self.entry - self.risk_per_share
        self.stop = self.initial_stop
        self.highest = self.entry
        self.trailing = False

    @property
    def open_risk(self) -> float:
        return self.shares * max(self.entry - self.stop, 0.0)

    def stop_fill(self, bar_open: float, bar_low: float) -> Optional[float]:
        """A resting stop: filled when the bar trades at or below it, at the stop or the
        bar's open if it opened below, less the half-spread."""
        if bar_low <= self.stop:
            return min(self.stop, bar_open) - self.p.half_spread
        return None

    def after_bar(self, bar_high: float) -> None:
        """Update the trailing stop once the bar has closed (applies from the next bar)."""
        self.highest = max(self.highest, bar_high)
        if self.highest >= self.entry + self.p.trail_after_r * self.risk_per_share:
            self.trailing = True
        if self.trailing:
            self.stop = max(self.stop, self.highest - self.p.trail_atr * self.atr_at_entry)

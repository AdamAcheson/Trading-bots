"""Mining "buy the close, sell the open" bot: bots/mining_overnight/RULES.md
(pre-registered 2026-10-02). Pure parts; the simulation is scripts/backtest_mining_overnight.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from strategy import swing
from strategy.healthcare_momentum import rsi


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    max_positions: int = 3
    min_price: float = 3.0
    min_dollar_volume: float = 5_000_000.0
    rsi_below: float = 10.0
    max_days: int = 10
    disaster: float = 0.85
    slippage: float = 0.0015
    min_fill_fraction: float = 0.5


class Series(swing.Daily):
    """swing.Daily plus SMA5 and RSI(2)."""

    def __post_init__(self):
        super().__post_init__()
        self.sma5 = swing.sma(self.closes, 5)
        self.rsi2 = rsi(self.closes, 2)


def entry_signal(s: Series, i: int, etf_ok: bool, p: Params = Params()) -> Optional[float]:
    """RSI(2) if every entry condition (RULES.md section 4, items 1-4) holds at close i."""
    if i < 199 or not etf_ok:
        return None
    c = s.closes[i]
    if c < p.min_price or (s.dollar_vol[i] or 0) < p.min_dollar_volume:
        return None
    if s.sma200[i] is None or c <= s.sma200[i]:
        return None
    r = s.rsi2[i]
    if r is None or r >= p.rsi_below:
        return None
    return r


def exit_reason(s: Series, i: int, entry: float, days_held: int, p: Params = Params()) -> Optional[str]:
    """Why to sell at the next open, judged at close i; None to keep holding."""
    c = s.closes[i]
    if c < p.disaster * entry:
        return "DISASTER_STOP"
    if s.sma5[i] is not None and c > s.sma5[i]:
        return "ABOVE_SMA5"
    if days_held >= p.max_days:
        return "TIME_LIMIT"
    return None

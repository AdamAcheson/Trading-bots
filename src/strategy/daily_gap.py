"""S&P 500 daily "gap and go": bots/sp500_gap/RULES.md (pre-registered 2026-10-12). Pure parts;
the simulation is scripts/backtest_daily_gap.py. Account sizing is sp500_dip.buy_amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from strategy import sp500_dip as sd
from strategy import swing


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    max_positions: int = 2
    min_price: float = 10.0                # real (not split-adjusted) close
    min_dollar_volume: float = 20_000_000.0
    gap_min: float = 0.03
    volume_multiple: float = 2.0
    volume_days: int = 14
    close_in_range: float = 0.5            # close in the upper half of the day's range
    max_days: int = 5
    min_amount: float = 2500.0
    max_amount: float = 5500.0
    slippage: float = 0.001


class Series(sd.Series):
    """sd.Series plus the average volume of the 14 days before each day."""

    def __post_init__(self):
        super().__post_init__()
        n = Params.volume_days
        self.avg_volume = [None] * len(self.volumes)
        for i in range(n, len(self.volumes)):
            self.avg_volume[i] = sum(self.volumes[i - n:i]) / n


def entry_signal(s: Series, i: int, member_since: Optional[str],
                 p: Params = Params()) -> Optional[Tuple[float, float]]:
    """(volume ratio, signal-day low) if every buy condition (RULES.md section 2, items 1-8)
    holds at close i, else None."""
    if i < 200:
        return None
    if member_since is None or s.dates[i] < member_since:
        return None
    if s.sma200[i - 1] is None or s.closes[i - 1] <= s.sma200[i - 1]:           # D2
        return None
    if s.opens[i] < (1 + p.gap_min) * s.closes[i - 1]:                          # D3
        return None
    if s.closes[i] <= s.highs[i - 1]:                                           # D1
        return None
    rng = s.highs[i] - s.lows[i]                                                # I2
    if rng <= 0 or s.closes[i] <= s.opens[i] or (s.closes[i] - s.lows[i]) / rng < p.close_in_range:
        return None
    avg = s.avg_volume[i]                                                       # I3
    if not avg or s.volumes[i] < p.volume_multiple * avg:
        return None
    real = s.real_closes[i]
    if real is None or real < p.min_price or (s.dollar_vol[i] or 0) < p.min_dollar_volume:
        return None
    return s.volumes[i] / avg, s.lows[i]


def exit_reason(s: Series, i: int, stop: float, days_held: int, p: Params = Params()) -> Optional[str]:
    """Why to sell at the next open, judged at close i (days_held counts the closes since
    buying, the buy day included); None to keep holding."""
    if s.closes[i] < stop:
        return "STOP"
    if days_held >= p.max_days:
        return "TIME_LIMIT"
    return None

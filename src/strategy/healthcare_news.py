"""Healthcare "news-day drift" bot: bots/healthcare_news/RULES.md (pre-registered
2026-10-02). Pure parts; the simulation is scripts/backtest_healthcare_news.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from strategy import swing


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    max_positions: int = 3
    min_jump: float = 0.05            # close >= +5% over the previous close
    volume_multiple: float = 3.0      # volume >= 3x the previous 50 days' average
    volume_days: int = 50
    min_price: float = 10.0
    min_dollar_volume: float = 20_000_000.0
    hold_days: int = 40
    slippage: float = 0.001
    min_fill_fraction: float = 0.5


class Series(swing.Daily):
    """swing.Daily plus the 50-day average volume before each day."""

    def __post_init__(self):
        super().__post_init__()
        avg = swing.sma(self.volumes, 50)
        self.prior_avg_volume = [None] + avg[:-1]         # average of the 50 days BEFORE i
        dv = [c * v for c, v in zip(self.closes, self.volumes)]
        self.prior_dollar_vol = [None] + swing.sma(dv, 20)[:-1]


def news_day(s: Series, i: int, p: Params = Params()) -> Optional[float]:
    """The volume multiple if close i is a news day (RULES.md section 3), else None."""
    if i < p.volume_days + 1:
        return None
    c, prev = s.closes[i], s.closes[i - 1]
    if prev <= 0 or c / prev - 1 < p.min_jump:
        return None
    avg = s.prior_avg_volume[i]
    if not avg or s.volumes[i] < p.volume_multiple * avg:
        return None
    if c < (s.highs[i] + s.lows[i]) / 2:
        return None
    if c < p.min_price or (s.prior_dollar_vol[i] or 0) < p.min_dollar_volume:
        return None
    return s.volumes[i] / avg


def exit_reason(s: Series, i: int, news_low: float, days_held: int, p: Params = Params()) -> Optional[str]:
    """Why to sell at the next open, judged at close i; None to keep holding."""
    if s.closes[i] < news_low:
        return "NEWS_FAILED"
    if days_held >= p.hold_days:
        return "TIME_40_DAYS"
    return None

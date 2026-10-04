"""S&P 500 "buy the dip in strong companies, in a healthy market": bots/sp500_dip/RULES.md
(pre-registered 2026-10-04). Pure parts; the simulation is scripts/backtest_sp500_dip.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from strategy import swing
from strategy.healthcare_momentum import rsi


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    max_positions: int = 2
    min_price: float = 15.0               # real (not split-adjusted) close
    min_dollar_volume: float = 20_000_000.0
    rsi_below: float = 10.0
    max_gap: float = 0.04                 # no open 4%+ from the prior close, that day or the day before
    max_days: int = 10
    disaster: float = 0.85
    min_amount: float = 2500.0
    max_amount: float = 5500.0
    slippage: float = 0.001


def split_factors(dates: Sequence[str], splits: Sequence[dict]) -> List[float]:
    """For each date, the factor that turns a split-adjusted price into the price the stock
    actually traded at: the product of from_factor/to_factor over splits AFTER that date
    (a 4-for-1 split multiplies earlier adjusted prices by 4)."""
    out = []
    for d in dates:
        f = 1.0
        for s in splits:
            if s["date"] > d:
                f *= s["from_factor"] / s["to_factor"]
        out.append(f)
    return out


class Series(swing.Daily):
    """swing.Daily plus SMA5, RSI(2) and the real close. Set `splits` before use via
    `with_splits`; without it the real close equals the adjusted close."""

    def __post_init__(self):
        super().__post_init__()
        self.sma5 = swing.sma(self.closes, 5)
        self.rsi2 = rsi(self.closes, 2)
        self.real_closes = list(self.closes)

    def with_splits(self, splits: Sequence[dict]) -> "Series":
        self.real_closes = [c * f for c, f in zip(self.closes, split_factors(self.dates, splits))]
        return self


def gapped(s: Series, i: int, max_gap: float) -> bool:
    """True if the open on day i or i-1 was max_gap or more away from the prior close."""
    for j in (i, i - 1):
        if j < 1 or s.closes[j - 1] <= 0:
            return True
        if abs(s.opens[j] / s.closes[j - 1] - 1) >= max_gap:
            return True
    return False


def entry_signal(s: Series, i: int, market_ok: bool, member_since: Optional[str],
                 p: Params = Params()) -> Optional[float]:
    """RSI(2) if every buy condition (RULES.md section 4, items 1-7) holds at close i."""
    if i < 199 or not market_ok:
        return None
    if member_since is None or s.dates[i] < member_since:
        return None
    if s.real_closes[i] < p.min_price or (s.dollar_vol[i] or 0) < p.min_dollar_volume:
        return None
    if s.sma200[i] is None or s.closes[i] <= s.sma200[i]:
        return None
    r = s.rsi2[i]
    if r is None or r >= p.rsi_below:
        return None
    if gapped(s, i, p.max_gap):
        return None
    return r


def exit_reason(s: Series, i: int, entry: float, days_held: int, market_ok: bool,
                p: Params = Params()) -> Optional[str]:
    """Why to sell at the next open, judged at close i (days_held counts the closes since
    buying, the buy day included); None to keep holding."""
    c = s.closes[i]
    if not market_ok:
        return "MARKET_SWITCH"
    if c < p.disaster * entry:
        return "DISASTER_STOP"
    if s.sma5[i] is not None and c > s.sma5[i]:
        return "ABOVE_SMA5"
    if days_held >= p.max_days:
        return "TIME_LIMIT"
    return None


def market_ok(spy: swing.Daily, i: Optional[int]) -> bool:
    """SPY's close above its SMA200."""
    return i is not None and spy.sma200[i] is not None and spy.closes[i] > spy.sma200[i]


def buy_amount(settled_cash: float, account_value: float, p: Params = Params()) -> float:
    """RULES.md section 6: min(settled cash, $5,500, max($2,500, half the account)); 0 if
    that is under $2,500."""
    amount = min(settled_cash, p.max_amount, max(p.min_amount, account_value / p.max_positions))
    return amount if amount >= p.min_amount else 0.0

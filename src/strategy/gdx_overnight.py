"""GDX overnight-only bot: bots/gdx_overnight/RULES.md (pre-registered 2026-10-02).

Buy GDX at every close, sell at the next open. Pure simulation; loading and reporting
are in scripts/backtest_gdx_overnight.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from execution.costs import TransactionCostModel


@dataclass(frozen=True)
class Params:
    account_size: float = 5000.0
    slippage: float = 0.0005          # 0.05% against the bot on every fill
    mode: str = "cash"                # "cash": two alternating halves, T+1; "margin": one pot


@dataclass
class Pot:
    cash: float
    unsettled: list = field(default_factory=list)   # (trading-day index it settles, amount)
    shares: int = 0
    entry: float = 0.0
    buy_comm: float = 0.0
    bought: str = ""

    def settle(self, t: int) -> None:
        self.cash += sum(a for d, a in self.unsettled if d <= t)
        self.unsettled = [(d, a) for d, a in self.unsettled if d > t]


def simulate(dates: List[str], opens: List[float], closes: List[float], i0: int, i1: int,
             costs: TransactionCostModel = TransactionCostModel(), p: Params = Params()) -> dict:
    """Run the rules over the days with indices i0..i1 (inclusive)."""
    if p.mode not in ("cash", "margin"):
        raise ValueError(f"unknown mode {p.mode!r}")
    n_pots = 2 if p.mode == "cash" else 1
    pots = [Pot(cash=p.account_size / n_pots) for _ in range(n_pots)]
    settle_lag = 1 if p.mode == "cash" else 0
    nights, curve, comm_paid = [], [], 0.0

    for t in range(i0, i1 + 1):
        # open: sell last night's position
        for pot in pots:
            if pot.shares:
                fill = opens[t] * (1 - p.slippage)
                c = costs.commission(fill, pot.shares, sell=True)
                comm_paid += c
                pot.unsettled.append((t + settle_lag, fill * pot.shares - c))
                gross = (fill - pot.entry) * pot.shares
                nights.append(dict(date=pot.bought, shares=pot.shares, entry=pot.entry, exit=fill,
                                   gross=gross, net=gross - pot.buy_comm - c,
                                   price_return=opens[t] / closes[t - 1] - 1))
                pot.shares = 0
        for pot in pots:
            pot.settle(t)

        # close: tonight's buy (none on the period's last day)
        if t < i1:
            pot = pots[(t - i0) % n_pots]
            fill = closes[t] * (1 + p.slippage)
            shares = int(pot.cash // fill)
            c = costs.commission(fill, shares)
            while shares > 0 and shares * fill + c > pot.cash:
                shares -= 1
                c = costs.commission(fill, shares)
            if shares > 0:
                pot.cash -= shares * fill + c
                comm_paid += c
                pot.shares, pot.entry, pot.buy_comm, pot.bought = shares, fill, c, dates[t]

        curve.append(sum(pt.cash + sum(a for _, a in pt.unsettled) + pt.shares * closes[t]
                         for pt in pots))

    return dict(dates=dates[i0:i1 + 1], nights=nights, curve=curve, final=curve[-1],
                commission=comm_paid)


def split_returns(opens: List[float], closes: List[float], i0: int, i1: int) -> dict:
    """GDX's own compounded overnight-only and day-only returns over i0..i1, before costs."""
    night = day = 1.0
    for t in range(i0, i1 + 1):
        if t > i0:
            night *= opens[t] / closes[t - 1]
        day *= closes[t] / opens[t]
    return dict(overnight=night - 1, day=day - 1)


def geometric_mean(returns: List[float]) -> float:
    """Average per-period return that compounds to the same total."""
    if not returns:
        return 0.0
    return math.exp(sum(math.log1p(r) for r in returns) / len(returns)) - 1

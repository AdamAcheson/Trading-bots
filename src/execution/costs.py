"""Transaction cost model (spread, impact, commission).

Backtests in this project originally filled at bar prices with no costs at all, so
`gross_profit == net_profit` on every trade. That is harmless when comparing two
configurations to each other and badly misleading in absolute terms: the holdout
turns ~$92M of notional on $100k of equity, so it breaks even at roughly 10 bps
per side.

Cost is modelled per SHARE rather than in basis points, because the binding
constraint here is the one-cent minimum tick, not a percentage. Crossing a
penny-wide market costs half a cent per share whatever the stock costs -- which is
0.5 bps on a $95 stock and 12 bps on a $4 one. Over half this strategy's notional
sits in sub-$10 miners, so a flat-bps model would hide exactly the effect that
matters.

The three components:

  * SPREAD -- `spread_ticks` is the assumed quoted width in cents. Crossing costs
    half of it per side. 1.0 is the tightest a US equity quote can legally be, so
    the default is a FLOOR on real cost, not an estimate of it.
  * IMPACT -- `impact_bps` per side on notional, for the book moving against a
    $25k order. Zero by default; genuinely zero only for small orders in liquid
    names.
  * COMMISSION -- what the broker charges per order. Either a flat
    `commission_per_order`, or a per-share schedule like IBKR Pro's:
    `commission_per_share` with a per-order minimum and a cap at a % of the order's
    value, plus `fees_per_share` (exchange + clearing) on every order and
    `sell_fees_per_share` (FINRA TAF) on sales. Zero at E*TRADE; IBKR Lite is
    commission-free but has no API.

`crossing_fraction` scales the spread term for strategies that sometimes rest a
passive order instead of crossing. Exits here always cross (`submit_exit_order`
sends a marketable limit), so 1.0 is right for this strategy unless entries are
modelled separately; anything below 1.0 is an assumption that passive entries fill
without adverse selection, which is optimistic in a momentum strategy.
"""

from __future__ import annotations

from dataclasses import dataclass

TICK_SIZE = 0.01


@dataclass(frozen=True)
class TransactionCostModel:
    spread_ticks: float = 0.0
    impact_bps: float = 0.0
    commission_per_order: float = 0.0
    crossing_fraction: float = 1.0
    tick_size: float = TICK_SIZE
    commission_per_share: float = 0.0
    commission_min_per_order: float = 0.0
    commission_max_pct_of_value: float = 0.0    # 0 = no cap
    fees_per_share: float = 0.0
    sell_fees_per_share: float = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.spread_ticks or self.impact_bps or self.commission_per_order
                    or self.commission_per_share or self.fees_per_share)

    def commission(self, price: float, shares: int, sell: bool = False) -> float:
        """What the broker charges for one order of `shares` at `price`."""
        if shares <= 0:
            return 0.0
        charge = self.commission_per_order
        if self.commission_per_share:
            per_share = max(self.commission_min_per_order, shares * self.commission_per_share)
            if self.commission_max_pct_of_value:
                per_share = min(per_share, shares * price * self.commission_max_pct_of_value / 100.0)
            charge += per_share
        charge += shares * self.fees_per_share
        if sell:
            charge += shares * self.sell_fees_per_share
        return charge

    def market_cost(self, price: float, shares: int) -> float:
        """Spread and impact of one fill: what the market takes, not the broker."""
        if shares <= 0:
            return 0.0
        half_spread = self.spread_ticks * self.tick_size / 2.0 * self.crossing_fraction
        return shares * half_spread + shares * price * self.impact_bps / 10000.0

    def per_side(self, price: float, shares: int, sell: bool = False) -> float:
        """Cost of one fill of `shares` at `price`."""
        if shares <= 0:
            return 0.0
        return self.market_cost(price, shares) + self.commission(price, shares, sell)

    def round_trip(self, entry_price: float, exit_price: float, shares: int) -> float:
        return self.per_side(entry_price, shares) + self.per_side(exit_price, shares, sell=True)

    @classmethod
    def from_config(cls, risk_config: dict) -> "TransactionCostModel":
        cfg = (risk_config or {}).get("transaction_costs") or {}
        return cls(
            spread_ticks=float(cfg.get("spread_ticks", 0.0)),
            impact_bps=float(cfg.get("impact_bps", 0.0)),
            commission_per_order=float(cfg.get("commission_per_order", 0.0)),
            crossing_fraction=float(cfg.get("crossing_fraction", 1.0)),
            commission_per_share=float(cfg.get("commission_per_share", 0.0) or 0.0),
            commission_min_per_order=float(cfg.get("commission_min_per_order", 0.0) or 0.0),
            commission_max_pct_of_value=float(cfg.get("commission_max_pct_of_value", 0.0) or 0.0),
            fees_per_share=float(cfg.get("fees_per_share", 0.0) or 0.0),
            sell_fees_per_share=float(cfg.get("sell_fees_per_share", 0.0) or 0.0),
        )

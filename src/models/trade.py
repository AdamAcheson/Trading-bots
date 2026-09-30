"""Ticker state machine + the completed-trade journal record (spec sections 23 & 28)."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class TradeState(str, Enum):
    WATCHING = "WATCHING"
    SETUP_FORMING = "SETUP_FORMING"
    ENTRY_ELIGIBLE = "ENTRY_ELIGIBLE"
    ORDER_PENDING = "ORDER_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_PARTIAL = "POSITION_PARTIAL"
    OVERNIGHT_REVIEW = "OVERNIGHT_REVIEW"
    OVERNIGHT_POSITION = "OVERNIGHT_POSITION"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    LOCKED_OUT = "LOCKED_OUT"


# Valid transitions for PositionManager to enforce (spec section 23: "prevent
# contradictory actions"). LOCKED_OUT is reachable from any state.
ALLOWED_TRANSITIONS = {
    # WATCHING -> ORDER_PENDING / POSITION_OPEN directly is allowed because
    # SETUP_FORMING/ENTRY_ELIGIBLE are represented by Signal log entries rather than
    # persisted PositionManager states in Phase 1/2 -- the granular states remain
    # available for a future pipeline that tracks them explicitly.
    TradeState.WATCHING: {
        TradeState.SETUP_FORMING,
        TradeState.ORDER_PENDING,
        TradeState.POSITION_OPEN,
        TradeState.LOCKED_OUT,
    },
    TradeState.SETUP_FORMING: {TradeState.ENTRY_ELIGIBLE, TradeState.WATCHING, TradeState.LOCKED_OUT},
    TradeState.ENTRY_ELIGIBLE: {TradeState.ORDER_PENDING, TradeState.WATCHING, TradeState.LOCKED_OUT},
    TradeState.ORDER_PENDING: {TradeState.POSITION_OPEN, TradeState.WATCHING, TradeState.LOCKED_OUT},
    TradeState.POSITION_OPEN: {
        TradeState.POSITION_PARTIAL,
        TradeState.OVERNIGHT_REVIEW,
        TradeState.EXIT_PENDING,
        TradeState.LOCKED_OUT,
    },
    TradeState.POSITION_PARTIAL: {
        TradeState.OVERNIGHT_REVIEW,
        TradeState.EXIT_PENDING,
        TradeState.LOCKED_OUT,
    },
    TradeState.OVERNIGHT_REVIEW: {
        TradeState.OVERNIGHT_POSITION,
        TradeState.EXIT_PENDING,
        TradeState.LOCKED_OUT,
    },
    TradeState.OVERNIGHT_POSITION: {
        TradeState.POSITION_OPEN,
        TradeState.EXIT_PENDING,
        TradeState.LOCKED_OUT,
    },
    TradeState.EXIT_PENDING: {TradeState.CLOSED, TradeState.LOCKED_OUT},
    TradeState.CLOSED: {TradeState.WATCHING},
    TradeState.LOCKED_OUT: set(),
}


class ExitReason(str, Enum):
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    TRAILING_STOP = "TRAILING_STOP"
    END_OF_DAY = "END_OF_DAY"
    OVERNIGHT_REJECTED = "OVERNIGHT_REJECTED"
    MAX_HOLD_EXCEEDED = "MAX_HOLD_EXCEEDED"
    MANUAL_EXIT = "MANUAL_EXIT"
    RISK_LIMIT = "RISK_LIMIT"
    SYSTEM_SAFETY_EXIT = "SYSTEM_SAFETY_EXIT"


@dataclass
class Trade:
    ticker: str
    date: str
    entry_time: datetime
    entry_price: float
    shares: int
    initial_stop: float
    initial_target: float

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None

    gross_profit: Optional[float] = None
    net_profit: Optional[float] = None
    percentage_return: Optional[float] = None
    r_return: Optional[float] = None

    maximum_favorable_excursion: float = 0.0
    maximum_adverse_excursion: float = 0.0
    benchmark_return_during_trade: Optional[float] = None

    setup_score: Optional[float] = None
    score_components: Optional[dict] = None
    setup_type: Optional[str] = None
    overnight_yes_no: bool = False
    # The broker's commission and fees within (gross_profit - net_profit); the rest
    # is modelled spread and impact. Absent from journals written before 2026-09-30.
    broker_commission: float = 0.0

    def close(self, exit_time: datetime, exit_price: float, reason: ExitReason,
              commission: float = 0.0, benchmark_return: Optional[float] = None,
              partial_exits: Optional[list] = None) -> None:
        """`partial_exits`: (price, shares) already sold before this final exit. Only
        the remaining shares go at `exit_price`.

        Until 2026-09-28 every share was booked at `exit_price`, so the 35% partial
        sale at 1.5R was valued at the final exit's price instead of its own. The
        holdout's intraday gross was overstated by $262 (10.6%) and the tuning
        period's by $109 (7.4%), because the biggest winners exit at the target,
        above the partial's price. The broker was never affected: the partial really
        was sold. Only the bot's own record of it was wrong."""
        partial_exits = partial_exits or []
        sold = sum(s for _, s in partial_exits)
        remaining = max(self.shares - sold, 0)
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = reason
        self.gross_profit = (sum((p - self.entry_price) * s for p, s in partial_exits)
                             + (exit_price - self.entry_price) * remaining)
        self.net_profit = self.gross_profit - commission
        cost_basis = self.entry_price * self.shares
        self.percentage_return = self.gross_profit / cost_basis * 100.0 if cost_basis else 0.0
        risk_per_share = self.entry_price - self.initial_stop
        risk = risk_per_share * self.shares
        self.r_return = self.gross_profit / risk if risk else 0.0
        self.benchmark_return_during_trade = benchmark_return

    def update_excursion(self, current_price: float) -> None:
        favorable = current_price - self.entry_price
        adverse = self.entry_price - current_price
        if favorable > self.maximum_favorable_excursion:
            self.maximum_favorable_excursion = favorable
        if adverse > self.maximum_adverse_excursion:
            self.maximum_adverse_excursion = adverse

    def as_log_row(self) -> dict:
        row = asdict(self)
        row["entry_time"] = self.entry_time.isoformat()
        row["exit_time"] = self.exit_time.isoformat() if self.exit_time else None
        row["exit_reason"] = self.exit_reason.value if self.exit_reason else None
        return row

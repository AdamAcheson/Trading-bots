"""A partial sale must be booked at its own price. Until 2026-09-28 every share was booked
at the final exit's price, so the backtest's P&L was wrong on every trade that took the
1.5R partial (242 of 902 intraday trades), overstating the holdout by $262."""

from datetime import datetime, timezone

import pytest

from models.trade import ExitReason
from positions.position_manager import PositionManager

T0 = datetime(2025, 10, 20, 14, 40, tzinfo=timezone.utc)


def _open(pm):
    return pm.open_position("AG", "SIL", T0, 14.254275, 175, 14.173506, 14.855625, "VWAP_RECLAIM", 80.0)


def test_the_ag_trade_that_exposed_it():
    """AG 2025-10-20: 61 shares sold at $14.3901 (1.5R), the other 114 trailed out at
    $14.317918. The journal said $11.14, as if all 175 went at $14.3179. Correct: $15.54."""
    pm = PositionManager(10)
    pos = _open(pm)
    pos.apply_partial_exit(T0, 14.3901, 61, "partial_target_1_5R")
    trade = pm.close_position("AG", T0, 14.317918, ExitReason.TRAILING_STOP)
    assert trade.gross_profit == pytest.approx(61 * (14.3901 - 14.254275) + 114 * (14.317918 - 14.254275))
    assert trade.gross_profit == pytest.approx(15.54, abs=0.01)
    assert trade.shares == 175
    assert trade.r_return == pytest.approx(trade.gross_profit / ((14.254275 - 14.173506) * 175))


def test_a_winner_that_reaches_its_target_is_not_overstated():
    """The direction that mattered: the partial went at 1.5R, the rest at the target.
    Booking everything at the target overstated exactly the big winners."""
    pm = PositionManager(10)
    pos = _open(pm)
    pos.apply_partial_exit(T0, 14.375, 61, "partial_target_1_5R")
    trade = pm.close_position("AG", T0, 14.855625, ExitReason.TARGET_HIT)
    all_at_target = 175 * (14.855625 - 14.254275)
    assert trade.gross_profit < all_at_target
    assert trade.gross_profit == pytest.approx(61 * (14.375 - 14.254275) + 114 * (14.855625 - 14.254275))


def test_no_partial_is_unchanged():
    pm = PositionManager(10)
    _open(pm)
    trade = pm.close_position("AG", T0, 14.173506, ExitReason.STOP_HIT)
    assert trade.gross_profit == pytest.approx(175 * (14.173506 - 14.254275))
    assert trade.r_return == pytest.approx(-1.0)

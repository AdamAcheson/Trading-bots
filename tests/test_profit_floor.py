"""The "$15 net profit floor" exit (docs/PREREG_PROFIT_FLOOR.md): no partial sale, no
breakeven and no trailing until a close reaches the price that books $15 net after
commission and spread; then the stop locks there and the trailing stop runs above it."""

from datetime import datetime, timedelta

import pytest

from execution.costs import TransactionCostModel
from models.trade import ExitReason
from positions.position_manager import PositionManager

T0 = datetime(2026, 3, 2, 10, 0)
FIXED = TransactionCostModel(spread_ticks=1.0, commission_per_share=0.005, commission_min_per_order=1.0,
                             commission_max_pct_of_value=1.0, sell_fees_per_share=0.000166)


def open_position(mgr, entry=25.0, stop=24.85, target=26.0, shares=100):
    mgr.mark_order_pending("AG")
    return mgr.open_position(
        ticker="AG", benchmark="SIL", entry_time=T0, entry_price=entry,
        shares=shares, stop_price=stop, target_price=target,
        setup_type="VWAP_RECLAIM", setup_score=80.0,
    )


def manage(mgr, price, minutes=5, atr=0.10, **kw):
    params = dict(
        breakeven_trigger_r=1.0, partial_exit_enabled=True,
        partial_exit_trigger_r=1.5, partial_exit_sell_fraction=0.35,
        trailing_enabled=True, trailing_atr_multiplier=1.0, trailing_activate_r=1.0,
        atr=atr, profit_floor_net=15.0,
    )
    params.update(kw)
    return mgr.manage("AG", current_price=price, current_time=T0 + timedelta(minutes=minutes), **params)


@pytest.fixture
def mgr():
    return PositionManager(max_concurrent_positions=1, cost_model=FIXED)


def test_lock_price_books_exactly_the_floor_net(mgr):
    p = open_position(mgr)
    lock = mgr.profit_floor_price(p, 15.0)
    # 100 shares: $1 + $1 commission, $0.50 + $0.50 half-spread, $0.0166 TAF -> $18.0166 gross
    assert lock == pytest.approx(25.0 + 18.0166 / 100)
    trade = mgr.close_position("AG", T0, lock, ExitReason.TRAILING_STOP)
    assert trade.net_profit == pytest.approx(15.0)


def test_no_partial_no_breakeven_no_trailing_before_the_floor(mgr):
    p = open_position(mgr)                  # R = $0.15/share = $15
    a = manage(mgr, 25.17)                  # +1.13R: shipped rules would move to breakeven
    assert p.current_stop == 24.85 and not p.breakeven_moved and not a.should_exit
    assert p.shares == 100 and not p.partial_exits     # 1.5R partial would also be due later
    a = manage(mgr, 25.175, minutes=10)    # still just under the $15-net price (25.1802)
    assert p.current_stop == 24.85 and a.partial_exit_shares == 0


def test_close_at_the_floor_locks_the_stop_there(mgr):
    p = open_position(mgr)
    lock = mgr.profit_floor_price(p, 15.0)
    a = manage(mgr, 25.19, atr=0.50)        # wide ATR: trailing (25.19 - 0.50) stays below the lock
    assert p.profit_floor_locked and a.breakeven_moved
    assert p.current_stop == pytest.approx(lock)
    a = manage(mgr, 25.18, minutes=10, atr=0.50)
    assert a.should_exit and a.exit_reason == ExitReason.TRAILING_STOP
    trade = mgr.close_position("AG", T0, a.exit_price, a.exit_reason)
    assert trade.net_profit == pytest.approx(15.0)


def test_trailing_runs_above_the_lock(mgr):
    p = open_position(mgr)
    manage(mgr, 25.19)
    manage(mgr, 25.60, minutes=10)          # high water 25.60, ATR 0.10 -> stop 25.50
    assert p.current_stop == pytest.approx(25.50)
    manage(mgr, 25.52, minutes=15)          # the stop never moves down
    assert p.current_stop == pytest.approx(25.50)


def test_original_stop_and_target_still_apply(mgr):
    open_position(mgr)
    a = manage(mgr, 24.80)
    assert a.should_exit and a.exit_reason == ExitReason.STOP_HIT and a.exit_price == 24.85
    mgr2 = PositionManager(max_concurrent_positions=1, cost_model=FIXED)
    open_position(mgr2)
    a = manage(mgr2, 26.05)
    assert a.should_exit and a.exit_reason == ExitReason.TARGET_HIT


def test_off_by_default_keeps_the_shipped_rules(mgr):
    p = open_position(mgr)
    manage(mgr, 25.17, profit_floor_net=None)
    assert p.breakeven_moved and p.current_stop >= 25.0

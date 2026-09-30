"""Transaction cost model.

The point of costing per SHARE rather than in basis points is that the one-cent
minimum tick, not a percentage, is what actually binds this strategy: over half its
traded notional is in sub-$10 miners where a penny is 10+ bps.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest

from execution.costs import TransactionCostModel


def test_penny_spread_costs_half_a_cent_per_share_per_side():
    model = TransactionCostModel(spread_ticks=1.0)
    assert model.per_side(price=50.0, shares=1000) == 5.0
    assert model.round_trip(entry_price=50.0, exit_price=51.0, shares=1000) == 10.0


def test_same_notional_costs_far_more_in_a_cheap_stock():
    """The whole reason for a per-share model. Equal dollar positions, 25x apart in
    relative cost -- a flat-bps model would price these identically and hide it."""
    model = TransactionCostModel(spread_ticks=1.0)
    cheap_bps = model.round_trip(4.05, 4.05, int(25000 / 4.05)) / (25000 * 2) * 10000
    rich_bps = model.round_trip(94.61, 94.61, int(25000 / 94.61)) / (25000 * 2) * 10000
    assert round(cheap_bps, 1) == 12.3
    assert round(rich_bps, 1) == 0.5


def test_impact_and_commission_stack_on_top_of_spread():
    model = TransactionCostModel(spread_ticks=1.0, impact_bps=2.0, commission_per_order=1.0)
    # 1000 shares at $10: $5 spread + $2 impact (2bps of $10k) + $1 commission
    assert model.per_side(price=10.0, shares=1000) == 8.0


def test_crossing_fraction_scales_only_the_spread_term():
    model = TransactionCostModel(spread_ticks=1.0, impact_bps=2.0, crossing_fraction=0.5)
    # spread halves to $2.50, impact untouched at $2
    assert model.per_side(price=10.0, shares=1000) == 4.5


def test_default_model_is_free_and_reports_itself_disabled():
    """An omitted cost model must reproduce the old frictionless backtest exactly."""
    model = TransactionCostModel()
    assert not model.enabled
    assert model.round_trip(10.0, 11.0, 1000) == 0.0


def test_zero_or_negative_shares_cost_nothing():
    model = TransactionCostModel(spread_ticks=1.0, commission_per_order=5.0)
    assert model.per_side(price=10.0, shares=0) == 0.0


def test_from_config_reads_the_shipped_defaults():
    from config_loader import load_config
    model = TransactionCostModel.from_config(load_config().risk)
    assert model.spread_ticks == 1.0
    assert model.crossing_fraction == 1.0
    assert model.enabled


def test_from_config_tolerates_a_missing_section():
    assert not TransactionCostModel.from_config({}).enabled


# --- IBKR Pro Tiered commission (config/risk.yaml, from 2026-09-30) ---------------

def _ibkr():
    return TransactionCostModel(commission_per_share=0.0035, commission_min_per_order=0.35,
                                commission_max_pct_of_value=1.0, fees_per_share=0.0032,
                                sell_fees_per_share=0.000166)


def test_per_share_rate_above_the_minimum():
    # 125 shares of a $20 stock: 125 x $0.0035 = $0.4375, plus 125 x $0.0032 fees
    assert _ibkr().commission(20.0, 125) == pytest.approx(0.4375 + 0.40)


def test_minimum_per_order_for_a_small_share_count():
    # 16 shares of a $150 stock: 16 x $0.0035 = $0.056, raised to the $0.35 minimum
    assert _ibkr().commission(150.0, 16) == pytest.approx(0.35 + 16 * 0.0032)


def test_one_percent_cap_matches_what_the_paper_account_charged():
    """2026-09-24, DUT160852: a 1-share $18.69 order was charged $0.19. The $0.35
    minimum is capped at 1% of the order's value, $0.187."""
    assert round(_ibkr().commission(18.69, 1), 2) == 0.19


def test_sales_pay_the_finra_fee_and_buys_do_not():
    m = _ibkr()
    assert m.commission(20.0, 125, sell=True) - m.commission(20.0, 125) == pytest.approx(125 * 0.000166)


def test_a_partial_exit_is_a_third_order_with_its_own_minimum():
    from datetime import datetime, timezone
    from models.trade import ExitReason
    from positions.position_manager import PositionManager
    t0 = datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc)
    m = _ibkr()
    pm = PositionManager(10, cost_model=m)
    pos = pm.open_position("XYZ", "XLV", t0, 150.0, 16, 149.0, 153.0, "VWAP_RECLAIM", 80.0)
    pos.apply_partial_exit(t0, 151.5, 5, "partial_target_1_5R")
    trade = pm.close_position("XYZ", t0, 152.0, ExitReason.TRAILING_STOP)
    expected = m.commission(150.0, 16) + m.commission(151.5, 5, sell=True) + m.commission(152.0, 11, sell=True)
    assert trade.broker_commission == pytest.approx(expected)
    assert trade.broker_commission > 3 * 0.35
    assert trade.gross_profit - trade.net_profit == pytest.approx(expected)


def test_shipped_config_charges_ibkr_pro_fixed():
    """The account holder chose IBKR Pro Fixed on 2026-09-30: $0.005/share, $1.00
    minimum, 1% cap, exchange fees included."""
    from config_loader import load_config
    m = TransactionCostModel.from_config(load_config().risk)
    assert (m.commission_per_share, m.commission_min_per_order, m.commission_max_pct_of_value) == (0.005, 1.00, 1.0)
    assert m.fees_per_share == 0.0 and m.sell_fees_per_share == 0.000166
    # 125 shares of a $20 stock: $0.625 raised to the $1.00 minimum
    assert m.commission(20.0, 125) == pytest.approx(1.00)
    # 400 shares: $2.00, above the minimum
    assert m.commission(20.0, 400) == pytest.approx(2.00)
    # still capped at 1% of value: the paper account's 1-share order
    assert round(m.commission(18.69, 1), 2) == 0.19

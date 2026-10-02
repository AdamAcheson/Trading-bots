"""The healthcare momentum rules (bots/healthcare/MOMENTUM_RULES.md), piece by piece."""

import pytest

from strategy import healthcare_momentum as hm

P = hm.Params()


# --- indicators -------------------------------------------------------------------

def test_ema_uses_two_over_n_plus_one():
    out = hm.ema([10.0, 12.0], 9)            # k = 0.2
    assert out == pytest.approx([10.0, 10.4])


def test_rsi_all_gains_is_100_and_mixed_is_wilder():
    assert hm.rsi([float(i) for i in range(20)], 14)[14] == 100.0
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
              45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
    r = hm.rsi(closes, 14)
    assert r[13] is None
    assert r[14] == pytest.approx(70.46, abs=0.05)     # Wilder's textbook example
    assert r[15] == pytest.approx(66.25, abs=0.1)


def test_macd_histogram_is_macd_minus_signal():
    closes = [100 + (i % 7) - 0.1 * i for i in range(60)]
    line, sig, hist = hm.macd(closes)
    assert all(h == pytest.approx(a - b) for a, b, h in zip(line, sig, hist))


def test_atr_is_wilder_smoothed_true_range():
    highs, lows, closes = [11.0] * 15, [10.0] * 15, [10.5] * 15
    highs[14], lows[14] = 13.0, 10.5            # true range 2.5 on the 15th bar
    a = hm.atr(highs, lows, closes, 14)
    assert a[12] is None and a[13] == pytest.approx(1.0)
    assert a[14] == pytest.approx((1.0 * 13 + 2.5) / 14)


# --- score --------------------------------------------------------------------------

def reading(**kw):
    base = dict(price=100.0, ema9=99.8, ema20=99.5, ema20_prev=99.4, rsi14=60.0, macd=0.2,
                macd_signal=0.1, macd_hist=0.1, atr14=0.5, bar_volume=13000, slot_avg_volume=10000)
    base.update(kw)
    return hm.Reading(**base)


def test_everything_true_scores_100():
    assert hm.score(reading(), xlv_bullish=True)["total"] == 100.0


def test_one_block_may_fail_and_still_reach_75():
    s = hm.score(reading(bar_volume=5000), xlv_bullish=False)   # confirmation fails: 75
    assert s["total"] == 75.0


def test_failing_momentum_macd_costs_twenty():
    s = hm.score(reading(macd=0.05, macd_signal=0.1, macd_hist=-0.05), xlv_bullish=True)
    assert s["total"] == 80.0
    s = hm.score(reading(macd=0.05, macd_signal=0.1, macd_hist=-0.05, rsi14=70), xlv_bullish=True)
    assert s["total"] == 70.0                                    # below 75: no trade


def test_rsi_band_is_inclusive_52_to_68():
    assert hm.score(reading(rsi14=52.0), True)["rsi_in_band"] == 10.0
    assert hm.score(reading(rsi14=68.0), True)["rsi_in_band"] == 10.0
    assert hm.score(reading(rsi14=68.1), True)["rsi_in_band"] == 0.0


def test_entry_quality_needs_price_within_one_atr_of_ema9():
    assert hm.score(reading(price=100.3), True)["entry_quality"] == 15.0     # 99.8 + 0.5
    assert hm.score(reading(price=100.31), True)["entry_quality"] == 0.0


def test_xlv_needs_trend_and_vwap():
    assert hm.xlv_is_bullish(150.0, 149.8, 149.5, 149.4, 149.9)
    assert not hm.xlv_is_bullish(150.0, 149.8, 149.5, 149.4, 150.1)     # below VWAP
    assert not hm.xlv_is_bullish(150.0, 149.8, 149.5, 149.6, 149.0)     # EMA20 falling


# --- size -----------------------------------------------------------------------------

def test_position_cap_usually_binds():
    # $150 stock, ATR 0.30: risk 0.375/share -> 66 by risk, 8 by the $1,250 cap
    assert hm.position_size(150.0, 0.30) == 8


def test_risk_cap_binds_on_a_volatile_cheap_stock():
    # $20 stock, ATR 0.40: risk 0.50/share -> 50 by risk, 62 by capital
    assert hm.position_size(20.0, 0.40) == 50


def test_no_shares_when_price_exceeds_the_cap():
    assert hm.position_size(1300.0, 3.0) == 0


# --- stops ------------------------------------------------------------------------------

def test_initial_stop_is_one_and_a_quarter_atr():
    pos = hm.Position("X", "t", 100.0, 10, 0.4, 80.0)
    assert pos.initial_stop == pytest.approx(99.5)
    assert pos.open_risk == pytest.approx(5.0)


def test_stop_fills_at_stop_or_a_lower_open():
    pos = hm.Position("X", "t", 100.0, 10, 0.4, 80.0)
    assert pos.stop_fill(bar_open=99.9, bar_low=99.4) == pytest.approx(99.5 - 0.005)
    assert pos.stop_fill(bar_open=99.2, bar_low=99.0) == pytest.approx(99.2 - 0.005)
    assert pos.stop_fill(bar_open=99.9, bar_low=99.6) is None


def test_trailing_starts_at_plus_one_r_and_only_moves_up():
    pos = hm.Position("X", "t", 100.0, 10, 0.4, 80.0)     # R = 0.5
    pos.after_bar(100.4)
    assert not pos.trailing and pos.stop == pytest.approx(99.5)
    pos.after_bar(100.5)                                   # +1R reached
    assert pos.trailing and pos.stop == pytest.approx(100.0)
    pos.after_bar(100.3)                                   # a lower high: stop stays
    assert pos.stop == pytest.approx(100.0)
    pos.after_bar(101.0)
    assert pos.stop == pytest.approx(100.5)
    assert pos.open_risk == 0.0                            # locked in: frees risk budget

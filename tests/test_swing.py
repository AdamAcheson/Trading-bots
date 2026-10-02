"""Swing bot rules (bots/swing/RULES.md), piece by piece."""

import pytest

from strategy import swing

P = swing.Params()


def test_sma_and_atr():
    assert swing.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    a = swing.atr([11, 12, 13], [9, 10, 11], [10, 11, 12], 2)
    assert a == [None, 2.0, 2.0]                 # true ranges 2, 2, 2


def series(closes, volume=1_000_000):
    n = len(closes)
    return swing.Daily([f"d{i:04d}" for i in range(n)], list(closes), [c * 1.01 for c in closes],
                       [c * 0.99 for c in closes], list(closes), [volume] * n)


def rising(n=260, start=10.0, step=0.01):
    return [start * (1 + step) ** i for i in range(n)]


def test_a_strong_uptrending_breakout_qualifies():
    s = series(rising())
    r = swing.entry_signal(s, 259)
    assert r == pytest.approx((1.01) ** 126 - 1)   # about +250%


def test_not_a_breakout_does_not_qualify():
    closes = rising()
    closes[-1] = closes[-2] * 0.999                 # today below the prior 20-day high
    assert swing.entry_signal(series(closes), 259) is None


def test_weak_six_months_does_not_qualify():
    closes = rising(step=0.001)                     # +13% over 126 days
    assert swing.entry_signal(series(closes), 259) is None


def test_illiquid_or_cheap_does_not_qualify():
    assert swing.entry_signal(series(rising(), volume=10_000), 259) is None
    assert swing.entry_signal(series(rising(start=0.2)), 259) is None    # ends near $2.7: under $5


def test_needs_two_hundred_days():
    assert swing.entry_signal(series(rising()), 150) is None


def test_trailing_stop_three_atr_below_the_highest_close():
    h = swing.Holding("X", "d", entry=100.0, shares=10, atr_at_entry=2.0)
    assert h.stop == 94.0
    assert not h.on_close(110.0)                   # stop rises to 104
    assert h.stop == 104.0
    assert not h.on_close(105.0)                   # a lower close never lowers it
    assert h.stop == 104.0
    assert h.on_close(103.9)                       # below: sell at the next open


def test_sector_filter():
    etf = series(rising(step=0.002))
    assert swing.sector_ok(etf, 259)
    falling = series([100 * 0.999 ** i for i in range(260)])
    assert not swing.sector_ok(falling, 259)
    assert not swing.sector_ok(etf, None)

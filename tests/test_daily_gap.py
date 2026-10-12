"""S&P 500 daily gap-and-go (src/strategy/daily_gap.py)."""

import pytest

from strategy import daily_gap as dg

P = dg.Params()
N = 230


def make(**today):
    """230 days (closes 90 then 100, high 101, low 99, volume 1e6 -> $100M a day), then a signal day
    (index 230) that passes every condition unless overridden."""
    dates = [f"d{i:04d}" for i in range(N + 1)]
    opens = [100.0] * N + [104.0]
    highs = [101.0] * N + [108.0]
    lows = [99.0] * N + [103.5]
    closes = [90.0] * 100 + [100.0] * (N - 100) + [107.0]      # SMA200 is about 95
    volumes = [1_000_000.0] * N + [2_500_000.0]
    for key, (i, v) in {"open": (opens, today.get("open")), "high": (highs, today.get("high")),
                        "low": (lows, today.get("low")), "close": (closes, today.get("close")),
                        "volume": (volumes, today.get("volume"))}.items():
        if v is not None:
            key_list = i
            key_list[N] = v
    return dg.Series(dates, opens, highs, lows, closes, volumes)


def test_signal_when_everything_holds():
    s = make()
    ratio, low = dg.entry_signal(s, N, "a", P)
    assert ratio == pytest.approx(2.5) and low == 103.5


def test_not_a_member_yet():
    s = make()
    assert dg.entry_signal(s, N, None, P) is None
    assert dg.entry_signal(s, N, "z", P) is None          # joined after day t ("z" > "d0230")


def test_each_condition_blocks():
    assert dg.entry_signal(make(open=102.9), N, "a", P) is None                  # D3: gap under 3%
    assert dg.entry_signal(make(close=101.0, high=108.0), N, "a", P) is None     # D1: not above yesterday's high
    assert dg.entry_signal(make(close=103.0), N, "a", P) is None                 # I2: red day (close < open)
    assert dg.entry_signal(make(close=105.0, high=110.0), N, "a", P) is None     # I2: lower half of the range
    assert dg.entry_signal(make(volume=1_900_000.0), N, "a", P) is None          # I3: volume under 2x
    s = make()
    s.real_closes[N] = 9.99
    assert dg.entry_signal(s, N, "a", P) is None                                 # price under $10
    low_dollar = make()
    low_dollar.dollar_vol[N] = 1_000_000
    assert dg.entry_signal(low_dollar, N, "a", P) is None                        # not liquid


def test_below_the_200_day_average_yesterday():
    s = make()
    s.sma200[N - 1] = 100.5                                                      # yesterday's close 100 < SMA
    assert dg.entry_signal(s, N, "a", P) is None


def test_zero_range_day_is_not_a_signal():
    assert dg.entry_signal(make(open=107.0, high=107.0, low=107.0, close=107.0), N, "a", P) is None


def test_exit_reasons():
    s = make()
    assert dg.exit_reason(s, N, 103.5, 1, P) is None
    assert dg.exit_reason(s, N, 108.0, 1, P) == "STOP"           # close 107 below the signal-day low
    assert dg.exit_reason(s, N, 103.5, 5, P) == "TIME_LIMIT"
    assert dg.exit_reason(s, N, 103.5, 4, P) is None

"""S&P 500 dip-buying rules (bots/sp500_dip/RULES.md)."""

import json
import os

import pytest

from strategy import sp500_dip as sd

P = sd.Params()


def series(closes, opens=None, volume=1_000_000, start=0):
    n = len(closes)
    dates = [f"2010-{1 + (start + i) // 28:02d}-{1 + (start + i) % 28:02d}" for i in range(n)]
    opens = opens or list(closes)
    return sd.Series(dates, list(opens), [c * 1.01 for c in closes], [c * 0.99 for c in closes],
                     list(closes), [volume] * n)


def uptrend_then_dip(n=250, drop=(0.98, 0.97)):
    closes = [50 * 1.002 ** i for i in range(n)]
    for d in drop:
        closes.append(closes[-1] * d)
    # opens equal to the prior close: no gaps
    opens = [closes[0]] + closes[:-1]
    return closes, opens


def test_real_price_matches_apple_around_its_splits():
    """Apple split 7-for-1 on 2014-06-09 and 4-for-1 on 2020-08-31, so the real close is
    28x the adjusted close before 2014-06-09, 4x until 2020-08-31, then equal."""
    daily, raw = os_path("daily", "AAPL.json"), os_path("daily_unadjusted", "AAPL.json")
    if not (os.path.exists(daily) and os.path.exists(raw)):
        pytest.skip("AAPL data not downloaded")
    rows = json.load(open(daily))
    s = sd.Series(*[list(c) for c in zip(*rows)]).with_real_closes({r[0]: r[4] for r in json.load(open(raw))})
    for day, factor in (("2014-06-06", 28), ("2014-06-10", 4), ("2020-08-28", 4), ("2020-08-31", 1)):
        i = s.index[day]
        assert s.real_closes[i] / s.closes[i] == pytest.approx(factor, rel=0.002)
    assert s.real_closes[s.index["2014-06-10"]] == pytest.approx(94.25, rel=0.002)


def test_missing_real_price_fails_the_minimum():
    closes, opens = uptrend_then_dip()
    s = series(closes, opens).with_real_closes({})
    assert sd.entry_signal(s, len(closes) - 1, True, "2000-01-01") is None


def os_path(*parts):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_cache", *parts)


def test_a_dip_in_a_strong_member_qualifies():
    closes, opens = uptrend_then_dip()
    s = series(closes, opens)
    i = len(closes) - 1
    r = sd.entry_signal(s, i, True, "2000-01-01")
    assert r is not None and r < 10


def test_needs_a_healthy_market_and_membership():
    closes, opens = uptrend_then_dip()
    s = series(closes, opens)
    i = len(closes) - 1
    assert sd.entry_signal(s, i, False, "2000-01-01") is None
    assert sd.entry_signal(s, i, True, "2099-01-01") is None      # joined later
    assert sd.entry_signal(s, i, True, None) is None


def test_real_price_under_15_is_skipped_even_if_adjusted_price_is_high():
    closes, opens = uptrend_then_dip()
    s = series(closes, opens)
    i = len(closes) - 1
    s.real_closes = [c / 10 for c in s.closes]                    # traded at about $6 then
    assert sd.entry_signal(s, i, True, "2000-01-01") is None
    s.real_closes = [c * 10 for c in s.closes]                    # adjusted low, real high: fine
    assert sd.entry_signal(s, i, True, "2000-01-01") is not None


def test_downtrend_thin_or_no_dip_is_skipped():
    closes, opens = uptrend_then_dip()
    assert sd.entry_signal(series(closes, opens, volume=100_000), len(closes) - 1, True, "2000-01-01") is None
    flat = [50 * 1.002 ** i for i in range(252)]
    assert sd.entry_signal(series(flat), 251, True, "2000-01-01") is None
    down = [80 * 0.998 ** i for i in range(250)] + [40, 39]
    assert sd.entry_signal(series(down), 251, True, "2000-01-01") is None


@pytest.mark.parametrize("back", [0, 1])
def test_a_news_gap_today_or_yesterday_is_skipped(back):
    closes, opens = uptrend_then_dip()
    i = len(closes) - 1
    opens[i - back] = closes[i - back - 1] * 0.95                 # opened 5% lower
    assert sd.entry_signal(series(closes, opens), i, True, "2000-01-01") is None


def test_exit_reasons():
    closes = [100.0] * 10
    s = series(closes)
    assert sd.exit_reason(s, 9, 100.0, 3, False) == "MARKET_SWITCH"
    s.closes[9] = 84.0
    assert sd.exit_reason(s, 9, 100.0, 3, True) == "DISASTER_STOP"
    s.closes[9] = 101.0
    s.sma5[9] = 100.0
    assert sd.exit_reason(s, 9, 100.0, 3, True) == "ABOVE_SMA5"
    s.closes[9] = 99.0
    assert sd.exit_reason(s, 9, 100.0, 9, True) is None
    assert sd.exit_reason(s, 9, 100.0, 10, True) == "TIME_LIMIT"


@pytest.mark.parametrize("cash, account, expected", [
    (5000, 5000, 2500),       # start: half the account
    (2500, 5000, 2500),       # second position with what is left
    (2300, 4800, 0),          # under $2,500 available: skipped
    (5000, 4800, 2500),       # account below $5,000: still $2,500 minimum
    (8000, 8000, 4000),       # grows with the account
    (20000, 20000, 5500),     # capped at $5,500
])
def test_buy_amount(cash, account, expected):
    assert sd.buy_amount(cash, account) == expected


def test_split_factor_uses_the_real_price():
    closes, opens = uptrend_then_dip()
    s = series(closes, opens).with_real_closes({})
    assert sd.split_factor(s, 5) == 1.0                           # no real price: no adjustment
    s.real_closes = [c * 40 for c in s.closes]                    # e.g. 4-for-1 then 10-for-1 later
    assert sd.split_factor(s, 5) == pytest.approx(40)
    s.real_closes[5] = None
    assert sd.split_factor(s, 5) == pytest.approx(40)             # falls back to the day before


def test_nvidia_2011_shares_and_commission_use_the_real_price():
    """Nvidia's adjusted 2011 price is under $1; it really traded near $19, so $2,500 buys
    about 130 shares and the commission is the $1 minimum, not ~$26 on 5,000+ shares."""
    daily, raw = os_path("daily", "NVDA.json"), os_path("daily_unadjusted", "NVDA.json")
    if not (os.path.exists(daily) and os.path.exists(raw)):
        pytest.skip("NVDA data not downloaded")
    s = sd.Series(*[list(c) for c in zip(*json.load(open(daily)))]).with_real_closes(
        {r[0]: r[4] for r in json.load(open(raw))})
    i = s.index["2011-03-10"]
    real_fill = s.opens[i] * sd.split_factor(s, i)
    assert 10 < real_fill < 30
    shares = int(2500 // real_fill)
    from execution.costs import TransactionCostModel
    fixed = TransactionCostModel(commission_per_share=0.005, commission_min_per_order=1.0,
                                 commission_max_pct_of_value=1.0)
    assert 80 < shares < 250 and fixed.commission(real_fill, shares) == 1.0

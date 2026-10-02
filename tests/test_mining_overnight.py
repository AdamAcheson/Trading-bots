"""Mining buy-the-close, sell-the-open rules (bots/mining_overnight/RULES.md)."""

from strategy import mining_overnight as mo


def series(closes, volume=2_000_000):
    n = len(closes)
    return mo.Series([f"d{i:04d}" for i in range(n)], list(closes), [c * 1.01 for c in closes],
                     [c * 0.99 for c in closes], list(closes), [volume] * n)


def uptrend_then_dip():
    closes = [10 * 1.003 ** i for i in range(250)]
    closes += [closes[-1] * 0.97, closes[-1] * 0.94]       # two sharp down days
    return closes


def test_a_dip_in_an_uptrend_qualifies():
    s = series(uptrend_then_dip())
    r = mo.entry_signal(s, len(s.closes) - 1, etf_ok=True)
    assert r is not None and r < 10


def test_needs_the_sector_uptrend():
    s = series(uptrend_then_dip())
    assert mo.entry_signal(s, len(s.closes) - 1, etf_ok=False) is None


def test_no_dip_no_entry():
    s = series([10 * 1.003 ** i for i in range(252)])
    assert mo.entry_signal(s, 251, etf_ok=True) is None


def test_below_sma200_no_entry():
    closes = [20 * 0.998 ** i for i in range(250)] + [9.0, 8.5]
    assert mo.entry_signal(series(closes), 251, etf_ok=True) is None


def test_cheap_or_thin_no_entry():
    closes = [c / 8 for c in uptrend_then_dip()]           # ends near $2.48: under $3
    assert mo.entry_signal(series(closes), 251, etf_ok=True) is None
    assert mo.entry_signal(series(uptrend_then_dip(), volume=10_000), 251, etf_ok=True) is None


def test_exits():
    closes = uptrend_then_dip() + [25.0]            # well above SMA5
    s = series(closes)
    i = len(closes) - 1
    assert mo.exit_reason(s, i, entry=19.0, days_held=1) == "ABOVE_SMA5"
    s2 = series(uptrend_then_dip() + [15.0])
    assert mo.exit_reason(s2, i, entry=18.0, days_held=1) == "DISASTER_STOP"
    s3 = series(uptrend_then_dip() + [uptrend_then_dip()[-1]])
    assert mo.exit_reason(s3, i, entry=s3.closes[-1], days_held=10) == "TIME_LIMIT"
    assert mo.exit_reason(s3, i, entry=s3.closes[-1], days_held=3) is None

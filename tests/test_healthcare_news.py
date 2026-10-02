"""Healthcare news-day drift rules (bots/healthcare_news/RULES.md)."""

from strategy import healthcare_news as hn


def series(closes, volumes, highs=None, lows=None):
    n = len(closes)
    return hn.Series([f"d{i:04d}" for i in range(n)], list(closes),
                     highs or [c * 1.005 for c in closes], lows or [c * 0.995 for c in closes],
                     list(closes), list(volumes))


def base(n=60, price=50.0, vol=1_000_000):
    return [price] * n, [vol] * n


def test_a_jump_on_heavy_volume_that_holds_is_a_news_day():
    c, v = base()
    c[-1], v[-1] = 53.0, 3_500_000                         # +6%, 3.5x volume
    s = series(c, v, highs=[x * 1.005 for x in c[:-1]] + [53.5], lows=[x * 0.995 for x in c[:-1]] + [51.0])
    assert hn.news_day(s, 59) == 3.5


def test_too_small_a_jump_or_volume_is_not():
    c, v = base()
    c[-1], v[-1] = 52.0, 3_500_000                         # +4%
    assert hn.news_day(series(c, v), 59) is None
    c[-1], v[-1] = 53.0, 2_500_000                         # 2.5x
    assert hn.news_day(series(c, v), 59) is None


def test_a_jump_that_faded_into_the_close_is_not():
    c, v = base()
    c[-1], v[-1] = 53.0, 3_500_000
    s = series(c, v, highs=[x * 1.005 for x in c[:-1]] + [58.0], lows=[x * 0.995 for x in c[:-1]] + [51.0])
    assert hn.news_day(s, 59) is None                      # closed below the range midpoint 54.5


def test_small_or_thin_stocks_are_skipped():
    c, v = base(price=8.0)
    c[-1], v[-1] = 8.6, 3_500_000
    assert hn.news_day(series(c, v), 59) is None           # under $10
    c, v = base(price=50.0, vol=100_000)                   # $5M a day: under $20M
    c[-1], v[-1] = 53.0, 350_000
    assert hn.news_day(series(c, v), 59) is None


def test_exits():
    c, v = base()
    s = series(c + [48.0], v + [1_000_000])
    assert hn.exit_reason(s, 60, news_low=49.0, days_held=3) == "NEWS_FAILED"
    s = series(c + [55.0], v + [1_000_000])
    assert hn.exit_reason(s, 60, news_low=49.0, days_held=40) == "TIME_40_DAYS"
    assert hn.exit_reason(s, 60, news_low=49.0, days_held=39) is None

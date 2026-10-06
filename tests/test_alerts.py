"""Morning alerts (src/alerts.py)."""

from alerts import Alert, Bar, check, read_watchlist, summary


def bars(closes, volumes=None):
    volumes = volumes or [1_000_000] * len(closes)
    return [Bar(f"d{i:03d}", c, c * 1.01, c * 0.99, c, v) for i, (c, v) in enumerate(zip(closes, volumes))]


def flat(n=260, price=100.0):
    return [price + (0.5 if i % 2 else -0.5) for i in range(n)]


def test_quiet_day_no_alert():
    assert check("X", bars(flat())) is None


def test_big_move_up_and_down():
    # the last flat close is $100.50
    a = check("X", bars(flat() + [105.0]))
    assert a and a.reasons == ["up 4.5%", "new 52-week high"]
    a = check("X", bars(flat() + [96.0]))
    assert a and a.reasons == ["down 4.5%", "new 52-week low"]
    assert check("X", bars(flat() + [100.0])) is None              # a quiet day


def test_volume_spike():
    closes = flat() + [100.4]
    vols = [1_000_000] * 260 + [2_500_000]
    a = check("X", bars(closes, vols))
    assert a and a.reasons == ["volume 2.5x normal"]
    assert check("X", bars(closes, [1_000_000] * 260 + [1_900_000])) is None


def test_new_52_week_high_and_low():
    a = check("X", bars(flat() + [101.0]))
    assert a and a.reasons == ["new 52-week high"]
    a = check("X", bars(flat() + [99.0]))
    assert a and a.reasons == ["new 52-week low"]


def test_short_history_skips_volume_and_52_week_checks():
    assert check("X", bars([100.0] * 10 + [101.0], [1] * 10 + [10])) is None
    assert check("X", bars([100.0])) is None


def test_read_watchlist():
    text = "aapl, msft  # big tech\n\nNVDA\n# comment line\nAAPL xom"
    assert read_watchlist(text) == ["AAPL", "MSFT", "NVDA", "XOM"]


def test_summary():
    alerts = [Alert("AAA", "2026-10-02", 10.0, 0.05, ["up 5.0%"]),
              Alert("BBB", "2026-10-02", 20.0, -0.08, ["down 8.0%", "volume 3.0x normal"])]
    text = summary(alerts, 25, ["CCC (error)"], "2026-10-02")
    lines = text.splitlines()
    assert lines[0] == "Morning alerts (close of 2026-10-02): 2 of 25 stocks flagged"
    assert lines[1].startswith("- BBB")                            # biggest move first
    assert "Could not fetch: CCC (error)" in text
    assert text.endswith("not a recommendation.")
    assert "nothing flagged in 25 stocks" in summary([], 25, [], "2026-10-02")

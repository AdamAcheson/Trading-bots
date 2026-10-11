"""Silver gap-and-go (src/strategy/gap_go.py, scripts/backtest_gap_go.py)."""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from models.bar import Bar  # noqa: E402
from strategy import gap_go as gg  # noqa: E402
import backtest_gap_go as bt  # noqa: E402

ET = ZoneInfo("America/New_York")
P = gg.Params()


def ts(day, t):
    h, m = map(int, t.split(":"))
    y, mo, d = map(int, day.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=ET)


def day_bars(day, opens_closes, volume=1000, start_t=0):
    """5-minute bars from 09:30; opens_closes = [(open, high, low, close), ...]."""
    out = []
    for k, (o, h, l, c) in enumerate(opens_closes):
        mins = 9 * 60 + 30 + 5 * (start_t + k)
        out.append(Bar(ts(day, f"{mins // 60:02d}:{mins % 60:02d}"), o, h, l, c, volume))
    return out


def test_sma():
    assert gg.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert gg.sma([1.0], 3) == [None]


def test_day_context_conditions():
    c = gg.DayContext(prev_high=10.5, prev_close=10.0, prev_sma200=9.0, open=10.3)
    assert c.d2() and c.d3(P) and c.gap == pytest.approx(0.03)
    assert not gg.DayContext(10.5, 10.0, 11.0, 10.3).d2()           # below the 200-day average
    assert not gg.DayContext(10.5, 10.0, None, 10.3).d2()           # no 200 days of history
    assert not gg.DayContext(10.5, 10.0, 9.0, 10.29).d3(P)          # gap just under 3%


def test_entry_conditions_each_one_blocks():
    c = gg.DayContext(10.5, 10.0, 9.0, 10.4)
    ok = gg.entry_conditions(11.0, c, 10.9, 2.0, P)
    assert gg.signal(ok)
    assert not gg.signal(gg.entry_conditions(10.5, c, 10.0, 2.0, P))      # D1: not above yesterday's high
    assert not gg.signal(gg.entry_conditions(11.0, c, 11.0, 2.0, P))      # I2: only equals the high so far
    assert not gg.signal(gg.entry_conditions(11.0, c, None, 2.0, P))      # I2: no earlier bar
    assert not gg.signal(gg.entry_conditions(11.0, c, 10.9, 1.99, P))    # I3
    assert not gg.signal(gg.entry_conditions(11.0, c, 10.9, None, P))    # I3: short history
    cheap = gg.DayContext(9.0, 8.0, 7.0, 8.3)
    assert not gg.signal(gg.entry_conditions(9.5, cheap, 9.4, 3.0, P))    # under the $10 gate


def make_series(n_prior=15, today_volume=5000, gap_open=10.4):
    """15 prior sessions of flat quiet bars (high 10.1; daily closes 9.0 then 10.0, so yesterday is above its average) then a gap-up day."""
    bars = []
    daily = []
    for i in range(n_prior):
        d = f"2026-06-{i + 1:02d}"
        bars += day_bars(d, [(10.0, 10.1, 9.9, 10.0)] * 78, volume=1000)
        daily.append((d, 10.1, 9.0 if i < 10 else 10.0))
    today = "2026-06-30"
    rows = [(gap_open, gap_open + 0.05, gap_open - 0.05, gap_open)]                 # 09:30
    rows += [(gap_open, gap_open + 0.1, gap_open - 0.05, gap_open + 0.05)]          # 09:35
    rows += [(gap_open + 0.05, gap_open + 0.5, gap_open + 0.05, gap_open + 0.45)]   # 09:40 breakout
    rows += [(gap_open + 0.45, gap_open + 1.5, gap_open + 0.4, gap_open + 1.4)]     # 09:45
    rows += [(gap_open + 1.4, gap_open + 1.5, gap_open + 1.3, gap_open + 1.4)] * 72
    bars += day_bars(today, rows, volume=today_volume)
    daily.append((today, 11.9, 11.8))
    s = gg.Series("TST", bars, daily[:-1] + [daily[-1]], gg.Params(sma_days=15))
    return s, today


def test_cumulative_volume_and_rvol():
    s, today = make_series()
    assert s.cum_volume("2026-06-01", "09:30") == 1000
    assert s.cum_volume("2026-06-01", "09:40") == 3000
    assert s.avg_cum_volume(today, "09:40", 14) == 3000
    assert s.rvol(today, "09:40", 14) == pytest.approx(5.0)
    assert s.avg_cum_volume("2026-06-10", "09:40", 14) is None          # fewer than 14 prior sessions


def test_high_before_excludes_the_signal_bar():
    s, today = make_series()
    assert s.high_before(today, "09:30") is None
    assert s.high_before(today, "09:35") == pytest.approx(10.45)
    assert s.high_before(today, "09:40") == pytest.approx(10.5)        # 09:35 bar high 10.5


def test_context_uses_the_previous_session():
    s, today = make_series()
    c = s.context(today)
    assert c.prev_close == 10.0 and c.prev_high == 10.1 and c.open == pytest.approx(10.4)


def test_position_stops_and_trailing():
    pos = gg.Position("T", "x", entry=100.0, shares=10, atr_at_entry=0.2, rvol=2.0, p=P)
    assert pos.risk_per_share == pytest.approx(0.5)                     # the 0.5% floor beats 1.25 x 0.2
    assert pos.initial_stop == pytest.approx(99.5)
    assert pos.stop_fill(100.0, 99.6) is None
    assert pos.stop_fill(100.0, 99.5) == pytest.approx(99.5 - 0.005)
    assert pos.stop_fill(99.0, 98.0) == pytest.approx(99.0 - 0.005)     # gapped through: bar open
    pos.after_bar(100.6)                                                # +1R reached
    assert pos.trailing and pos.stop == pytest.approx(100.1)
    pos.after_bar(100.2)
    assert pos.stop == pytest.approx(100.1)                             # never moves down
    big = gg.Position("T", "x", 100.0, 10, atr_at_entry=1.0, rvol=2.0, p=P)
    assert big.risk_per_share == pytest.approx(1.25)                    # the ATR beats the floor


def test_shares_for():
    assert gg.shares_for(12.5, P) == 200
    assert gg.shares_for(2600.0, P) == 0


def test_simulate_takes_the_breakout_and_sells_at_1550():
    s, today = make_series()
    days = [today]
    from execution.costs import TransactionCostModel
    res = bt.simulate({"TST": s}, days, gg.Params(sma_days=15), TransactionCostModel())
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["entry_time"] == f"{today}T09:45"                          # signal bar 09:40, filled at 09:45's open
    assert t["entry_price"] == pytest.approx(10.85 + 0.005)
    assert t["shares"] == int(2500 // 10.85)
    assert t["exit_reason"] in ("END_OF_DAY", "TRAILING_STOP")
    assert res["funnel"]["I3"] == 1 and res["funnel"]["taken"] == 1


def test_simulate_no_trade_on_normal_volume():
    s, today = make_series(today_volume=1500)                           # rvol 1.5
    from execution.costs import TransactionCostModel
    res = bt.simulate({"TST": s}, [today], gg.Params(sma_days=15), TransactionCostModel())
    assert res["trades"] == [] and res["funnel"]["I2"] == 1 and res["funnel"]["I3"] == 0

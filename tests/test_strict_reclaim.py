"""Stricter VWAP reclaim (docs/PREREG_STRICT_RECLAIM.md): a 1-4 bar dip from above VWAP,
a reclaim bar on above-normal volume for its clock time, and entry within 0.5 x ATR of
VWAP, on top of the shipped reclaim."""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from config_loader import load_config
from data.market_data import Quote
from models.bar import Bar
from models.signal import RejectionReason
from strategy.setups import detect_vwap_reclaim, strict_reclaim_rejection
from strategy.signal_engine import evaluate_ticker

from test_ema_trend_filter import make_bot
from test_signals import make_ctx, orb_strategy

T0 = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def bar(i, o, h, l, c, v):
    return Bar(timestamp=T0 + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=v)


def session(dip_bars=2, reclaim_volume=5000, above_before=True):
    """VWAP anchored near $10 by heavy early volume; then (optionally) above VWAP, a dip,
    a reclaim, a retest that holds and a green confirmation bar."""
    bars = [bar(i, 10.0, 10.05, 9.95, 10.0, 100_000) for i in range(10)]
    if above_before:
        bars += [bar(len(bars), 10.2, 10.25, 10.15, 10.2, 1000) for _ in range(3)]
    for _ in range(dip_bars):
        bars.append(bar(len(bars), 9.95, 9.95, 9.85, 9.9, 1000))
    bars.append(bar(len(bars), 9.95, 10.10, 9.95, 10.08, reclaim_volume))     # reclaim
    bars.append(bar(len(bars), 10.05, 10.08, 10.03, 10.06, 1200))             # retest holds
    bars.append(bar(len(bars), 10.05, 10.09, 10.04, 10.08, 1300))             # green confirm
    return bars


def check(bars, norm=2000.0, atr=0.2):
    return strict_reclaim_rejection(bars, [norm] * len(bars), atr, lookback_bars=6)


def test_the_test_session_is_a_shipped_reclaim():
    assert detect_vwap_reclaim(session(), lookback_bars=6).matched


def test_a_quick_reclaim_on_heavy_volume_near_vwap_qualifies():
    assert check(session()) is None


@pytest.mark.parametrize("dip", [1, 4])
def test_dips_of_one_to_four_bars_qualify(dip):
    assert check(session(dip_bars=dip)) is None


def test_a_five_bar_dip_is_too_long():
    assert check(session(dip_bars=5)) == "strict_dip_too_long"


def test_the_stock_must_have_been_above_vwap_before_the_dip():
    # Without the above-VWAP bars the dip runs back into the opening bars, which close
    # exactly at VWAP: far more than four bars at or below it.
    assert check(session(above_before=False)) == "strict_dip_too_long"
    opening_dip = [bar(0, 10.0, 10.05, 9.85, 9.86, 1000), bar(1, 9.9, 9.95, 9.8, 9.85, 1000),
                   bar(2, 9.9, 10.1, 9.9, 10.05, 5000), bar(3, 10.0, 10.06, 10.0, 10.04, 1200),
                   bar(4, 10.02, 10.08, 10.01, 10.07, 1300)]
    assert check(opening_dip) == "strict_not_above_before_dip"


def test_reclaim_volume_must_be_above_normal_for_its_time():
    assert check(session(reclaim_volume=1500), norm=2000.0) == "strict_reclaim_volume_not_above_normal"
    assert check(session(reclaim_volume=2000), norm=2000.0) == "strict_reclaim_volume_not_above_normal"
    assert check(session(reclaim_volume=2001), norm=2000.0) is None


def test_no_volume_history_rejects():
    bars = session()
    assert strict_reclaim_rejection(bars, [None] * len(bars), 0.2, lookback_bars=6) == "strict_no_volume_history"


def test_entry_too_far_above_vwap_rejects():
    # The confirmation closes about $0.08 above VWAP: within 0.5 x $0.20, not 0.5 x $0.10.
    assert check(session(), atr=0.2) is None
    assert check(session(), atr=0.1) == "strict_too_far_above_vwap"


def test_signal_engine_rejects_a_loose_reclaim_only_when_enabled():
    config = load_config()
    strat = copy.deepcopy(orb_strategy(config))
    strat["setups"]["enable_orb_pullback"] = False
    loose = session(dip_bars=5)
    ctx = make_ctx(config, bars=loose, bar_volume_norms=[2000.0] * len(loose))
    off = evaluate_ticker(ctx, strat, config.risk)
    strat["setups"]["strict_vwap_reclaim"]["enabled"] = True
    on = evaluate_ticker(ctx, strat, config.risk)
    assert on.rejection_reason == RejectionReason.REJECTED_NO_SETUP
    assert on.extra["strict_reclaim_detail"] == "strict_dip_too_long"
    assert off.extra.get("strict_reclaim_detail") is None


def test_off_by_default():
    assert load_config().strategy["setups"]["strict_vwap_reclaim"]["enabled"] is False


def test_volume_norms_average_the_same_clock_time_over_previous_sessions(tmp_path):
    bot, provider = make_bot(tmp_path, enabled=False)
    strict = bot.config.strategy["setups"]["strict_vwap_reclaim"]
    strict["enabled"] = True
    days = [2, 3, 4, 5, 6, 9]                      # six previous sessions
    for d, day in enumerate(days):
        start = datetime(2026, 3, day, 14, 30, tzinfo=timezone.utc)
        for i in range(3):
            ts = start + timedelta(minutes=5 * i)
            provider.push_bar("AG", Bar(timestamp=ts, open=10, high=10.1, low=9.9, close=10,
                                        volume=1000 * (d + 1) * (i + 1)))
    today = datetime(2026, 3, 10, 14, 30, tzinfo=timezone.utc)
    todays = []
    for i in range(2):
        b = Bar(timestamp=today + timedelta(minutes=5 * i), open=10, high=10.1, low=9.9, close=10, volume=1)
        provider.push_bar("AG", b)
        todays.append(b)
    provider.push_quote("AG", Quote(bid=9.99, ask=10, last=10, timestamp=todays[-1].timestamp),
                        received_at=todays[-1].timestamp)
    norms = bot._bar_volume_norms("AG", todays, todays[-1].timestamp)
    avg = sum(1000 * (d + 1) for d in range(6)) / 6       # 3,500 for the 9:30 bar
    assert norms == [pytest.approx(avg), pytest.approx(2 * avg)]

    strict["min_sessions"] = 7                            # only six sessions of history
    bot._volume_norm_cache.clear()
    assert bot._bar_volume_norms("AG", todays, todays[-1].timestamp) == [None, None]
    strict["enabled"] = False
    assert bot._bar_volume_norms("AG", todays, todays[-1].timestamp) is None

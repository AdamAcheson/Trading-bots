"""The simulated broker fills stops and targets on a bar's low/high, as resting orders
would -- not only when a bar CLOSES beyond them, and never at the level when it only
closed beyond it (1-minute study, docs/BACKTEST_RESULTS.md: the old model overstated
gross P&L by 60-92%)."""

from datetime import datetime, timedelta, timezone

import pytest

from models.bar import Bar
from models.trade import ExitReason

T0 = datetime(2026, 3, 2, 14, 55, tzinfo=timezone.utc)      # 09:55 ET


def _bot_with_position(tmp_path, monkeypatch, exit_model="resting_orders"):
    from test_exposure_cap import _bot, _enter
    bot, provider = _bot(tmp_path, equity=5000)
    bot.config.strategy["trade_management"]["exit_model"] = exit_model
    t = bot.config.auto_tradeable_universe()[0]
    _enter(bot, provider, monkeypatch, t, T0, price=10.30, stop_distance=0.10)
    pos = bot.position_manager.get_position(t)
    assert pos is not None
    return bot, provider, t, pos


def _next_bar(bot, provider, t, o, h, l, c, minutes=5):
    from data.market_data import Quote
    now = T0 + timedelta(minutes=minutes)
    bench = bot.config.tickers[t].benchmark
    for sym, (oo, hh, ll, cc) in ((t, (o, h, l, c)), (bench, (50.3, 50.4, 50.2, 50.3))):
        provider.push_bar(sym, Bar(timestamp=now, open=oo, high=hh, low=ll, close=cc, volume=100_000))
        provider.push_quote(sym, Quote(bid=cc - 0.01, ask=cc, last=cc, timestamp=now), received_at=now)
    bot.manage_open_positions(now)
    return now


def test_a_dip_through_the_stop_exits_at_the_stop_even_if_the_bar_closes_above(tmp_path, monkeypatch):
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch)
    stop = pos.current_stop
    _next_bar(bot, provider, t, o=10.29, h=10.32, l=stop - 0.02, c=10.28)
    trade = bot.trade_journal.trades[-1]
    assert trade.exit_reason == ExitReason.STOP_HIT
    assert trade.exit_price == pytest.approx(stop)


def test_the_old_model_ignored_that_dip(tmp_path, monkeypatch):
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch, exit_model="close_at_level")
    _next_bar(bot, provider, t, o=10.29, h=10.32, l=pos.current_stop - 0.02, c=10.28)
    assert bot.position_manager.has_open_position(t)


def test_a_gap_through_the_stop_fills_at_the_open_not_the_stop(tmp_path, monkeypatch):
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch)
    stop = pos.current_stop
    _next_bar(bot, provider, t, o=stop - 0.08, h=stop - 0.05, l=stop - 0.12, c=stop - 0.10)
    assert bot.trade_journal.trades[-1].exit_price == pytest.approx(stop - 0.08)


def test_the_old_model_booked_a_close_below_the_stop_at_the_stop(tmp_path, monkeypatch):
    """The optimism the study measured: closed 10 cents past the stop, booked at the stop."""
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch, exit_model="close_at_level")
    stop = pos.current_stop
    _next_bar(bot, provider, t, o=stop - 0.08, h=stop - 0.05, l=stop - 0.12, c=stop - 0.10)
    assert bot.trade_journal.trades[-1].exit_price == pytest.approx(stop)


def test_a_target_touched_intrabar_fills_at_the_target(tmp_path, monkeypatch):
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch)
    target = pos.current_target
    _next_bar(bot, provider, t, o=10.35, h=target + 0.03, l=10.33, c=target - 0.05)
    trade = bot.trade_journal.trades[-1]
    assert trade.exit_reason == ExitReason.TARGET_HIT
    assert trade.exit_price == pytest.approx(target)


def test_a_bar_touching_both_counts_as_the_stop(tmp_path, monkeypatch):
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch)
    _next_bar(bot, provider, t, o=10.30, h=pos.current_target + 0.1, l=pos.current_stop - 0.1, c=10.30)
    assert bot.trade_journal.trades[-1].exit_reason == ExitReason.STOP_HIT


def test_the_entry_bar_itself_cannot_stop_the_position(tmp_path, monkeypatch):
    """The position was opened at the entry bar's close; its low happened before."""
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch)
    bot.manage_open_positions(T0)
    assert bot.position_manager.has_open_position(t)


def test_a_real_broker_is_never_simulated(tmp_path, monkeypatch):
    bot, provider, t, pos = _bot_with_position(tmp_path, monkeypatch)
    monkeypatch.setattr("main.PaperBrokerAdapter", type("Other", (), {}))
    assert bot._resting_order_exit(pos, T0 + timedelta(minutes=5)) is None


def test_shipped_config_uses_resting_orders():
    from config_loader import load_config
    assert load_config().strategy["trade_management"]["exit_model"] == "resting_orders"

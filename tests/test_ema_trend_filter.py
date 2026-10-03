"""9/20 EMA trend filter (docs/PREREG_EMA_TREND.md): take a signal only when price is
above the 9 EMA and the 9 EMA is above the 20 EMA, on 5-minute EMAs carried over from
previous sessions."""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from broker.paper import PaperBrokerAdapter
from config_loader import load_config
from data.indicators import ema
from data.market_data import InMemoryMarketDataProvider, Quote
from main import TradingBot
from models.bar import Bar
from models.signal import Decision, RejectionReason
from reporting.journal import SignalJournal, TradeJournal
from strategy.signal_engine import evaluate_ticker

from factories import base_stock_snapshot
from test_signals import make_ctx, orb_strategy


@pytest.fixture(scope="module")
def config():
    return load_config()


def with_filter(config):
    strat = copy.deepcopy(orb_strategy(config))
    strat["eligibility"]["require_ema_trend"] = True
    return strat


def test_off_by_default(config):
    assert config.strategy["eligibility"]["require_ema_trend"] is False


def test_uptrend_passes(config):
    ctx = make_ctx(config, snapshot=base_stock_snapshot(trend_ema_fast=10.30, trend_ema_slow=10.20))
    assert evaluate_ticker(ctx, with_filter(config), config.risk).decision == Decision.ENTRY_CANDIDATE


@pytest.mark.parametrize("fast, slow", [
    (10.45, 10.20),     # price (10.40) below the 9 EMA
    (10.30, 10.35),     # 9 EMA below the 20 EMA
])
def test_no_uptrend_rejects(config, fast, slow):
    ctx = make_ctx(config, snapshot=base_stock_snapshot(trend_ema_fast=fast, trend_ema_slow=slow))
    signal = evaluate_ticker(ctx, with_filter(config), config.risk)
    assert signal.decision != Decision.ENTRY_CANDIDATE
    assert signal.rejection_reason == RejectionReason.REJECTED_EMA_TREND


def test_missing_emas_reject(config):
    signal = evaluate_ticker(make_ctx(config), with_filter(config), config.risk)
    assert signal.rejection_reason == RejectionReason.REJECTED_DATA_QUALITY


def test_filter_off_ignores_the_trend(config):
    ctx = make_ctx(config, snapshot=base_stock_snapshot(trend_ema_fast=10.45, trend_ema_slow=10.50))
    assert evaluate_ticker(ctx, orb_strategy(config), config.risk).decision == Decision.ENTRY_CANDIDATE


def make_bot(tmp_path, enabled=True):
    config = load_config()
    config.strategy["eligibility"]["require_ema_trend"] = enabled
    provider = InMemoryMarketDataProvider()
    bot = TradingBot(config, provider, PaperBrokerAdapter(starting_equity=5000),
                     SignalJournal(str(tmp_path / "s.jsonl")), TradeJournal(str(tmp_path / "t.jsonl")))
    return bot, provider


def push_session(provider, day, closes):
    start = datetime(2026, 3, day, 14, 30, tzinfo=timezone.utc)       # 9:30 ET
    for i, c in enumerate(closes):
        ts = start + timedelta(minutes=5 * i)
        provider.push_bar("AG", Bar(timestamp=ts, open=c, high=c + 0.05, low=c - 0.05, close=c, volume=10_000))
        provider.push_quote("AG", Quote(bid=c - 0.01, ask=c, last=c, timestamp=ts), received_at=ts)
    return start + timedelta(minutes=5 * (len(closes) - 1))


def test_snapshot_carries_the_emas_over_from_previous_sessions(tmp_path):
    bot, provider = make_bot(tmp_path)
    day1 = [10 + 0.01 * i for i in range(78)]
    push_session(provider, 2, day1)
    now = push_session(provider, 3, [11.0, 11.1])          # two bars into the next session
    snap = bot._snapshot_for("AG", now)
    closes = day1 + [11.0, 11.1]
    assert snap.trend_ema_fast == pytest.approx(ema(closes, 9))
    assert snap.trend_ema_slow == pytest.approx(ema(closes, 20))
    assert snap.ema_20 is None                              # the session-only EMA is not ready


def test_snapshot_skips_the_work_when_off(tmp_path):
    bot, provider = make_bot(tmp_path, enabled=False)
    now = push_session(provider, 2, [10 + 0.01 * i for i in range(30)])
    snap = bot._snapshot_for("AG", now)
    assert snap.trend_ema_fast is None and snap.trend_ema_slow is None

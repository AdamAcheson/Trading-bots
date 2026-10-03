"""RSI 52-70 band (docs/PREREG_RSI_BAND.md): take a signal only when RSI(14) of 5-minute
closes, carried over from previous sessions, is within the band."""

import copy
import random

import pytest

from config_loader import load_config
from data.indicators import rsi
from models.signal import Decision, RejectionReason
from strategy import healthcare_momentum as hm
from strategy.signal_engine import evaluate_ticker

from factories import base_stock_snapshot
from test_ema_trend_filter import make_bot, push_session
from test_signals import make_ctx, orb_strategy


@pytest.fixture(scope="module")
def config():
    return load_config()


def with_band(config, band=(52, 70)):
    strat = copy.deepcopy(orb_strategy(config))
    strat["eligibility"]["rsi_band"] = list(band)
    return strat


def test_off_by_default(config):
    assert config.strategy["eligibility"]["rsi_band"] is None


def test_rsi_matches_the_existing_wilder_rsi():
    rng = random.Random(7)
    closes = [10.0]
    for _ in range(120):
        closes.append(closes[-1] * (1 + rng.uniform(-0.01, 0.01)))
    for n in (14, 30, 121):
        assert rsi(closes[:n], 14) == pytest.approx(hm.rsi(closes[:n], 14)[-1])
    assert rsi(closes[:14], 14) is None


def test_rsi_edge_cases():
    assert rsi([1.0 + i for i in range(20)]) == 100.0
    assert rsi([5.0] * 20) == 50.0


@pytest.mark.parametrize("value", [52.0, 60.0, 70.0])
def test_inside_the_band_passes(config, value):
    ctx = make_ctx(config, snapshot=base_stock_snapshot(trend_rsi=value))
    assert evaluate_ticker(ctx, with_band(config), config.risk).decision == Decision.ENTRY_CANDIDATE


@pytest.mark.parametrize("value", [51.9, 30.0, 70.1, 85.0])
def test_outside_the_band_rejects(config, value):
    ctx = make_ctx(config, snapshot=base_stock_snapshot(trend_rsi=value))
    signal = evaluate_ticker(ctx, with_band(config), config.risk)
    assert signal.rejection_reason == RejectionReason.REJECTED_RSI_BAND


def test_missing_rsi_rejects(config):
    signal = evaluate_ticker(make_ctx(config), with_band(config), config.risk)
    assert signal.rejection_reason == RejectionReason.REJECTED_DATA_QUALITY


def test_band_off_ignores_rsi(config):
    ctx = make_ctx(config, snapshot=base_stock_snapshot(trend_rsi=90.0))
    assert evaluate_ticker(ctx, orb_strategy(config), config.risk).decision == Decision.ENTRY_CANDIDATE


def test_snapshot_carries_rsi_over_from_previous_sessions(tmp_path):
    bot, provider = make_bot(tmp_path, enabled=False)
    bot.config.strategy["eligibility"]["rsi_band"] = [52, 70]
    day1 = [10 + 0.01 * ((-1) ** i) * (i % 7) for i in range(78)]
    push_session(provider, 2, day1)
    now = push_session(provider, 3, [10.2])                # first bar of the next session
    snap = bot._snapshot_for("AG", now)
    assert snap.trend_rsi == pytest.approx(rsi(day1 + [10.2], 14))
    assert snap.trend_ema_fast is None                      # the EMA filter stays off

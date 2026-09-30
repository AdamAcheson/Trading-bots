"""The healthcare bot's config and its two engine features (bots/healthcare/RULES.md).

bots/healthcare/config/ copies strategy.yaml and risk.yaml rather than symlinking them,
because each needs one setting the mining bot does not use. That makes drift possible:
a later change to config/ would silently not reach the healthcare copy. The first
tests pin the copies to config/ apart from the pre-registered differences.
"""

import copy
import os
from datetime import datetime, timezone

import yaml

from config_loader import load_config
from models.signal import Decision, RejectionReason
from strategy.signal_engine import evaluate_ticker

from factories import base_stock_snapshot
from test_exposure_cap import _bot, _enter
from test_signals import make_ctx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HC = os.path.join(ROOT, "bots", "healthcare", "config")
UNIVERSE = set(
    "ABT ABBV A ALGN AMGN BAX BDX BIIB TECH BSX BMY CAH COR CNC CRL CI COO CVS DHR DVA "
    "DXCM EW ELV LLY GEHC GILD HCA HSIC HUM IDXX ILMN INCY PODD ISRG IQV JNJ LH MCK MDT "
    "MRK MTD MRNA PFE DGX REGN RMD RVTY SOLV STE SYK TMO UNH UHS VEEV VRTX VTRS WAT WST "
    "ZBH ZTS".split())


def _yaml(*parts):
    with open(os.path.join(*parts)) as f:
        return yaml.safe_load(f)


# --- the config ------------------------------------------------------------------

def test_strategy_copy_differs_only_by_the_gap_day_skip():
    shipped, hc = _yaml(ROOT, "config", "strategy.yaml"), _yaml(HC, "strategy.yaml")
    assert shipped["eligibility"]["skip_gap_day_pct"] is None
    assert hc["eligibility"]["skip_gap_day_pct"] == 4.0
    hc["eligibility"]["skip_gap_day_pct"] = None
    assert hc == shipped


def test_risk_copy_differs_only_by_the_share_minimum():
    shipped, hc = _yaml(ROOT, "config", "risk.yaml"), _yaml(HC, "risk.yaml")
    assert shipped["sizing"]["min_shares"] is None
    assert hc["sizing"]["min_shares"] == 5
    hc["sizing"]["min_shares"] = None
    assert hc == shipped


def test_broker_and_schedule_are_shared_by_symlink():
    for name in ("broker.yaml", "schedule.yaml"):
        path = os.path.join(HC, name)
        assert os.path.islink(path)
        assert os.path.realpath(path) == os.path.join(ROOT, "config", name)


def test_universe_is_the_sixty_chosen_stocks_on_xlv_never_held_overnight():
    config = load_config(HC)
    assert set(config.auto_tradeable_universe()) == UNIVERSE
    for t in UNIVERSE:
        cfg = config.tickers[t]
        assert cfg.benchmark == "XLV"
        assert cfg.overnight_category == "manual_only"
        assert not cfg.manual_only          # the ENTRY flag: must stay tradeable
        assert cfg.max_spread_pct == 0.15
        assert cfg.profit_target_pct == [1.5, 3.0]
        assert cfg.volatility_category == "normal"


def test_mining_universe_does_not_pick_up_healthcare_stocks():
    assert not set(load_config().auto_tradeable_universe()) & UNIVERSE


# --- the gap-day skip ------------------------------------------------------------

def _strategy(skip):
    strategy = copy.deepcopy(load_config().strategy)
    strategy["eligibility"]["skip_gap_day_pct"] = skip
    return strategy


def _evaluate(gap, skip):
    config = load_config()
    ctx = make_ctx(config, snapshot=base_stock_snapshot(overnight_gap_pct=gap))
    return evaluate_ticker(ctx, _strategy(skip), config.risk)


def test_a_big_gap_up_or_down_skips_the_stock():
    assert _evaluate(4.0, 4.0).rejection_reason == RejectionReason.REJECTED_GAP_DAY
    assert _evaluate(-6.5, 4.0).rejection_reason == RejectionReason.REJECTED_GAP_DAY


def test_a_smaller_gap_is_not_skipped():
    assert _evaluate(3.9, 4.0).rejection_reason != RejectionReason.REJECTED_GAP_DAY


def test_off_by_default_so_the_mining_bot_is_unchanged():
    assert _evaluate(9.0, None).rejection_reason != RejectionReason.REJECTED_GAP_DAY


def test_unknown_gap_is_not_skipped():
    # The first session in a feed has no prior close; that is not evidence of news.
    assert _evaluate(None, 4.0).rejection_reason != RejectionReason.REJECTED_GAP_DAY


# --- the share minimum -------------------------------------------------------------

NOW = datetime(2026, 3, 2, 14, 55, tzinfo=timezone.utc)


def test_a_position_below_the_share_minimum_is_skipped(tmp_path, monkeypatch):
    bot, provider = _bot(tmp_path, equity=5000)
    bot.config.risk["sizing"]["min_shares"] = 5
    ticker = next(t for t in bot.config.tickers if bot.config.tickers[t].benchmark)
    # $2,500 buys 2 shares at $1,100: below the minimum.
    _enter(bot, provider, monkeypatch, ticker, NOW, price=1100.0, stop_distance=6.0)
    assert not bot.position_manager.has_open_position(ticker)
    assert bot.min_shares_skips == 1


def test_a_position_at_the_minimum_is_taken(tmp_path, monkeypatch):
    bot, provider = _bot(tmp_path, equity=5000)
    bot.config.risk["sizing"]["min_shares"] = 5
    ticker = next(t for t in bot.config.tickers if bot.config.tickers[t].benchmark)
    _enter(bot, provider, monkeypatch, ticker, NOW, price=500.0, stop_distance=2.5)
    assert bot.position_manager.get_position(ticker).shares == 5
    assert bot.min_shares_skips == 0


def test_share_minimum_off_by_default(tmp_path, monkeypatch):
    bot, provider = _bot(tmp_path, equity=5000)
    assert bot.config.risk["sizing"]["min_shares"] is None
    ticker = next(t for t in bot.config.tickers if bot.config.tickers[t].benchmark)
    _enter(bot, provider, monkeypatch, ticker, NOW, price=1100.0, stop_distance=6.0)
    assert bot.position_manager.get_position(ticker).shares == 2

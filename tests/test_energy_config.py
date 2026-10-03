"""The energy bot (bots/energy/RULES.md) uses the healthcare bot's settings unchanged; only
the stocks and the benchmark differ."""

import yaml

from config_loader import load_config


def load(path):
    return yaml.safe_load(open(path))


def test_strategy_and_risk_match_the_healthcare_bot():
    for name in ("strategy", "risk"):
        assert load(f"bots/energy/config/{name}.yaml") == load(f"bots/healthcare/config/{name}.yaml")


def test_universe_and_benchmark():
    config = load_config("bots/energy/config")
    universe = config.auto_tradeable_universe()
    assert len(universe) == 26
    assert {config.tickers[s].benchmark for s in universe} == {"XLE"}
    assert all(config.tickers[s].profit_target_pct == [1.5, 3.0] for s in universe)

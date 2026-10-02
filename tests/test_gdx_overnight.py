"""GDX overnight-only rules (bots/gdx_overnight/RULES.md)."""

import pytest

from execution.costs import TransactionCostModel
from strategy import gdx_overnight as go

FIXED = TransactionCostModel(commission_per_share=0.005, commission_min_per_order=1.0,
                             commission_max_pct_of_value=1.0, sell_fees_per_share=0.000166)
NO_SLIP = go.Params(slippage=0.0)


def days(n):
    return [f"2020-01-{i + 1:02d}" for i in range(n)]


def test_margin_buys_every_close_and_sells_every_open():
    # +1% every night, flat every day
    closes, opens = [100.0], [100.0]
    for _ in range(4):
        opens.append(closes[-1] * 1.01)
        closes.append(opens[-1])
    res = go.simulate(days(5), opens, closes, 0, 4, p=go.Params(slippage=0.0, mode="margin"))
    assert len(res["nights"]) == 4
    assert all(nt["price_return"] == pytest.approx(0.01) for nt in res["nights"])
    assert res["final"] > 5000 * 1.01 ** 4 - 110            # whole shares only
    assert res["final"] == pytest.approx(res["curve"][-1])


def test_no_buy_on_the_last_day():
    res = go.simulate(days(3), [10.0] * 3, [10.0] * 3, 0, 2, p=go.Params(slippage=0.0, mode="margin"))
    assert len(res["nights"]) == 2
    assert res["final"] == pytest.approx(5000)


def test_cash_halves_alternate_and_respect_settlement():
    res = go.simulate(days(5), [50.0] * 5, [50.0] * 5, 0, 4, p=NO_SLIP)
    # each half is about $2,500, so each night is 50 shares at $50
    assert [nt["shares"] for nt in res["nights"]] == [50, 50, 50, 50]
    # half A bought on days 0 and 2 (its sale on day 1 settled on day 2), half B on 1 and 3
    assert [nt["date"] for nt in res["nights"]] == days(4)


def test_cash_half_cannot_rebuy_before_settlement():
    # margin mode would be fully invested every night; cash mode only half
    opens = closes = [50.0] * 3
    cash = go.simulate(days(3), opens, closes, 0, 2, p=NO_SLIP)
    margin = go.simulate(days(3), opens, closes, 0, 2, p=go.Params(slippage=0.0, mode="margin"))
    assert cash["nights"][0]["shares"] == 50
    assert margin["nights"][0]["shares"] == 100


def test_commission_and_slippage_are_charged_on_both_orders():
    opens = closes = [40.0] * 2
    res = go.simulate(days(2), opens, closes, 0, 1, FIXED, go.Params(mode="margin"))
    nt = res["nights"][0]
    assert nt["entry"] == pytest.approx(40.02) and nt["exit"] == pytest.approx(39.98)
    assert res["commission"] == pytest.approx(2.0 + nt["shares"] * 0.000166)
    assert nt["net"] == pytest.approx(nt["gross"] - res["commission"])
    assert res["final"] == pytest.approx(5000 + nt["net"])


def test_purchase_never_exceeds_cash():
    res = go.simulate(days(2), [10.0, 10.0], [10.0, 10.0], 0, 1, FIXED,
                      go.Params(slippage=0.0, mode="margin"))
    assert res["nights"][0]["shares"] == 499                 # 500 x $10 + $2.50 would not fit


def test_split_returns_and_geometric_mean():
    opens, closes = [10.0, 11.0], [10.0, 10.5]
    s = go.split_returns(opens, closes, 0, 1)
    assert s["overnight"] == pytest.approx(0.1)
    assert s["day"] == pytest.approx(10.5 / 11 - 1)
    assert go.geometric_mean([0.1, -0.1]) == pytest.approx((1.1 * 0.9) ** 0.5 - 1)


def test_unknown_mode():
    with pytest.raises(ValueError):
        go.simulate(days(2), [1.0] * 2, [1.0] * 2, 0, 1, p=go.Params(mode="other"))

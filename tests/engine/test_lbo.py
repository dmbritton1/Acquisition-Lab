import math

import pytest

from acqlab.engine import Params, covenant_safe_debt, evaluate, project, size_debt
from tests.conftest import FULL_PARAMS, make_simple


def test_simple_base_projection_is_hand_checkable(simple):
    years = project(simple, Params(), debt0=80)
    # EBITDA 20, interest 10% x 80 = 8, FCF 12/yr, no repayment -> cash builds 12/yr.
    assert [y.fcf for y in years] == pytest.approx([12.0] * 5)
    assert years[-1].cash == pytest.approx(60.0)
    assert years[-1].net_debt == pytest.approx(20.0)


def test_simple_downside_applies_revenue_and_margin_shocks(simple):
    years = project(simple, Params(), debt0=80, downside=True)
    # Revenue 100 x 0.9 = 90, margin 20% - 2pts = 18% -> EBITDA 16.2
    assert years[0].ebitda == pytest.approx(16.2)
    assert years[0].leverage == pytest.approx((80 - (16.2 - 8)) / 16.2)


def test_revolver_draw_is_charged_interest(simple):
    years = project(simple, Params(ebitda_adjustment=-15), debt0=80)
    # EBITDA 5, term-loan interest 8 -> FCF -3, cash -3; year 2 adds 10% x 3 revolver interest.
    assert years[0].cash == pytest.approx(-3.0)
    assert years[1].interest == pytest.approx(8.3)
    assert years[1].cash == pytest.approx(-6.3)


def test_nonpositive_ebitda_gives_infinite_leverage(simple):
    years = project(simple, Params(ebitda_adjustment=-25), debt0=10)
    assert math.isinf(years[0].leverage)


def test_covenant_safe_debt_is_lender_cap_when_covenant_is_loose(simple):
    assert covenant_safe_debt(simple, Params()) == pytest.approx(80.0)


def test_covenant_safe_debt_binds_when_covenant_is_tight():
    # Downside yr1 leverage = (1.1D - 16.2) / 16.2 <= 4  ->  D <= 81 / 1.1
    assert covenant_safe_debt(make_simple(covenant=4.0), Params()) == pytest.approx(81 / 1.1, abs=1e-5)


def test_min_equity_caps_debt_at_low_prices(simple):
    # uses = 50 x 1.02 = 51; 60% of uses = 30.6 < lender cap 80
    assert size_debt(simple, Params(), price=50) == pytest.approx(30.6)


def test_size_debt_never_goes_negative(simple):
    assert size_debt(simple, Params(), price=0.01) >= 0.0


def test_simple_returns_match_hand_calculation(simple):
    r = evaluate(simple, Params())
    assert r.uses == pytest.approx(153.0)
    assert r.debt == pytest.approx(80.0)
    assert r.equity == pytest.approx(73.0)
    assert r.exit_equity == pytest.approx(140.0)  # 8 x 20 - (80 - 60)
    assert r.moic == pytest.approx(140 / 73)
    assert r.irr == pytest.approx((140 / 73) ** 0.2 - 1)


def test_full_fixture_matches_independent_reference(full):
    r = evaluate(full, FULL_PARAMS)
    assert r.debt == pytest.approx(123.227576, abs=1e-4)  # covenant-safe debt binds
    assert r.equity == pytest.approx(118.372424, abs=1e-4)
    assert r.exit_equity == pytest.approx(191.200361, abs=1e-4)
    assert r.irr == pytest.approx(0.1006459, abs=1e-6)
    assert [y.net_debt for y in r.base] == pytest.approx(
        [116.2836, 109.1841, 100.8884, 91.3186, 80.3924], abs=1e-4)
    assert [y.leverage for y in r.downside] == pytest.approx(
        [5.5, 5.120933, 4.735547, 4.343739, 3.945400], abs=1e-5)  # downside draws the revolver from yr 2
    assert r.covenant_headroom[0] == pytest.approx(0.0, abs=1e-5)


def test_covenant_schedule_mismatch_fails_loudly_even_when_validation_is_bypassed(simple):
    longer = simple.model_copy(update={"policy": simple.policy.model_copy(update={"hold_years": 7})})
    with pytest.raises(ValueError):
        evaluate(longer, Params())


def test_debt_limit_reports_which_cap_binds(simple, full):
    assert evaluate(simple, Params()).debt_limit == "lender_cap"  # covenant ties at 80; lender reported first
    assert evaluate(make_simple(covenant=4.0), Params()).debt_limit == "covenant"
    assert evaluate(simple, Params(), price=50).debt_limit == "min_equity"
    r = evaluate(full, FULL_PARAMS)
    assert r.debt_limit == "covenant"
    assert r.debt_caps == pytest.approx({"lender_cap": 140.0, "covenant": 123.227576, "min_equity": 144.96}, abs=1e-4)


def test_simple_equity_bridge_matches_hand_calculation(simple):
    b = evaluate(simple, Params()).bridge
    # Entry multiple 150/20 = 7.5x, flat EBITDA: growth 0, multiple (8 - 7.5) x 20 = 10,
    # net debt 80 -> 20 = 60 paid down, fees 3.
    assert (b.entry_equity, b.ebitda_growth, b.multiple_change, b.debt_paydown, b.closing_costs, b.exit_equity) \
        == pytest.approx((73, 0, 10, 60, -3, 140))


def test_full_equity_bridge_sums_to_exit_equity(full):
    r = evaluate(full, FULL_PARAMS)
    b = r.bridge
    assert b.entry_equity + b.ebitda_growth + b.multiple_change + b.debt_paydown + b.closing_costs \
        == pytest.approx(b.exit_equity)
    assert b.exit_equity == pytest.approx(r.exit_equity)
    assert b.closing_costs == pytest.approx(-(230 * 0.02 + 5 + 2))

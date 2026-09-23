import pytest
from pydantic import ValidationError

from acqlab.engine import PARAM_NAMES, Params, Policy
from tests.conftest import make_simple


def test_params_default_to_face_value():
    p = Params()
    assert all(getattr(p, name) == 0.0 for name in PARAM_NAMES)


def test_param_names_are_the_generic_engine_parameters():
    assert PARAM_NAMES == ("ebitda_adjustment", "debt_like", "revenue_haircut",
                           "nwc_adjustment", "capex_adjustment_pct")


def test_policy_defaults_match_spec():
    p = Policy(exit_multiple=8.0)
    assert (p.irr_hurdle, p.hold_years, p.min_equity_pct) == (0.20, 5, 0.40)
    assert (p.downside_revenue_shock, p.downside_margin_shock) == (-0.10, -0.02)


def test_negative_debt_like_is_rejected():
    with pytest.raises(ValidationError):
        Params(debt_like=-1)


def test_negative_nwc_adjustment_is_rejected():
    with pytest.raises(ValidationError):
        Params(nwc_adjustment=-1)


def test_revenue_haircut_of_one_is_rejected():
    with pytest.raises(ValidationError):
        Params(revenue_haircut=1.0)


def test_zero_min_equity_pct_is_rejected():
    with pytest.raises(ValidationError):
        Policy(exit_multiple=8, min_equity_pct=0)


def test_covenant_schedule_must_match_hold_years():
    from acqlab.engine import Deal

    deal = make_simple()
    with pytest.raises(ValidationError):
        Deal(company=deal.company, financing=deal.financing.model_copy(update={"covenant_max_leverage": [5.0]}),
             policy=deal.policy, asking_price=deal.asking_price)


def test_nan_parameter_is_rejected():
    with pytest.raises(ValidationError):
        Params.model_validate_json('{"ebitda_adjustment": "NaN"}')


def test_misspelled_parameter_is_rejected():
    with pytest.raises(ValidationError):
        Params.model_validate({"debtlike": 3})

import pytest
from pydantic import ValidationError

from acqlab.engine import Params, flip_threshold, is_go, walk_away
from acqlab.engine.walkaway import PRICE_FLOOR


def test_simple_walk_away_matches_hand_calculation(simple):
    # Debt fixed at 80: (260 - 1.5 x 80) / (1.02P - 80) = 1.2^5  ->  P = (140 / 1.2^5 + 80) / 1.02
    expected = (140 / 1.2 ** 5 + 80) / 1.02
    assert walk_away(simple, Params()) == pytest.approx(expected, abs=1e-3)


def test_asking_above_walk_away_is_no_go(simple):
    assert not is_go(simple, Params())  # asking 150 > ~133.59


def test_asking_below_walk_away_is_go(simple):
    assert is_go(simple.model_copy(update={"asking_price": 120}), Params())


def test_hopeless_deal_walks_away_at_floor(simple):
    assert walk_away(simple, Params(ebitda_adjustment=-20)) == PRICE_FLOOR  # zero EBITDA: no price clears the hurdle


def test_flip_threshold_finds_where_the_decision_changes(simple):
    deal = simple.model_copy(update={"asking_price": 120})  # go at face value
    v = flip_threshold(deal, Params(), "debt_like", 0, 50)
    assert v is not None
    assert is_go(deal, Params(debt_like=v - 1e-3))
    assert not is_go(deal, Params(debt_like=v + 1e-3))


def test_flip_threshold_is_none_when_decision_never_changes(simple):
    assert flip_threshold(simple, Params(), "debt_like", 0, 5) is None  # already no-go, more debt-like keeps it no-go


def test_flip_threshold_rejects_out_of_range_bound(simple):
    with pytest.raises(ValidationError):
        flip_threshold(simple, Params(), "debt_like", -5, 5)


def test_flip_threshold_rejects_unknown_parameter(simple):
    with pytest.raises(ValidationError):
        flip_threshold(simple, Params(), "exit_multiple", 0, 50)


def test_is_go_is_exact_not_bisection_tolerant(simple):
    true_walk_away = (140 / 1.2 ** 5 + 80) / 1.02
    just_above = simple.model_copy(update={"asking_price": true_walk_away + 1e-6})
    assert not is_go(just_above, Params())
    just_below = simple.model_copy(update={"asking_price": true_walk_away - 1e-6})
    assert is_go(just_below, Params())

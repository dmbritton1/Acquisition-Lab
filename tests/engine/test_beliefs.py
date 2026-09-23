import numpy as np
import pytest
from pydantic import ValidationError

from acqlab.engine import Params, evaluate_under, walk_away


def test_no_uncertainty_gives_point_mass(simple):
    out = evaluate_under(simple, Params(), {}, n=5)
    assert out == pytest.approx([walk_away(simple, Params())] * 5)


def test_samples_stay_within_extremes(simple):
    lo = walk_away(simple, Params(debt_like=10))
    hi = walk_away(simple, Params(debt_like=0))
    out = evaluate_under(simple, Params(), {"debt_like": (0, 10)}, n=50)
    assert np.all(out >= lo - 1e-3) and np.all(out <= hi + 1e-3)
    assert out.std() > 0


def test_same_seed_is_reproducible(full):
    b = {"ebitda_adjustment": (-4, 0)}
    assert np.array_equal(evaluate_under(full, Params(), b, n=20, seed=7),
                          evaluate_under(full, Params(), b, n=20, seed=7))


def test_unknown_parameter_is_rejected(simple):
    with pytest.raises(ValueError, match="unknown parameters"):
        evaluate_under(simple, Params(), {"exit_multiple": (7, 9)}, n=1)


def test_out_of_range_belief_draw_is_rejected(simple):
    with pytest.raises(ValidationError):
        evaluate_under(simple, Params(), {"debt_like": (-5, 0)}, n=5)


def test_sampling_order_is_independent_of_belief_key_order(simple):
    a = {"debt_like": (0, 10), "ebitda_adjustment": (-4, 0)}
    b = {"ebitda_adjustment": (-4, 0), "debt_like": (0, 10)}
    assert np.array_equal(evaluate_under(simple, Params(), a, n=20, seed=3),
                          evaluate_under(simple, Params(), b, n=20, seed=3))

import numpy as np

from acqlab.generator.traps import TRAPS
from acqlab.generator.truth import generate
from acqlab.routers.beliefs import HAIRCUT_CAP, Issue, draw, walk_aways


def _beliefs(**over) -> dict:
    return {t: over.get(t, Issue(known=(0.0, 0.0))) for t in TRAPS}


def test_known_values_stay_fixed_and_ranges_stay_inside():
    b = _beliefs(addback=Issue(known=(1.5, 1.5)), nwc=Issue(known=(2.0, 3.0)))
    v = draw(b, 500, np.random.default_rng(0))
    assert v.shape == (500, 5)
    assert np.all(v[:, TRAPS.index("addback")] == 1.5)
    col = v[:, TRAPS.index("nwc")]
    assert col.min() >= 2.0 and col.max() <= 3.0 and col.std() > 0.1


def test_open_issue_is_clean_with_probability_one_minus_p_real():
    b = _beliefs(debt_like=Issue(p_real=0.3, hi=10.0))
    col = draw(b, 20_000, np.random.default_rng(1))[:, TRAPS.index("debt_like")]
    assert abs(np.mean(col == 0) - 0.7) < 0.02 and col.max() <= 10.0


def test_forgotten_issue_is_assumed_zero_and_is_not_open():
    b = _beliefs(capex=Issue(p_real=0.9, hi=5.0, proposed=False))
    assert not b["capex"].open and b["debt_like"].known is not None
    assert np.all(draw(b, 100, np.random.default_rng(2))[:, TRAPS.index("capex")] == 0)
    assert Issue(p_real=0.3, hi=1.0).open


def test_draws_are_common_random_numbers_across_belief_states():
    """Learning one issue must not reshuffle the draws of the others."""
    a = _beliefs(debt_like=Issue(p_real=0.5, hi=10.0), nwc=Issue(p_real=0.5, hi=4.0))
    b = dict(a, debt_like=Issue(known=(3.0, 3.0)))
    va, vb = draw(a, 50, np.random.default_rng(3)), draw(b, 50, np.random.default_rng(3))
    assert np.array_equal(va[:, TRAPS.index("nwc")], vb[:, TRAPS.index("nwc")])


def test_walk_aways_fall_with_worse_worlds_and_cap_the_haircut():
    t = generate("x", "test", 4, mc=20, force_case="clean")
    rev = t.base.teaser.revenue_ltm
    values = np.zeros((3, 5))
    values[1, TRAPS.index("debt_like")] = 10.0
    values[2, TRAPS.index("concentration")] = 5 * rev  # impossible loss: capped, not an engine error
    w = walk_aways(t.base, values)
    assert abs(w[0] - t.face_walk_away) < 1e-6 and w[1] < w[0] and w[2] < w[1]
    assert HAIRCUT_CAP < 1

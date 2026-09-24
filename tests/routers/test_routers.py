import inspect

import numpy as np
import pytest

import acqlab.routers.routers as routers
from acqlab.generator.traps import TRAPS
from acqlab.generator.truth import generate
from acqlab.routers.beliefs import Issue, draw, walk_aways
from acqlab.routers.routers import (ROUTERS, checklist, decide, random_order, score_flip, score_regret,
                                    score_sensitivity)

COSTS = {t: 1.0 for t in TRAPS}


@pytest.fixture(scope="module")
def roomy():
    """A deal whose face-value walk-away is comfortably above the asking price."""
    t = generate("x", "test", 4, mc=20, force_case="clean")
    return t, t.face_walk_away - t.deal.asking_price


def _worlds(t, **issues):
    b = {x: issues.get(x, Issue(known=(0.0, 0.0))) for x in TRAPS}
    v = draw(b, 400, np.random.default_rng(0))
    return v, walk_aways(t.base, v)


def test_decide_picks_the_lower_expected_regret():
    assert decide(np.array([90.0, 130.0, 140.0]), 100.0) == (True, 130.0)
    assert decide(np.array([50.0, 60.0, 140.0]), 100.0) == (False, 60.0)


def test_the_demo_moment_a_big_mover_that_cannot_flip_ranks_low_on_router_6(roomy):
    """Spec §5: a big-valuation-impact issue that never flips the decision ranks below one that can flip it.
    debt_like moves walk-away more (router 3 prefers it) but alone never crosses the asking price."""
    t, gap = roomy
    v, w = _worlds(t, nwc=Issue(p_real=0.15, hi=1.6 * gap), debt_like=Issue(p_real=0.5, hi=0.8 * gap))
    ask, open_ = t.deal.asking_price, ["nwc", "debt_like"]
    six, three, five = (f(v, w, ask, COSTS, open_) for f in (score_regret, score_sensitivity, score_flip))
    assert three["debt_like"] > three["nwc"]
    assert six["nwc"] > six["debt_like"] and five["nwc"] > five["debt_like"] == 0.0


def test_router_6_divides_by_cost(roomy):
    t, gap = roomy
    v, w = _worlds(t, nwc=Issue(p_real=0.3, hi=1.6 * gap))
    cheap = score_regret(v, w, t.deal.asking_price, COSTS, ["nwc"])["nwc"]
    dear = score_regret(v, w, t.deal.asking_price, dict(COSTS, nwc=4.0), ["nwc"])["nwc"]
    assert cheap > 0 and dear == pytest.approx(cheap / 4)


def test_an_issue_that_cannot_matter_scores_zero_on_router_6(roomy):
    t, gap = roomy
    v, w = _worlds(t, capex=Issue(p_real=0.5, hi=1e-6))
    assert score_regret(v, w, t.deal.asking_price, COSTS, ["capex"])["capex"] == 0.0


def test_pair_screening_lifts_an_interaction_pair(roomy, monkeypatch):
    """Each issue alone stays short of the asking price; together they can cross it."""
    t, gap = roomy
    v, w = _worlds(t, nwc=Issue(p_real=0.5, hi=0.8 * gap), debt_like=Issue(p_real=0.5, hi=0.8 * gap))
    args = (v, w, t.deal.asking_price, COSTS, ["nwc", "debt_like"])
    with_pairs = score_regret(*args)
    monkeypatch.setattr(routers, "PAIR_TOP", 0)
    alone = score_regret(*args)
    assert all(with_pairs[x] > alone[x] for x in ("nwc", "debt_like"))


def test_ordering_rules():
    open_ = ["capex", "addback", "nwc"]
    s = checklist(None, None, 0.0, COSTS, open_)
    assert max(open_, key=s.get) == "addback"
    a = random_order(None, None, 0.0, COSTS, open_, np.random.default_rng(5))
    assert a == random_order(None, None, 0.0, COSTS, open_, np.random.default_rng(5)) and set(a) == set(open_)


def test_routers_never_see_the_answer_key():
    """Isolation rule: scoring code takes worlds, costs and open issues only, and never imports answer keys."""
    src = inspect.getsource(routers)
    assert "AnswerKey" not in src and "DealTruth" not in src and "facts" not in src
    for fn, _ in ROUTERS.values():
        assert list(inspect.signature(fn).parameters) == ["values", "w", "ask", "costs", "open_", "rng"]

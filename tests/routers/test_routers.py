import inspect

import numpy as np
import pytest

import acqlab.routers.routers as routers
from acqlab.generator.traps import TRAPS
from acqlab.generator.truth import generate
from acqlab.routers.beliefs import Issue, draw, walk_aways
from acqlab.routers.routers import (ROUTERS, checklist, decide, random_order, score_docs, score_flip,
                                    score_regret, score_sensitivity)

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


def test_the_document_router_scores_how_far_a_read_moves_the_walk_away_per_page():
    """D2 §2: router 3's sensitivity per document. Two issues, each 0, 3 or 9 in equal thirds; walk-away 110 less both.
    Learning one moves the mean walk-away (102) by (4 + 1 + 5) / 3; learning both, by the mean of |a + b - 8| = 40 / 9.
    """
    grid = np.array([(a, b) for a in (0.0, 3.0, 9.0) for b in (0.0, 3.0, 9.0)] * 100)
    values = np.zeros((len(grid), len(TRAPS)))
    values[:, TRAPS.index("addback")], values[:, TRAPS.index("nwc")] = grid[:, 0], grid[:, 1]
    w = 110.0 - grid.sum(axis=1)
    u = np.random.default_rng(1).random(values.shape)
    both = {"addback": 1.0, "nwc": 1.0}
    weights = {"both": both, "both_long": both, "one": {"addback": 1.0}, "none": {}}
    pages = {"both": 2.0, "both_long": 4.0, "one": 1.0, "none": 1.0}
    s = score_docs(values, w, weights, pages, ["addback", "nwc"], u)
    assert s["one"] == pytest.approx(10 / 3) and s["both"] == pytest.approx(40 / 9 / 2) and s["none"] == 0
    assert s["both_long"] == pytest.approx(s["both"] / 2)  # twice the pages, half the score
    assert s == score_docs(values, w, weights, pages, ["addback", "nwc"], u)


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

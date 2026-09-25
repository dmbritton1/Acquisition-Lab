"""Routers: score each open issue from shared simulated worlds (Plan 3 design §2). A router sees beliefs, worlds and
costs only, never the answer key. Higher score = read first."""
import itertools

import numpy as np

from acqlab.generator.traps import TRAPS
from acqlab.generator.truth import cross_fit, value_groups

PAIR_TOP = 3  # pair screening looks at the top issues by value
PAIR_BINS = 4  # size groups per issue when two issues are grouped jointly
DOC_BINS = 2  # settled sizes per issue for the document router: below or above the median (0 is its own label)


def regrets(w: np.ndarray, ask: float) -> tuple[np.ndarray, np.ndarray]:
    """Per world: regret of going (overpaying) and of not going (value forgone)."""
    return np.maximum(0.0, ask - w), np.maximum(0.0, w - ask)


def decide(w: np.ndarray, ask: float) -> tuple[bool, float]:
    """(go, walk-away estimate): go if its expected regret is no higher than passing."""
    reg_go, reg_no = regrets(w, ask)
    return bool(reg_go.mean() <= reg_no.mean()), float(np.median(w))


def _labels(col: np.ndarray, bins: int) -> np.ndarray:
    """0 where the value is 0, else its size quantile group 1..bins."""
    lab = np.zeros(len(col), dtype=int)
    rest = np.flatnonzero(col > 0)
    for k, g in enumerate(np.array_split(rest[np.argsort(col[rest])], bins)):
        lab[g] = k + 1
    return lab


def _pair_groups(a: np.ndarray, b: np.ndarray) -> list[np.ndarray]:
    joint = _labels(a, PAIR_BINS) * (PAIR_BINS + 1) + _labels(b, PAIR_BINS)
    return [np.flatnonzero(joint == k) for k in np.unique(joint)]


def score_regret(values, w, ask, costs, open_, rng=None) -> dict[str, float]:
    """Router 6: expected $ of decision regret removed by learning the issue, per page. Pair screening lifts two
    issues worth more together than apart to their joint value per joint cost."""
    reg_go, reg_no = regrets(w, ask)
    now = cross_fit([np.arange(len(w))], reg_go, reg_no)[0]
    col = {t: values[:, TRAPS.index(t)] for t in open_}
    value = {t: max(0.0, float(now - cross_fit(value_groups(col[t]), reg_go, reg_no)[0])) for t in open_}
    score = {t: value[t] / costs[t] for t in open_}
    for a, b in itertools.combinations(sorted(open_, key=lambda t: -value[t])[:PAIR_TOP], 2):
        joint = max(0.0, float(now - cross_fit(_pair_groups(col[a], col[b]), reg_go, reg_no)[0]))
        if joint > value[a] + value[b]:
            pair = joint / (costs[a] + costs[b])
            score[a], score[b] = max(score[a], pair), max(score[b], pair)
    return score


def score_docs(values, w, weights, pages, open_, u) -> dict[str, float]:
    """Document router (D2 §2): router 3's sensitivity per document, per page. In each world a document settles open
    issue t where u < its weight for t; worlds are grouped by what the reader would learn (each issue settled at 0,
    small, large, or not here), and the score is the expected absolute move of the mean walk-away from learning the
    group. One table u for every document, so noise can't reorder them."""
    labels = {t: _labels(values[:, TRAPS.index(t)], DOC_BINS) for t in open_}
    m, out = w.mean(), {}
    for d, wd in weights.items():
        key = np.zeros(len(w), dtype=np.int64)
        for t in open_:
            seen = u[:, TRAPS.index(t)] < wd.get(t, 0.0)
            key = key * (DOC_BINS + 2) + np.where(seen, labels[t], DOC_BINS + 1)
        groups = [np.flatnonzero(key == k) for k in np.unique(key)]
        out[d] = float(sum(len(g) * abs(w[g].mean() - m) for g in groups) / len(w)) / pages[d]
    return out


def score_flip(values, w, ask, costs, open_, rng=None) -> dict[str, float]:
    """Router 5: probability that learning the issue changes the current go/no-go."""
    reg_go, reg_no = regrets(w, ask)
    now = decide(w, ask)[0]
    return {t: float(np.mean(cross_fit(value_groups(values[:, TRAPS.index(t)]), reg_go, reg_no)[1] != now))
            for t in open_}


def score_sensitivity(values, w, ask, costs, open_, rng=None) -> dict[str, float]:
    """Router 3: expected absolute move in mean walk-away from learning the issue."""
    m = w.mean()
    return {t: float(sum(len(g) * abs(w[g].mean() - m) for g in value_groups(values[:, TRAPS.index(t)])) / len(w))
            for t in open_}


def checklist(values, w, ask, costs, open_, rng=None) -> dict[str, float]:
    """Router 1: fixed order (add-backs, debt-like, customers, working capital, capex)."""
    return {t: -float(TRAPS.index(t)) for t in open_}


def random_order(values, w, ask, costs, open_, rng=None) -> dict[str, float]:
    """Floor: a random order."""
    return {t: float(rng.random()) for t in open_}


ROUTERS = {  # name -> (score function, needs simulated worlds)
    "checklist": (checklist, False), "random": (random_order, False), "sensitivity": (score_sensitivity, True),
    "flip": (score_flip, True), "regret": (score_regret, True),
}

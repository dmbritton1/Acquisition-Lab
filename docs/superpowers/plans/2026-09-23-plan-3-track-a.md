# Plan 3: Track A Routers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the router math on thousands of simulated runs with no LLM: routers 1, 3, 5 and 6 (plus random and an oracle) choose which facts a simulated investigator reads under a budget, and are scored on decision regret.

**Architecture:** Three files in `acqlab/routers/`.
- `beliefs.py` holds each issue's state and draws simulated worlds, costed with the Plan 1 engine.
- `routers.py` scores open issues from those shared worlds; router 6 reuses Plan 2's cross-fitted value-of-information estimator, moved into a shared helper in Task 1.
- `track_a.py` builds noisy priors, runs the simulated investigator and residual sweep, and records metrics and a paired-bootstrap summary. It has three grids: headline, full and hints.

**Tech Stack:** Python 3.12, uv, pydantic 2, numpy 2, pytest. Parallelism via stdlib `concurrent.futures`.

**Spec:** `docs/superpowers/specs/2026-09-23-plan-3-track-a-design.md` (this plan's design, including §7 revisions), under `docs/superpowers/specs/2026-09-22-acquisition-lab-design.md` §3–4 (binding authority).

**Where this fits:** Plan 3 of 7. It feeds the week-4 checkpoint (~2026-10-19, Track A: router 6 vs 3 and 5). Plan 4 adds router 2 (LLM judgment) and Track B.

## Global Constraints

- Python `>=3.12`; no new dependencies.
- All money in **$M**. Convert fact amounts to engine parameters only with `acqlab.generator.traps.params_for` (it takes the generator's `BaseDeal`, `truth.base`).
- The engine is the only source of financial numbers; this plan does not change `acqlab/engine`.
- **Routers never see the answer key.** Only `track_a.py` (the investigator, oracle, priors and scoring) reads it; a test enforces this for `routers.py`.
- **Priors are never the generator's own prior** (0 with probability 0.70, else uniform on (0, worst)). The hints study uses the answer key on purpose and is labelled a "what if" study.
- Track A deals come from a separate batch (`data/track_a`, `--seed 200000`), never the benchmark splits in `data/`.
- **No LLM calls anywhere in this plan.**
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Subagents must never modify settings or permissions files, and must stop and report if a git operation is blocked.
- Never edit golden test numbers to make a test pass. Task 1 must leave every Plan 2 answer key byte-identical.

## Findings from pre-verifying this plan (read before starting)

All code below was run before the plan was written: 154 tests pass in about 35 s, and the headline and hints grids ran on 120 Track A deals. The spec's §7 records the design changes this caused.

1. **On generator truth, every router is close to random.** Mean normalised regret at the 50% budget (120 deals): random 0.0151, checklist 0.0142, router 5 0.0132, router 3 0.0126, router 6 0.0122, 6+veto 0.0161, oracle 0.0011. The noisy priors carry no deal-specific clue about *which* issue is real; in the real system that clue comes from reading the documents.
2. **The math works when beliefs are right (the self-consistent "fair game").** Mean normalised regret at the 50% budget: router 3 0.0095, router 6 0.0099, checklist 0.0108, router 5 0.0144, random 0.0164, oracle 0.0013. An earlier diagnostic with nothing forgotten (360 runs) gave router 6 0.0050 against random 0.0131, a CI that excludes zero.
3. **Router 6 ties router 3, even when beliefs are right** (+0.0004, CI [−0.0002, +0.0013] at the 50% budget). Page costs are nearly flat (1–2 pages per fact), so "$ per page" ranks issues almost like "how far the value moves". This is an early warning for H2, to be confirmed at 2,000 deals.
4. **Hints help every smart router about equally.** At the 50% budget, routers 3, 5 and 6 reach 0.0115 / 0.0148 / 0.0113 with weak hints (0.7), and 0.0080 / 0.0079 / 0.0079 with strong hints (0.9), against random at about 0.015.
5. **The 25% budget buys about one fact**, so all routers score about the same there; the 100% budget buys nearly everything. The 50% budget is where routers differ.
6. **"6 + veto" at 0.25% of asking price per page stops too early on generator truth** (0.0161 against 0.0122 at 50%). Report it; the page-price sweep is on the later list.
7. **Prior calibration at medium noise:** 87% of real problems fall inside the prior range. Sweep: 3–4% of runs find a forgotten problem.
8. **Runtime:** a walk-away takes 0.3 ms, and 400 worlds take 0.12 s. Worlds are cached per deal: routers at the same step with the same beliefs share them. Measured on this 8-core laptop (about 3.9 cores' worth of throughput): headline about 26 s of CPU per deal (2 truths), full about 45 s per deal on top, hints about 26 s per deal. Estimated wall time: headline on 2,000 deals is about 3.7 h, full on 500 about 1.6 h, and hints on 500 about 0.9 h. Every grid is resumable.
9. **Task 1 is byte-identical:** a 43-deal batch generated before and after the helper refactor diffs clean.
10. **Hand-built "demo moment" (spec §5):** on a roomy deal, a debt-like item that moves walk-away a lot but can't flip the decision ranks first on router 3 and below a rarer, decision-flipping working-capital issue on router 6. Pair screening correctly lifts the debt-like item a little, because its size decides whether the working-capital hit tips the deal.

## File Structure

| File | Responsibility |
|---|---|
| `acqlab/generator/truth.py` | (modify) move grouping and cross-fitting into `value_groups` and `cross_fit` |
| `acqlab/routers/__init__.py` | empty package marker |
| `acqlab/routers/beliefs.py` | `Issue` state, world draws, walk-aways per world |
| `acqlab/routers/routers.py` | Routers 1, 3, 5, 6 (with pair screening), random, `decide` |
| `acqlab/routers/track_a.py` | Priors, clue hints, fair-game truth, investigator, run loop, sweep, oracle, summary, CLI |
| `tests/routers/__init__.py` | empty package marker |
| `tests/routers/test_beliefs.py`, `test_routers.py`, `test_track_a.py` | tests |
| `tests/generator/test_truth.py` | (modify) two tests for the shared helper |

---

### Task 1: Shared value-of-information helper

**Files:**
- Modify: `acqlab/generator/truth.py` (replace the whole `value_of_knowing` function)
- Test: `tests/generator/test_truth.py` (append two tests, extend imports)

**Interfaces:**
- Produces: `value_groups(col: np.ndarray, bins: int = 10) -> list[np.ndarray]` and `cross_fit(groups: list[np.ndarray], reg_go: np.ndarray, reg_no: np.ndarray) -> tuple[float, np.ndarray]` (regret, per-draw decision with True = go). `value_of_knowing` keeps its signature and output exactly.

- [ ] **Step 1: Generate a reference batch before touching anything**

```bash
uv run python -m acqlab.generator.batch --out data/ref_task1 --dev 20 --test 20 --hand 2 --showcase 1
```
Expected: `generated 43 deals into data/ref_task1; 0 batch problems`

- [ ] **Step 2: Write the failing tests**

In `tests/generator/test_truth.py`, add `import pytest` after `import numpy as np`, and change the truth import line to:

```python
from acqlab.generator.truth import cross_fit, generate, prior_draws, simulate, value_groups, value_of_knowing
```

Append at the end of the file:

```python
def test_cross_fit_regret_is_the_mean_regret_of_its_own_decisions():
    rng = np.random.default_rng(0)
    reg_go, reg_no = rng.random(101), rng.random(101)
    groups = value_groups(np.where(rng.random(101) < 0.5, 0.0, rng.random(101)), bins=4)
    assert sorted(np.concatenate(groups).tolist()) == list(range(101))
    regret, decision = cross_fit(groups, reg_go, reg_no)
    assert regret == pytest.approx(np.where(decision, reg_go, reg_no).mean())
    one = cross_fit([np.arange(101)], reg_go, reg_no)[1]
    assert set(one[::2]) | set(one[1::2]) <= {True, False} and len(set(one[::2])) == 1


def test_value_groups_puts_zeros_first_and_sorts_the_rest_into_size_groups():
    col = np.array([0.0, 5.0, 0.0, 1.0, 3.0, 2.0])
    groups = value_groups(col, bins=2)
    assert groups[0].tolist() == [0, 2]
    assert [col[g].tolist() for g in groups[1:]] == [[1.0, 2.0], [3.0, 5.0]]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/generator/test_truth.py -q`
Expected: collection error, `ImportError: cannot import name 'cross_fit'`

- [ ] **Step 4: Replace `value_of_knowing` in `acqlab/generator/truth.py`**

Delete the whole existing `def value_of_knowing(...)` function (from its `def` line down to the line before `def _decision_values`) and put this in its place:

```python
def value_groups(col: np.ndarray, bins: int = 10) -> list[np.ndarray]:
    """Draw indices grouped by one column's value: one group where it is exactly 0, then quantile groups for the
    rest (empty groups dropped)."""
    rest = np.flatnonzero(col > 0)
    groups = [np.flatnonzero(col == 0)] + np.array_split(rest[np.argsort(col[rest])], bins)
    return [g for g in groups if len(g)]


def cross_fit(groups: list[np.ndarray], reg_go: np.ndarray, reg_no: np.ndarray) -> tuple[float, np.ndarray]:
    """Expected regret when the go/no-go decision is chosen separately within each group, and each draw's decision
    (True = go). Cross-fitted: a group's decision is chosen on one half of the draws and scored on the other (both
    ways round), so noise in a group that cannot matter does not look like value."""
    n = len(reg_go)
    first = np.arange(n) % 2 == 0  # draws are iid, so alternate draws make two independent halves
    decision = np.zeros(n, dtype=bool)

    def go(idx: np.ndarray) -> bool:
        return bool(reg_go[idx].mean() <= reg_no[idx].mean())

    total = 0.0
    for half in (first, ~first):
        prior_go = go(np.flatnonzero(~half))  # a group with no draws in the other half keeps the prior decision
        for g in groups:
            score, fit = g[half[g]], g[~half[g]]
            chosen = go(fit) if len(fit) else prior_go
            decision[score] = chosen
            total += (reg_go if chosen else reg_no)[score].sum()
    return total / n, decision


def value_of_knowing(draws: np.ndarray, reg_go: np.ndarray, reg_no: np.ndarray, bins: int = 10) -> list[float]:
    """Per column: expected regret with every fact at its prior, minus expected regret with that fact known.
    Knowing a fact is approximated by deciding separately within groups of its draws (`value_groups`), cross-fitted
    (`cross_fit`)."""
    everything = cross_fit([np.arange(len(draws))], reg_go, reg_no)[0]
    return [max(0.0, everything - cross_fit(value_groups(col, bins), reg_go, reg_no)[0]) for col in draws.T]
```

- [ ] **Step 5: Run the whole suite, and confirm the batch is byte-identical**

Run: `uv run pytest -q`
Expected: `132 passed`

```bash
uv run python -m acqlab.generator.batch --out data/ref_task1_after --dev 20 --test 20 --hand 2 --showcase 1
diff -r data/ref_task1 data/ref_task1_after && echo IDENTICAL
```
Expected: `IDENTICAL`. If anything differs, stop: the refactor changed Plan 2's numbers.

- [ ] **Step 6: Clean up and commit**

```bash
rm -rf data/ref_task1 data/ref_task1_after
git add acqlab/generator/truth.py tests/generator/test_truth.py
git commit -m "refactor(truth): share value_groups and cross_fit with the routers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Beliefs and simulated worlds

**Files:**
- Create: `acqlab/routers/__init__.py` (empty), `acqlab/routers/beliefs.py`
- Create: `tests/routers/__init__.py` (empty), `tests/routers/test_beliefs.py`

**Interfaces:**
- Consumes: `acqlab.generator.traps.TRAPS`, `params_for`; `acqlab.engine.walk_away`; `acqlab.generator.sample.BaseDeal`.
- Produces:
  - `Issue(p_real=0.0, hi=0.0, known=None, proposed=True)`, a NamedTuple with property `.open` (True when proposed and not yet known)
  - `Beliefs = dict[str, Issue]`
  - `draw(beliefs, n, rng) -> np.ndarray`, n×5 in `TRAPS` order, in $M
  - `walk_aways(b: BaseDeal, values) -> np.ndarray`
  - `HAIRCUT_CAP = 0.95`

- [ ] **Step 1: Write the failing tests**

Create empty `tests/routers/__init__.py`, then `tests/routers/test_beliefs.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/routers/test_beliefs.py -q`
Expected: `ModuleNotFoundError: No module named 'acqlab.routers'`

- [ ] **Step 3: Implement**

Create empty `acqlab/routers/__init__.py`, then `acqlab/routers/beliefs.py`:

```python
"""A router's beliefs about the five issues, and simulated worlds drawn from them (Plan 3 design §1). All values $M."""
from typing import NamedTuple

import numpy as np

from acqlab.engine import walk_away
from acqlab.generator.sample import BaseDeal
from acqlab.generator.traps import TRAPS, params_for

HAIRCUT_CAP = 0.95  # a sampled customer loss never exceeds 95% of revenue (the engine needs haircut < 1)


class Issue(NamedTuple):
    p_real: float = 0.0  # open: chance the problem exists
    hi: float = 0.0  # open: top of the size range if it does
    known: tuple[float, float] | None = None  # learned (low, high); low == high for a point value
    proposed: bool = True  # False: forgotten, so no router scores it and worlds assume 0

    @property
    def open(self) -> bool:
        return self.proposed and self.known is None


Beliefs = dict[str, Issue]  # trap -> issue


def draw(beliefs: Beliefs, n: int, rng: np.random.Generator) -> np.ndarray:
    """n worlds x 5 traps ($M, TRAPS order). Every issue consumes the same random numbers whatever its state, so two
    routers at the same step share their draws (common random numbers)."""
    cols = []
    for trap in TRAPS:
        issue, u, r = beliefs[trap], rng.random(n), rng.random(n)
        if issue.known is not None:
            low, high = issue.known
            cols.append(low + u * (high - low))
        elif issue.proposed:
            cols.append(u * issue.hi * (r < issue.p_real))
        else:
            cols.append(np.zeros(n))
    return np.column_stack(cols)


def walk_aways(b: BaseDeal, values: np.ndarray) -> np.ndarray:
    """Walk-away price of each world."""
    capped = values.copy()
    col = TRAPS.index("concentration")
    capped[:, col] = np.minimum(capped[:, col], HAIRCUT_CAP * b.teaser.revenue_ltm)
    return np.array([walk_away(b.deal, params_for(dict(zip(TRAPS, row.tolist())), b)) for row in capped])
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/routers/test_beliefs.py -q` → `5 passed`; then `uv run pytest -q` → `137 passed`

- [ ] **Step 5: Commit**

```bash
git add acqlab/routers/__init__.py acqlab/routers/beliefs.py tests/routers/__init__.py tests/routers/test_beliefs.py
git commit -m "feat(routers): issue beliefs and simulated worlds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Routers

**Files:**
- Create: `acqlab/routers/routers.py`
- Test: `tests/routers/test_routers.py`

**Interfaces:**
- Consumes: `Issue`, `draw`, `walk_aways` (Task 2); `cross_fit`, `value_groups` (Task 1).
- Produces:
  - Every router has the signature `fn(values, w, ask, costs, open_, rng=None) -> dict[str, float]`, where a higher score means read first: `score_regret` (router 6), `score_flip` (5), `score_sensitivity` (3), `checklist` (1) and `random_order`.
  - `ROUTERS = {name: (fn, needs_worlds)}`, with names checklist, random, sensitivity, flip and regret.
  - `decide(w, ask) -> (go: bool, walk_away_estimate: float)`
  - `regrets(w, ask)`, `PAIR_TOP = 3`, `PAIR_BINS = 4`.

- [ ] **Step 1: Write the failing tests**

Create `tests/routers/test_routers.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/routers/test_routers.py -q`
Expected: `ModuleNotFoundError: No module named 'acqlab.routers.routers'`

- [ ] **Step 3: Implement**

Create `acqlab/routers/routers.py`:

```python
"""Routers: score each open issue from shared simulated worlds (Plan 3 design §2). A router sees beliefs, worlds and
costs only, never the answer key. Higher score = read first."""
import itertools

import numpy as np

from acqlab.generator.traps import TRAPS
from acqlab.generator.truth import cross_fit, value_groups

PAIR_TOP = 3  # pair screening looks at the top issues by value
PAIR_BINS = 4  # size groups per issue when two issues are grouped jointly


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
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/routers/test_routers.py -q` → `7 passed`; then `uv run pytest -q` → `144 passed`

- [ ] **Step 5: Commit**

```bash
git add acqlab/routers/routers.py tests/routers/test_routers.py
git commit -m "feat(routers): checklist, sensitivity, flip and regret routers with pair screening

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Track A runner

**Files:**
- Create: `acqlab/routers/track_a.py`
- Test: `tests/routers/test_track_a.py`

**Interfaces:**
- Consumes: Tasks 1–3; `acqlab.generator.batch.AnswerKey`, `build`, `run`; `acqlab.dataroom.tools.BUDGET_SHARE`.
- Produces:
  - `Setting(router, investigator, level, share, truth="generator", clue=0.5)` and `grid(name)` for the headline, full and hints grids.
  - `priors(key, level, clue=0.5) -> Beliefs`, `self_consistent(key, level) -> AnswerKey`, `investigate(fact, kind, rng)`.
  - `run(key, setting, cache=None) -> dict`, `oracle_table(key, level, clue=0.5, cache=None)`, `run_oracle(key, setting, table)`, `run_deal(path, settings) -> list[dict]`.
  - `summarize(rows) -> dict`, `bootstrap_ci(diff)`, `main(argv) -> int`.
  - Output: `<deals>/results.jsonl` and `<deals>/summary.json`.

Run semantics (from the spec):
1. Route while an open issue fits in `remaining − 10% reserve`.
2. The sweep then reads the cheapest never-read issue that still fits.
3. The final decision comes from `N_WORLDS` worlds at seed slot `FINAL`.

The worlds at each step are seeded by (deal seed, level, step), so routers with the same beliefs share them. The oracle always gets the perfect investigator and may spend the whole budget.

- [ ] **Step 1: Write the failing tests**

Create `tests/routers/test_track_a.py`:

```python
import json
import math

import numpy as np
import pytest

import acqlab.routers.track_a as ta
from acqlab.dataroom.tools import BUDGET_SHARE
from acqlab.generator.batch import build, run as run_batch
from acqlab.generator.traps import TRAPS
from acqlab.routers.track_a import (ALL_ROUTERS, Setting, bootstrap_ci, grid, investigate, oracle_table, priors, run,
                                    run_oracle, self_consistent, summarize)


@pytest.fixture(autouse=True)
def few_worlds(monkeypatch):
    """No assertion here depends on the number of simulated worlds; 60 keeps the file fast."""
    monkeypatch.setattr(ta, "N_WORLDS", 60)


@pytest.fixture(scope="module")
def keys():
    out = []
    for i in range(6):
        key, docs, _ = build(f"t-{i:03d}", "test", 300 + i, mc=20)
        key.budget = float(math.ceil(BUDGET_SHARE * sum(d.pages for d in docs)))
        out.append(key)
    return out


def test_priors_are_noisy_deterministic_and_never_the_generator_prior(keys):
    k = keys[0]
    a, b = priors(k, "medium"), priors(k, "medium")
    assert a == b and set(a) == set(TRAPS)
    assert any(abs(a[f.trap].hi - f.worst) > 1e-6 for f in k.truth.facts)
    assert any(abs(i.p_real - 0.30) > 1e-6 for i in a.values())
    assert all(i.proposed for i in priors(k, "low").values())


def test_no_hint_at_clue_one_half_and_strong_hints_point_at_real_problems(keys):
    assert all(priors(k, "medium") == priors(k, "medium", 0.5) for k in keys)
    gap = []
    for k in keys:
        base, hinted = priors(k, "medium"), priors(k, "medium", 0.9)
        for f in k.truth.facts:
            assert hinted[f.trap].hi == base[f.trap].hi
            gap.append((hinted[f.trap].p_real - base[f.trap].p_real) * (1 if f.role != "clean" else -1))
    assert np.mean(gap) > 0


def test_investigator_variants(keys):
    facts = [f for k in keys for f in k.truth.facts]
    rng = np.random.default_rng(0)
    for f in facts:
        want = tuple(f.documented) if f.documented else (f.amount, f.amount)
        assert investigate(f, "perfect", rng) == want
        noisy = investigate(f, "noisy", rng)
        assert noisy[0] <= (f.documented[0] if f.documented else f.amount) + 1e-9
        assert noisy[1] >= (f.documented[1] if f.documented else f.amount) - 1e-9
        if f.amount == 0 and not f.documented:
            assert noisy == (0.0, 0.0)
    fails = sum(investigate(facts[0], "failure", rng) is None for _ in range(2000))
    assert abs(fails / 2000 - 0.25) < 0.04


def test_a_run_is_deterministic_within_budget_and_records_what_it_read(keys):
    for r in ALL_ROUTERS[:-1]:
        s = Setting(r, "failure", "high", 0.5)
        a, b = run(keys[1], s), run(keys[1], s)
        assert a == b
        assert a["pages"] <= 0.5 * keys[1].budget + 1e-9
        assert a["pages"] == sum(keys[1].retrieval_cost[x] for x in a["reads"])
        assert a["regret"] >= 0 and (a["regret"] == 0 or not a["correct"])  # regret only for a wrong call


def test_the_sweep_finds_a_forgotten_problem(keys, monkeypatch):
    key = next(k for k in keys if any(f.role != "clean" for f in k.truth.facts))
    problem = next(f.trap for f in key.truth.facts if f.role != "clean")
    real = ta.priors
    monkeypatch.setattr(ta, "priors", lambda k, level, clue=0.5: {
        t: i._replace(proposed=t != problem) for t, i in real(k, level, clue).items()})
    row = run(key, Setting("checklist", "perfect", "low", 1.0))
    assert problem in row["reads"] and row["found_by_sweep"]


def test_the_oracle_is_never_worse_than_any_router(keys):
    for k in keys:
        table = oracle_table(k, "medium")
        for share in (0.25, 0.5):
            best = run_oracle(k, Setting("oracle", "perfect", "medium", share), table)["regret"]
            for r in ("checklist", "random", "sensitivity", "flip", "regret"):
                assert best <= run(k, Setting(r, "perfect", "medium", share))["regret"] + 1e-12


def test_self_consistent_truth_is_drawn_from_the_priors(keys):
    k = keys[2]
    s = self_consistent(k, "medium")
    assert s.truth.base == k.truth.base and s.truth.face_go == k.truth.face_go
    assert {f.role for f in s.truth.facts} <= {"clean", "problem"}
    b = priors(k, "medium")
    assert all(f.amount == 0 or f.amount <= b[f.trap].hi for f in s.truth.facts)
    assert s == self_consistent(k, "medium")


def test_grids():
    assert len(grid("headline")) == 7 * 3 * 2
    assert len(grid("full")) == 7 * 3 * 3 * 3
    assert len(grid("hints")) == 7 * 3 * 2 and {s.clue for s in grid("hints")} == {0.7, 0.9}


def test_bootstrap_ci_and_summary():
    lo, hi = bootstrap_ci(np.array([-1.0, -2.0, -1.5, -0.5]))
    assert lo < hi < 0
    rows = [{"deal": f"d{i}", **Setting(r, "perfect", "medium", 0.5)._asdict(), "regret": reg, "flip": True,
             "has_decoy": False, "has_interaction": False, "prior_inside": 1.0, "found_by_sweep": False}
            for i in range(20) for r, reg in (("regret", 0.0), ("sensitivity", 0.1), ("flip", 0.1),
                                              ("checklist", 0.1))]
    cell = next(c for c in summarize(rows)["cells"] if c["slice"] == "all")
    assert cell["mean_regret"]["regret"] == 0.0 and cell["regret_minus_sensitivity"]["router6_wins"]


def test_main_writes_resumes_and_skips_broken_deals(tmp_path, monkeypatch, capsys):
    # --workers 1 runs in-process, so the few_worlds patch applies
    run_batch(tmp_path, {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, mc=20)
    argv = ["--deals", str(tmp_path), "--grid", "headline", "--workers", "1"]
    assert ta.main(argv) == 0
    lines = (tmp_path / "results.jsonl").read_text().splitlines()
    assert len(lines) == 2 * 7 * 3 * 2
    assert ta.main(argv) == 0
    assert (tmp_path / "results.jsonl").read_text().splitlines() == lines
    assert json.loads((tmp_path / "summary.json").read_text())["cells"]
    (tmp_path / "truth" / "dev-999.json").write_text("{not json")
    assert ta.main(argv) == 1
    assert "SKIPPED dev-999" in capsys.readouterr().err
    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == len(lines)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/routers/test_track_a.py -q`
Expected: `ModuleNotFoundError: No module named 'acqlab.routers.track_a'`

- [ ] **Step 3: Implement**

Create `acqlab/routers/track_a.py`:

```python
"""Track A (Plan 3 design): routers against a simulated investigator, no LLM.

  uv run python -m acqlab.routers.track_a --deals data/track_a --grid headline --workers 8

Results go to <deals>/results.jsonl (one line per run; reruns skip finished runs) and <deals>/summary.json.
"""
import argparse
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import NamedTuple

import numpy as np

from acqlab.engine import is_go, walk_away
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS, params_for
from acqlab.generator.truth import Fact
from acqlab.routers.beliefs import Beliefs, Issue, draw, walk_aways
from acqlab.routers.routers import ROUTERS, decide

LEVELS = {"low": (0.2, 0.0), "medium": (0.4, 0.10), "high": (0.7, 0.25)}  # prior noise s, forget probability f
INVESTIGATORS = ("perfect", "failure", "noisy")
SHARES = (0.25, 0.5, 1.0)  # budget as a share of the deal's default budget
ALL_ROUTERS = ("checklist", "random", "sensitivity", "flip", "regret", "regret+veto", "oracle")
N_WORLDS = 400
BASE_P_REAL = 0.30
SWEEP_SHARE = 0.10
FAIL_P = 0.25
NOISE = 0.25
VETO = 0.0025  # "regret+veto" stops when the best score is below this share of the asking price per page
FULL_DEALS = 500  # the full and hints grids use the first 500 deals
CLUES = (0.7, 0.9)  # hints grid: chance each hint is right (0.5 = a coin flip = no hint)
FINAL = 10_000  # world-draw seed slot for the final decision (steps use 0, 1, 2, ...)


class Setting(NamedTuple):
    router: str
    investigator: str
    level: str
    share: float
    truth: str = "generator"  # generator: the answer key; self: true values drawn from the router's own priors
    clue: float = 0.5  # chance each prior hint is right; 0.5 = no information


def grid(name: str) -> list[Setting]:
    """headline: both truths at medium priors; full: every investigator and prior level; hints: the clue study."""
    if name == "headline":
        axes = (ALL_ROUTERS, ("perfect",), ("medium",), SHARES, ("generator", "self"), (0.5,))
    elif name == "full":
        axes = (ALL_ROUTERS, INVESTIGATORS, tuple(LEVELS), SHARES, ("generator",), (0.5,))
    else:
        axes = (ALL_ROUTERS, ("perfect",), ("medium",), SHARES, ("generator",), CLUES)
    return [Setting(*s) for s in itertools.product(*axes)]


def _idx(s: Setting) -> tuple[int, int, int]:
    return INVESTIGATORS.index(s.investigator), list(LEVELS).index(s.level), SHARES.index(s.share)


def priors(key: AnswerKey, level: str, clue: float = 0.5) -> Beliefs:
    """Noisy versions of each trap's range (0, worst), never the generator's own prior. The same for every router.
    With clue > 0.5, each issue also gets a hint ("real problem" or "clean") that is right with probability `clue`,
    and p_real is scaled by the hint's likelihood ratio. Hints come from the answer key: a "what if" study only."""
    s, forget = LEVELS[level]
    rng = np.random.default_rng([key.truth.seed, list(LEVELS).index(level)])
    hints = np.random.default_rng([key.truth.seed, list(LEVELS).index(level), 7])  # base priors ignore the clue
    out = {}
    for f in key.truth.facts:
        p = BASE_P_REAL * float(np.exp(rng.normal(0, s)))
        hi = f.worst * float(np.exp(rng.normal(0, s)))
        proposed = bool(rng.random() >= forget)
        says_real = (f.role != "clean") == (hints.random() < clue)
        ratio = clue / (1 - clue)
        p = float(np.clip(p * (ratio if says_real else 1 / ratio), 0.02, 0.95))
        out[f.trap] = Issue(p_real=p, hi=hi, proposed=proposed)
    return out


def self_consistent(key: AnswerKey, level: str) -> AnswerKey:
    """The fair game: the same deal, with true values drawn from the medium-noise priors themselves (forgotten
    issues included), so the routers' beliefs are exactly right. Roles become "problem" or "clean"."""
    t = key.truth
    b = {trap: issue._replace(proposed=True) for trap, issue in priors(key, level).items()}
    values = draw(b, 1, np.random.default_rng([t.seed, list(LEVELS).index(level), 777]))[0]
    facts = [f.model_copy(update={"amount": float(v), "realized": float(v), "documented": None,
                                  "role": "clean" if v == 0 else "problem"}) for f, v in zip(t.facts, values)]
    p = params_for({f.trap: f.amount for f in facts}, t.base)
    return key.model_copy(update={"truth": t.model_copy(update={
        "facts": facts, "walk_away": walk_away(t.deal, p), "go": is_go(t.deal, p),
        "case_type": "clean" if all(f.role == "clean" for f in facts) else "problem"})})


def investigate(f: Fact, kind: str, rng: np.random.Generator) -> tuple[float, float] | None:
    """The simulated investigator's reply: a (low, high) range, or None if the read failed."""
    if kind == "failure" and rng.random() < FAIL_P:
        return None
    if f.documented:
        return tuple(f.documented)
    if kind == "noisy" and f.amount > 0:
        r = f.amount * rng.uniform(1 - NOISE, 1 + NOISE)
        return r / (1 + NOISE), r / (1 - NOISE)
    return f.amount, f.amount


def regret(key: AnswerKey, go: bool) -> float:
    """$M regret against the answer key's knowable truth."""
    t = key.truth
    ask = t.deal.asking_price
    if go and not t.go:
        return max(0.0, ask - t.walk_away)
    if not go and t.go:
        return max(0.0, t.walk_away - ask)
    return 0.0


def _simulate(key: AnswerKey, beliefs: Beliefs, level: str, slot: int, cache: dict) -> tuple[np.ndarray, np.ndarray]:
    """(values, walk-aways) of N_WORLDS worlds. Seeded by deal, level and slot (step number or FINAL) only, so every
    router at the same step with the same beliefs gets the same worlds, which are therefore computed once per deal."""
    k = (level, slot, tuple(beliefs[t] for t in TRAPS))
    if k not in cache:
        rng = np.random.default_rng([key.truth.seed, list(LEVELS).index(level), slot])
        values = draw(beliefs, N_WORLDS, rng)
        cache[k] = values, walk_aways(key.truth.base, values)
    return cache[k]


def _record(key: AnswerKey, s: Setting, beliefs0: Beliefs, reads: list[str], go: bool, est: float,
            found: bool) -> dict:
    t = key.truth
    ask, facts = t.deal.asking_price, {f.trap: f for f in t.facts}
    nonclean = [f for f in t.facts if f.role != "clean"]
    return {
        "deal": t.id, **s._asdict(), "regret": regret(key, go) / ask, "correct": go == t.go,
        "wa_error": abs(est - t.walk_away) / ask, "pages": sum(key.retrieval_cost[r] for r in reads),
        "pages_on_decoys": sum(key.retrieval_cost[r] for r in reads if facts[r].role == "decoy"),
        "found_by_sweep": found, "reads": reads, "flip": t.go != t.face_go,
        "has_decoy": any(f.role == "decoy" for f in t.facts),
        "has_interaction": any(f.role == "interaction" for f in t.facts), "case_type": t.case_type,
        "prior_inside": (sum(f.realized <= beliefs0[f.trap].hi for f in nonclean) / len(nonclean)) if nonclean
        else None,
    }


def run(key: AnswerKey, s: Setting, cache: dict | None = None) -> dict:
    """One run: route, sweep, decide. `cache` shares simulated worlds between runs on the same deal."""
    cache = {} if cache is None else cache
    t = key.truth
    ask, costs, facts = t.deal.asking_price, key.retrieval_cost, {f.trap: f for f in t.facts}
    beliefs0 = priors(key, s.level, s.clue)
    beliefs = dict(beliefs0)
    budget = key.budget * s.share
    spent, reads, attempts = 0.0, [], {trap: 0 for trap in TRAPS}
    inv, lvl, shr = _idx(s)
    order_rng = np.random.default_rng([t.seed, lvl, shr, 99])

    def read(trap: str) -> tuple[float, float] | None:
        nonlocal spent
        spent += costs[trap]
        reads.append(trap)
        attempts[trap] += 1
        rng = np.random.default_rng([t.seed, inv, lvl, TRAPS.index(trap), attempts[trap]])
        return investigate(facts[trap], s.investigator, rng)

    name = s.router.removesuffix("+veto")
    fn, needs_worlds = ROUTERS[name]
    reserve = SWEEP_SHARE * budget
    for step in itertools.count():
        open_ = [x for x in TRAPS if beliefs[x].open and costs[x] <= budget - spent - reserve + 1e-9]
        if not open_:
            break
        values = w = None
        if needs_worlds:
            values, w = _simulate(key, beliefs, s.level, step, cache)
        scores = fn(values, w, ask, costs, open_, order_rng)
        best = max(open_, key=lambda x: (scores[x], -TRAPS.index(x)))
        if s.router.endswith("+veto") and scores[best] < VETO * ask:
            break
        reply = read(best)
        if reply is not None:
            beliefs[best] = beliefs[best]._replace(known=reply)
    found = False
    while cand := [x for x in TRAPS if x not in reads and costs[x] <= budget - spent + 1e-9]:
        trap = min(cand, key=lambda x: (costs[x], TRAPS.index(x)))
        reply = read(trap)
        if reply is not None:
            found |= not beliefs[trap].proposed and facts[trap].role != "clean"
            beliefs[trap] = beliefs[trap]._replace(known=reply, proposed=True)
    go, est = decide(_simulate(key, beliefs, s.level, FINAL, cache)[1], ask)
    return _record(key, s, beliefs0, reads, go, est, found)


def oracle_table(key: AnswerKey, level: str, clue: float = 0.5,
                 cache: dict | None = None) -> dict[tuple[str, ...], tuple[float, float, bool, float]]:
    """For every subset of traps learned perfectly: (true regret, cost, go, walk-away estimate)."""
    cache = {} if cache is None else cache
    beliefs0 = priors(key, level, clue)
    out = {}
    for k in range(len(TRAPS) + 1):
        for subset in itertools.combinations(TRAPS, k):
            beliefs = dict(beliefs0)
            for f in key.truth.facts:
                if f.trap in subset:
                    beliefs[f.trap] = beliefs[f.trap]._replace(known=tuple(f.documented or (f.amount, f.amount)),
                                                               proposed=True)
            go, est = decide(_simulate(key, beliefs, level, FINAL, cache)[1], key.truth.deal.asking_price)
            out[subset] = (regret(key, go), sum(key.retrieval_cost[x] for x in subset), go, est)
    return out


def run_oracle(key: AnswerKey, s: Setting, table: dict) -> dict:
    """Ceiling: the affordable subset of perfect reads with the lowest true regret (ties: cheaper)."""
    budget = key.budget * s.share
    subset = min((sub for sub, v in table.items() if v[1] <= budget + 1e-9), key=lambda sub: table[sub][:2])
    _, _, go, est = table[subset]
    return _record(key, s, priors(key, s.level, s.clue), list(subset), go, est, False)


def run_deal(path: Path, settings: list[Setting]) -> list[dict]:
    """Every pending setting for one deal. Errors come back as a single {"deal", "error"} row."""
    try:
        real = AnswerKey.model_validate_json(path.read_text())
        keys = {"generator": real}
        tables: dict[tuple, dict] = {}
        caches: dict[str, dict] = {"generator": {}, "self": {}}  # worlds depend on the truth mode's key
        rows = []
        for s in settings:
            if s.truth not in keys:
                keys[s.truth] = self_consistent(real, s.level)
            key, cache = keys[s.truth], caches[s.truth]
            if s.router == "oracle":
                tk = (s.truth, s.level, s.clue)
                if tk not in tables:
                    tables[tk] = oracle_table(key, s.level, s.clue, cache)
                rows.append(run_oracle(key, s, tables[tk]))
            else:
                rows.append(run(key, s, cache))
        return rows
    except Exception as e:  # logged and skipped by main(), never scored
        return [{"deal": path.stem, "error": f"{type(e).__name__}: {e}"}]


def _key(row: dict) -> tuple:
    return (row["deal"], *(row[f] for f in Setting._fields))


def bootstrap_ci(diff: np.ndarray, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Paired bootstrap 95% CI of the mean of per-deal differences."""
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, len(diff), (n, len(diff)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


COMPARED = ("sensitivity", "flip", "random")  # router 6 minus each of these, per cell (H2, and the floor)
SLICES = {"all": lambda r: True, "flip": lambda r: r["flip"], "decoy": lambda r: r["has_decoy"],
          "interaction": lambda r: r["has_interaction"]}


def summarize(rows: list[dict]) -> dict:
    """Mean normalised regret per router and cell, and paired CIs for router 6 minus routers 3, 5 and random."""
    cells: dict[tuple, dict[str, dict[str, float]]] = {}
    for r in rows:
        cell_key = (r["truth"], r["clue"], r["investigator"], r["level"], r["share"])
        cells.setdefault(cell_key, {}).setdefault(r["router"], {})[r["deal"]] = r
    out = []
    for (truth, clue, inv, level, share), by_router in sorted(cells.items()):
        for name, keep in SLICES.items():
            cell = {"truth": truth, "clue": clue, "investigator": inv, "level": level, "share": share, "slice": name,
                    "mean_regret": {}}
            for router, by_deal in by_router.items():
                vals = [r["regret"] for r in by_deal.values() if keep(r)]
                cell["mean_regret"][router] = float(np.mean(vals)) if vals else None
            six = by_router.get("regret", {})
            for other in COMPARED:
                deals = [d for d, r in six.items() if keep(r) and d in by_router.get(other, {})]
                if len(deals) >= 2:
                    diff = np.array([six[d]["regret"] - by_router[other][d]["regret"] for d in deals])
                    lo, hi = bootstrap_ci(diff)
                    cell[f"regret_minus_{other}"] = {"mean": float(diff.mean()), "ci95": [lo, hi], "n": len(deals),
                                                     "router6_wins": bool(diff.mean() < 0 and hi < 0)}
            cell["n"] = sum(keep(r) for r in six.values())
            out.append(cell)
    calib = {}
    for level in LEVELS:
        vals = [r["prior_inside"] for r in rows if r["level"] == level and r["router"] == "checklist"
                and r["truth"] == "generator" and r["clue"] == 0.5 and r["prior_inside"] is not None]
        if vals:
            calib[level] = float(np.mean(vals))
    sweep = float(np.mean([r["found_by_sweep"] for r in rows])) if rows else 0.0
    return {"cells": out, "prior_calibration": calib, "sweep_find_rate": sweep}


def _print(summary: dict) -> None:
    for c in summary["cells"]:
        if c["slice"] != "all" and c["n"] == 0:
            continue
        regrets = " ".join(f"{k}={v:.4f}" for k, v in c["mean_regret"].items() if v is not None)
        wins = " ".join(f"6<{k.removeprefix('regret_minus_')}:{'yes' if v['router6_wins'] else 'no'}"
                        f"({v['mean']:+.4f} [{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}])"
                        for k, v in c.items() if k.startswith("regret_minus_"))
        print(f"{c['truth']:9s} clue={c['clue']:.1f} {c['investigator']:7s} {c['level']:6s} {c['share']:.2f} "
              f"{c['slice']:11s} n={c['n']:4d} {regrets} {wins}")
    print("prior calibration (share of problems inside the prior range):", summary["prior_calibration"])
    print("share of runs where the sweep found a forgotten problem:", round(summary["sweep_find_rate"], 4))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=Path, default=Path("data/track_a"))
    ap.add_argument("--grid", choices=("headline", "full", "hints"), default="headline")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="use only the first N deals")
    args = ap.parse_args(argv)
    paths = sorted((args.deals / "truth").glob("*.json"))
    limit = None if args.grid == "headline" else FULL_DEALS
    if args.limit is not None:
        limit = args.limit if limit is None else min(limit, args.limit)
    paths = paths[:limit]
    settings = grid(args.grid)
    out = args.deals / "results.jsonl"
    rows = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
    done = {_key(r) for r in rows}
    todo = [(p, [s for s in settings if (p.stem, *s) not in done]) for p in paths]
    todo = [(p, pending) for p, pending in todo if pending]
    errors = 0
    with out.open("a") as fh, ProcessPoolExecutor(args.workers) as pool:
        mapper = map if args.workers == 1 else pool.map  # 1 = in-process (tests, debugging)
        for got in mapper(run_deal, [p for p, _ in todo], [pending for _, pending in todo]):
            for r in got:
                if "error" in r:
                    errors += 1
                    print(f"SKIPPED {r['deal']}: {r['error']}", file=sys.stderr)
                else:
                    fh.write(json.dumps(r) + "\n")
                    rows.append(r)
            fh.flush()
    wanted = {(p.stem, *s) for p in paths for s in settings}
    summary = summarize([r for r in rows if _key(r) in wanted])
    (args.deals / "summary.json").write_text(json.dumps(summary, indent=2))
    _print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/routers/test_track_a.py -q` → `10 passed` (about 20 s); then `uv run pytest -q` → `154 passed`

- [ ] **Step 5: Commit**

```bash
git add acqlab/routers/track_a.py tests/routers/test_track_a.py
git commit -m "feat(routers): Track A runner with priors, investigator, sweep, oracle and summary

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Track A runs and write-up (controller, not a subagent)

These are long, unattended runs (about 6 hours in total). The controller runs them in the background, and every command is resumable: rerun it after an interruption. **No LLM calls.**

- [ ] **Step 1: Generate the Track A deals** (about 5 min)

```bash
uv run python -m acqlab.generator.batch --out data/track_a --dev 2000 --test 0 --hand 0 --showcase 0 --seed 200000
```
Expected: `generated 2000 deals into data/track_a; 0 batch problems`

- [ ] **Step 2: Run the three grids** (about 3.7 h, 1.6 h and 0.9 h)

```bash
uv run python -m acqlab.routers.track_a --deals data/track_a --grid headline --workers 8
uv run python -m acqlab.routers.track_a --deals data/track_a --grid full --workers 8
uv run python -m acqlab.routers.track_a --deals data/track_a --grid hints --workers 8
```
Each prints its table and writes `data/track_a/summary.json` for the rows of that grid. Save each printed table (for example, redirect to `data/track_a/<grid>.txt`). Expected exit code 0; a `SKIPPED` line means a deal failed, so investigate it and don't ignore it.

- [ ] **Step 3: Statistical checks** (the project's standing rule)

1. **Fair game:** in the headline table, the `self` rows should show router 6's regret below random's, with a CI that excludes zero (`6<random:yes`) at the 50% and 100% budgets. At 120 deals in pre-verification, the means were −0.0064 and −0.0036, but the CIs were still [−0.0160, +0.0026] and [−0.0099, +0.0001]. 2,000 deals narrows them about 4×. If either CI still includes zero at 2,000 deals, stop and investigate before writing anything up.
2. **Generator truth:** measure how often each router reads a decision-relevant fact (flipper, interaction, or an unresolvable fact that flips alone), and how often one comes before any decoy. Report the rates; don't assert them:

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from acqlab.generator.batch import AnswerKey
rows = [json.loads(l) for l in open("data/track_a/results.jsonl")]
keys = {p.stem: AnswerKey.model_validate_json(p.read_text()) for p in Path("data/track_a/truth").glob("*.json")}
rel = lambda f: f.role in ("flipper", "interaction") or (f.role == "unresolvable" and f.alone_flips)
for share in (0.25, 0.5, 1.0):
    for r in ("checklist", "random", "sensitivity", "flip", "regret", "oracle"):
        rs = [x for x in rows if x["share"] == share and x["router"] == r and x["truth"] == "generator"
              and x["investigator"] == "perfect" and x["level"] == "medium" and x["clue"] == 0.5]
        hit = n = first = m = 0
        for x in rs:
            facts = {f.trap: f for f in keys[x["deal"]].truth.facts}
            if any(rel(f) for f in facts.values()):
                n += 1; hit += any(rel(facts[t]) for t in x["reads"])
                if any(f.role == "decoy" for f in facts.values()):
                    m += 1
                    f0 = next((t for t in x["reads"] if rel(facts[t]) or facts[t].role == "decoy"), None)
                    first += f0 is not None and rel(facts[f0])
        print(f"{share:.2f} {r:12s} reads a relevant fact {hit}/{n}; relevant before decoy {first}/{m}")
PY
```

- [ ] **Step 4: Update `docs/HANDOFF.md`**

Record the Plan 3 status and the headline numbers: per cell, router 6 against 3, 5 and random, with CIs, on the all/flip/decoy/interaction slices. Also record: the fair-game result, the hints study (labelled "what if"), prior calibration, the sweep find rate, the veto row, and the Step 3 rates. **State the H2 verdict exactly as the pre-registered rule gives it**, cell by cell, and flag it for the week-4 checkpoint decision (spec §4: "if the router doesn't help, reframe").

- [ ] **Step 5: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs: Track A results (Plan 3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Done when

- `uv run pytest -q` → 154 passed.
- `uv run python -m acqlab.generator.batch` still gives 181 deals and 0 batch problems, with answer keys identical to before Task 1.
- The three Track A grids have run on `data/track_a`, and the handoff records the results and the H2 verdict.
- The final review runs on Opus. It re-runs the Task 5 Step 3 checks from the results files, and confirms `routers.py` never touches answer keys.

## Later

- Veto on for every router, and a page-price sweep (regret against pages spent), as requested in brainstorming.
- Router 2 (LLM judgment) in Track A once Plan 4's adapter exists.
- If router 6 keeps tying router 3: make costs vary (bigger, more varied data rooms), since "$ per page" can only differ from "value moved" when pages differ.
- Raise `N_WORLDS`, or average scores over seeds, if score noise limits router 6.

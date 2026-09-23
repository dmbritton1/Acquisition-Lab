# Plan 2: Deal Generator & Data Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the benchmark's synthetic LBO deals — each a budgeted data room plus a hidden answer key with engine-computed ground truth — so every system can be scored on decision regret.

**Architecture:** A pure-Python pipeline in `acqlab/generator/`: sample a deal's visible side from sourced ranges (`sample.py`), place five hidden facts whose roles are constructed with the Plan 1 engine (`traps.py`, `roles.py`), compute the answer key (`truth.py`), render documents where code writes every number (`documents.py`, `render.py`), validate (`validate.py`), and write rooms that only the budgeted tools in `acqlab/dataroom/tools.py` can read. Codex prose (`acqlab/llm.py`, `prose.py`) and the recoverability check (`recover.py`) sit on top and are optional; everything runs with template prose and no LLM.

**Tech Stack:** Python 3.12, uv, pydantic 2, numpy 2, pytest, hypothesis. Codex CLI (`codex exec`) for prose and extraction only.

**Spec:** `docs/superpowers/specs/2026-09-23-plan-2-generator-design.md` (this plan's design), under `docs/superpowers/specs/2026-09-22-acquisition-lab-design.md` §2 (binding authority).

**Where this fits:** Plan 2 of 7. Plan 3 (Track A routers) consumes the answer keys; Plan 4 hardens `acqlab/llm.py` and adds the solver sandbox.

## Global Constraints

- Python `>=3.12`; no new dependencies (pydantic, numpy; dev: pytest, hypothesis).
- All money in **$M**; rates as **decimals**. Fact amounts are rounded to **$0.1M** (documents show `$X.XM`).
- The engine (`acqlab.engine`) is the only source of financial outputs. The one engine change in this plan is the `flip_threshold` bounds fix in Task 2.
- **Code writes every number.** LLM prose may contain no digits; every value is a `{{placeholder}}` whose name has no digits.
- **Answer keys never sit under a room folder.** Rooms: `data/deals/<id>/room/`; keys: `data/truth/<id>.json`; both git-ignored (`data/` is in `.gitignore`).
- **Tests never call a real LLM.** They use fakes; real Codex calls happen only in Task 7 Step 6 (with user approval) and in batch runs with `--llm` / `--recover`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Subagents must never modify settings or permissions files, and must stop and report if a git operation is blocked.
- Never edit golden test numbers to make a test pass.

## Findings from pre-verifying this plan (read before starting)

All code below was run before the plan was written (108 tests pass in ~13 s; a full 181-deal batch generates in ~45 s with no batch problems). Running it changed or sharpened these points of the design; the design doc's "Revisions from pre-verification" section records them:

1. **Every deal records all five traps as facts.** The presence rule means an absent trap is rendered exactly like a clean one, so each deal has five facts: the planned roles plus clean facts. "2–5 facts" becomes "five facts, of which typically one to three are not clean".
2. **Case mix is clean 15%, flip 25%, interaction 10%, other 50%** (not ~60% flippers): every trap is adverse, so a flipper always turns go into no-go, and ~60% flips cannot coexist with ~50% true go. Measured over 1,200 deals: true go 44–48%, a deal with an unresolvable fact ~37%.
3. **Asking price = market EV × (1 + N(−15%, 10%)).** At the GF Data multiple, a 20% hurdle with no multiple expansion almost never clears (face-value walk-away is a median 83% of market EV), so asking prices sit below market averages. The minimum-equity cap then binds in about half of deals.
4. **Decision value uses a base-rate prior:** each fact is 0 with probability 0.70, else uniform on its range. With a uniform prior every deal is a certain no-go and every decision value is zero. Measured: flippers' median decision value is 0.7% of EV; decoys' and clean facts' median is 0.
5. **Engine bug fixed in Task 2:** `flip_threshold(..., lo, hi)` silently returned the midpoint when `lo > hi` — which is exactly how a negative EBITDA range arrives.
6. **Industry figures:** D&A % = EBITDA/Sales − pre-tax *unadjusted* operating margin (this cross-checks against Damodaran's capex dollars); Transportation was dropped (margin too thin for the margin rule) and Software excluded. Values were read twice from Damodaran's HTML tables and agree; checking them against his .xls files is on the later list.
7. **The working-capital trap is weak:** at most ~3% of EV, it rarely flips a deal or qualifies as a decoy. That is realistic and the planner only assigns roles a deal can support.
8. **About 1% of deals fail a check after amounts are rounded to $0.1M** (a decoy moving walk-away by $12.7M against a $12.75M bar). `batch.build` regenerates them; that is the checks working.
9. **Codex CLI comes bundled with the ChatGPT desktop app** (`/Applications/ChatGPT.app/Contents/Resources/codex`, codex-cli 0.155.0-alpha.9.2) but is not on PATH. The adapter looks for `CODEX_BIN`, then PATH, then the app's copy. Every flag it uses was checked against `codex exec --help`; it adds `--ephemeral` so thousands of generator calls stay out of the user's Codex history. Token parsing is still unverified until the first real call (Task 7 Step 6).
10. **Codex calls per deal: about 7 for prose, 10 for recoverability.** Prose is written one call per document (Codex returns every paragraph of that document as JSON, enforced with `--output-schema`); a paragraph that breaks a rule is retried on its own. Recoverability stays one fact per call (a positive and a negative probe per fact), because isolating each fact is the point of that check. A full batch is about 2,400 calls, so it spans several Codex usage windows.
12. **Usage limits are resumable.** Any sign of a failed Codex call (non-zero exit, an `error` or `turn.failed` event, an empty reply) raises `LLMUnavailable`; failed calls are never cached, so a limit message can never be mistaken for an answer. The batch stops with exit code 2 and says to run the same command again; the rerun replays every cached reply for free and continues from the first unanswered call (tested).
11. **A budget unit is 120 words of text** ("page"); a template-prose deal is ~20 pages, so the default budget (35%) is ~7 units. Codex prose makes documents longer, so budgets are computed per room.

## File Structure

| File | Responsibility |
|---|---|
| `acqlab/generator/industries.py` | Damodaran industry table |
| `acqlab/generator/sample.py` | Visible deal: teaser, financing, history, names |
| `acqlab/generator/traps.py` | Trap library: params, variants, worst cases, industry weights |
| `acqlab/generator/roles.py` | Severity-space role placement with the engine |
| `acqlab/generator/truth.py` | Answer key: plan roles, facts, ground truth, decision values |
| `acqlab/generator/documents.py` | Document model: slots, placeholders, pages, styles |
| `acqlab/generator/render.py` | Teaser and data-room documents; evidence per fact |
| `acqlab/dataroom/tools.py` | Room writer and budgeted `DataRoom` tools |
| `acqlab/generator/validate.py` | Engine, leak, consistency and batch checks |
| `acqlab/llm.py` | Minimal cached Codex adapter (hardened in Plan 4) |
| `acqlab/generator/prose.py` | LLM prose fill with digit and placeholder guards |
| `acqlab/generator/recover.py` | Recoverability check |
| `acqlab/generator/batch.py` | CLI: generate, validate and write every split |
| `acqlab/engine/walkaway.py` | (modify) `flip_threshold` bounds fix |

Each task creates its own modules and test files; the only edit to an existing file is the Task 2 engine fix.

---

### Task 1: Industry table and deal sampler

**Files:**
- Create: `acqlab/generator/__init__.py` (empty), `acqlab/generator/industries.py`, `acqlab/generator/sample.py`
- Create: `tests/generator/__init__.py` (empty)
- Test: `tests/generator/test_sample.py`

**Interfaces:**
- Consumes: `acqlab.engine.{Company, Deal, Financing, Policy}`.
- Produces: `INDUSTRIES: tuple[Industry, ...]` with `Industry.{name, kind, ebitda_margin, op_margin, capex_to_dep, nwc_pct, da_pct, capex_pct}`; `FISCAL_YEARS = (2023, 2024, 2025)`; models `Teaser`, `YearHistory`, `BaseDeal{teaser, deal, kind, market_multiple, top_customer_share, history}`; `sample_base(rng: np.random.Generator) -> BaseDeal` (asking price = market EV); `with_asking(b: BaseDeal, asking: float) -> BaseDeal`; `company_name(rng) -> str`; `REAL_NAMES`.

Create the two empty `__init__.py` files first.

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_sample.py`:
```python
import numpy as np
import pytest

from acqlab.generator.industries import INDUSTRIES
from acqlab.generator.sample import FISCAL_YEARS, REAL_NAMES, sample_base, with_asking


def test_capex_and_da_are_derived_from_damodaran_ratios():
    m = next(i for i in INDUSTRIES if i.name == "Machinery")
    assert m.da_pct == pytest.approx(0.1962 - 0.1586)
    assert m.capex_pct == pytest.approx((0.1962 - 0.1586) * 0.6786)


def test_every_industry_clears_the_margin_rule_at_face_value():
    assert all(i.ebitda_margin >= i.capex_pct + 0.05 for i in INDUSTRIES)


def test_same_seed_gives_the_same_deal():
    assert sample_base(np.random.default_rng(3)) == sample_base(np.random.default_rng(3))


def test_teaser_and_engine_inputs_agree_and_stay_in_sourced_ranges():
    for seed in range(50):
        b = sample_base(np.random.default_rng(seed))
        t, c = b.teaser, b.deal.company
        assert t.adj_ebitda == pytest.approx(t.reported_ebitda + t.claimed_addbacks)
        assert (c.reported_adj_ebitda, c.revenue_ltm) == (t.adj_ebitda, t.revenue_ltm)
        assert 50 <= t.asking_price <= 500 and 6 <= b.market_multiple <= 10
        assert 3 <= b.deal.financing.max_leverage <= 5
        cov = b.deal.financing.covenant_max_leverage
        assert [round(x - y, 9) for x, y in zip(cov, cov[1:])] == [0.25] * 4
        assert b.history[-1].fiscal_year == FISCAL_YEARS[-1] and b.history[-1].revenue == t.revenue_ltm
        assert not any(real in t.name.lower() for real in REAL_NAMES)


def test_with_asking_updates_teaser_and_deal_together():
    b = with_asking(sample_base(np.random.default_rng(0)), 99.0)
    assert b.deal.asking_price == b.teaser.asking_price == 99.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_sample.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/industries.py`:
```python
"""LBO-typical industries, from Damodaran (NYU Stern) US industry data, January 2026 update.

Read 2026-09-23 from pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/:
  margin.html  EBITDA/Sales; Pre-tax Unadjusted Operating Margin
  capex.html   Cap Ex/Deprecn
  wcdata.html  Non-cash WC/Sales
Derived: D&A % = EBITDA/Sales - pre-tax unadjusted operating margin; capex % = D&A % x Cap Ex/Deprecn.
Public-company figures stand in for mid-market targets (a stated proxy).
"""
from typing import Literal, NamedTuple


class Industry(NamedTuple):
    name: str
    kind: Literal["services", "manufacturing"]
    ebitda_margin: float
    op_margin: float
    capex_to_dep: float
    nwc_pct: float

    @property
    def da_pct(self) -> float:
        return self.ebitda_margin - self.op_margin

    @property
    def capex_pct(self) -> float:
        return self.da_pct * self.capex_to_dep


INDUSTRIES = (
    Industry("Business & Consumer Services", "services", 0.1565, 0.1227, 0.6525, 0.1452),
    Industry("Machinery", "manufacturing", 0.1962, 0.1586, 0.6786, 0.2442),
    Industry("Healthcare Products", "manufacturing", 0.2034, 0.1534, 0.7954, 0.2565),
    Industry("Building Materials", "manufacturing", 0.1732, 0.1264, 1.0863, 0.1844),
    Industry("Packaging & Container", "manufacturing", 0.1436, 0.0958, 0.8984, 0.1266),
    Industry("Electrical Equipment", "manufacturing", 0.1265, 0.0953, 1.1106, 0.2944),
    Industry("Chemical (Specialty)", "manufacturing", 0.1801, 0.1217, 1.5528, 0.2380),
    Industry("Food Processing", "manufacturing", 0.1525, 0.1063, 1.3435, 0.0668),
    Industry("Information Services", "services", 0.1728, 0.1189, 0.3519, 0.1662),
)
```

`acqlab/generator/sample.py`:
```python
"""Sample a deal's visible side: industry profile, teaser, financing terms, three years of history."""
import math

import numpy as np
from pydantic import BaseModel

from acqlab.engine import Company, Deal, Financing, Policy
from acqlab.generator.industries import INDUSTRIES

FISCAL_YEARS = (2023, 2024, 2025)  # last = LTM
_FIRST = ("Alder", "Brook", "Cedar", "Dunmore", "Elm", "Fairhaven", "Granite", "Harrow", "Iverson", "Juniper",
          "Kestrel", "Linden", "Marlow", "Northgate", "Osprey", "Pinecrest", "Quarry", "Redfern", "Stonebridge",
          "Thistle", "Upland", "Vantor", "Westmere", "Yarrow")
_SECOND = ("Ridge", "Harbor", "Valley", "Point", "Crest", "Field", "Mill", "Bay", "Hollow", "Summit")
_SUFFIX = ("Industries", "Holdings", "Group", "Solutions", "Manufacturing", "Services")
REAL_NAMES = frozenset({"granite construction", "summit materials", "cedar fair", "harbor freight"})


class Teaser(BaseModel):
    name: str
    industry: str
    revenue_ltm: float
    reported_ebitda: float
    claimed_addbacks: float
    adj_ebitda: float
    growth: float
    capex_pct: float
    nwc_pct: float
    asking_price: float


class YearHistory(BaseModel):
    fiscal_year: int
    revenue: float
    reported_ebitda: float


class BaseDeal(BaseModel):
    teaser: Teaser
    deal: Deal  # engine input at face value (asking price set by the caller)
    kind: str  # industry kind: services | manufacturing
    market_multiple: float
    top_customer_share: float
    history: list[YearHistory]  # oldest first; last is LTM


def company_name(rng: np.random.Generator) -> str:
    while True:
        name = f"{rng.choice(_FIRST)} {rng.choice(_SECOND)} {rng.choice(_SUFFIX)}"
        if not any(real in name.lower() for real in REAL_NAMES):
            return name


def _noisy(rng: np.random.Generator, x: float, sd: float = 0.15) -> float:
    return x * float(np.exp(rng.normal(0.0, sd)))


def sample_base(rng: np.random.Generator) -> BaseDeal:
    """Everything a teaser shows, plus the history behind it. Asking price = market EV; set_asking adds noise."""
    ind = INDUSTRIES[int(rng.integers(len(INDUSTRIES)))]
    multiple = float(rng.triangular(6.0, 7.2, 10.0))  # GF Data 2025 average 7.2x
    ev = math.exp(rng.uniform(math.log(50), math.log(500)))  # GF Data universe, $M
    adj = ev / multiple
    revenue = adj / _noisy(rng, ind.ebitda_margin)
    claimed = adj * float(rng.uniform(0.03, 0.30))  # add-backs claimed in the teaser
    growth = float(rng.uniform(-0.02, 0.08))
    capex_pct, nwc_pct = _noisy(rng, ind.capex_pct), _noisy(rng, ind.nwc_pct)
    max_lev = float(rng.uniform(3.0, 5.0))  # GF Data 3.6x; Lincoln 4.75-6.25x for larger borrowers
    cov1 = max_lev / (1 - float(rng.uniform(0.25, 0.35)))  # Sidley: 25-35% cushion
    deal = Deal(
        company=Company(revenue_ltm=revenue, reported_adj_ebitda=adj, growth=growth, capex_pct=capex_pct,
                        nwc_pct=nwc_pct, da_pct=_noisy(rng, ind.da_pct), tax_rate=0.25),
        financing=Financing(max_leverage=max_lev, interest_rate=float(rng.uniform(0.075, 0.095)),
                            amortization_pct=0.01, cash_sweep=0.5,
                            covenant_max_leverage=[cov1 - 0.25 * t for t in range(5)],
                            fees_pct=float(rng.uniform(0.02, 0.03))),
        policy=Policy(exit_multiple=multiple),
        asking_price=ev,
    )
    history = [YearHistory(fiscal_year=fy, revenue=revenue / (1 + growth) ** k * (_noisy(rng, 1, 0.02) if k else 1),
                           reported_ebitda=(adj - claimed) / (1 + growth) ** k * (_noisy(rng, 1, 0.03) if k else 1))
               for k, fy in zip((2, 1, 0), FISCAL_YEARS)]
    teaser = Teaser(name=company_name(rng), industry=ind.name, revenue_ltm=revenue, reported_ebitda=adj - claimed,
                    claimed_addbacks=claimed, adj_ebitda=adj, growth=growth, capex_pct=capex_pct, nwc_pct=nwc_pct,
                    asking_price=ev)
    return BaseDeal(teaser=teaser, deal=deal, kind=ind.kind, market_multiple=multiple,
                    top_customer_share=float(rng.uniform(0.10, 0.30)), history=history)


def with_asking(b: BaseDeal, asking: float) -> BaseDeal:
    return b.model_copy(update={"deal": b.deal.model_copy(update={"asking_price": asking}),
                                "teaser": b.teaser.model_copy(update={"asking_price": asking})})
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 53 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): industry table and deal sampler

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Trap library and engine-based role placement

**Files:**
- Create: `acqlab/generator/traps.py`, `acqlab/generator/roles.py`
- Modify: `acqlab/engine/walkaway.py` (one line in `flip_threshold`), `tests/engine/test_walkaway.py` (append one test)
- Test: `tests/generator/test_traps.py`, `tests/generator/test_roles.py`

**Interfaces:**
- Consumes: `BaseDeal`, `sample_base`, `with_asking` (Task 1); `acqlab.engine.{Params, flip_threshold, is_go, walk_away}`.
- Produces: `TRAPS`, `PARAM`, `VARIANTS`, `TEST_ONLY`; `worst_amount(trap, b) -> float`; `param_value(trap, amount, b) -> float`; `params_for(amounts: dict[str, float], b) -> Params`; `trap_weight(trap, b) -> float`; `sample_variant(rng, trap, kind, dev) -> str`. In `roles.py`: constants `MARGIN, PULL_BACK, DECOY_MOVE, UNRESOLVED_WIDTH`; `amounts(b, sev) -> dict`; `go(b, sev) -> bool`; `flip_severity(b, trap, others=None) -> float | None`; `min_severity_to_move(b, trap, drop) -> float | None`; `place(b, roles: dict[str, str], rng) -> dict[str, dict] | None` (trap → `{severity, documented}`).

This task also fixes a Plan 1 engine bug that role placement depends on: `flip_threshold` silently returns the midpoint when called with `lo > hi`, which is how a negative EBITDA range arrives. Append this test to `tests/engine/test_walkaway.py`:

```python

def test_flip_threshold_accepts_bounds_in_either_order(simple):
    deal = simple.model_copy(update={"asking_price": 120})
    assert flip_threshold(deal, Params(), "ebitda_adjustment", 0, -20) == pytest.approx(
        flip_threshold(deal, Params(), "ebitda_adjustment", -20, 0))
```

and in `acqlab/engine/walkaway.py` replace the line

```python
    go_lo, go_hi = go_at(lo), go_at(hi)
```

with

```python
    lo, hi = min(lo, hi), max(lo, hi)  # bounds may come in either order (e.g. a negative EBITDA range)
    go_lo, go_hi = go_at(lo), go_at(hi)
```

Run `uv run pytest -q tests/engine` → 49 passed (the new test fails before the edit: it gets −10.0 instead of ≈ −2.03).

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_traps.py`:
```python
import numpy as np
import pytest

from acqlab.generator.sample import sample_base
from acqlab.generator.traps import TEST_ONLY, TRAPS, params_for, sample_variant, worst_amount


def test_addback_worst_case_never_exceeds_what_was_claimed():
    for seed in range(30):
        b = sample_base(np.random.default_rng(seed))
        assert worst_amount("addback", b) <= min(b.teaser.claimed_addbacks, 0.25 * b.teaser.adj_ebitda) + 1e-9


def test_params_for_converts_dollar_amounts_to_engine_units():
    b = sample_base(np.random.default_rng(0))
    rev = b.teaser.revenue_ltm
    p = params_for({"addback": 2, "debt_like": 3, "concentration": 10, "nwc": 1, "capex": 5}, b)
    assert (p.ebitda_adjustment, p.debt_like, p.nwc_adjustment) == (-2, 3, 1)
    assert p.revenue_haircut == pytest.approx(10 / rev) and p.capex_adjustment_pct == pytest.approx(5 / rev)


def test_dev_deals_never_draw_test_only_variants():
    rng = np.random.default_rng(0)
    for trap in TRAPS:
        dev = {sample_variant(rng, trap, "manufacturing", dev=True) for _ in range(300)}
        test = {sample_variant(rng, trap, "manufacturing", dev=False) for _ in range(300)}
        assert TEST_ONLY[trap] not in dev and TEST_ONLY[trap] in test


def test_debt_like_variants_follow_the_industry():
    rng = np.random.default_rng(0)
    services = [sample_variant(rng, "debt_like", "services", dev=False) for _ in range(500)]
    assert services.count("deferred_revenue") > 3 * services.count("pension")
```

`tests/generator/test_roles.py`:
```python
import numpy as np
import pytest

from acqlab.engine import walk_away
from acqlab.generator.roles import (DECOY_MOVE, MARGIN, PULL_BACK, UNRESOLVED_WIDTH, amounts, flip_severity, go,
                                    place)
from acqlab.generator.sample import sample_base, with_asking
from acqlab.generator.traps import params_for


def face_go_deals(n: int):
    """Deals that are a go at face value and where both add-backs and debt-like items can flip them."""
    rng, found = np.random.default_rng(0), []
    while len(found) < n:
        b = sample_base(rng)
        b = with_asking(b, 0.75 * b.deal.asking_price)
        ts = [flip_severity(b, t) for t in ("addback", "debt_like")]
        if go(b, {}) and all(t is not None and t + MARGIN <= 1 for t in ts):
            found.append(b)
    return found, rng


def test_flip_severity_is_where_the_decision_changes_even_for_negative_parameters():
    (b,), _ = face_go_deals(1)
    for trap in ("addback", "debt_like"):
        s = flip_severity(b, trap)
        assert go(b, {trap: s - 0.01}) and not go(b, {trap: s + 0.01})


def test_flipper_clears_its_flip_point_by_the_margin():
    deals, rng = face_go_deals(5)
    for b in deals:
        s = place(b, {"addback": "flipper"}, rng)["addback"]["severity"]
        assert s >= flip_severity(b, "addback") + MARGIN and not go(b, {"addback": s})


def test_decoy_moves_walk_away_but_stays_short_of_flipping():
    deals, rng = face_go_deals(5)
    placed = 0
    for b in deals:
        out = place(b, {"debt_like": "decoy"}, rng)
        if out is None:
            continue
        placed += 1
        s = out["debt_like"]["severity"]
        w0 = walk_away(b.deal, params_for({}, b))
        assert w0 - walk_away(b.deal, params_for(amounts(b, {"debt_like": s}), b)) >= DECOY_MOVE * b.deal.asking_price - 1e-6
        assert go(b, {"debt_like": s}) and s <= flip_severity(b, "debt_like") - MARGIN + 1e-9
    assert placed


def test_interaction_pair_flips_only_together_and_survives_pull_back():
    deals, rng = face_go_deals(30)
    placed = 0
    for b in deals:
        out = place(b, {"addback": "interaction", "debt_like": "interaction"}, rng)
        if out is None:
            continue
        placed += 1
        a, d = out["addback"]["severity"], out["debt_like"]["severity"]
        assert go(b, {"addback": a}) and go(b, {"debt_like": d})
        assert not go(b, {"addback": a, "debt_like": d})
        assert not go(b, {"addback": a - PULL_BACK, "debt_like": d})
        assert not go(b, {"addback": a, "debt_like": d - PULL_BACK})
    assert placed


def test_unresolvable_sits_at_the_middle_of_its_documented_range_and_clean_is_zero():
    deals, rng = face_go_deals(1)
    out = place(deals[0], {"capex": "unresolvable", "nwc": "clean"}, rng)
    low, high = out["capex"]["documented"]
    assert high - low == pytest.approx(UNRESOLVED_WIDTH)
    assert out["capex"]["severity"] == pytest.approx((low + high) / 2)
    assert out["nwc"] == {"severity": 0.0, "documented": None}


def test_impossible_roles_are_refused():
    deals, rng = face_go_deals(1)
    b = with_asking(deals[0], 0.3 * deals[0].deal.asking_price)  # so cheap nothing flips it
    assert place(b, {"addback": "flipper"}, rng) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_traps.py tests/generator/test_roles.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/traps.py`:
```python
"""Trap library: one trap per engine parameter. A fact's amount ($M) is severity x the trap's worst case."""
import numpy as np

from acqlab.engine import Params
from acqlab.generator.sample import BaseDeal

TRAPS = ("addback", "debt_like", "concentration", "nwc", "capex")
PARAM = {"addback": "ebitda_adjustment", "debt_like": "debt_like", "concentration": "revenue_haircut",
         "nwc": "nwc_adjustment", "capex": "capex_adjustment_pct"}
VARIANTS = {
    "addback": ("restructuring", "consulting", "owner_comp"),
    "debt_like": ("earnout", "pension", "deferred_revenue", "litigation"),
    "concentration": ("expiring", "rfp", "acquired"),
    "nwc": ("stretched_payables", "pulled_collections"),
    "capex": ("aged_equipment", "deferred_maintenance", "lease_return"),
}
TEST_ONLY = {"addback": "owner_comp", "debt_like": "pension", "concentration": "acquired",
             "nwc": "pulled_collections", "capex": "lease_return"}  # never sampled for dev deals


def worst_amount(trap: str, b: BaseDeal) -> float:
    """$M at severity 1: the top of the trap's true-value range (design §2)."""
    t = b.teaser
    return {
        "addback": min(t.claimed_addbacks, 0.25 * t.adj_ebitda),  # can't disallow more than was claimed
        "debt_like": 0.15 * b.market_multiple * t.adj_ebitda,
        "concentration": b.top_customer_share * t.revenue_ltm,  # annual revenue lost
        "nwc": 0.20 * t.nwc_pct * t.revenue_ltm,
        "capex": 0.03 * t.revenue_ltm,  # extra capex per year
    }[trap]


def param_value(trap: str, amount: float, b: BaseDeal) -> float:
    """Engine parameter for a $M amount."""
    rev = b.teaser.revenue_ltm
    return {"addback": -amount, "debt_like": amount, "concentration": amount / rev, "nwc": amount,
            "capex": amount / rev}[trap]


def params_for(amounts: dict[str, float], b: BaseDeal) -> Params:
    return Params(**{PARAM[trap]: param_value(trap, a, b) for trap, a in amounts.items()})


def trap_weight(trap: str, b: BaseDeal) -> float:
    """Industry and teaser cues: big add-back gaps and capital-heavy businesses are likelier trap sites."""
    t = b.teaser
    return {"addback": t.claimed_addbacks / t.adj_ebitda / 0.10, "capex": t.capex_pct / 0.03}.get(trap, 1.0)


def sample_variant(rng: np.random.Generator, trap: str, kind: str, dev: bool) -> str:
    names = VARIANTS[trap]
    w = np.ones(len(names))
    if trap == "debt_like":
        bias = {"services": {"deferred_revenue": 3.0, "pension": 0.3},
                "manufacturing": {"pension": 2.0, "deferred_revenue": 0.5}}[kind]
        w = np.array([bias.get(n, 1.0) for n in names])
    if dev:
        w[names.index(TEST_ONLY[trap])] = 0.0
    return str(rng.choice(names, p=w / w.sum()))
```

`acqlab/generator/roles.py`:
```python
"""Place each fact's value so it provably plays its role (design §3). Everything is in severity units:
0 = teaser at face value, 1 = the trap's worst case. Roles are judged against the face-value decision."""
import numpy as np

from acqlab.engine import flip_threshold, is_go, walk_away
from acqlab.generator.sample import BaseDeal
from acqlab.generator.traps import PARAM, param_value, params_for, worst_amount

MARGIN = 0.20  # flippers clear, and decoys stay short of, their flip point by 20% of the prior range
PULL_BACK = 0.10  # an interaction still flips if either value is pulled back this far
DECOY_MOVE = 0.05  # decoys move walk-away by at least 5% of EV
UNRESOLVED_WIDTH = 0.40  # documented range width for unresolvable facts


def amounts(b: BaseDeal, sev: dict[str, float]) -> dict[str, float]:
    return {trap: s * worst_amount(trap, b) for trap, s in sev.items()}


def go(b: BaseDeal, sev: dict[str, float]) -> bool:
    return is_go(b.deal, params_for(amounts(b, sev), b))


def flip_severity(b: BaseDeal, trap: str, others: dict[str, float] | None = None) -> float | None:
    """Severity of `trap` at which go/no-go flips, others held at `others`. None if it never flips."""
    others = others or {}
    base = params_for(amounts(b, others), b)
    hi = param_value(trap, worst_amount(trap, b), b)
    v = flip_threshold(b.deal, base, PARAM[trap], 0.0, hi, tol=1e-9 if abs(hi) < 1 else 1e-6)
    return None if v is None else v / hi


def min_severity_to_move(b: BaseDeal, trap: str, drop: float) -> float | None:
    """Smallest severity that lowers walk-away by `drop` ($M). None if even the worst case doesn't."""
    w0 = walk_away(b.deal, params_for({}, b))

    def moved(s: float) -> bool:
        return w0 - walk_away(b.deal, params_for(amounts(b, {trap: s}), b)) >= drop

    if not moved(1.0):
        return None
    lo, hi = 0.0, 1.0
    while hi - lo > 1e-3:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if moved(mid) else (mid, hi)
    return hi


def _upper(t: float | None) -> float:
    return 1.0 if t is None else t - MARGIN


def place(b: BaseDeal, roles: dict[str, str], rng: np.random.Generator) -> dict[str, dict] | None:
    """roles: trap -> role. Returns trap -> {severity, documented} or None if these roles can't coexist here.
    `documented` is the (low, high) severity range stated in the documents for unresolvable facts."""
    alone = {trap: flip_severity(b, trap) for trap in roles}
    out: dict[str, dict] = {}
    for trap, role in roles.items():
        t = alone[trap]
        if role == "clean":
            out[trap] = {"severity": 0.0, "documented": None}
        elif role == "flipper":
            if t is None or t + MARGIN > 1:
                return None
            out[trap] = {"severity": float(rng.uniform(t + MARGIN, 1.0)), "documented": None}
        elif role == "decoy":
            lo = min_severity_to_move(b, trap, DECOY_MOVE * b.deal.asking_price)
            if lo is None or lo > _upper(t):
                return None
            out[trap] = {"severity": float(rng.uniform(lo, _upper(t))), "documented": None}
        elif role == "unresolvable":
            for _ in range(20):
                low = float(rng.uniform(0.0, 1.0 - UNRESOLVED_WIDTH))
                mid = low + UNRESOLVED_WIDTH / 2
                if t is None or abs(mid - t) >= PULL_BACK:
                    out[trap] = {"severity": mid, "documented": (low, low + UNRESOLVED_WIDTH)}
                    break
            else:
                return None
    pair = [trap for trap, role in roles.items() if role == "interaction"]
    if pair:
        placed = _place_pair(b, pair, alone, rng)
        if placed is None:
            return None
        out.update(placed)
    return out


def _place_pair(b: BaseDeal, pair: list[str], alone: dict, rng: np.random.Generator) -> dict | None:
    a, c = pair
    top = max(PULL_BACK, _upper(alone[a]))
    # Feasible pairs cluster where `a` is near its cap, so the cap itself is the last try.
    for sa in [float(rng.uniform(PULL_BACK, top)) for _ in range(19)] + [top]:
        joint = flip_severity(b, c, {a: sa})
        pulled = flip_severity(b, c, {a: sa - PULL_BACK})
        if joint is None or pulled is None:
            continue
        lo, hi = max(joint + PULL_BACK, pulled), _upper(alone[c])
        if lo <= hi:
            return {a: {"severity": sa, "documented": None},
                    c: {"severity": float(rng.uniform(lo, hi)), "documented": None}}
    return None
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 64 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab tests
git commit -m "feat(generator): trap library and engine-based role placement; fix flip_threshold bounds order

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Answer keys

**Files:**
- Create: `acqlab/generator/truth.py`
- Test: `tests/generator/test_truth.py`

**Interfaces:**
- Consumes: Tasks 1–2; `acqlab.engine.{Deal, Params, evaluate, is_go, walk_away}`.
- Produces: `GENERATOR_VERSION`, tuning constants `ASK_NOISE, CASE_MIX, FACE_GO, PRIOR_CLEAN, OTHER_ROLES, PLACEMENT`; models `Fact{trap, variant, param, role, placement, worst, amount, documented, realized, alone_flips, decision_value}` and `DealTruth{id, split, seed, generator_version, style, base, facts, face_walk_away, face_go, walk_away, go, debt_limit, case_type}` with `.deal` and `.params()`; `case_type(roles) -> str`; `generate(deal_id, split, seed, *, mc=400, force_case=None, max_tries=500) -> DealTruth`. Splits: `dev | test | hand | showcase`; only `dev` excludes `TEST_ONLY` variants and is always style `A`.

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_truth.py`:
```python
from collections import Counter

import numpy as np

from acqlab.generator.traps import TEST_ONLY, TRAPS
from acqlab.generator.truth import generate


def test_same_seed_gives_the_same_answer_key():
    assert generate("x", "test", 5, mc=40) == generate("x", "test", 5, mc=40)


def test_every_deal_has_one_fact_per_trap_with_rounded_amounts():
    t = generate("x", "test", 1, mc=40)
    assert [f.trap for f in t.facts] == list(TRAPS)
    assert all(f.amount == round(f.amount, 1) and 0 <= f.amount <= f.worst + 0.05 for f in t.facts)


def test_forced_case_types_come_out_as_labelled():
    for case in ("clean", "flip", "interaction"):
        t = generate("x", "test", 7, mc=40, force_case=case)
        assert t.case_type == case
        if case == "clean":
            assert t.go == t.face_go and all(f.amount == 0 for f in t.facts)
        else:
            assert t.face_go and not t.go


def test_unresolvable_amount_is_the_documented_midpoint_and_realized_is_inside():
    facts = [f for s in range(40) for f in generate("x", "test", s, mc=20).facts if f.role == "unresolvable"]
    assert facts
    for f in facts:
        low, high = f.documented
        assert abs(f.amount - (low + high) / 2) <= 0.051 and low <= f.realized <= high


def test_margin_rule_and_dev_rules_hold():
    for s in range(20):
        t = generate("x", "dev", s, mc=20)
        tz, by = t.base.teaser, {f.trap: f for f in t.facts}
        margin = (tz.adj_ebitda - by["addback"].amount) / tz.revenue_ltm
        assert margin >= tz.capex_pct + by["capex"].amount / tz.revenue_ltm + 0.05
        assert t.style == "A" and not any(f.variant == TEST_ONLY[f.trap] for f in t.facts)


def test_batch_mix_is_near_the_targets():
    ts = [generate(f"d{s}", "test", s, mc=20) for s in range(60)]
    assert 0.35 <= np.mean([t.go for t in ts]) <= 0.65
    assert set(Counter(t.case_type for t in ts)) == {"clean", "flip", "interaction", "unresolvable", "decoy"}
    assert all(f.decision_value >= 0 for t in ts for f in t.facts)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_truth.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/truth.py`:
```python
"""Generate one deal's answer key: visible teaser, hidden facts with roles, and engine ground truth."""
import numpy as np
from pydantic import BaseModel

from acqlab.engine import Deal, Params, evaluate, is_go, walk_away
from acqlab.generator.roles import DECOY_MOVE, MARGIN, PULL_BACK, flip_severity, min_severity_to_move, place
from acqlab.generator.sample import BaseDeal, sample_base, with_asking
from acqlab.generator.traps import PARAM, TRAPS, params_for, sample_variant, trap_weight, worst_amount

GENERATOR_VERSION = "2.0.0"
ASK_NOISE = (-0.15, 0.10)  # asking = market EV x (1 + N(mean, sd)); a 20% hurdle rarely clears at market prices
CASE_MIX = {"clean": 0.15, "flip": 0.25, "interaction": 0.10, "none": 0.50}
FACE_GO = 0.97
PRIOR_CLEAN = 0.70  # generator prior: share of facts that are clean (roughly the realized mix)  # P(face-value go) for clean and no-flip deals; flip deals are always face-value go
OTHER_ROLES = {"decoy": 0.25, "unresolvable": 0.06, "clean": 0.69}  # roles for the remaining facts
PLACEMENT = {  # mode weights by role: decoys lean loud, flippers lean buried (design §4)
    "flipper": {"explicit": 1, "footnote": 2, "calculation": 2, "contradicted": 1},
    "interaction": {"explicit": 1, "footnote": 2, "calculation": 2, "contradicted": 1},
    "decoy": {"explicit": 3, "footnote": 1, "calculation": 1, "contradicted": 1},
    "clean": {"explicit": 2, "footnote": 1, "calculation": 1},
    "unresolvable": {"range": 1},
}


class Fact(BaseModel):
    trap: str
    variant: str
    param: str
    role: str
    placement: str
    worst: float  # $M at severity 1; prior range is (0, worst)
    amount: float  # $M knowable value (midpoint of the documented range if unresolvable), rounded to 0.1
    documented: tuple[float, float] | None  # $M range the documents state (unresolvable only)
    realized: float  # $M; equals amount unless unresolvable
    alone_flips: bool  # flips the face-value decision on its own
    decision_value: float = 0.0  # $M of expected regret removed by learning this fact alone


class DealTruth(BaseModel):
    id: str
    split: str
    seed: int
    generator_version: str
    style: str  # document template style: A or B
    base: BaseDeal
    facts: list[Fact]  # all five traps, one fact each
    face_walk_away: float
    face_go: bool
    walk_away: float
    go: bool
    debt_limit: str
    case_type: str

    @property
    def deal(self) -> Deal:
        return self.base.deal

    def params(self) -> Params:
        return params_for({f.trap: f.amount for f in self.facts}, self.base)


def case_type(roles: list[str]) -> str:
    for role, case in (("flipper", "flip"), ("interaction", "interaction"), ("unresolvable", "unresolvable"),
                       ("decoy", "decoy")):
        if role in roles:
            return case
    return "clean"


def _pick(rng: np.random.Generator, weights: dict[str, float]) -> str:
    keys = list(weights)
    w = np.array([weights[k] for k in keys], dtype=float)
    return str(rng.choice(keys, p=w / w.sum()))


def _plan(rng: np.random.Generator, b: BaseDeal, case: str) -> dict[str, str] | None:
    """trap -> role, using only roles this deal can support."""
    alone = {t: flip_severity(b, t) for t in TRAPS}
    roles = {t: "clean" for t in TRAPS}
    if case == "clean":
        return roles
    if case == "flip":
        can_flip = [t for t in TRAPS if alone[t] is not None and alone[t] + MARGIN <= 1]
        if not can_flip:
            return None
        roles[_pick(rng, {t: trap_weight(t, b) for t in can_flip})] = "flipper"
    if case == "interaction":
        w0 = walk_away(b.deal, Params())
        drop = {t: w0 - walk_away(b.deal, params_for({t: worst_amount(t, b)}, b)) for t in TRAPS
                if alone[t] is None or alone[t] - MARGIN >= PULL_BACK}
        strong = {t: d for t, d in drop.items() if d >= DECOY_MOVE * b.deal.asking_price}
        if len(strong) < 2:
            return None
        for t in rng.choice(list(strong), size=2, replace=False, p=np.array(list(strong.values())) / sum(strong.values())):
            roles[str(t)] = "interaction"
    for _ in range(10):
        trial = dict(roles)
        for t in TRAPS:
            if trial[t] != "clean":
                continue
            role = _pick(rng, OTHER_ROLES)
            if role == "decoy":
                lo = min_severity_to_move(b, t, DECOY_MOVE * b.deal.asking_price)
                if lo is None or lo > (1.0 if alone[t] is None else alone[t] - MARGIN):
                    role = "clean"
            trial[t] = role
        if case != "none" or any(r != "clean" for r in trial.values()):  # a "none" deal needs something to find
            return trial
    return None


def _decision_values(b: BaseDeal, worst: dict[str, float], n: int, rng: np.random.Generator,
                     bins: int = 10) -> dict[str, float]:
    """Expected regret with every fact at its prior, minus expected regret with one fact known.
    Prior: severity 0 with probability PRIOR_CLEAN, else uniform on (0, 1) -- most facts are clean.
    Knowing a fact is approximated by sorting draws on it and deciding separately within each bin."""
    traps = list(worst)
    draws = rng.uniform(0.0, 1.0, (n, len(traps))) * (rng.random((n, len(traps))) >= PRIOR_CLEAN)
    w = np.array([walk_away(b.deal, params_for({t: d * worst[t] for t, d in zip(traps, row)}, b))
                  for row in draws])
    ask = b.deal.asking_price
    reg_go, reg_no = np.maximum(0.0, ask - w), np.maximum(0.0, w - ask)

    def best(idx: np.ndarray) -> float:
        return min(reg_go[idx].mean(), reg_no[idx].mean()) * len(idx) / n

    everything = best(np.arange(n))
    out = {}
    for i, t in enumerate(traps):
        known = sum(best(chunk) for chunk in np.array_split(np.argsort(draws[:, i]), bins))
        out[t] = max(0.0, everything - known)
    return out


def generate(deal_id: str, split: str, seed: int, *, mc: int = 400, force_case: str | None = None,
             max_tries: int = 500) -> DealTruth:
    rng = np.random.default_rng(seed)
    dev = split == "dev"
    case = force_case or _pick(rng, CASE_MIX)  # drawn once, so hard cases aren't swapped for easy ones on retry
    for _ in range(max_tries):
        b = sample_base(rng)
        want_go = case in ("flip", "interaction") or rng.random() < FACE_GO
        ask = b.deal.asking_price * (1 + rng.normal(*ASK_NOISE))
        b = with_asking(b, ask)
        if is_go(b.deal, Params()) != want_go:
            continue
        roles = _plan(rng, b, case)
        placed = roles and place(b, roles, rng)
        if not placed:
            continue
        facts = _facts(rng, b, roles, placed, dev)
        truth = _finish(deal_id, split, seed, rng, b, facts, mc)
        if truth is not None:
            return truth
    raise RuntimeError(f"could not generate {deal_id} (seed {seed}) in {max_tries} tries")


def _facts(rng, b: BaseDeal, roles: dict[str, str], placed: dict[str, dict], dev: bool) -> list[Fact]:
    facts = []
    for t in TRAPS:
        worst = worst_amount(t, b)
        amount = round(placed[t]["severity"] * worst, 1)
        documented = placed[t]["documented"]
        doc_range = None if documented is None else (round(documented[0] * worst, 1), round(documented[1] * worst, 1))
        if doc_range:
            amount = round((doc_range[0] + doc_range[1]) / 2, 1)
        realized = amount if doc_range is None else round(float(rng.uniform(*doc_range)), 1)
        facts.append(Fact(trap=t, variant=sample_variant(rng, t, b.kind, dev), param=PARAM[t], role=roles[t],
                          placement=_pick(rng, PLACEMENT[roles[t]]), worst=worst, amount=amount,
                          documented=doc_range, realized=realized, alone_flips=False))
    return facts


def _finish(deal_id, split, seed, rng, b: BaseDeal, facts: list[Fact], mc: int) -> DealTruth | None:
    t = b.teaser
    true_margin = (t.adj_ebitda - facts[0].amount) / t.revenue_ltm
    capex = t.capex_pct + facts[4].amount / t.revenue_ltm
    if true_margin < capex + 0.05:  # margin rule (design §1)
        return None
    face_go = is_go(b.deal, Params())
    for f in facts:
        f.alone_flips = is_go(b.deal, params_for({f.trap: f.amount}, b)) != face_go
    params = params_for({f.trap: f.amount for f in facts}, b)
    go_ = is_go(b.deal, params)
    explained = any(f.role in ("flipper", "interaction") or (f.role == "unresolvable" and f.alone_flips)
                    for f in facts)
    if go_ != face_go and not explained:  # several decoys added up to an unlabelled flip
        return None
    dv = _decision_values(b, {f.trap: f.worst for f in facts}, mc, rng)
    for f in facts:
        f.decision_value = dv[f.trap]
    result = evaluate(b.deal, params)
    return DealTruth(id=deal_id, split=split, seed=seed, generator_version=GENERATOR_VERSION,
                     style="A" if split == "dev" else str(rng.choice(["A", "B"])), base=b, facts=facts,
                     face_walk_away=walk_away(b.deal, Params()), face_go=face_go,
                     walk_away=walk_away(b.deal, params), go=go_, debt_limit=result.debt_limit,
                     case_type=case_type([f.role for f in facts]))
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 70 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): answer keys with engine ground truth and decision values

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Documents and renderer (template prose)

**Files:**
- Create: `acqlab/generator/documents.py`, `acqlab/generator/render.py`
- Test: `tests/generator/test_documents.py`, `tests/generator/test_render.py`

**Interfaces:**
- Consumes: `DealTruth`, `Fact` (Task 3); `FISCAL_YEARS` (Task 1).
- Produces: in `documents.py`: `WORDS_PER_PAGE`, `PLACEHOLDER` (regex), `Slot{id, brief, template, values, text}` with `.render()`, `Doc{id, title, domain, blocks}` with `.render()` and `.pages`, `money(x)`, `pct(x)`, `slot(sid, brief, template, **values)`, `heading(style, n, text)`, `table(style, header, rows)`. In `render.py`: `LABELS`, `FILLER`, `Evidence{trap, docs, formula, values}`, `answer(ev) -> float | tuple[float, float]`, `teaser_text(t) -> str`, `render(t) -> tuple[list[Doc], list[Evidence]]` (evidence in `TRAPS` order). Document ids: `cim, qoe, audited, credit, contract_1..3, assets, legal` plus 4–5 filler ids from `FILLER`.

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_documents.py`:
```python
from acqlab.generator.documents import Doc, heading, money, pct, slot, table


def test_slot_fills_placeholders_from_template_or_llm_text():
    s = slot("x", "brief", "Debt of {{amount}} at {{rate}}.", amount=money(12.345), rate=pct(0.085))
    assert s.render() == "Debt of $12.3M at 8.5%."
    assert s.model_copy(update={"text": "At {{rate}}, debt is {{amount}}."}).render() == "At 8.5%, debt is $12.3M."


def test_pages_count_words_and_are_at_least_one():
    assert Doc(id="a", title="A", domain="filler", blocks=["word " * 130]).pages == 2
    assert Doc(id="b", title="B", domain="filler", blocks=["short"]).pages == 1


def test_styles_format_headings_and_tables_differently():
    assert heading("A", 2, "Notes") == "## Notes" and heading("B", 2, "Notes") == "SECTION 2. NOTES"
    assert table("A", ["k", "v"], [["x", "1"]]).startswith("| k | v |")
    assert table("B", ["k", "v"], [["x", "1"]]).endswith("x ........ 1")
```

`tests/generator/test_render.py`:
```python
import re

from acqlab.generator.documents import PLACEHOLDER, Slot
from acqlab.generator.render import answer, render, teaser_text
from acqlab.generator.truth import generate

DEALS = [generate(f"d{s}", "test", s, mc=20) for s in range(40)]
CORE = {"cim", "qoe", "audited", "credit", "contract_1", "assets", "legal"}
TOPICS = ("add-back", "debt", "customer", "working capital", "capital expenditure", "litigation")


def test_every_room_has_the_core_documents_contracts_and_filler():
    for t in DEALS:
        docs, _ = render(t)
        ids = {d.id for d in docs}
        assert CORE <= ids
        assert 4 <= sum(d.domain == "filler" for d in docs) <= 5
        assert 1 <= sum(i.startswith("contract_") for i in ids) <= 3


def test_evidence_reproduces_every_answer_and_sits_in_the_named_documents():
    for t in DEALS:
        docs, evidence = render(t)
        for f, ev in zip(t.facts, evidence):
            want = f.documented if f.documented else (f.amount if f.role != "clean" else 0.0)
            got = answer(ev)
            assert got == want if isinstance(want, tuple) else abs(got - want) <= max(0.1, 0.01 * want)
            assert set(ev.docs) <= {d.id for d in docs}


def test_templates_hold_no_digits_so_llm_prose_can_be_digit_checked():
    for t in DEALS:
        for d in render(t)[0]:
            for b in d.blocks:
                if isinstance(b, Slot):
                    assert not re.search(r"\d", b.template), (d.id, b.id)
                    assert set(PLACEHOLDER.findall(b.template)) <= set(b.values)


def test_every_topic_appears_in_every_deal():
    for t in DEALS:
        text = " ".join(d.render() for d in render(t)[0]).lower()
        assert all(topic in text for topic in TOPICS), t.id


def test_the_cims_assertive_claims_also_appear_for_clean_facts():
    claim = "has renewed its contract on a long-term basis"
    roles = {f.role for t in DEALS for f in t.facts if f.trap == "concentration"
             and claim in next(d for d in render(t)[0] if d.id == "cim").render()}
    assert "clean" in roles


def test_teaser_shows_visible_terms_only():
    t = DEALS[0]
    text = teaser_text(t)
    assert t.base.teaser.name in text and f"${t.deal.asking_price:,.1f}M" in text
    assert "disallow" not in text.lower() and "lawsuit" not in text.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_documents.py tests/generator/test_render.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/documents.py`:
```python
"""Document model. Code writes every number; prose slots hold {{placeholders}} that code fills in."""
import math
import re

from pydantic import BaseModel

WORDS_PER_PAGE = 120  # a budget unit, not a printed page
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")  # names never contain digits, so prose can be digit-checked


class Slot(BaseModel):
    id: str
    brief: str  # what an LLM writer is asked to say (no numbers)
    template: str  # plain template prose with {{placeholders}}
    values: dict[str, str]  # placeholder -> formatted value
    text: str | None = None  # LLM prose with the same placeholders; None -> use template

    def render(self) -> str:
        return PLACEHOLDER.sub(lambda m: self.values[m.group(1)], self.text or self.template)


class Doc(BaseModel):
    id: str
    title: str
    domain: str  # accounting | legal | credit | commercial | filler
    blocks: list[str | Slot]

    def render(self) -> str:
        return "\n\n".join(b if isinstance(b, str) else b.render() for b in self.blocks)

    @property
    def pages(self) -> int:
        return max(1, math.ceil(len(self.render().split()) / WORDS_PER_PAGE))


def money(x: float) -> str:
    return f"${x:,.1f}M"


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def slot(sid: str, brief: str, template: str, **values: str) -> Slot:
    return Slot(id=sid, brief=brief, template=template, values=values)


def heading(style: str, n: int, text: str) -> str:
    return f"## {text}" if style == "A" else f"SECTION {n}. {text.upper()}"


def table(style: str, header: list[str], rows: list[list[str]]) -> str:
    if style == "A":
        lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])
    return "\n".join([" / ".join(header)] + [f"{r[0]} ........ " + " / ".join(r[1:]) for r in rows])
```

`acqlab/generator/render.py`:
```python
"""Render a deal's data room from its answer key. Every trap topic appears in every deal (presence rule);
only the reveal passage differs between a real problem and a clean fact."""
import numpy as np
from pydantic import BaseModel

from acqlab.generator.documents import PLACEHOLDER, Doc, heading, money, pct, slot, table
from acqlab.generator.sample import FISCAL_YEARS
from acqlab.generator.truth import DealTruth, Fact

FY_LAST, FY_NEXT, FY_END = str(FISCAL_YEARS[-1]), str(FISCAL_YEARS[-1] + 1), str(FISCAL_YEARS[-1] + 5)
LABELS = {
    "restructuring": "restructuring costs", "consulting": "strategic consulting fees",
    "owner_comp": "owner compensation adjustments",
    "earnout": "earnout payable to the sellers of an acquired business", "pension": "unfunded pension obligation",
    "deferred_revenue": "customer prepayments that require future service", "litigation": "pending customer lawsuit",
    "expiring": "its contract is expiring and it will not renew in full",
    "rfp": "it is re-tendering the contract", "acquired": "it was acquired by a competitor",
    "stretched_payables": "stretched supplier payments", "pulled_collections": "customer collections pulled forward",
    "aged_equipment": "equipment past its useful life", "deferred_maintenance": "deferred maintenance",
    "lease_return": "lease return conditions on leased equipment",
}
SUPPORT = {"earnout": "earnout calculation", "pension": "actuarial valuation",
           "deferred_revenue": "deferred revenue roll-forward"}
BOILERPLATE = (
    "This document has been prepared solely for the use of prospective acquirers in connection with the proposed "
    "transaction. It does not purport to contain all information a prospective acquirer may require.",
    "Recipients should conduct their own investigation and analysis of the business and the data set out herein. "
    "No representation or warranty is made as to the accuracy or completeness of this document.",
    "The Company operates from owned and leased facilities and serves customers through a direct sales team "
    "supported by regional distributors and a customer service function.",
    "Management has invested in systems and processes that support the scalability of the platform, including an "
    "enterprise resource planning system and monthly management reporting.",
    "The Company's workforce is non-unionized. Employee turnover has been in line with industry norms and senior "
    "management has an average tenure of more than ten years.",
    "Information in this document is based on management accounts and discussions with management. It has not "
    "been independently verified except where stated.",
    "The Company maintains insurance coverage that management considers adequate for a business of its size, "
    "including property, general liability, product liability and cyber policies.",
    "Pricing is reviewed annually. Historically the Company has been able to pass through the majority of input "
    "cost increases to customers with a short lag.",
    "Capital allocation decisions are reviewed by the board. Investment proposals above a set threshold require a "
    "written business case and a post-investment review.",
    "Terms not otherwise defined have the meaning given in the purchase agreement. Headings are for convenience "
    "only and do not affect interpretation.",
)
FILLER = {
    "board_minutes": "Board Meeting Minutes", "hr_policy": "Human Resources Policy Manual",
    "insurance": "Insurance Certificates", "it_policy": "IT and Information Security Policy",
    "environmental": "Environmental, Health and Safety Policy",
}
_CUSTOMERS = ("Meridian", "Castell", "Northwind", "Bramble", "Oakhurst", "Selwyn", "Tavira", "Wexford")
_CUSTOMER_KIND = ("Retail", "Foods", "Logistics", "Health", "Supply", "Distribution")


class Evidence(BaseModel):
    """Where a fact's answer sits and how to compute it from what the documents state."""
    trap: str
    docs: list[str]
    formula: str  # none | value | difference | product | per_year | gap | range
    values: dict[str, float]


def answer(ev: Evidence) -> float | tuple[float, float]:
    v = ev.values
    return {"none": lambda: 0.0, "value": lambda: v["amount"], "difference": lambda: v["gross"] - v["settled"],
            "product": lambda: v["purchases"] * v["fraction"], "per_year": lambda: v["gross"] / 5,
            "gap": lambda: v["peg"] - v["latest"], "range": lambda: (v["low"], v["high"])}[ev.formula]()


def _cap(s: str) -> str:
    return s[0].upper() + s[1:]


def _note(sid: str, brief: str, template: str, **values: str) -> list:
    """Audited-accounts note: the numbered heading is code-written, so only the digit-free body is prose."""
    head, body = template.split(". ", 1)
    return [PLACEHOLDER.sub(lambda m: values[m.group(1)], head) + ".", slot(sid, brief, body, **values)]


def _trap_side(f: Fact) -> bool:
    return f.role != "clean"


def _claims(f: Fact, rng: np.random.Generator) -> bool:
    """Does the CIM make the seller's assertive claim? Always when contradicted; for clean facts half the time
    (where it is true), so the claim alone never gives the answer away."""
    return f.placement == "contradicted" or (f.role == "clean" and rng.random() < 0.5)


def _addback(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    lab, claimed, style = LABELS[f.variant], t.base.teaser.claimed_addbacks, t.style
    item = f.documented[1] if f.documented else (f.amount if _trap_side(f) else round(0.4 * claimed, 1))
    sites = {"cim.addback": [table(style, ["Add-back", "Amount"], [[_cap(lab), money(item)],
                                                                      ["Other one-time items", money(claimed - item)],
                                                                      ["Total add-backs", money(claimed)]])]}
    claim = "The add-backs of {{total}} remove costs that management considers non-recurring, including {{label}} of {{item}}."
    if _claims(f, rng):
        claim = "{{label_cap}} of {{item}} were a one-time cost and will not recur."
    sites["cim.addback"].append(slot("cim_addback", "Explain the add-back schedule", claim, total=money(claimed),
                                     label=lab, label_cap=_cap(lab), item=money(item)))
    qoe = "We reviewed the add-back for {{label}} of {{item}}; its history is set out in the audited financial statements."
    note = "Note 9 — {{label_cap}}. {{label_cap}} are included in operating expenses."
    rows = None
    trap = _trap_side(f)
    if f.placement in ("explicit", "contradicted"):
        qoe = ("We do not accept {{label}} of {{item}} as an add-back: the cost recurred in each of the last three "
               "years and is expected to continue." if trap else
               "We accept {{label}} of {{item}} as an add-back: the cost arose once and has not recurred.")
        if f.placement == "contradicted":
            qoe = "Contrary to the CIM, {{label}} recur every year; we do not accept the {{item}} add-back."
    elif f.placement == "footnote":
        note = ("Note 9 — {{label_cap}}. The Company incurred {{label}} of {{item}} in {{fy_last}}; similar costs were "
                "incurred in each prior year and management expects them to continue." if trap else
                "Note 9 — {{label_cap}}. The Company incurred {{label}} of {{item}} in {{fy_last}}; no similar costs "
                "were incurred in prior years and none are expected.")
    elif f.placement == "calculation":
        past = [round(item * k, 1) for k in (0.92, 1.05)] if trap else [0.0, 0.0]
        rows = [_cap(lab)] + [money(x) for x in past + [item]]
        note = "Note 9 — {{label_cap}}. {{label_cap}} are shown separately in the income statement."
    elif f.placement == "range":
        qoe = ("We could not determine whether {{label}} will recur. Between {{low}} and {{high}} of the {{item}} "
               "may prove recurring; supporting invoices were not provided.")
    vals = dict(label=lab, label_cap=_cap(lab), item=money(item), fy_last=FY_LAST)
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
    sites["qoe.addback"] = [slot("qoe_addback", "Give the QoE view on this add-back", qoe, **vals)]
    sites["audited.note9"] = _note("note9", "Write the note on this cost line", note, **vals)
    sites["audited.is_rows"] = [rows] if rows else []
    doc = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"],
           "calculation": ["audited"], "range": ["qoe"]}[f.placement]
    if f.documented:
        ev = Evidence(trap=f.trap, docs=doc, formula="range", values={"low": f.documented[0], "high": f.documented[1]})
    else:
        ev = Evidence(trap=f.trap, docs=doc, formula="value" if trap else "none",
                      values={"amount": item} if trap else {})
    return sites, ev


def _debt(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    lab, trap, lit = LABELS[f.variant], _trap_side(f), f.variant == "litigation"
    vals = dict(label=lab, label_cap=_cap(lab), amount=money(f.amount), support=SUPPORT.get(f.variant, ""))
    cim = "The business will be delivered cash-free and debt-free; the price excludes items such as any {{label}}."
    if _claims(f, rng):
        cim += " The business has no {{label}}."
    qoe = "Debt-like items, including any {{label}}: see the notes to the audited financial statements."
    note = ("Note 12 — Commitments and contingencies. The Company has operating leases and purchase commitments "
            "in the ordinary course of business.")
    legal = "We are not aware of any material pending litigation against the Company, including any {{label}}."
    ev_formula, ev_vals = ("value", {"amount": f.amount}) if trap else ("none", {})
    if lit:
        docs = ["cim", "legal"] if f.placement == "contradicted" else ["legal"]
        if f.placement in ("explicit", "footnote", "contradicted"):
            legal = ("We represent the Company in a {{label}}. We expect it to settle for {{amount}}, payable by the "
                     "Company." if trap else "The {{label}} against the Company was dismissed; there is no liability.")
        elif f.placement == "calculation":
            gross = round(f.amount + (float(np.round(f.worst * 0.3, 1)) if trap else 0.0), 1) if trap else 0.0
            insured = round(gross - f.amount, 1) if trap else 0.0
            legal = ("A {{label}} claims damages of {{gross}}. Insurance available to cover the claim is {{settled}}; "
                     "the Company bears the rest." if trap else
                     "The {{label}} against the Company was dismissed; there is no liability.")
            vals |= dict(gross=money(gross), settled=money(insured))
            if trap:
                ev_formula, ev_vals = "difference", {"gross": gross, "settled": insured}
        elif f.placement == "range":
            legal = ("We cannot predict the outcome of the {{label}}; a settlement between {{low}} and {{high}} "
                     "is possible.")
    else:
        docs = {"explicit": ["qoe"], "footnote": ["audited"], "calculation": ["audited"],
                "contradicted": ["cim", "audited"], "range": ["audited"]}[f.placement]
        if f.placement == "explicit":
            qoe = ("Debt-like items: we identify a {{label}} of {{amount}}, which should be treated as debt at closing."
                   if trap else "Debt-like items: we reviewed any {{label}} and identify no amount to be treated as "
                   "debt at closing.")
        elif f.placement in ("footnote", "contradicted"):
            note = ("Note 12 — Commitments and contingencies. The Company has a {{label}} of {{amount}}, payable "
                    "within twelve months of closing." if trap else
                    "Note 12 — Commitments and contingencies. The Company has no {{label}}.")
        elif f.placement == "calculation":
            settled = round(float(np.round(f.worst * 0.5, 1)), 1)
            gross = round(settled + f.amount, 1) if trap else settled
            note = ("Note 12 — Commitments and contingencies. Gross {{label}}: {{gross}}. Amounts settled or funded to "
                    "date: {{settled}}.")
            vals |= dict(gross=money(gross), settled=money(settled))
            if trap:
                ev_formula, ev_vals = "difference", {"gross": gross, "settled": settled}
        elif f.placement == "range":
            note = ("Note 12 — Commitments and contingencies. Management estimates the {{label}} at between {{low}} "
                    "and {{high}}; the supporting {{support}} is referenced but was not provided.")
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
        ev_formula, ev_vals = "range", {"low": f.documented[0], "high": f.documented[1]}
    sites = {"cim.debt": [slot("cim_debt", "State the cash-free, debt-free basis", cim, **vals)],
             "qoe.debt": [slot("qoe_debt", "Summarise debt-like items", qoe, **vals)],
             "audited.note12": _note("note12", "Write the commitments note", note, **vals),
             "legal.letter": [slot("legal", "Write the litigation paragraph of a legal letter", legal, **vals)]}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def _customer(f: Fact, t: DealTruth, customer: str, rng: np.random.Generator) -> tuple[dict, Evidence]:
    trap, share, rev = _trap_side(f), t.base.top_customer_share, t.base.teaser.revenue_ltm
    purchases = round(share * rev, 1)
    vals = dict(customer=customer, share=pct(share), purchases=money(purchases), amount=money(f.amount),
                reason=LABELS[f.variant], fy_next=FY_NEXT, fy_end=FY_END)
    cim = "Our largest customer, {{customer}}, accounts for {{share}} of revenue."
    if _claims(f, rng):
        cim += " {{customer}} has renewed its contract on a long-term basis."
    terms = "Term: through {{fy_end}}. Annual purchases under this agreement: {{purchases}}."
    notice = "{{customer}} has not given notice of any change to its purchase volumes."
    note = "Note 14 — Subsequent events. No events requiring disclosure occurred after year end."
    ev_formula, ev_vals = ("value", {"amount": f.amount}) if trap else ("none", {})
    docs = {"explicit": ["contract_1"], "contradicted": ["cim", "contract_1"], "footnote": ["audited"],
            "calculation": ["cim", "contract_1"], "range": ["contract_1"]}[f.placement]
    if f.placement in ("explicit", "contradicted"):
        notice = ("{{customer}} has notified the Company that, because {{reason}}, it will reduce annual purchases by "
                  "{{amount}} from {{fy_next}}." if trap else "{{customer}} has renewed through {{fy_end}} on the "
                  "same terms.")
    elif f.placement == "footnote":
        note = ("Note 14 — Subsequent events. After year end, {{customer}} gave notice that, because {{reason}}, it "
                "will reduce annual purchases by {{amount}}." if trap else
                "Note 14 — Subsequent events. After year end, {{customer}} confirmed its purchase commitments for the "
                "coming year.")
    elif f.placement == "calculation":
        fraction = f.amount / purchases if trap else 0.0
        notice = ("{{customer}} has given notice that, because {{reason}}, it will move {{fraction}} of its volume to "
                  "another supplier." if trap else "{{customer}} has confirmed it will keep all of its volume.")
        vals |= dict(fraction=pct(fraction))
        if trap:
            ev_formula, ev_vals = "product", {"purchases": share * rev, "fraction": fraction}
    elif f.placement == "range":
        notice = ("{{customer}} is re-tendering this contract and the outcome is expected after closing. Management "
                  "estimates that {{low}} to {{high}} of annual revenue is at risk.")
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
        ev_formula, ev_vals = "range", {"low": f.documented[0], "high": f.documented[1]}
    sites = {"cim.customer": [slot("cim_customer", "Describe customer relationships", cim, **vals)],
             "contract_1.terms": [slot("contract_terms", "State the contract term and volumes", terms, **vals)],
             "contract_1.notice": [slot("contract_notice", "State the customer's current position", notice, **vals)],
             "audited.note14": _note("note14", "Write the subsequent-events note", note, **vals)}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def _nwc(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    trap, lab, style = _trap_side(f), LABELS[f.variant], t.style
    peg = round(t.base.teaser.nwc_pct * t.base.teaser.revenue_ltm, 1)
    vals = dict(peg=money(peg), amount=money(f.amount), label=lab)
    hint = "The purchase agreement sets a normal level of net working capital (the peg) of {{peg}}."
    qoe = "We compared expected closing net working capital with the peg; see the notes to the audited accounts."
    note = "Note 6 — Working capital. Working capital comprises receivables, inventory and payables."
    cim = "Net working capital is managed closely and is at normal levels." if _claims(f, rng) else \
        "Working capital needs grow in line with revenue."
    ev_formula, ev_vals = ("value", {"amount": f.amount}) if trap else ("none", {})
    docs = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"], "calculation": ["qoe"],
            "range": ["qoe"]}[f.placement]
    extra: list = []
    if f.placement in ("explicit", "contradicted"):
        qoe = ("At closing, net working capital is expected to be {{amount}} below the peg because of {{label}}."
               if trap else "At closing, net working capital is expected to be in line with the peg; we found no "
               "{{label}}.")
    elif f.placement == "footnote":
        note = ("Note 6 — Working capital. At year end, {{label}} reduced net working capital by {{amount}} below "
                "normal levels." if trap else "Note 6 — Working capital. At year end, net working capital was at "
                "normal levels, with no {{label}}.")
    elif f.placement == "calculation":
        latest = round(peg - f.amount, 1) if trap else peg
        months = [money(round(peg * float(rng.uniform(0.97, 1.03)), 1)) for _ in range(5)] + [money(latest)]
        qoe = "Monthly net working capital is shown below; closing is expected at the latest month's level."
        extra = [table(style, ["Month", "Net working capital"], [[f"Month {i + 1}", m] for i, m in enumerate(months)])]
        if trap:
            ev_formula, ev_vals = "gap", {"peg": peg, "latest": latest}
    elif f.placement == "range":
        qoe = ("Net working capital at closing could fall between {{low}} and {{high}} below the peg; the closing "
               "balance sheet was not provided.")
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
        ev_formula, ev_vals = "range", {"low": f.documented[0], "high": f.documented[1]}
    sites = {"qoe.nwc": [slot("qoe_peg", "Explain the working-capital peg", hint, **vals),
                         slot("qoe_nwc", "Give the closing working-capital view", qoe, **vals)] + extra,
             "audited.note6": _note("note6", "Write the working-capital note", note, **vals),
             "cim.nwc": [slot("cim_nwc", "Comment on working capital", cim, **vals)]}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def _capex(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    trap, lab = _trap_side(f), LABELS[f.variant]
    tz = t.base.teaser
    vals = dict(label=lab, amount=money(f.amount), capex=money(tz.capex_pct * tz.revenue_ltm), fy_last=FY_LAST,
                years="five")
    cim = "The asset base is well maintained; capital expenditure was {{capex}} in {{fy_last}}."
    if _claims(f, rng):
        cim += " There is no {{label}}."
    review = "The schedule above lists fixed assets by class; the condition review found nothing further to report."
    note = "Note 7 — Property, plant and equipment. Assets are depreciated on a straight-line basis."
    ev_formula, ev_vals = ("value", {"amount": f.amount}) if trap else ("none", {})
    docs = {"explicit": ["assets"], "contradicted": ["cim", "assets"], "footnote": ["audited"],
            "calculation": ["assets"], "range": ["assets"]}[f.placement]
    if f.placement in ("explicit", "contradicted"):
        review = ("Condition review: {{label}} requires additional capital expenditure of {{amount}} per year over "
                  "the plan." if trap else "Condition review: we found no {{label}}; no additional capital "
                  "expenditure is required.")
    elif f.placement == "footnote":
        note = ("Note 7 — Property, plant and equipment. Because of {{label}}, management expects additional capital "
                "expenditure of {{amount}} per year." if trap else "Note 7 — Property, plant and equipment. "
                "Management expects no additional capital expenditure; there is no {{label}}.")
    elif f.placement == "calculation":
        gross = round(f.amount * 5, 1)
        review = ("Replacement cost of {{label}}: {{gross}}, to be spent evenly over the {{years}}-year plan."
                  if trap else "Replacement cost of {{label}}: none identified.")
        vals |= dict(gross=money(gross))
        if trap:
            ev_formula, ev_vals = "per_year", {"gross": gross}
    elif f.placement == "range":
        review = ("An engineering survey was commissioned but not provided. Management estimates additional capital "
                  "expenditure for {{label}} of {{low}} to {{high}} per year.")
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
        ev_formula, ev_vals = "range", {"low": f.documented[0], "high": f.documented[1]}
    sites = {"cim.capex": [slot("cim_capex", "Describe the asset base", cim, **vals)],
             "assets.review": [slot("asset_review", "Summarise the equipment condition review", review, **vals)],
             "audited.note7": _note("note7", "Write the fixed-asset note", note, **vals)}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def teaser_text(t: DealTruth) -> str:
    tz, fin, pol = t.base.teaser, t.deal.financing, t.deal.policy
    covs = ", ".join(f"{c:.2f}x" for c in fin.covenant_max_leverage)
    return "\n".join([
        f"# {tz.name} — Teaser", f"Industry: {tz.industry}",
        f"LTM revenue: {money(tz.revenue_ltm)}; revenue growth: {pct(tz.growth)} per year",
        f"Reported EBITDA: {money(tz.reported_ebitda)}; claimed add-backs: {money(tz.claimed_addbacks)}; "
        f"adjusted EBITDA: {money(tz.adj_ebitda)}",
        f"Capex: {pct(tz.capex_pct)} of revenue; net working capital: {pct(tz.nwc_pct)} of revenue",
        f"Asking price: {money(tz.asking_price)}",
        f"Lender terms: up to {fin.max_leverage:.2f}x adjusted EBITDA at {pct(fin.interest_rate)}; amortization "
        f"{pct(fin.amortization_pct)} per year; cash sweep {pct(fin.cash_sweep)}; fees {pct(fin.fees_pct)} of price; "
        f"maximum net leverage covenant by year: {covs}",
        f"Sponsor policy: IRR hurdle {pct(pol.irr_hurdle)}; hold {pol.hold_years} years; exit at "
        f"{pol.exit_multiple:.2f}x EBITDA; minimum equity {pct(pol.min_equity_pct)}; downside case revenue "
        f"{pct(pol.downside_revenue_shock)}, margin {pct(pol.downside_margin_shock)}",
    ])


def render(t: DealTruth) -> tuple[list[Doc], list[Evidence]]:
    rng = np.random.default_rng(t.seed + 1)
    style, tz = t.style, t.base.teaser
    customers = [f"{c} {k}" for c, k in zip(rng.choice(_CUSTOMERS, 3, replace=False),
                                            rng.choice(_CUSTOMER_KIND, 3, replace=False))]
    by_trap = {f.trap: f for f in t.facts}
    sites: dict[str, list] = {}
    evidence = []
    for part in (_addback(by_trap["addback"], t, rng), _debt(by_trap["debt_like"], t, rng),
                 _customer(by_trap["concentration"], t, customers[0], rng), _nwc(by_trap["nwc"], t, rng),
                 _capex(by_trap["capex"], t, rng)):
        sites |= part[0]
        evidence.append(part[1])

    def boiler(k: int) -> list[str]:
        return [BOILERPLATE[i] for i in rng.choice(len(BOILERPLATE), k, replace=False)]

    hist = [[str(h.fiscal_year), money(h.revenue), money(h.reported_ebitda)] for h in t.base.history]
    is_rows = [[f"FY{h.fiscal_year}" for h in t.base.history]]
    is_table = table(style, ["Line"] + is_rows[0],
                     [["Revenue"] + [money(h.revenue) for h in t.base.history],
                      ["Reported EBITDA"] + [money(h.reported_ebitda) for h in t.base.history]]
                     + sites["audited.is_rows"])
    fin = t.deal.financing
    n_contracts = int(rng.integers(1, 4))
    docs = [
        Doc(id="cim", title="Confidential Information Memorandum", domain="commercial", blocks=[
            heading(style, 1, f"{tz.name} — Overview"),
            slot("cim_overview", f"Introduce a {tz.industry} company", "{{name}} operates in the {{industry}} sector.",
                 name=tz.name, industry=tz.industry.lower()),
            *boiler(2), heading(style, 2, "Financial summary"),
            table(style, ["Fiscal year", "Revenue", "Reported EBITDA"], hist),
            heading(style, 3, "Adjusted EBITDA"), *sites["cim.addback"],
            heading(style, 4, "Customers"), *sites["cim.customer"],
            heading(style, 5, "Operations and assets"), *sites["cim.capex"], *sites["cim.nwc"],
            heading(style, 6, "Transaction"), *sites["cim.debt"]]),
        Doc(id="qoe", title="Quality of Earnings Report", domain="accounting", blocks=[
            heading(style, 1, "Scope"), *boiler(2), heading(style, 2, "Adjusted EBITDA"), *sites["qoe.addback"],
            heading(style, 3, "Net working capital"), *sites["qoe.nwc"],
            heading(style, 4, "Debt-like items"), *sites["qoe.debt"]]),
        Doc(id="audited", title=f"Audited Financial Statements FY{FISCAL_YEARS[0]}–FY{FISCAL_YEARS[-1]}",
            domain="accounting", blocks=[
                heading(style, 1, "Income statement"), is_table, heading(style, 2, "Notes"),
                *sites["audited.note6"], *sites["audited.note7"], *sites["audited.note9"],
                *sites["audited.note12"], *sites["audited.note14"], *boiler(1)]),
        Doc(id="credit", title="Credit Agreement Excerpt", domain="credit", blocks=[
            heading(style, 1, "Term loan"),
            table(style, ["Term", "Value"], [
                ["Maximum leverage at close", f"{fin.max_leverage:.2f}x adjusted EBITDA"],
                ["Interest rate", pct(fin.interest_rate)], ["Amortization", f"{pct(fin.amortization_pct)} per year"],
                ["Excess cash flow sweep", pct(fin.cash_sweep)], ["Fees", f"{pct(fin.fees_pct)} of price"]]
                + [[f"Maximum net leverage, year {i + 1}", f"{c:.2f}x"]
                   for i, c in enumerate(fin.covenant_max_leverage)]),
            *boiler(1)]),
        Doc(id="contract_1", title=f"Customer Agreement — {customers[0]}", domain="commercial", blocks=[
            heading(style, 1, "Agreement"), *sites["contract_1.terms"], *sites["contract_1.notice"], *boiler(1)]),
        *[Doc(id=f"contract_{i + 1}", title=f"Customer Agreement — {customers[i]}", domain="commercial", blocks=[
            heading(style, 1, "Agreement"),
            slot("contract_terms", "State the contract term", "Term: through {{fy_end}}.", fy_end=FY_END), *boiler(1)])
          for i in range(1, n_contracts)],
        Doc(id="assets", title="Fixed Asset and Lease Schedule", domain="accounting", blocks=[
            heading(style, 1, "Fixed assets"),
            table(style, ["Asset class", "Gross cost", "Average age (years)"], [
                [c, money(tz.revenue_ltm * float(rng.uniform(0.02, 0.12))), f"{rng.uniform(3, 15):.0f}"]
                for c in ("Plant and machinery", "Vehicles", "IT equipment", "Leasehold improvements")]),
            *sites["assets.review"]]),
        Doc(id="legal", title="Legal Letter", domain="legal", blocks=[heading(style, 1, "Litigation"),
                                                                     *sites["legal.letter"], *boiler(1)]),
    ]
    for key in rng.choice(list(FILLER), int(rng.integers(4, 6)), replace=False):
        docs.append(Doc(id=str(key), title=FILLER[key], domain="filler",
                        blocks=[heading(style, 1, FILLER[key]), *boiler(int(rng.integers(4, 11)))]))
    return docs, evidence
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 79 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): documents and template-prose renderer with presence rule

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 5: Data room tools and budget

**Files:**
- Create: `acqlab/dataroom/__init__.py` (empty), `acqlab/dataroom/tools.py`
- Test: `tests/generator/test_tools.py`

**Interfaces:**
- Consumes: `Doc` (Task 4); `render`, `teaser_text` (tests only).
- Produces: `SEARCH_COST = 1.0`, `SNIPPET_CHARS = 150`, `BUDGET_SHARE = 0.35`, `BudgetExceeded`, `write_room(room: Path, teaser: str, docs: list[Doc], budget_share=BUDGET_SHARE) -> float` (default budget), `DataRoom(room: Path, budget: float | None = None)` with `.teaser()`, `.list_documents()`, `.search(query)`, `.open_document(doc_id)`, `.budget`, `.spent`, `.remaining`, `.log`.

Create the empty `acqlab/dataroom/__init__.py` first.

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_tools.py`:
```python
import math

import pytest

from acqlab.dataroom.tools import BUDGET_SHARE, BudgetExceeded, DataRoom, write_room
from acqlab.generator.render import render, teaser_text
from acqlab.generator.truth import generate


@pytest.fixture
def room(tmp_path):
    t = generate("d0", "test", 0, mc=20)
    docs, _ = render(t)
    budget = write_room(tmp_path / "deals" / "d0" / "room", teaser_text(t), docs)
    (tmp_path / "truth").mkdir()
    (tmp_path / "truth" / "d0.json").write_text("{}")
    return tmp_path / "deals" / "d0" / "room", docs, budget


def test_default_budget_buys_a_share_of_the_room(room):
    path, docs, budget = room
    assert budget == math.ceil(BUDGET_SHARE * sum(d.pages for d in docs))
    assert DataRoom(path).budget == budget


def test_listing_and_teaser_are_free_and_opening_costs_pages(room):
    path, docs, _ = room
    dr = DataRoom(path, budget=100)
    listing = dr.list_documents()
    assert {d["id"] for d in listing} == {d.id for d in docs} and dr.spent == 0 and dr.teaser()
    pages = next(d["pages"] for d in listing if d["id"] == "cim")
    assert "Adjusted EBITDA" in dr.open_document("cim") and dr.spent == pages


def test_search_costs_one_unit_and_returns_short_snippets(room):
    dr = DataRoom(room[0], budget=100)
    hits = dr.search("working capital peg")
    assert dr.spent == 1 and 0 < len(hits) <= 5
    assert all(len(h["snippet"]) <= 150 and h["doc_id"] for h in hits)


def test_over_budget_calls_are_refused_and_logged(room):
    dr = DataRoom(room[0], budget=1)
    dr.search("debt")
    with pytest.raises(BudgetExceeded):
        dr.open_document("cim")
    assert dr.log[-1]["refused"] and dr.spent == 1


def test_only_indexed_documents_can_be_opened(room):
    dr = DataRoom(room[0], budget=100)
    for bad in ("../../truth/d0", "../index", "index.json"):
        with pytest.raises(KeyError):
            dr.open_document(bad)
    assert dr.spent == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_tools.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/dataroom/tools.py`:
```python
"""Budgeted data room: the only way any system reads a deal's documents. It reads nothing outside its room folder."""
import json
import math
import re
from pathlib import Path

from acqlab.generator.documents import Doc

SEARCH_COST = 1.0
SNIPPET_CHARS = 150
BUDGET_SHARE = 0.35  # default budget buys ~35% of the room's total page cost (design §5)


class BudgetExceeded(Exception):
    pass


def write_room(room: Path, teaser: str, docs: list[Doc], budget_share: float = BUDGET_SHARE) -> float:
    """Write documents and index; return the default budget."""
    room.mkdir(parents=True, exist_ok=True)
    budget = float(math.ceil(budget_share * sum(d.pages for d in docs)))
    for d in docs:
        (room / f"{d.id}.md").write_text(d.render())
    index = {"teaser": teaser, "default_budget": budget,
             "documents": [{"id": d.id, "title": d.title, "domain": d.domain, "pages": d.pages} for d in docs]}
    (room / "index.json").write_text(json.dumps(index, indent=2))
    return budget


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class DataRoom:
    def __init__(self, room: Path, budget: float | None = None):
        self._room = room
        index = json.loads((room / "index.json").read_text())
        self._teaser = index["teaser"]
        self._docs = {d["id"]: d for d in index["documents"]}
        self.budget = index["default_budget"] if budget is None else budget
        self.spent = 0.0
        self.log: list[dict] = []

    @property
    def remaining(self) -> float:
        return self.budget - self.spent

    def _charge(self, tool: str, arg: str, cost: float) -> None:
        if cost > self.remaining:
            self.log.append({"tool": tool, "arg": arg, "cost": 0.0, "remaining": self.remaining, "refused": True})
            raise BudgetExceeded(f"{tool}({arg!r}) costs {cost}, {self.remaining} left")
        self.spent += cost
        self.log.append({"tool": tool, "arg": arg, "cost": cost, "remaining": self.remaining, "refused": False})

    def _text(self, doc_id: str) -> str:
        return (self._room / f"{doc_id}.md").read_text()  # doc_id is always an index key, never user text

    def teaser(self) -> str:
        return self._teaser

    def list_documents(self) -> list[dict]:
        self.log.append({"tool": "list_documents", "arg": "", "cost": 0.0, "remaining": self.remaining,
                         "refused": False})
        return [dict(d) for d in self._docs.values()]

    def search(self, query: str) -> list[dict]:
        """Top 5 paragraphs by number of query words they contain."""
        self._charge("search", query, SEARCH_COST)
        terms = _words(query)
        hits = []
        for order, doc_id in enumerate(self._docs):
            for para in self._text(doc_id).split("\n\n"):
                score = len(terms & _words(para))
                if score:
                    hits.append((-score, order, doc_id, para[:SNIPPET_CHARS]))
        return [{"doc_id": d, "snippet": s} for _, _, d, s in sorted(hits)[:5]]

    def open_document(self, doc_id: str) -> str:
        if doc_id not in self._docs:
            raise KeyError(f"no document {doc_id!r}")
        self._charge("open_document", doc_id, float(self._docs[doc_id]["pages"]))
        return self._text(doc_id)
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 84 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/dataroom tests/generator
git commit -m "feat(dataroom): budgeted list/search/open tools and room writer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Validators

**Files:**
- Create: `acqlab/generator/validate.py`
- Test: `tests/generator/test_validate.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: `check_engine(t) -> list[str]`, `check_leaks(t, docs, teaser) -> list[str]`, `check_consistency(t, docs, evidence) -> list[str]`, `check_batch(truths, texts: dict[str, str]) -> list[str]`; constants `ROUND_STEP, CORE_TITLES, LEAK_WORDS, TOPIC_WORDS`. An empty list means the check passed.

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_validate.py`:
```python
from acqlab.generator.render import render, teaser_text
from acqlab.generator.truth import generate
from acqlab.generator.validate import check_batch, check_consistency, check_engine, check_leaks

DEALS = [generate(f"d{s}", "test", s, mc=20) for s in range(20)]


def test_generated_deals_pass_every_check():
    for t in DEALS:
        docs, evidence = render(t)
        assert check_engine(t) == [] and check_leaks(t, docs, teaser_text(t)) == []
        assert check_consistency(t, docs, evidence) == []


def _first(role):
    return next((t, i) for t in DEALS for i, f in enumerate(t.facts) if f.role == role)


def test_engine_check_catches_a_mislabelled_fact_and_a_wrong_decision():
    t, i = _first("clean")
    bad = t.model_copy(deep=True)
    bad.facts[i].amount = 1.0
    assert any("clean fact" in p for p in check_engine(bad))
    t, i = _first("flipper")
    bad = t.model_copy(deep=True)
    bad.facts[i].amount = 0.0
    assert any("flipper" in p for p in check_engine(bad)) and any("stored go" in p for p in check_engine(bad))


def test_consistency_catches_llm_digits_and_missing_evidence():
    t = DEALS[0]
    docs, evidence = render(t)
    slot = next(b for b in docs[0].blocks if not isinstance(b, str))
    slot.text = "Revenue grew 12 percent."
    assert any("LLM prose" in p for p in check_consistency(t, docs, evidence))
    docs, evidence = render(t)
    ev = next(e for e in evidence if e.formula != "none")
    ev.values = {k: v + 50 for k, v in ev.values.items()}
    assert check_consistency(t, docs, evidence)


def test_leak_check_catches_revealing_titles_and_teasers():
    t = DEALS[0]
    docs, _ = render(t)
    docs[0].title = "Disallowed add-backs memo"
    problems = check_leaks(t, docs, teaser_text(t) + " Seller has an unfunded pension.")
    assert any("title" in p for p in problems) and any("unfunded" in p for p in problems)


def test_batch_check_flags_uneven_topic_mentions():
    texts = {t.id: " ".join(d.render() for d in render(t)[0]) for t in DEALS}
    assert check_batch(DEALS, texts) == []
    skewed = {tid: text + (" debt" * 200 if any(f.trap == "debt_like" and f.role != "clean" for f in t.facts) else "")
              for (tid, text), t in zip(texts.items(), DEALS)}
    assert any("presence" in p for p in check_batch(DEALS, skewed))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_validate.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/validate.py`:
```python
"""Checks run on every generated deal (design §7). Each returns a list of problems; empty means it passed."""
import re

import numpy as np

from acqlab.engine import is_go, walk_away
from acqlab.generator.documents import PLACEHOLDER, Doc, money, pct
from acqlab.generator.render import FILLER, Evidence, answer
from acqlab.generator.roles import DECOY_MOVE, MARGIN, PULL_BACK, UNRESOLVED_WIDTH
from acqlab.generator.traps import params_for
from acqlab.generator.truth import DealTruth

ROUND_STEP = 0.051  # amounts are rounded to $0.1M, so allow half a step (plus float fuzz) of slack
CORE_TITLES = {"Confidential Information Memorandum", "Quality of Earnings Report", "Credit Agreement Excerpt",
               "Fixed Asset and Lease Schedule", "Legal Letter"} | set(FILLER.values())
LEAK_WORDS = ("disallow", "recur", "notice", "lawsuit", "unfunded", "shortfall", "below the peg", "deferred maintenance",
              "re-tender", "not renew")
TOPIC_WORDS = {"addback": "add-back", "debt_like": "debt", "concentration": "customer", "nwc": "working capital",
               "capex": "capital expenditure"}


def _go_with(t: DealTruth, amounts: dict[str, float]) -> bool:
    return is_go(t.deal, params_for(amounts, t.base))


def check_engine(t: DealTruth) -> list[str]:
    problems = []
    face = _go_with(t, {})
    w0 = walk_away(t.deal, params_for({}, t.base))
    if face != t.face_go or _go_with(t, {f.trap: f.amount for f in t.facts}) != t.go:
        problems.append("stored go/no-go does not match the engine")
    pair = [f for f in t.facts if f.role == "interaction"]
    for f in t.facts:
        flips = _go_with(t, {f.trap: f.amount}) != face
        slack = MARGIN - ROUND_STEP / f.worst
        if f.role == "clean" and f.amount != 0:
            problems.append(f"{f.trap}: clean fact has amount {f.amount}")
        if f.role == "flipper" and not (flips and _go_with(t, {f.trap: f.amount - slack * f.worst}) != face):
            problems.append(f"{f.trap}: flipper does not clear its flip point by the margin")
        if f.role == "decoy":
            moved = w0 - walk_away(t.deal, params_for({f.trap: f.amount}, t.base))
            if flips or _go_with(t, {f.trap: min(f.worst, f.amount + slack * f.worst)}) != face:
                problems.append(f"{f.trap}: decoy is within the margin of flipping")
            if moved < DECOY_MOVE * t.deal.asking_price - 0.05:
                problems.append(f"{f.trap}: decoy moves walk-away by only {moved:.1f}")
        if f.role == "interaction" and (flips or _go_with(t, {f.trap: min(f.worst, f.amount + slack * f.worst)}) != face):
            problems.append(f"{f.trap}: interaction fact is within the margin of flipping alone")
        if f.role == "unresolvable" and (f.documented is None or
                                         abs(f.documented[1] - f.documented[0] - UNRESOLVED_WIDTH * f.worst) > 0.11):
            problems.append(f"{f.trap}: unresolvable range is missing or the wrong width")
    if pair:
        joint = {f.trap: f.amount for f in pair}
        if _go_with(t, joint) == face:
            problems.append("interaction pair does not flip together")
        for f in pair:
            back = dict(joint, **{f.trap: max(0.0, f.amount - PULL_BACK * f.worst + ROUND_STEP)})
            if _go_with(t, back) == face:
                problems.append(f"{f.trap}: interaction stops flipping when pulled back")
    tz = t.base.teaser
    by = {f.trap: f for f in t.facts}
    if (tz.adj_ebitda - by["addback"].amount) / tz.revenue_ltm < tz.capex_pct + by["capex"].amount / tz.revenue_ltm + 0.05:
        problems.append("margin rule: true EBITDA margin is not 5 points above capex")
    p = t.params()
    worse = p.model_copy(update={"revenue_haircut": p.revenue_haircut + 0.05})
    if walk_away(t.deal, worse) > walk_away(t.deal, p) + 1e-3:
        problems.append("a bigger revenue haircut raises walk-away")
    return problems


def check_leaks(t: DealTruth, docs: list[Doc], teaser: str) -> list[str]:
    problems = [f"unexpected title {d.title!r}" for d in docs
                if d.title not in CORE_TITLES and not d.title.startswith(("Customer Agreement — ", "Audited Financial"))]
    problems += [f"teaser mentions {w!r}" for w in LEAK_WORDS if w in teaser.lower()]
    return problems


def check_consistency(t: DealTruth, docs: list[Doc], evidence: list[Evidence]) -> list[str]:
    text = {d.id: d.render() for d in docs}
    problems = []
    for f, ev in zip(t.facts, evidence):
        got = answer(ev)
        want = f.documented if f.documented else (f.amount if f.role != "clean" else 0.0)
        if isinstance(want, tuple):
            ok = got == want
        else:
            ok = abs(got - want) <= max(0.1, 0.01 * abs(want))
        if not ok:
            problems.append(f"{f.trap}: evidence gives {got}, answer key says {want}")
        body = " ".join(text[d] for d in ev.docs)
        for name, v in ev.values.items():
            shown = pct(v) if name == "fraction" else money(v)
            if shown not in body:
                problems.append(f"{f.trap}: {name} {shown} not found in {ev.docs}")
    for d in docs:
        for b in d.blocks:
            if isinstance(b, str) or b.text is None:
                continue
            if re.search(r"\d", b.text) or set(PLACEHOLDER.findall(b.text)) != set(PLACEHOLDER.findall(b.template)):
                problems.append(f"{d.id}/{b.id}: LLM prose adds digits or changes placeholders")
    return problems


def check_batch(truths: list[DealTruth], texts: dict[str, str]) -> list[str]:
    """Batch-level checks: go rate near 50%, and topic mentions equally common in trap and clean deals."""
    problems = []
    rate = float(np.mean([t.go for t in truths]))
    if len(truths) >= 100 and not 0.38 <= rate <= 0.62:  # smaller batches are too noisy to judge
        problems.append(f"go rate {rate:.2f} outside 0.38-0.62")
    for trap, word in TOPIC_WORDS.items():
        counts = {True: [], False: []}
        for t in truths:
            f = next(f for f in t.facts if f.trap == trap)
            counts[f.role != "clean"].append(texts[t.id].lower().count(word))
        if counts[True] and counts[False]:
            ratio = np.mean(counts[True]) / np.mean(counts[False])
            if not 0.67 <= ratio <= 1.5:
                problems.append(f"presence: {trap!r} mentioned {ratio:.2f}x as often in trap deals")
    return problems
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 89 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): engine, leak, consistency and batch validators

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: Minimal Codex adapter and prose fill

**Files:**
- Create: `acqlab/llm.py`, `acqlab/generator/prose.py`
- Test: `tests/test_llm.py`, `tests/generator/test_prose.py`

**Interfaces:**
- Consumes: `Doc`, `Slot`, `PLACEHOLDER` (Task 4).
- Produces: in `acqlab/llm.py`: `Runner = Callable[[str], tuple[str, int]]`, `Runner = Callable[[str, dict | None], tuple[str, int]]`, `CACHE_DIR`, `APP_CODEX`, `CODEX_ARGS`, `ERROR_EVENTS`, `LLMUnavailable`, `codex_bin() -> str`, `_usage_tokens(jsonl) -> int`, `run_codex(prompt, schema=None) -> tuple[str, int]` (raises `LLMUnavailable` on any failure), `complete(prompt, *, schema=None, run=run_codex, cache_dir=CACHE_DIR) -> tuple[str, int]` (caches successes only; the schema is part of the cache key). In `prose.py`: `ATTEMPTS = 3`, `RULES`, `doc_prompt(doc, slots) -> str`, `doc_schema(slots) -> dict`, `prompt_for(doc, slot, attempt) -> str` (single-paragraph retry), `acceptable(text, template) -> bool`, `fill(docs, complete) -> tuple[list[Doc], int, int]` (docs, tokens, fallbacks); `complete` is called as `complete(prompt, schema=...)` for documents and `complete(prompt)` for retries. Plan 4 keeps `complete`'s signature.

- [ ] **Step 1: Write the failing tests**

`tests/test_llm.py`:
```python
import json
import subprocess
from pathlib import Path

import pytest

from acqlab import llm


def test_complete_caches_by_prompt_and_schema(tmp_path):
    calls = []

    def fake(prompt, schema):
        calls.append((prompt, schema))
        return f"echo {prompt}", 7

    assert llm.complete("hi", run=fake, cache_dir=tmp_path) == ("echo hi", 7)
    assert llm.complete("hi", run=fake, cache_dir=tmp_path) == ("echo hi", 7)
    llm.complete("hi", schema={"type": "object"}, run=fake, cache_dir=tmp_path)
    assert calls == [("hi", None), ("hi", {"type": "object"})]


def test_a_failed_call_is_never_cached(tmp_path):
    def limit(prompt, schema):
        raise llm.LLMUnavailable("usage limit reached")

    with pytest.raises(llm.LLMUnavailable):
        llm.complete("hi", run=limit, cache_dir=tmp_path)
    assert not list(tmp_path.glob("*.json"))
    assert llm.complete("hi", run=lambda p, s: ("ok", 1), cache_dir=tmp_path) == ("ok", 1)


def test_usage_tokens_sums_nested_usage_and_skips_junk():
    stream = "\n".join([json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
                        "not json", json.dumps({"msg": {"usage": {"input_tokens": 1, "output_tokens": 2}}})])
    assert llm._usage_tokens(stream) == 18
    assert llm._usage_tokens("") == 0


def _fake_codex(monkeypatch, *, reply="answer", code=0, events=(), seen=None):
    def fake_run(cmd, **kwargs):
        if seen is not None:
            seen["cmd"] = cmd
            if "--output-schema" in cmd:
                seen["schema"] = json.loads(Path(cmd[cmd.index("--output-schema") + 1]).read_text())
        if reply is not None:
            Path(cmd[cmd.index("--output-last-message") + 1]).write_text(reply + "\n")
        stdout = "\n".join(json.dumps(e) for e in events)
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="boom" if code else "")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setenv("CODEX_BIN", "/opt/codex")


def test_run_codex_uses_an_empty_temp_dir_and_reads_the_last_message(monkeypatch):
    seen = {}
    _fake_codex(monkeypatch, events=[{"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 4}}],
                seen=seen)
    assert llm.run_codex("the prompt", {"type": "object"}) == ("answer", 7)
    cmd = seen["cmd"]
    assert cmd[:2] == ["/opt/codex", "exec"] and cmd[-1] == "the prompt"
    assert "--ephemeral" in cmd and seen["schema"] == {"type": "object"}  # ephemeral: stays out of Codex history
    workdir = Path(cmd[cmd.index("-C") + 1])
    assert "read-only" in cmd and workdir != Path.cwd() and not workdir.exists()  # temp dir, removed afterwards


def test_run_codex_raises_on_any_sign_of_failure(monkeypatch):
    for kwargs in ({"code": 1}, {"events": [{"type": "error", "message": "usage limit reached"}]},
                   {"events": [{"type": "turn.failed", "error": {"message": "rate limited"}}]}, {"reply": None},
                   {"reply": "   "}):
        _fake_codex(monkeypatch, **kwargs)
        with pytest.raises(llm.LLMUnavailable):
            llm.run_codex("the prompt")


def test_codex_bin_falls_back_to_the_chatgpt_app_copy(monkeypatch):
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    assert llm.codex_bin() == llm.APP_CODEX
```

`tests/generator/test_prose.py`:
```python
import json
import re

from acqlab.generator.documents import Slot
from acqlab.generator.prose import ATTEMPTS, doc_prompt, doc_schema, fill
from acqlab.generator.render import render
from acqlab.generator.truth import generate

DOCS = render(generate("d0", "test", 0, mc=20))[0]
WITH_SLOTS = [d for d in DOCS if any(isinstance(b, Slot) for b in d.blocks)]
NUMBERS = re.compile(r"\$[\d,.]+M|[\d.]+%")


def _slots(doc):
    return [b for b in doc.blocks if isinstance(b, Slot)]


def _good(doc):
    return json.dumps({s.id: "In summary, " + s.template for s in _slots(doc)})


class Fake:
    """Answers whole-document prompts from a table, and counts every call."""

    def __init__(self, doc_reply, retry_reply="Revenue rose 12 percent."):
        self.doc_reply, self.retry_reply, self.calls = doc_reply, retry_reply, []

    def __call__(self, prompt, schema=None):
        self.calls.append((prompt, schema))
        if schema is not None:
            doc = next(d for d in WITH_SLOTS if doc_prompt(d, _slots(d)) == prompt)
            return self.doc_reply(doc), 5
        return self.retry_reply, 1


def test_slot_ids_are_unique_within_each_document():
    for d in DOCS:
        ids = [s.id for s in _slots(d)]
        assert len(ids) == len(set(ids)), d.id


def test_one_call_per_document_writes_every_paragraph_and_keeps_every_number():
    fake = Fake(_good)
    out, tokens, fallbacks = fill(DOCS, fake)
    assert fallbacks == 0 and len(fake.calls) == len(WITH_SLOTS) and tokens == 5 * len(WITH_SLOTS)
    for before, after in zip(DOCS, out):
        assert sorted(NUMBERS.findall(before.render())) == sorted(NUMBERS.findall(after.render()))
        assert all(s.text.startswith("In summary") for s in _slots(after))


def test_only_the_broken_paragraph_is_retried_on_its_own():
    def one_bad(doc):
        replies = json.loads(_good(doc))
        replies[_slots(doc)[0].id] = "Revenue rose 12 percent."  # digits: rejected
        return json.dumps(replies)

    fake = Fake(one_bad)
    out, _, fallbacks = fill(WITH_SLOTS[:1], fake)
    retries = [p for p, schema in fake.calls if schema is None]
    assert fallbacks == 1 and len(retries) == ATTEMPTS - 1 and len(set(retries)) == len(retries)
    first, *rest = _slots(out[0])
    assert first.text is None and all(s.text.startswith("In summary") for s in rest)


def test_malformed_json_falls_back_paragraph_by_paragraph():
    fake = Fake(lambda doc: "not json")
    out, _, fallbacks = fill(WITH_SLOTS[:1], fake)
    assert fallbacks == len(_slots(out[0])) and all(s.text is None for s in _slots(out[0]))


def test_document_prompt_keeps_paragraphs_separate_and_the_schema_requires_each_one():
    doc = WITH_SLOTS[0]
    prompt, schema = doc_prompt(doc, _slots(doc)), doc_schema(_slots(doc))
    assert "do not mention one paragraph's subject in another" in prompt and "Write no digits" in prompt
    assert all(f"- id: {s.id}" in prompt for s in _slots(doc))
    assert schema["required"] == [s.id for s in _slots(doc)] and schema["additionalProperties"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_llm.py tests/generator/test_prose.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/llm.py`:
```python
"""Minimal LLM adapter: prompt in, (text, tokens) out, cached on disk.
ponytail: Codex CLI only, for the Plan 2 renderer and extractor. Plan 4 adds `claude -p`, the solver sandbox and an
API backend behind this same signature."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

Runner = Callable[[str, dict | None], tuple[str, int]]
CACHE_DIR = Path("data/llm_cache")
# The ChatGPT desktop app bundles the Codex CLI without putting it on PATH.
APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
# Flags checked against `codex exec --help` (codex-cli 0.155.0-alpha.9.2). --ephemeral keeps thousands of
# generator calls out of the user's Codex session history.
CODEX_ARGS = ["exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only"]
ERROR_EVENTS = {"error", "turn.failed"}  # JSONL event types that mean the call did not complete


class LLMUnavailable(RuntimeError):
    """A call failed (usage limit, auth, network). Nothing was cached, so rerunning the same command resumes."""


def codex_bin() -> str:
    return os.environ.get("CODEX_BIN") or shutil.which("codex") or APP_CODEX


def _events(jsonl: str) -> list[dict]:
    out = []
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def _usage_tokens(jsonl: str) -> int:
    """Sum input+output tokens over every `usage` object in Codex's JSONL event stream (0 if none reported)."""
    total = 0
    stack: list = _events(jsonl)
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            usage = node.get("usage")
            if isinstance(usage, dict):
                total += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
            stack.extend(v for k, v in node.items() if k != "usage")
        elif isinstance(node, list):
            stack.extend(node)
    return total


def run_codex(prompt: str, schema: dict | None = None) -> tuple[str, int]:
    """One Codex call from an empty temp dir with a read-only sandbox, so it can't see the repo or answer keys.
    Raises LLMUnavailable on any sign of failure, so a limit message is never mistaken for an answer."""
    with tempfile.TemporaryDirectory() as tmp:
        last = Path(tmp) / "last_message.txt"
        cmd = [codex_bin(), *CODEX_ARGS, "-C", tmp, "--output-last-message", str(last)]
        if schema is not None:
            (Path(tmp) / "schema.json").write_text(json.dumps(schema))
            cmd += ["--output-schema", str(Path(tmp) / "schema.json")]
        proc = subprocess.run([*cmd, prompt], capture_output=True, text=True, timeout=600)
        failed = [e for e in _events(proc.stdout) if e.get("type") in ERROR_EVENTS]
        text = last.read_text().strip() if last.exists() else ""
        if proc.returncode != 0 or failed or not text:
            detail = (failed and json.dumps(failed[-1])) or proc.stderr.strip()[-500:] or "empty reply"
            raise LLMUnavailable(f"codex exec failed (exit {proc.returncode}): {detail}")
        return text, _usage_tokens(proc.stdout)


def complete(prompt: str, *, schema: dict | None = None, run: Runner = run_codex,
             cache_dir: Path = CACHE_DIR) -> tuple[str, int]:
    """Cached call: the same prompt (and schema) never costs twice. Tokens are those recorded when it first ran.
    Only successful replies are cached; a failed call raises and leaves nothing behind."""
    key = prompt if schema is None else prompt + "\n" + json.dumps(schema, sort_keys=True)
    path = cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    if path.exists():
        hit = json.loads(path.read_text())
        return hit["text"], hit["tokens"]
    text, tokens = run(prompt, schema)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"text": text, "tokens": tokens}))
    return text, tokens
```

`acqlab/generator/prose.py`:
```python
"""Replace template prose with LLM prose, one call per document. The LLM never writes a number: every value stays a
{{placeholder}}. Paragraphs that come back broken are retried one at a time; after ATTEMPTS they keep the template."""
import json
import re
from collections.abc import Callable

from acqlab.generator.documents import PLACEHOLDER, Doc, Slot

ATTEMPTS = 3  # one whole-document call, then up to two single-paragraph retries
Complete = Callable[..., tuple[str, int]]
RULES = ("Write no digits. Keep each placeholder exactly as written, at least once, and use no other placeholders. "
         "Do not add amounts, dates, percentages, names or facts beyond the placeholders.")


def _names(s: Slot) -> str:
    names = sorted(set(PLACEHOLDER.findall(s.template)))
    return ", ".join("{{" + n + "}}" for n in names) or "none"


def doc_prompt(doc: Doc, slots: list[Slot]) -> str:
    lines = [
        f"You are writing the prose paragraphs of a {doc.title} for a fictional company.",
        "Write each paragraph as two to four sentences of professional prose. Keep each paragraph to its own "
        "meaning: do not mention one paragraph's subject in another.",
        f"Rules for every paragraph: {RULES}",
        "Return JSON mapping each paragraph id to its text.", "Paragraphs:",
    ]
    for s in slots:
        lines += [f"- id: {s.id}", f"  purpose: {s.brief}", f'  meaning: "{s.template}"',
                  f"  placeholders: {_names(s)}"]
    return "\n".join(lines)


def doc_schema(slots: list[Slot]) -> dict:
    return {"type": "object", "properties": {s.id: {"type": "string"} for s in slots},
            "required": [s.id for s in slots], "additionalProperties": False}


def prompt_for(doc: Doc, s: Slot, attempt: int) -> str:
    """Single-paragraph retry. The attempt number changes the prompt, so a retry is never served from the cache."""
    return "\n".join([
        f"You are writing one passage of a {doc.title} for a fictional company. Attempt {'I' * (attempt + 1)}.",
        f"Purpose: {s.brief}.",
        f'Convey exactly this meaning, in two to four sentences of professional prose: "{s.template}"',
        f"Placeholders: {_names(s)}. {RULES}",
        "Return only the passage.",
    ])


def acceptable(text: object, template: str) -> bool:
    return (isinstance(text, str) and bool(text.strip()) and not re.search(r"\d", text)
            and set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(template)))


def _parse(text: str) -> dict:
    try:
        got = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return got if isinstance(got, dict) else {}


def fill(docs: list[Doc], complete: Complete) -> tuple[list[Doc], int, int]:
    """Returns (docs with prose, tokens used, paragraphs left as template)."""
    tokens = fallbacks = 0
    out = []
    for doc in docs:
        slots = [b for b in doc.blocks if isinstance(b, Slot)]
        if not slots:
            out.append(doc)
            continue
        text, used = complete(doc_prompt(doc, slots), schema=doc_schema(slots))
        tokens += used
        replies = _parse(text)
        written: dict[str, str] = {}
        for s in slots:
            reply = replies.get(s.id)
            attempt = 1
            while not acceptable(reply, s.template) and attempt < ATTEMPTS:
                reply, used = complete(prompt_for(doc, s, attempt))
                tokens += used
                attempt += 1
            if acceptable(reply, s.template):
                written[s.id] = reply
            else:
                fallbacks += 1
        blocks = [b.model_copy(update={"text": written[b.id]}) if isinstance(b, Slot) and b.id in written else b
                  for b in doc.blocks]
        out.append(doc.model_copy(update={"blocks": blocks}))
    return out, tokens, fallbacks
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 100 passed.

- [ ] **Step 5: Confirm the Codex CLI the adapter will use**

Run: `"$(uv run python -c 'from acqlab.llm import codex_bin; print(codex_bin())')" exec --help`
Expected: help text listing every flag in `CODEX_ARGS` plus `-C` and `--output-last-message` (verified on codex-cli 0.155.0-alpha.9.2, bundled with the ChatGPT app). If a flag differs in a newer version, change only `CODEX_ARGS` / `run_codex`, keep the tests green, and note it in the commit message.

- [ ] **Step 6: One real smoke call (only with the user's explicit OK — it uses their subscription)**

Run: `uv run python -c "from pathlib import Path; from acqlab.llm import complete; print(complete('Reply with the single word: ok', cache_dir=Path('data/llm_cache')))"`
Expected: `('ok', <tokens>)` with tokens > 0. If tokens is 0, inspect `codex exec --json` output and adjust `_usage_tokens` to the reported event shape (add a test with that shape).

- [ ] **Step 7: Commit**

```bash
git add acqlab tests
git commit -m "feat(llm): cached Codex adapter that never caches failures; per-document prose fill

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: Recoverability check

**Files:**
- Create: `acqlab/generator/recover.py`
- Test: `tests/generator/test_recover.py`

**Interfaces:**
- Consumes: `LABELS`, `Evidence`, `answer` (Task 4); `DealTruth` (Task 3).
- Produces: `QUESTIONS`, `SCHEMA` (JSON schema for `{low, high}`, passed to `complete`), `question(trap, variant) -> str`, `prompt_for(docs: list[str], q) -> str`, `parse(text) -> tuple[float | None, float | None]`, `check(t, evidence, texts: dict[str, str], complete, unrelated: str) -> tuple[list[str], int]` (problems, tokens).

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_recover.py`:
```python
import json

from acqlab.generator.recover import check, parse, prompt_for, question
from acqlab.generator.render import answer, render
from acqlab.generator.truth import generate


def _setup(seed=3):
    t = generate("d", "test", seed, mc=20)
    docs, evidence = render(t)
    texts = {d.id: d.render() for d in docs}
    filler = next(d.id for d in docs if d.domain == "filler")
    return t, evidence, texts, filler


def _oracle(t, evidence, texts):
    """Answers correctly when shown a fact's evidence, and 'not found' otherwise."""
    replies = {}
    for f, ev in zip(t.facts, evidence):
        want = answer(ev)
        lo, hi = want if isinstance(want, tuple) else (want, want)
        replies[prompt_for([texts[d] for d in ev.docs], question(f.trap, f.variant))] = {"low": lo, "high": hi}
    return lambda p, schema=None: (json.dumps(replies.get(p, {"low": None, "high": None})), 3)


def test_parse_reads_json_even_with_surrounding_text():
    assert parse('Sure: {"low": 1.5, "high": 2}') == (1.5, 2)
    assert parse("no json") == (None, None)
    assert parse('{"low": null, "high": null}') == (None, None)


def test_a_correct_extractor_passes():
    t, evidence, texts, filler = _setup()
    problems, tokens = check(t, evidence, texts, _oracle(t, evidence, texts), filler)
    assert problems == [] and tokens == 3 * 2 * len(t.facts)


def test_wrong_answers_and_answers_found_in_filler_both_fail():
    t, evidence, texts, filler = _setup()
    problems, _ = check(t, evidence, texts, lambda p, schema=None: ('{"low": 999, "high": 999}', 0), filler)
    assert len(problems) == 2 * len(t.facts)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_recover.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/recover.py`:
```python
"""Recoverability check (design §7): a non-solver model, shown only a fact's evidence documents, must recover the
answer; shown an unrelated filler document, it must say the answer is not there."""
import json
import re
from collections.abc import Callable

from acqlab.generator.render import LABELS, Evidence, answer
from acqlab.generator.truth import DealTruth

Complete = Callable[..., tuple[str, int]]
SCHEMA = {"type": "object", "properties": {"low": {"type": ["number", "null"]}, "high": {"type": ["number", "null"]}},
          "required": ["low", "high"], "additionalProperties": False}
QUESTIONS = {
    "addback": "How much of the claimed {label} add-back, in $M, should be disallowed because the cost recurs? "
               "Answer 0 if it is a genuine one-time cost.",
    "debt_like": "What amount, in $M, should be treated as debt at closing for any {label}? Answer 0 if none.",
    "concentration": "By how much, in $M per year, will revenue from the largest customer fall? Answer 0 if it "
                     "will not fall.",
    "nwc": "By how much, in $M, will net working capital at closing fall below the peg? Answer 0 if it will not.",
    "capex": "How much additional capital expenditure, in $M per year, is needed because of {label}? Answer 0 if "
             "none.",
}


def question(trap: str, variant: str) -> str:
    return QUESTIONS[trap].format(label=LABELS[variant])


def prompt_for(docs: list[str], q: str) -> str:
    return "\n\n".join([
        "Answer from the documents below alone.", *docs, f"Question: {q}",
        'Reply with JSON only: {"low": number or null, "high": number or null}. For a single value use low = high. '
        "If the documents give only a range, give that range. If they do not contain the answer, use null for both.",
    ])


def parse(text: str) -> tuple[float | None, float | None]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None, None
    try:
        got = json.loads(match.group(0))
        return got.get("low"), got.get("high")
    except (json.JSONDecodeError, AttributeError):
        return None, None


def _close(a: float | None, b: float) -> bool:
    return a is not None and abs(a - b) <= max(0.15, 0.03 * abs(b))


def check(t: DealTruth, evidence: list[Evidence], texts: dict[str, str], complete: Complete,
          unrelated: str) -> tuple[list[str], int]:
    """Returns (problems, tokens). `unrelated` is the id of a filler document with no answer in it."""
    problems, tokens = [], 0
    for f, ev in zip(t.facts, evidence):
        q = question(f.trap, f.variant)
        want = answer(ev)
        lo_hi = want if isinstance(want, tuple) else (want, want)
        (low, high), used = _ask([texts[d] for d in ev.docs], q, complete)
        tokens += used
        if not (_close(low, lo_hi[0]) and _close(high, lo_hi[1])):
            problems.append(f"{f.trap}: extractor answered {low}-{high}, answer key {lo_hi}")
        (low, high), used = _ask([texts[unrelated]], q, complete)
        tokens += used
        if low is not None or high is not None:
            problems.append(f"{f.trap}: extractor found an answer in unrelated document {unrelated!r}")
    return problems, tokens


def _ask(docs: list[str], q: str, complete: Complete) -> tuple[tuple, int]:
    text, used = complete(prompt_for(docs, q), schema=SCHEMA)
    return parse(text), used
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 103 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): recoverability check with positive and negative probes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: Batch command

**Files:**
- Create: `acqlab/generator/batch.py`
- Test: `tests/generator/test_batch.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `SEED_OFFSET`, `RETRY_SEED`, `MAX_RETRIES`, `AnswerKey{truth, evidence, budget, retrieval_cost, llm_tokens}` (the JSON written to `data/truth/<id>.json`), `build(deal_id, split, seed, *, mc, llm=None) -> tuple[AnswerKey, list[Doc], str]`, `run(out, counts, *, seed=0, mc=400, llm=None, recover=0, extract=None) -> list[str]` (lets `LLMUnavailable` propagate), `main(argv=None) -> int` (0 = clean, 1 = batch problems, 2 = Codex stopped; rerun to resume). CLI: `uv run python -m acqlab.generator.batch [--out data] [--dev 50] [--test 120] [--hand 10] [--showcase 1] [--seed 0] [--mc 400] [--llm] [--recover N]`.

- [ ] **Step 1: Write the failing tests**

`tests/generator/test_batch.py`:
```python
import json
import math
from functools import partial

import pytest

from acqlab.dataroom.tools import DataRoom
from acqlab import llm
from acqlab.generator import batch

COUNTS = {"dev": 4, "test": 3, "hand": 2, "showcase": 1}


def test_batch_writes_rooms_answer_keys_and_splits(tmp_path):
    assert batch.run(tmp_path, COUNTS, mc=20) == []
    splits = json.loads((tmp_path / "splits.json").read_text())
    assert {k: len(v) for k, v in splits.items()} == COUNTS
    for ids in splits.values():
        for deal_id in ids:
            room = tmp_path / "deals" / deal_id / "room"
            key = json.loads((tmp_path / "truth" / f"{deal_id}.json").read_text())
            assert not any(p.name.endswith(".json") and p.name != "index.json" for p in room.iterdir())
            dr = DataRoom(room)
            pages = sum(d["pages"] for d in dr.list_documents())
            assert key["budget"] == dr.budget == math.ceil(0.35 * pages)
            assert set(key["retrieval_cost"]) == {"addback", "debt_like", "concentration", "nwc", "capex"}
    showcase = json.loads((tmp_path / "truth" / "showcase-000.json").read_text())
    assert showcase["truth"]["case_type"] == "flip"


def test_recoverability_is_phased_in_to_hand_showcase_and_a_dev_sample(tmp_path):
    asked = set()

    def extract(prompt, schema=None):
        asked.add(prompt)
        return '{"low": null, "high": null}', 0

    problems = batch.run(tmp_path, COUNTS, mc=20, recover=1, extract=extract)
    checked = {p.split(":")[0] for p in problems}  # this extractor fails every deal it is shown
    assert {"hand-000", "hand-001", "showcase-000"} <= checked
    assert sum(d.startswith("dev-") for d in checked) == 1 and not any(d.startswith("test-") for d in checked)


def test_cli_runs_without_an_llm(tmp_path):
    code = batch.main(["--out", str(tmp_path), "--dev", "2", "--test", "1", "--hand", "0", "--showcase", "0",
                       "--mc", "20"])
    assert code == 0 and (tmp_path / "truth" / "dev-000.json").exists()


def _prose_runner(limit=None):
    """Fake Codex that writes valid prose, and hits a usage limit after `limit` calls if given."""
    state = {"calls": 0}

    def run(prompt, schema):
        if limit is not None and state["calls"] >= limit:
            raise llm.LLMUnavailable("usage limit reached")
        state["calls"] += 1
        if schema is None:
            return "Plain passage.", 1
        slots = [line[len("- id: "):] for line in prompt.splitlines() if line.startswith("- id: ")]
        meanings = [line.split('meaning: "', 1)[1][:-1] for line in prompt.splitlines() if "  meaning: " in line]
        return json.dumps({sid: "Put simply, " + m for sid, m in zip(slots, meanings)}), 1

    return run, state


def test_a_codex_limit_stops_the_batch_and_a_rerun_resumes_from_the_cache(tmp_path):
    counts, cache = {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, tmp_path / "cache"
    flaky, _ = _prose_runner(limit=5)
    with pytest.raises(llm.LLMUnavailable):
        batch.run(tmp_path / "a", counts, mc=20, llm=partial(llm.complete, run=flaky, cache_dir=cache))
    assert len(list(cache.glob("*.json"))) == 5  # the five good replies were kept
    resumed, state = _prose_runner()
    assert batch.run(tmp_path / "a", counts, mc=20, llm=partial(llm.complete, run=resumed, cache_dir=cache)) == []
    fresh, fresh_state = _prose_runner()
    batch.run(tmp_path / "b", counts, mc=20, llm=partial(llm.complete, run=fresh, cache_dir=tmp_path / "c2"))
    assert state["calls"] == fresh_state["calls"] - 5  # nothing already answered was paid for again
    for deal in ("dev-000", "dev-001"):
        a, b = (tmp_path / r / "deals" / deal / "room" / "cim.md" for r in ("a", "b"))
        assert a.read_text() == b.read_text()


def test_cli_reports_a_codex_stop_and_exits_2(tmp_path, monkeypatch, capsys):
    def limit(prompt, **kwargs):
        raise llm.LLMUnavailable("usage limit reached")

    monkeypatch.setattr(llm, "complete", limit)
    code = batch.main(["--out", str(tmp_path), "--dev", "1", "--test", "0", "--hand", "0", "--showcase", "0",
                       "--mc", "20", "--llm"])
    assert code == 2 and "Run the same command again" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/generator/test_batch.py`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

`acqlab/generator/batch.py`:
```python
"""Generate the benchmark's deals: data rooms under data/deals/<id>/room, answer keys under data/truth/<id>.json.

  uv run python -m acqlab.generator.batch --out data --dev 50 --test 120 --hand 10
"""
import argparse
import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from acqlab.dataroom.tools import write_room
from acqlab.generator.documents import Doc
from acqlab.generator.render import Evidence, render, teaser_text
from acqlab.generator.truth import DealTruth, generate
from acqlab.generator.validate import check_batch, check_consistency, check_engine, check_leaks
from acqlab.llm import LLMUnavailable

SEED_OFFSET = {"dev": 0, "test": 10_000, "hand": 20_000, "showcase": 30_000}
RETRY_SEED = 1_000_000
MAX_RETRIES = 5


class AnswerKey(BaseModel):
    truth: DealTruth
    evidence: list[Evidence]
    budget: float
    retrieval_cost: dict[str, float]  # trap -> pages to open its evidence documents
    llm_tokens: int = 0


def build(deal_id: str, split: str, seed: int, *, mc: int, llm=None) -> tuple[AnswerKey, list[Doc], str]:
    """One validated deal. Failed checks regenerate from a new seed."""
    for k in range(MAX_RETRIES):
        t = generate(deal_id, split, seed + k * RETRY_SEED, mc=mc, force_case="flip" if split == "showcase" else None)
        docs, evidence = render(t)
        tokens = 0
        if llm is not None:
            from acqlab.generator.prose import fill
            docs, tokens, _ = fill(docs, llm)
        teaser = teaser_text(t)
        if not (check_engine(t) + check_leaks(t, docs, teaser) + check_consistency(t, docs, evidence)):
            pages = {d.id: d.pages for d in docs}
            key = AnswerKey(truth=t, evidence=evidence, budget=0.0, llm_tokens=tokens,
                            retrieval_cost={e.trap: float(sum(pages[d] for d in e.docs)) for e in evidence})
            return key, docs, teaser
    raise RuntimeError(f"{deal_id}: failed validation {MAX_RETRIES} times")


def run(out: Path, counts: dict[str, int], *, seed: int = 0, mc: int = 400, llm=None, recover: int = 0,
        extract=None) -> list[str]:
    """Generate every split; returns batch-level problems (also printed)."""
    splits: dict[str, list[str]] = {}
    keys, texts = [], {}
    for split, n in counts.items():
        for i in range(n):
            deal_id = f"{split}-{i:03d}"
            key, docs, teaser = build(deal_id, split, seed + SEED_OFFSET[split] + i, mc=mc, llm=llm)
            key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs)
            (out / "truth").mkdir(parents=True, exist_ok=True)
            (out / "truth" / f"{deal_id}.json").write_text(key.model_dump_json(indent=2))
            splits.setdefault(split, []).append(deal_id)
            keys.append(key)
            texts[deal_id] = " ".join(d.render() for d in docs)
    (out / "splits.json").write_text(json.dumps(splits, indent=2))
    problems = check_batch([k.truth for k in keys], texts)
    if extract is not None:
        problems += _recoverability(out, keys, splits, recover, extract)
    for p in problems:
        print("PROBLEM:", p)
    return problems


def _recoverability(out: Path, keys: list[AnswerKey], splits: dict, n_dev: int, extract) -> list[str]:
    """Phase-in (design §7): hand-reviewed, showcase and a random sample of dev deals."""
    from acqlab.generator.recover import check
    rng = np.random.default_rng(0)
    dev = splits.get("dev", [])
    chosen = set(splits.get("hand", []) + splits.get("showcase", [])) | set(
        rng.choice(dev, min(n_dev, len(dev)), replace=False).tolist() if dev else [])
    problems = []
    for key in keys:
        if key.truth.id not in chosen:
            continue
        room = out / "deals" / key.truth.id / "room"
        texts = {p.stem: p.read_text() for p in room.glob("*.md")}
        filler = next(d["id"] for d in json.loads((room / "index.json").read_text())["documents"]
                      if d["domain"] == "filler")
        found, _ = check(key.truth, key.evidence, texts, extract, filler)
        problems += [f"{key.truth.id}: {p}" for p in found]
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--dev", type=int, default=50)
    ap.add_argument("--test", type=int, default=120)
    ap.add_argument("--hand", type=int, default=10)
    ap.add_argument("--showcase", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mc", type=int, default=400, help="Monte Carlo draws for per-fact decision value")
    ap.add_argument("--llm", action="store_true", help="write prose with Codex (default: template prose)")
    ap.add_argument("--recover", type=int, default=-1,
                    help="run the recoverability check on hand/showcase plus this many dev deals (needs Codex)")
    args = ap.parse_args(argv)
    llm = extract = None
    if args.llm or args.recover >= 0:
        from acqlab.llm import complete
        llm = complete if args.llm else None
        extract = complete if args.recover >= 0 else None
    counts = {"dev": args.dev, "test": args.test, "hand": args.hand, "showcase": args.showcase}
    try:
        problems = run(args.out, counts, seed=args.seed, mc=args.mc, llm=llm, recover=max(args.recover, 0),
                       extract=extract)
    except LLMUnavailable as e:
        print(f"Codex stopped: {e}\nEvery completed call is cached. Run the same command again (after any usage "
              "limit resets) to continue where it left off.")
        return 2
    print(f"generated {sum(counts.values())} deals into {args.out}; {len(problems)} batch problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 108 passed.

- [ ] **Step 5: Generate the full template-prose batch**

Run: `uv run python -m acqlab.generator.batch`
Expected: `generated 181 deals into data; 0 batch problems` in under two minutes, and `data/deals/`, `data/truth/`, `data/splits.json` exist. Nothing under `data/` is committed.

- [ ] **Step 6: Proof-of-concept LLM run (manual; only with the user's explicit OK)**

After Task 7 Steps 5–6 succeed, run a four-deal Codex batch into a separate folder, sized for about half a Codex usage window (~70 calls):
1. Prose (~27 calls): `uv run python -m acqlab.generator.batch --out data/poc --dev 3 --test 0 --hand 0 --showcase 1 --llm`
2. Recoverability on the same four deals (~40 calls; the prose replays from the cache): the same command plus `--recover 3`.

If Codex hits its usage limit, the command stops with exit code 2; run the same command again after the limit resets and it continues where it left off. Report batch problems, fallback paragraphs and total tokens (sum `llm_tokens` in `data/poc/truth/*.json`) to the user. The full recoverability run on every test deal is required before the main benchmark (design §7), not in this plan.

- [ ] **Step 7: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): batch command writing rooms, answer keys and splits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Done when

- `uv run pytest -q` → 108 passed.
- `uv run python -m acqlab.generator.batch` → 181 deals, 0 batch problems.
- Nothing under `acqlab/engine` changed except the `flip_threshold` bounds line; no answer key is written under a `room/` folder.
- `docs/HANDOFF.md` updated: Plan 2 status, the findings above, and the Codex smoke-call / PoC-run status.

## Later (from the design doc, plus items found here)

- Harden `acqlab/llm.py` (Plan 4): `claude -p`, solver sandbox, API backend.
- Pin Damodaran values against his .xls files (download with user approval).
- Dice-rolled realism batch; favorable surprises; aggressive sellers; messy documents.
- Source the trap size ranges and the assumption rows (growth, step-downs, sweep, fees).
- Richer story variants: today a held-out variant changes labels and reasons, not whole document structures.
- Full recoverability coverage of every test deal before the main benchmark (required).

# Plan 1: LBO Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic LBO engine that is the sole source of financial outputs for Acquisition Lab: projections, debt sizing, returns, walk-away price, go/no-go, flip thresholds, and walk-away distributions under uncertain beliefs.

**Architecture:** Pure Python package `acqlab.engine` with pydantic input/output types. Annual periods, one term loan, single exit cash flow (so IRR is closed-form). Debt is sized by the sponsor as min(lender cap, covenant-safe debt, min-equity cap); walk-away is a bisection on price against the IRR hurdle. No LLM code anywhere in this package.

**Tech Stack:** Python 3.12, uv, pydantic 2, numpy 2, pytest, hypothesis.

**Spec:** `docs/superpowers/specs/2026-09-22-acquisition-lab-design.md` (Section 1).

**Where this fits:** Plan 1 of 7. Later plans, each written when the previous one lands: (2) generator & data room, (3) Track A routers, (4) LLM adapter + sandbox + single-agent baselines S1a/S1b + week-4 checkpoint, (5) S4 multi-agent framework, (6) benchmark runner & metrics, (7) demo UI.

## Global Constraints

- Python `>=3.12`; dependencies limited to `pydantic>=2.7`, `numpy>=2.0`; dev: `pytest>=8`, `hypothesis>=6.100`.
- All money in **$M**; all rates and percentages as **decimals** (20% = `0.20`).
- **Annual periods, single term loan.** Hold period default 5 years.
- The engine contains **no LLM calls** and is the only code that produces financial outputs.
- Sponsor policy defaults (spec §1): IRR hurdle `0.20`, hold `5`, min equity `0.40`, downside revenue shock `-0.10`, downside margin shock `-0.02`.
- Generic hidden-fact parameters (the only ones agents may set): `ebitda_adjustment`, `debt_like`, `revenue_haircut`, `nwc_adjustment`, `capex_adjustment_pct`.
- Commit messages end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Engine definitions (read before starting)

- **Accepted EBITDA** = reported adjusted EBITDA + `ebitda_adjustment`. Base margin = accepted EBITDA / LTM revenue.
- **Revenue, year t** = LTM revenue × (1 + growth)^t × (1 − `revenue_haircut`) × (1 + downside revenue shock if downside). Downside margin = base margin + downside margin shock.
- **Year t cash flow:** EBITDA − capex (revenue × (capex % + `capex_adjustment_pct`)) − NWC % × (revenue_t − revenue_{t−1}, with revenue_0 = LTM revenue) − taxes − interest. Taxes = max(0, tax rate × (EBITDA − D&A % × revenue − interest)). Interest = rate × (opening debt + opening revolver draw, i.e. max(0, −opening cash)).
- **Debt paydown:** mandatory amortization = amortization % × initial debt (capped at remaining debt); cash sweep = sweep % × max(0, FCF − mandatory), capped at remaining debt. Everything else accumulates in cash (negative cash = revolver draw, charged interest from the next year). Net debt = debt − cash. Leverage = net debt / EBITDA (∞ if EBITDA ≤ 0).
- **Uses** = price × (1 + fees %) + `debt_like` + `nwc_adjustment`.
- **Debt sizing** = min(max leverage × accepted EBITDA, covenant-safe debt, (1 − min equity %) × uses). Covenant-safe debt = largest opening debt whose *downside* leverage never exceeds the covenant ceiling in any year.
- **Returns:** exit equity = exit multiple × year-5 base EBITDA − year-5 base net debt. MOIC = exit equity / equity. IRR = MOIC^(1/hold) − 1 (−1 if MOIC ≤ 0).
- **Walk-away** = max price with base IRR ≥ hurdle (bisection; `PRICE_FLOOR = 0.01` if nothing clears). **Go** ⇔ asking price ≤ walk-away.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml`, `.python-version`, `.gitignore` | Project config |
| `acqlab/__init__.py` | Package marker (empty) |
| `acqlab/engine/__init__.py` | Public engine API (re-exports) |
| `acqlab/engine/model.py` | Pydantic types: `Company`, `Financing`, `Policy`, `Params`, `Deal`, `Year`, `Result`, `PARAM_NAMES` |
| `acqlab/engine/lbo.py` | Projection, debt sizing, returns, `evaluate` |
| `acqlab/engine/walkaway.py` | `walk_away`, `is_go`, `flip_threshold` |
| `acqlab/engine/beliefs.py` | `Beliefs`, `sample_params`, `evaluate_under` |
| `tests/conftest.py` | Shared fixtures: `make_simple`, `make_full`, `FULL_PARAMS` |
| `tests/engine/test_*.py` | One test file per engine module + property tests |

---

### Task 1: Project scaffold and engine types

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `acqlab/__init__.py`, `acqlab/engine/__init__.py`, `acqlab/engine/model.py`
- Create: `tests/__init__.py`, `tests/engine/__init__.py`, `tests/conftest.py`
- Test: `tests/engine/test_model.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `acqlab.engine.{Company, Financing, Policy, Params, Deal, Year, Result, PARAM_NAMES}`; test helpers `tests.conftest.{make_simple(covenant: float = 5.0) -> Deal, make_full() -> Deal, FULL_PARAMS: Params}` and pytest fixtures `simple`, `full`.

- [ ] **Step 1: Create project config**

`pyproject.toml`:
```toml
[project]
name = "acqlab"
version = "0.1.0"
description = "Acquisition Lab: decision-directed diligence for leveraged buyouts"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7", "numpy>=2.0"]

[dependency-groups]
dev = ["pytest>=8", "hypothesis>=6.100"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["acqlab"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.python-version`:
```
3.12
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
.hypothesis/
data/
```

Create empty files `acqlab/__init__.py`, `tests/__init__.py`, `tests/engine/__init__.py`.

- [ ] **Step 2: Write the failing test**

`tests/engine/test_model.py`:
```python
from acqlab.engine import PARAM_NAMES, Params, Policy


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv sync && uv run pytest tests/engine/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` for `acqlab.engine`.

- [ ] **Step 4: Write the types**

`acqlab/engine/model.py`:
```python
"""Deal inputs and engine outputs. All money in $M, rates as decimals."""
from pydantic import BaseModel, Field


class Company(BaseModel):
    revenue_ltm: float
    reported_adj_ebitda: float
    growth: float
    capex_pct: float
    nwc_pct: float
    da_pct: float
    tax_rate: float


class Financing(BaseModel):
    max_leverage: float  # lender cap, x lender-accepted EBITDA at close
    interest_rate: float
    amortization_pct: float  # of initial principal, per year
    cash_sweep: float  # share of post-amortization FCF repaying debt
    covenant_max_leverage: list[float]  # net debt / EBITDA ceiling, years 1..hold
    fees_pct: float  # of price


class Policy(BaseModel):
    irr_hurdle: float = 0.20
    hold_years: int = 5
    exit_multiple: float
    min_equity_pct: float = 0.40
    downside_revenue_shock: float = -0.10
    downside_margin_shock: float = -0.02


class Params(BaseModel):
    """Generic hidden-fact parameters. Zero = teaser taken at face value."""
    ebitda_adjustment: float = 0.0  # $M added to reported adj. EBITDA (negative = disallowed add-back)
    debt_like: float = 0.0  # $M funded at close
    revenue_haircut: float = 0.0  # fraction of projected revenue lost
    nwc_adjustment: float = 0.0  # $M cash needed at close (peg shortfall)
    capex_adjustment_pct: float = 0.0  # extra capex, % of revenue


PARAM_NAMES = tuple(Params.model_fields)


class Deal(BaseModel):
    company: Company
    financing: Financing
    policy: Policy
    asking_price: float


class Year(BaseModel):
    revenue: float
    ebitda: float
    interest: float
    fcf: float  # after interest, taxes, capex, change in NWC
    debt: float  # closing gross debt
    cash: float  # closing cash (negative = funded by revolver)
    net_debt: float
    leverage: float  # net debt / EBITDA (inf if EBITDA <= 0)


class Result(BaseModel):
    price: float
    uses: float
    debt: float
    equity: float
    exit_equity: float
    irr: float
    moic: float
    base: list[Year]
    downside: list[Year]
    covenant_headroom: list[float] = Field(description="covenant max - downside leverage, per year")
```

`acqlab/engine/__init__.py`:
```python
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year

__all__ = ["Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year"]
```

- [ ] **Step 5: Add shared test fixtures**

`tests/conftest.py`:
```python
import pytest

from acqlab.engine import Company, Deal, Financing, Params, Policy


def make_simple(covenant: float = 5.0) -> Deal:
    """No taxes, growth, capex, NWC, amortization or sweep: every number is hand-checkable."""
    return Deal(
        company=Company(revenue_ltm=100, reported_adj_ebitda=20, growth=0, capex_pct=0,
                        nwc_pct=0, da_pct=0, tax_rate=0),
        financing=Financing(max_leverage=4.0, interest_rate=0.10, amortization_pct=0,
                            cash_sweep=0, covenant_max_leverage=[covenant] * 5, fees_pct=0.02),
        policy=Policy(exit_multiple=8.0),
        asking_price=150,
    )


def make_full() -> Deal:
    """Every mechanic switched on. Golden values come from an independent straight-line calculation."""
    return Deal(
        company=Company(revenue_ltm=200, reported_adj_ebitda=30, growth=0.05, capex_pct=0.03,
                        nwc_pct=0.10, da_pct=0.025, tax_rate=0.25),
        financing=Financing(max_leverage=5.0, interest_rate=0.09, amortization_pct=0.05,
                            cash_sweep=0.5, covenant_max_leverage=[5.5, 5.25, 5.0, 4.75, 4.5],
                            fees_pct=0.02),
        policy=Policy(exit_multiple=8.0),
        asking_price=230,
    )


FULL_PARAMS = Params(ebitda_adjustment=-2, debt_like=5, revenue_haircut=0.05,
                     nwc_adjustment=2, capex_adjustment_pct=0.005)


@pytest.fixture
def simple() -> Deal:
    return make_simple()


@pytest.fixture
def full() -> Deal:
    return make_full()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/engine/test_model.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .python-version .gitignore uv.lock acqlab tests
git commit -m "feat(engine): project scaffold and deal types

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Annual projection

**Files:**
- Create: `acqlab/engine/lbo.py`
- Modify: `acqlab/engine/__init__.py`
- Test: `tests/engine/test_lbo.py`

**Interfaces:**
- Consumes: `Deal`, `Params`, `Year` from Task 1.
- Produces: `acqlab.engine.lbo.accepted_ebitda(deal: Deal, params: Params) -> float`; `acqlab.engine.project(deal: Deal, params: Params, debt0: float, downside: bool = False) -> list[Year]`.

- [ ] **Step 1: Write the failing tests**

`tests/engine/test_lbo.py`:
```python
import math

import pytest

from acqlab.engine import Params, project


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


def test_nonpositive_ebitda_gives_infinite_leverage(simple):
    years = project(simple, Params(ebitda_adjustment=-25), debt0=10)
    assert math.isinf(years[0].leverage)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_lbo.py -v`
Expected: FAIL with `ImportError: cannot import name 'project'`.

- [ ] **Step 3: Implement the projection**

`acqlab/engine/lbo.py`:
```python
"""Annual LBO mechanics: projection, debt sizing, returns."""
import math

from acqlab.engine.model import Deal, Params, Year


def accepted_ebitda(deal: Deal, params: Params) -> float:
    return deal.company.reported_adj_ebitda + params.ebitda_adjustment


def project(deal: Deal, params: Params, debt0: float, downside: bool = False) -> list[Year]:
    c, f, p = deal.company, deal.financing, deal.policy
    margin = accepted_ebitda(deal, params) / c.revenue_ltm
    shock = 1.0
    if downside:
        margin += p.downside_margin_shock
        shock += p.downside_revenue_shock
    capex_pct = c.capex_pct + params.capex_adjustment_pct
    amort = f.amortization_pct * debt0
    debt, cash, prev_rev = debt0, 0.0, c.revenue_ltm
    years = []
    for t in range(1, p.hold_years + 1):
        rev = c.revenue_ltm * (1 + c.growth) ** t * (1 - params.revenue_haircut) * shock
        ebitda = rev * margin
        interest = f.interest_rate * debt
        taxes = max(0.0, c.tax_rate * (ebitda - c.da_pct * rev - interest))
        fcf = ebitda - rev * capex_pct - c.nwc_pct * (rev - prev_rev) - taxes - interest
        mandatory = min(amort, debt)
        sweep = min(max(0.0, fcf - mandatory) * f.cash_sweep, debt - mandatory)
        debt -= mandatory + sweep
        cash += fcf - mandatory - sweep
        net = debt - cash
        years.append(Year(revenue=rev, ebitda=ebitda, interest=interest, fcf=fcf, debt=debt,
                          cash=cash, net_debt=net, leverage=net / ebitda if ebitda > 0 else math.inf))
        prev_rev = rev
    return years
```

`acqlab/engine/__init__.py`:
```python
from acqlab.engine.lbo import project
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year

__all__ = ["Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year",
           "project"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/engine tests/engine/test_lbo.py
git commit -m "feat(engine): annual base and downside projection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Debt sizing

**Files:**
- Modify: `acqlab/engine/lbo.py` (append), `acqlab/engine/__init__.py`
- Test: `tests/engine/test_lbo.py` (append)

**Interfaces:**
- Consumes: `project`, `accepted_ebitda` from Task 2.
- Produces: `passes_covenants(deal, params, debt0: float) -> bool`; `acqlab.engine.covenant_safe_debt(deal, params, tol: float = 1e-6) -> float`; `uses(deal, params, price: float) -> float`; `acqlab.engine.size_debt(deal, params, price: float, safe_debt: float | None = None) -> float`.

- [ ] **Step 1: Write the failing tests**

Change the import at the top of `tests/engine/test_lbo.py` to:
```python
from acqlab.engine import Params, covenant_safe_debt, project, size_debt
from tests.conftest import make_simple
```

Append:
```python
def test_covenant_safe_debt_is_lender_cap_when_covenant_is_loose(simple):
    assert covenant_safe_debt(simple, Params()) == pytest.approx(80.0)


def test_covenant_safe_debt_binds_when_covenant_is_tight():
    # Downside yr1 leverage = (1.1D - 16.2) / 16.2 <= 4  ->  D <= 81 / 1.1
    assert covenant_safe_debt(make_simple(covenant=4.0), Params()) == pytest.approx(81 / 1.1, abs=1e-5)


def test_min_equity_caps_debt_at_low_prices(simple):
    # uses = 50 x 1.02 = 51; 60% of uses = 30.6 < lender cap 80
    assert size_debt(simple, Params(), price=50) == pytest.approx(30.6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_lbo.py -v`
Expected: FAIL with `ImportError: cannot import name 'covenant_safe_debt'`.

- [ ] **Step 3: Implement debt sizing**

Append to `acqlab/engine/lbo.py`:
```python


def passes_covenants(deal: Deal, params: Params, debt0: float) -> bool:
    down = project(deal, params, debt0, downside=True)
    return all(y.leverage <= cap for y, cap in zip(down, deal.financing.covenant_max_leverage))


def covenant_safe_debt(deal: Deal, params: Params, tol: float = 1e-6) -> float:
    """Largest opening debt whose downside case never breaches a covenant (bisection)."""
    hi = max(0.0, deal.financing.max_leverage * accepted_ebitda(deal, params))
    if passes_covenants(deal, params, hi):
        return hi
    if not passes_covenants(deal, params, 0.0):
        return 0.0
    lo = 0.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if passes_covenants(deal, params, mid) else (lo, mid)
    return lo


def uses(deal: Deal, params: Params, price: float) -> float:
    return price * (1 + deal.financing.fees_pct) + params.debt_like + params.nwc_adjustment


def size_debt(deal: Deal, params: Params, price: float, safe_debt: float | None = None) -> float:
    """Sponsor raises the most debt that the lender allows, the downside survives, and min equity permits."""
    if safe_debt is None:
        safe_debt = covenant_safe_debt(deal, params)
    lender_cap = max(0.0, deal.financing.max_leverage * accepted_ebitda(deal, params))
    equity_cap = (1 - deal.policy.min_equity_pct) * uses(deal, params, price)
    return min(lender_cap, safe_debt, equity_cap)
```

`acqlab/engine/__init__.py`:
```python
from acqlab.engine.lbo import covenant_safe_debt, project, size_debt
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year

__all__ = ["Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year",
           "covenant_safe_debt", "project", "size_debt"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/engine tests/engine/test_lbo.py
git commit -m "feat(engine): sponsor debt sizing with covenant-safe and min-equity caps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Returns and `evaluate`

**Files:**
- Modify: `acqlab/engine/lbo.py` (append; extend model import), `acqlab/engine/__init__.py`
- Test: `tests/engine/test_lbo.py` (append)

**Interfaces:**
- Consumes: `size_debt`, `uses`, `project` from Tasks 2–3.
- Produces: `returns(deal, params, price: float, safe_debt: float | None = None) -> tuple[float, float, float, float, list[Year]]` returning `(irr, moic, debt, equity, base_years)`; `acqlab.engine.evaluate(deal, params, price: float | None = None) -> Result` (price defaults to `deal.asking_price`).

- [ ] **Step 1: Write the failing tests**

Change the imports at the top of `tests/engine/test_lbo.py` to:
```python
from acqlab.engine import Params, covenant_safe_debt, evaluate, project, size_debt
from tests.conftest import FULL_PARAMS, make_simple
```

Append:
```python
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
        [5.5, 5.116646, 4.717406, 4.305496, 3.883822], abs=1e-5)
    assert r.covenant_headroom[0] == pytest.approx(0.0, abs=1e-5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_lbo.py -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate'`.

- [ ] **Step 3: Implement returns and evaluate**

In `acqlab/engine/lbo.py`, change the model import line to:
```python
from acqlab.engine.model import Deal, Params, Result, Year
```

Append:
```python


def returns(deal: Deal, params: Params, price: float,
            safe_debt: float | None = None) -> tuple[float, float, float, float, list[Year]]:
    """(irr, moic, debt, equity, base years). Single exit cash flow, so IRR is closed-form."""
    debt = size_debt(deal, params, price, safe_debt)
    equity = uses(deal, params, price) - debt
    base = project(deal, params, debt)
    exit_equity = deal.policy.exit_multiple * base[-1].ebitda - base[-1].net_debt
    moic = exit_equity / equity
    irr = moic ** (1 / deal.policy.hold_years) - 1 if moic > 0 else -1.0
    return irr, moic, debt, equity, base


def evaluate(deal: Deal, params: Params, price: float | None = None) -> Result:
    price = deal.asking_price if price is None else price
    irr, moic, debt, equity, base = returns(deal, params, price)
    down = project(deal, params, debt, downside=True)
    return Result(
        price=price, uses=uses(deal, params, price), debt=debt, equity=equity,
        exit_equity=moic * equity, irr=irr, moic=moic, base=base, downside=down,
        covenant_headroom=[cap - y.leverage for y, cap in zip(down, deal.financing.covenant_max_leverage)],
    )
```

`acqlab/engine/__init__.py`:
```python
from acqlab.engine.lbo import covenant_safe_debt, evaluate, project, size_debt
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year

__all__ = ["Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year",
           "covenant_safe_debt", "evaluate", "project", "size_debt"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/engine tests/engine/test_lbo.py
git commit -m "feat(engine): returns and evaluate with golden full-mechanics fixture

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Walk-away price and go/no-go

**Files:**
- Create: `acqlab/engine/walkaway.py`
- Modify: `acqlab/engine/__init__.py`
- Test: `tests/engine/test_walkaway.py`

**Interfaces:**
- Consumes: `returns`, `covenant_safe_debt` from Tasks 3–4.
- Produces: `acqlab.engine.walkaway.PRICE_FLOOR: float = 0.01`; `acqlab.engine.walk_away(deal, params, tol: float = 1e-4) -> float`; `acqlab.engine.is_go(deal, params) -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/engine/test_walkaway.py`:
```python
import pytest

from acqlab.engine import Params, is_go, walk_away
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_walkaway.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_go'`.

- [ ] **Step 3: Implement walk-away**

`acqlab/engine/walkaway.py`:
```python
"""Walk-away price, go/no-go, and single-parameter flip thresholds."""
from acqlab.engine.lbo import covenant_safe_debt, returns
from acqlab.engine.model import Deal, Params

PRICE_FLOOR = 0.01  # $M; walk-away never reported below this


def walk_away(deal: Deal, params: Params, tol: float = 1e-4) -> float:
    """Max price with base-case IRR >= hurdle. IRR falls as price rises, so bisect."""
    safe = covenant_safe_debt(deal, params)  # independent of price: compute once
    hurdle = deal.policy.irr_hurdle

    def clears(price: float) -> bool:
        return returns(deal, params, price, safe)[0] >= hurdle

    if not clears(PRICE_FLOOR):
        return PRICE_FLOOR
    lo, hi = PRICE_FLOOR, 2 * PRICE_FLOOR
    while clears(hi):
        lo, hi = hi, hi * 2
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if clears(mid) else (lo, mid)
    return lo


def is_go(deal: Deal, params: Params) -> bool:
    return deal.asking_price <= walk_away(deal, params)
```

`acqlab/engine/__init__.py`:
```python
from acqlab.engine.lbo import covenant_safe_debt, evaluate, project, size_debt
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year
from acqlab.engine.walkaway import is_go, walk_away

__all__ = ["Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year",
           "covenant_safe_debt", "evaluate", "is_go", "project", "size_debt", "walk_away"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/engine tests/engine/test_walkaway.py
git commit -m "feat(engine): walk-away price by bisection and go/no-go

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Flip threshold

**Files:**
- Modify: `acqlab/engine/walkaway.py` (append), `acqlab/engine/__init__.py`
- Test: `tests/engine/test_walkaway.py` (append)

**Interfaces:**
- Consumes: `is_go` from Task 5.
- Produces: `acqlab.engine.flip_threshold(deal, params, name: str, lo: float, hi: float, tol: float = 1e-6) -> float | None`. Used later to write Investigator intent briefs ("decision flips if accepted EBITDA < $X").

- [ ] **Step 1: Write the failing tests**

Change the import at the top of `tests/engine/test_walkaway.py` to:
```python
from acqlab.engine import Params, flip_threshold, is_go, walk_away
```

Append:
```python
def test_flip_threshold_finds_where_the_decision_changes(simple):
    deal = simple.model_copy(update={"asking_price": 120})  # go at face value
    v = flip_threshold(deal, Params(), "debt_like", 0, 50)
    assert v is not None
    assert is_go(deal, Params(debt_like=v - 1e-3))
    assert not is_go(deal, Params(debt_like=v + 1e-3))


def test_flip_threshold_is_none_when_decision_never_changes(simple):
    assert flip_threshold(simple, Params(), "debt_like", 0, 5) is None  # already no-go, more debt-like keeps it no-go
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_walkaway.py -v`
Expected: FAIL with `ImportError: cannot import name 'flip_threshold'`.

- [ ] **Step 3: Implement flip threshold**

Append to `acqlab/engine/walkaway.py`:
```python


def flip_threshold(deal: Deal, params: Params, name: str, lo: float, hi: float,
                   tol: float = 1e-6) -> float | None:
    """Value of one parameter in [lo, hi] where go/no-go flips, others held fixed. None if it never flips."""
    def go_at(v: float) -> bool:
        return is_go(deal, params.model_copy(update={name: v}))

    go_lo, go_hi = go_at(lo), go_at(hi)
    if go_lo == go_hi:
        return None
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if go_at(mid) == go_lo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
```

`acqlab/engine/__init__.py`:
```python
from acqlab.engine.lbo import covenant_safe_debt, evaluate, project, size_debt
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year
from acqlab.engine.walkaway import flip_threshold, is_go, walk_away

__all__ = ["Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year",
           "covenant_safe_debt", "evaluate", "flip_threshold", "is_go", "project", "size_debt",
           "walk_away"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine -v`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/engine tests/engine/test_walkaway.py
git commit -m "feat(engine): single-parameter decision flip threshold

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Walk-away distribution under beliefs

**Files:**
- Create: `acqlab/engine/beliefs.py`
- Modify: `acqlab/engine/__init__.py`
- Test: `tests/engine/test_beliefs.py`

**Interfaces:**
- Consumes: `walk_away` (Task 5), `PARAM_NAMES` (Task 1).
- Produces: `acqlab.engine.Beliefs = dict[str, tuple[float, float]]` (param → uniform (low, high)); `acqlab.engine.beliefs.sample_params(base: Params, beliefs: Beliefs, n: int, rng: np.random.Generator) -> list[Params]`; `acqlab.engine.evaluate_under(deal, base: Params, beliefs: Beliefs, n: int = 200, seed: int = 0) -> np.ndarray`. The routers (Plan 3) are built on these.

- [ ] **Step 1: Write the failing tests**

`tests/engine/test_beliefs.py`:
```python
import numpy as np
import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_beliefs.py -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_under'`.

- [ ] **Step 3: Implement beliefs**

`acqlab/engine/beliefs.py`:
```python
"""Walk-away distribution under uncertain parameters."""
import numpy as np

from acqlab.engine.model import PARAM_NAMES, Deal, Params
from acqlab.engine.walkaway import walk_away

Beliefs = dict[str, tuple[float, float]]  # param name -> (low, high), sampled uniformly


def sample_params(base: Params, beliefs: Beliefs, n: int, rng: np.random.Generator) -> list[Params]:
    unknown = set(beliefs) - set(PARAM_NAMES)
    if unknown:
        raise ValueError(f"unknown parameters: {sorted(unknown)}")
    draws = {k: rng.uniform(lo, hi, n) for k, (lo, hi) in beliefs.items()}
    return [base.model_copy(update={k: float(v[i]) for k, v in draws.items()}) for i in range(n)]


def evaluate_under(deal: Deal, base: Params, beliefs: Beliefs, n: int = 200, seed: int = 0) -> np.ndarray:
    """Monte Carlo walk-away prices. Params not in beliefs stay at their base value."""
    rng = np.random.default_rng(seed)
    return np.array([walk_away(deal, p) for p in sample_params(base, beliefs, n, rng)])
```

`acqlab/engine/__init__.py` (final form):
```python
from acqlab.engine.beliefs import Beliefs, evaluate_under
from acqlab.engine.lbo import covenant_safe_debt, evaluate, project, size_debt
from acqlab.engine.model import PARAM_NAMES, Company, Deal, Financing, Params, Policy, Result, Year
from acqlab.engine.walkaway import flip_threshold, is_go, walk_away

__all__ = ["Beliefs", "Company", "Deal", "Financing", "PARAM_NAMES", "Params", "Policy", "Result", "Year",
           "covenant_safe_debt", "evaluate", "evaluate_under", "flip_threshold", "is_go", "project",
           "size_debt", "walk_away"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine -v`
Expected: 21 passed. (Performance reference: 200 samples on the full fixture ≈ 0.2 s.)

- [ ] **Step 5: Commit**

```bash
git add acqlab/engine tests/engine/test_beliefs.py
git commit -m "feat(engine): Monte Carlo walk-away distribution under beliefs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Property tests

**Files:**
- Test: `tests/engine/test_properties.py`

**Interfaces:**
- Consumes: `walk_away`, `Params` (engine); `make_full` (conftest).
- Produces: the monotonicity guarantees the router and generator plans rely on.

- [ ] **Step 1: Write the property tests**

`tests/engine/test_properties.py`:
```python
"""Invariants the rest of the project relies on. Hypothesis searches for counterexamples."""
from hypothesis import given, settings
from hypothesis import strategies as st

from acqlab.engine import Params, walk_away
from tests.conftest import make_full

DEAL = make_full()
TOL = 1e-3  # bisection tolerance on walk-away

params = st.builds(
    Params,
    ebitda_adjustment=st.floats(-8, 4),
    debt_like=st.floats(0, 20),
    revenue_haircut=st.floats(0, 0.2),
    nwc_adjustment=st.floats(0, 10),
    capex_adjustment_pct=st.floats(0, 0.02),
)


@settings(max_examples=40, deadline=None)
@given(p=params, worse=st.floats(0.1, 5))
def test_worse_ebitda_never_raises_walk_away(p, worse):
    worse_p = p.model_copy(update={"ebitda_adjustment": p.ebitda_adjustment - worse})
    assert walk_away(DEAL, worse_p) <= walk_away(DEAL, p) + TOL


@settings(max_examples=40, deadline=None)
@given(p=params, extra=st.floats(0.5, 10))
def test_more_debt_like_items_lower_walk_away(p, extra):
    more = p.model_copy(update={"debt_like": p.debt_like + extra})
    assert walk_away(DEAL, more) < walk_away(DEAL, p)


@settings(max_examples=40, deadline=None)
@given(p=params, bump=st.floats(0.01, 0.1))
def test_higher_hurdle_never_raises_walk_away(p, bump):
    stricter = DEAL.model_copy(update={"policy": DEAL.policy.model_copy(
        update={"irr_hurdle": DEAL.policy.irr_hurdle + bump})})
    assert walk_away(stricter, p) <= walk_away(DEAL, p) + TOL
```

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/engine/test_properties.py -v`
Expected: 3 passed. These test existing code, so they should pass immediately; if Hypothesis finds a counterexample, that is an engine bug — stop and use superpowers:systematic-debugging rather than loosening the property.

- [ ] **Step 3: Run the whole suite**

Run: `uv run pytest -q`
Expected: 24 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/engine/test_properties.py
git commit -m "test(engine): monotonicity properties for walk-away

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Spreadsheet cross-check (manual, required by spec §1)

The spec requires a hand-built spreadsheet LBO for 3 deals that matches the engine to the dollar. The test goldens above came from an independent straight-line script; this task gets a human-built check in Excel/Numbers/Sheets.

**Files:**
- Create: `docs/verification/engine-spreadsheet-check.xlsx` (built by hand)
- Create: `docs/verification/engine-spreadsheet-check.md`

- [ ] **Step 1: Build the three deals in a spreadsheet using only the "Engine definitions" section above**

Deals: `make_simple()`, `make_simple(covenant=4.0)`, `make_full()` with `FULL_PARAMS`. For the covenant-safe debt, use Goal Seek on opening debt so the max downside leverage equals the covenant.

- [ ] **Step 2: Compare against these engine values**

| Deal | Debt | Equity | Exit equity | IRR | Walk-away |
|---|---|---|---|---|---|
| simple | 80.0000 | 73.0000 | 140.0000 | 13.9098% | 133.591 |
| simple, covenant 4.0 | 73.6364 (= 81/1.1) | — | — | — | — |
| full + FULL_PARAMS | 123.2276 | 118.3724 | 191.2004 | 10.0646% | 187.295 |

Full-fixture base years (for line-by-line checking). The downside case draws the revolver from year 2, so its leverage includes revolver interest; the base case never draws it:

| Year | Revenue | EBITDA | Interest | FCF | Debt | Cash | Net debt | Downside leverage |
|---|---|---|---|---|---|---|---|---|
| 1 | 199.5000 | 27.9300 | 11.0905 | 6.9440 | 116.6749 | 0.3913 | 116.2836 | 5.5000 |
| 2 | 209.4750 | 29.3265 | 10.5007 | 7.0994 | 110.0445 | 0.8603 | 109.1841 | 5.1209 |
| 3 | 219.9488 | 30.7928 | 9.9040 | 8.2957 | 102.8159 | 1.9275 | 100.8884 | 4.7355 |
| 4 | 230.9462 | 32.3325 | 9.2534 | 9.5698 | 94.9503 | 3.6317 | 91.3186 | 4.3437 |
| 5 | 242.4935 | 33.9491 | 8.5455 | 10.9263 | 86.4065 | 6.0142 | 80.3924 | 3.9454 |

- [ ] **Step 3: Record the result**

Write `docs/verification/engine-spreadsheet-check.md` noting, per deal, match / mismatch and the largest difference. Any mismatch > $0.001M is an engine or definition bug: fix the engine with a new failing test first (superpowers:test-driven-development), never adjust the goldens to match.

- [ ] **Step 4: Commit**

```bash
git add docs/verification
git commit -m "docs: spreadsheet cross-check of LBO engine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Post-review changes (2026-09-23)

Review after implementation added: revolver interest (definitions above; the Task 4 golden downside leverage is now `[5.5, 5.120933, 4.735547, 4.343739, 3.945400]`, everything else unchanged); `Result.debt_caps`, `Result.debt_limit` and `Result.bridge` (`EquityBridge`); input models reject unknown fields and NaN/inf; property tests run over random deals (revenue-haircut monotonicity only on the full fixture, see spec §1). Suite: 48 tests.

## Done when

- `uv run pytest -q` → 48 passed.
- Spreadsheet check recorded with all three deals matching.
- `from acqlab.engine import evaluate, walk_away, is_go, flip_threshold, evaluate_under` works; nothing under `acqlab/engine` imports an LLM library.

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

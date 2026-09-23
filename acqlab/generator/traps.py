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

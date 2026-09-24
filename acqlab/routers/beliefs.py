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

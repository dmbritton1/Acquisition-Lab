"""The board math: the checked numbers, the firm's settings, the price and the priced worries become the engine's
call, walk-away spread, flip sizes, pairs that flip together and the ask-the-seller ranking. One simulation per
recompute, so it can follow a slider."""
import math

import numpy as np

from acqlab.agents.knowledge import DILIGENCE_MAP
from acqlab.agents.record import N_WORLDS, Face, Record
from acqlab.engine import Company, Deal, Financing, Policy
from acqlab.generator.sample import Teaser
from acqlab.generator.traps import TRAPS
from acqlab.routers.beliefs import Issue
from acqlab.routers.routers import decide, score_regret

DOC_NAMES = {"qoe": "Quality of earnings report", "audited": "Audited accounts and notes", "cim": "CIM",
             "legal": "Legal letter", "contract": "Customer contracts", "assets": "Fixed asset schedule"}
BINS = 20


def face(numbers: dict[str, float], settings: dict, price: float, name: str, industry: str) -> Face:
    """The deal at face value from plain values (steps.values). Pydantic errors propagate as ValueError."""
    n = numbers
    teaser = Teaser(name=name, industry=industry, asking_price=price,
                    **{k: n[k] for k in ("revenue_ltm", "reported_ebitda", "claimed_addbacks", "adj_ebitda", "growth",
                                         "capex_pct", "nwc_pct")})
    company = Company(reported_adj_ebitda=n["adj_ebitda"],
                      **{k: n[k] for k in ("revenue_ltm", "growth", "capex_pct", "nwc_pct", "da_pct", "tax_rate")})
    return Face(teaser, Deal(company=company, financing=Financing(**settings["financing"]),
                             policy=Policy(**settings["policy"]), asking_price=price))


class BoardRecord(Record):
    """A Record of the priced worries. A worry in `yours` is priced at the size the analyst set, not floored at the
    usual range."""

    def __init__(self, face: Face, worries: dict[str, dict], yours: set[str]):
        super().__init__(face)
        self.yours = yours
        self.plan([{"type": t, "name": w.get("reason", ""), "chance": w["chance"], "low": w["low"],
                    "high": w["high"], "docs": []} for t, w in worries.items() if "not_priced" not in w])

    def issue(self, t: str) -> Issue:
        e = self.entries[t]
        if t in self.yours and e.open:
            return Issue(p_real=e.chance, hi=e.high)
        return super().issue(t)

    def size_limit(self, t: str) -> float:
        return self.entries[t].high if t in self.yours else super().size_limit(t)


def apply(worries: dict, overrides: dict[str, dict]) -> tuple[dict, set[str]]:
    """The worries with the analyst's chance and size set (low 0), and which types are theirs. Raises ValueError for
    an unknown type or a chance outside 0..1 or a size below 0."""
    out = dict(worries)
    for t, o in overrides.items():
        chance, high = o["chance"], o["high"]
        if t not in TRAPS or not (math.isfinite(chance) and math.isfinite(high) and 0 <= chance <= 1 and 0 <= high):
            raise ValueError(f"impossible override for {t}: {o}")
        out[t] = {**out.get(t, {}), "chance": float(chance), "low": 0.0, "high": float(high)}
        out[t].pop("not_priced", None)
    return out, set(overrides)


def compute(face: Face, worries: dict, yours: set[str]) -> dict:
    """The board at these worries: the call, walk-away spread, flip sizes, pairs and the ask ranking."""
    rec = BoardRecord(face, worries, yours)
    values, w = rec.worlds()
    price = face.deal.asking_price
    go, walk = decide(w, price)
    counts, edges = np.histogram(w, bins=BINS)
    open_ = [t for t, e in rec.entries.items() if e.open and e.chance > 0]
    score = score_regret(values, w, price, {t: 1.0 for t in open_}, open_) if open_ else {}
    return {"go": go, "walk_away": walk, "p10": float(np.percentile(w, 10)), "p90": float(np.percentile(w, 90)),
            "clears": float((w > price).mean()), "hist": {"edges": edges.tolist(), "counts": counts.tolist()},
            "flips": {t: rec.flip_amount(t) for t, e in rec.entries.items() if e.proposed},
            "pairs": [list(p) for p in rec.flagged_pairs()],
            "ask": [{"type": t, "value": float(v), "docs": [DOC_NAMES[k] for k in DILIGENCE_MAP[t]]}
                    for t, v in sorted(score.items(), key=lambda kv: -kv[1])],
            "price": float(price)}

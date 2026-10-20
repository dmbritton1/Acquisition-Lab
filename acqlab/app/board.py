"""The board math: the checked numbers, the firm's settings, the price and the priced worries become the engine's
call, walk-away spread, flip sizes, pairs that flip together and the ask-the-seller ranking. One simulation per
recompute, so it can follow a slider."""
import math

import numpy as np

from acqlab.agents.knowledge import DILIGENCE_MAP
from acqlab.agents.record import Face, Record
from acqlab.engine import Company, Deal, Financing, Policy
from acqlab.generator.sample import Teaser
from acqlab.generator.traps import TRAPS
from acqlab.routers.beliefs import Issue
from acqlab.routers.routers import decide, score_regret

# the documents that settle a worry; the CIM never does (it is the seller's own, and the analyst already has it)
DOC_NAMES = {"qoe": "Quality of earnings report", "audited": "Audited accounts and notes", "legal": "Legal letter",
             "contract": "Customer contracts", "assets": "Fixed asset schedule"}
BINS = 20
NUMBER_FIELDS = ("revenue_ltm", "reported_ebitda", "claimed_addbacks", "adj_ebitda", "growth", "capex_pct", "nwc_pct",
                 "da_pct", "tax_rate")


def _ok(x) -> bool:
    """A finite number (not a bool)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def face(numbers: dict[str, float], settings: dict, price: float, name: str, industry: str) -> Face:
    """The deal at face value from plain values (steps.values). Raises ValueError for a bad price, a missing,
    non-numeric or impossible field, or a bad setting."""
    n = numbers
    if bad := [k for k in NUMBER_FIELDS if not _ok(n.get(k))]:
        raise ValueError("missing or not a number: " + ", ".join(bad))
    bad = [f"{k} must be above 0" for k in ("revenue_ltm", "adj_ebitda") if n[k] <= 0]
    bad += ["growth must be between -100% and 100%"] if not -1 <= n["growth"] <= 1 else []
    bad += [f"{k} must be between 0% and 100%" for k in ("tax_rate", "capex_pct", "nwc_pct", "da_pct") if not 0 <= n[k] <= 1]
    if bad:
        raise ValueError("; ".join(bad))
    if not (_ok(price) and price > 0):
        raise ValueError(f"the price must be a number above 0, not {price!r}")
    if not isinstance(settings, dict) or not all(isinstance(settings.get(g), dict) for g in ("financing", "policy")):
        raise ValueError("settings need financing and policy")
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
        for t, w in worries.items():
            if t not in TRAPS or not isinstance(w, dict) or not ("not_priced" in w or all(_ok(w.get(k)) for k in
                                                                                    ("chance", "low", "high"))):
                raise ValueError(f"not a priced worry: {t}")
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
        chance, high = (o.get("chance"), o.get("high")) if isinstance(o, dict) else (None, None)
        if t not in TRAPS or not (_ok(chance) and _ok(high) and 0 <= chance <= 1 and 0 <= high):
            raise ValueError(f"impossible override for {t}: {o}")
        out[t] = {**out.get(t, {}), "chance": float(chance), "low": 0.0, "high": float(high)}
        out[t].pop("not_priced", None)
    return out, set(overrides)


def compute(face: Face, worries: dict, yours: set[str]) -> dict:
    """The board at these worries: the call, walk-away spread, flip sizes, pairs, the ask ranking, and each worry's
    priced size (an Opus size below the usual range is priced at it: "floored")."""
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
            "ask": [{"type": t, "value": float(v), "docs": [DOC_NAMES[k] for k in DILIGENCE_MAP[t] if k in DOC_NAMES]}
                    for t, v in sorted(score.items(), key=lambda kv: -kv[1])],
            "sizes": {t: {"size": rec.size_limit(t), "floored": e.proposed and rec.size_limit(t) > e.high}
                      for t, e in rec.entries.items()},
            "price": float(price)}

"""Generate one deal's answer key: visible teaser, hidden facts with roles, and engine ground truth."""
import numpy as np
from pydantic import BaseModel

from acqlab.engine import Deal, Params, evaluate, is_go, walk_away
from acqlab.generator.roles import (DECOY_MOVE, FLAG_ROLES, LOOK, MARGIN, PULL_BACK, RELIEF_FLOOR, flip_severity,
                                    min_severity_to_move, place)
from acqlab.generator.sample import BaseDeal, sample_base, with_asking
from acqlab.generator.traps import PARAM, TRAPS, params_for, sample_variant, trap_weight, worst_amount

GENERATOR_VERSION = "4.1.0"  # 4.1.0: flagged deals (upside spec); r2 deals generate as before
ASK_NOISE = (-0.15, 0.10)  # asking = market EV x (1 + N(mean, sd)); a 20% hurdle rarely clears at market prices
CASE_MIX = {"clean": 0.15, "flip": 0.25, "interaction": 0.10, "none": 0.50}
FACE_GO = 0.97  # P(face-value go) for clean and no-flip deals; flip deals are always face-value go
PRIOR_CLEAN = 0.70  # generator prior: share of facts that are clean (roughly the realized mix)
OTHER_ROLES = {"decoy": 0.25, "unresolvable": 0.06, "clean": 0.69}  # roles for the remaining facts


def _role_blind(weights: dict[str, float]) -> dict[str, dict[str, float]]:
    """Placement weights (mode -> weight) for every role alike, so where a sentence sits says nothing about whether it
    is a real problem (Plan 4b: search is back, and it would see a role-dependent placement). An unresolvable fact
    states its range in the same places, except a calculation."""
    return {r: weights for r in ("flipper", "interaction", "decoy", "clean", *FLAG_ROLES)} | {
        "unresolvable": {k: w for k, w in weights.items() if k != "calculation"}}


PLACEMENT = _role_blind({"explicit": 2, "footnote": 2, "calculation": 2, "contradicted": 1})
# Reframe design §4: the difficulty levers, pulled in this order by calibration (base, then r1, r2, r3). Fixed before
# any calibration run.
# - r1: two-issue interaction deals 2.5x as common; flip + interaction stays at 35% so the go rate stays near half.
# - r2: evidence more buried: less explicit, more contradicted, and the board minutes as a place.
# - r3: a tighter budget.
# clean_item_power shapes a clean add-back's line item to match trap sizes under that case mix (render).
_MULTI_ISSUE = {"clean": 0.15, "flip": 0.10, "interaction": 0.25, "none": 0.50}
_BURIED = _role_blind({"explicit": 1, "footnote": 2, "calculation": 2, "contradicted": 2, "minutes": 2})
PROFILES = {
    "base": {"case_mix": CASE_MIX, "placement": PLACEMENT, "budget_share": 0.25, "clean_item_power": 0.7},
    "r1": {"case_mix": _MULTI_ISSUE, "placement": PLACEMENT, "budget_share": 0.25, "clean_item_power": 1.0},
    "r2": {"case_mix": _MULTI_ISSUE, "placement": _BURIED, "budget_share": 0.25, "clean_item_power": 1.0},
}
PROFILES["r3"] = PROFILES["r2"] | {"budget_share": 0.20}
# Upside spec §1.3: r2 plus fixed shares of flagged deals, assigned by batch.cases_for; the rest draw from r2's mix.
PROFILES["r2u"] = PROFILES["r2"] | {"quota": {"relief": 0.4, "confirmed": 0.2}}


class Flag(BaseModel):
    """The teaser's seller disclosure (upside spec §1.1): one issue type and its stated upper bound."""
    trap: str
    bound: float  # $M: the trap's worst case


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
    profile: str = "base"  # difficulty profile (PROFILES); deals before generator 4.0.0 are "base"
    flag: Flag | None = None  # relief and confirmed deals only (upside spec)

    @property
    def deal(self) -> Deal:
        return self.base.deal

    def params(self) -> Params:
        return params_for({f.trap: f.amount for f in self.facts}, self.base)


def case_type(roles: list[str]) -> str:
    for role, case in (("relief", "relief"), ("confirmed", "confirmed"), ("flipper", "flip"), ("interaction", "interaction"), ("unresolvable", "unresolvable"),
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
    if case in FLAG_ROLES:  # upside spec §1.2: the deal fails at half the bound, with room for the role's amount
        can_flag = [t for t in TRAPS if alone[t] is not None and alone[t] < LOOK - PULL_BACK
                    and (case == "confirmed" or alone[t] - MARGIN >= RELIEF_FLOOR)]
        if not can_flag:
            return None
        roles[_pick(rng, {t: trap_weight(t, b) for t in can_flag})] = case
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


def prior_draws(rng: np.random.Generator, n: int, k: int) -> np.ndarray:
    """Severity draws from the prior: 0 with probability PRIOR_CLEAN, else uniform on (0, 1)."""
    return rng.uniform(0.0, 1.0, (n, k)) * (rng.random((n, k)) >= PRIOR_CLEAN)


def simulate(b: BaseDeal, worst: dict[str, float], n: int, rng: np.random.Generator):
    """n prior draws (one column per fact) and the regret of going / not going in each."""
    traps = list(worst)
    draws = prior_draws(rng, n, len(traps))
    w = np.array([walk_away(b.deal, params_for({t: d * worst[t] for t, d in zip(traps, row)}, b))
                  for row in draws])
    ask = b.deal.asking_price
    return draws, np.maximum(0.0, ask - w), np.maximum(0.0, w - ask)


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


def _decision_values(b: BaseDeal, worst: dict[str, float], n: int, rng: np.random.Generator) -> dict[str, float]:
    return dict(zip(worst, value_of_knowing(*simulate(b, worst, n, rng))))


def generate(deal_id: str, split: str, seed: int, *, mc: int = 400, force_case: str | None = None,
             max_tries: int = 500, profile: str = "base") -> DealTruth:
    rng = np.random.default_rng(seed)
    dev = split == "dev"
    prof = PROFILES[profile]
    case = force_case or _pick(rng, prof["case_mix"])  # drawn once, so hard cases aren't swapped for easy ones on retry
    for _ in range(max_tries):
        b = sample_base(rng)
        want_go = case in ("flip", "interaction", *FLAG_ROLES) or rng.random() < FACE_GO
        ask = b.deal.asking_price * (1 + rng.normal(*ASK_NOISE))
        b = with_asking(b, ask)
        if is_go(b.deal, Params()) != want_go:
            continue
        roles = _plan(rng, b, case)
        placed = roles and place(b, roles, rng)
        if not placed:
            continue
        facts = _facts(rng, b, roles, placed, dev, prof["placement"])
        truth = _finish(deal_id, split, seed, rng, b, facts, mc, profile)
        if truth is not None:
            return truth
    raise RuntimeError(f"could not generate {deal_id} (seed {seed}) in {max_tries} tries")


def _facts(rng, b: BaseDeal, roles: dict[str, str], placed: dict[str, dict], dev: bool,
           placement: dict[str, dict[str, float]]) -> list[Fact]:
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
                          placement=_pick(rng, placement[roles[t]]), worst=worst, amount=amount,
                          documented=doc_range, realized=realized, alone_flips=False))
    return facts


def _finish(deal_id, split, seed, rng, b: BaseDeal, facts: list[Fact], mc: int, profile: str) -> DealTruth | None:
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
    if any(f.role == "relief" for f in facts) and not go_ or any(f.role == "confirmed" for f in facts) and go_:
        return None  # upside spec §1.2: a relief deal is truly GO, a confirmed one truly NO-GO
    explained = any(f.role in ("flipper", "interaction", "confirmed") or (f.role == "unresolvable" and f.alone_flips)
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
                     case_type=case_type([f.role for f in facts]), profile=profile,
                     flag=next((Flag(trap=f.trap, bound=f.worst) for f in facts if f.role in FLAG_ROLES), None))

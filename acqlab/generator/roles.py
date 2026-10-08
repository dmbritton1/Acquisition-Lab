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
LOOK = 0.5  # upside spec §1.2: a flagged worry priced at half its stated bound already fails, by PULL_BACK
RELIEF_FLOOR = 0.05  # a relief amount is never 0: zero renders as "no such issue", contradicting the teaser
FLAG_ROLES = ("relief", "confirmed")  # the flagged issue's roles: the teaser states its bound (upside spec §1.1)


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
        elif role in FLAG_ROLES:
            if t is None or t >= LOOK - PULL_BACK:
                return None
            lo, hi = (RELIEF_FLOOR, t - MARGIN) if role == "relief" else (t + MARGIN, 1.0)
            if lo > hi:
                return None
            out[trap] = {"severity": float(rng.uniform(lo, hi)), "documented": None}
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

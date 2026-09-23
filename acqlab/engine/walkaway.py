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
    return returns(deal, params, deal.asking_price)[0] >= deal.policy.irr_hurdle


def flip_threshold(deal: Deal, params: Params, name: str, lo: float, hi: float,
                   tol: float = 1e-6) -> float | None:
    """Value of one parameter in [lo, hi] where go/no-go flips, others held fixed. None if it never flips."""
    def go_at(v: float) -> bool:
        return is_go(deal, Params.model_validate({**params.model_dump(), name: v}))

    lo, hi = min(lo, hi), max(lo, hi)  # bounds may come in either order (e.g. a negative EBITDA range)
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

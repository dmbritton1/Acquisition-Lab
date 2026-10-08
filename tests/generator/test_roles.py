import numpy as np
import pytest

from acqlab.engine import walk_away
from acqlab.generator.roles import (DECOY_MOVE, LOOK, MARGIN, PULL_BACK, RELIEF_FLOOR, UNRESOLVED_WIDTH, amounts,
                                    flip_severity, go, place)
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


def flaggable_deals(n: int):
    """Face-value go deals whose add-back flip point leaves room for both flagged roles (upside spec §1.2)."""
    rng, found = np.random.default_rng(1), []
    while len(found) < n:
        b = sample_base(rng)
        b = with_asking(b, 0.75 * b.deal.asking_price)
        t = flip_severity(b, "addback")
        if go(b, {}) and t is not None and RELIEF_FLOOR + MARGIN <= t < LOOK - PULL_BACK:
            found.append(b)
    return found, rng


def test_relief_fails_at_half_the_bound_but_its_real_amount_is_small_and_never_zero():
    deals, rng = flaggable_deals(5)
    for b in deals:
        s = place(b, {"addback": "relief"}, rng)["addback"]["severity"]
        t = flip_severity(b, "addback")
        assert not go(b, {"addback": LOOK - PULL_BACK})  # priced at half its bound, by the margin, it fails
        assert RELIEF_FLOOR <= s <= t - MARGIN and go(b, {"addback": s})


def test_confirmed_fails_at_half_the_bound_and_its_real_amount_clears_the_flip_point():
    deals, rng = flaggable_deals(5)
    for b in deals:
        s = place(b, {"addback": "confirmed"}, rng)["addback"]["severity"]
        assert not go(b, {"addback": LOOK - PULL_BACK})
        assert s >= flip_severity(b, "addback") + MARGIN and not go(b, {"addback": s})


def test_flagged_roles_are_refused_when_half_the_bound_would_not_fail():
    deals, rng = face_go_deals(20)
    late = [b for b in deals if flip_severity(b, "addback") >= LOOK - PULL_BACK]
    assert late
    for b in late:
        assert place(b, {"addback": "relief"}, rng) is None and place(b, {"addback": "confirmed"}, rng) is None

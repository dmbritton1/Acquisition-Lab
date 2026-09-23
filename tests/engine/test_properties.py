"""Invariants the rest of the project relies on. Hypothesis searches for counterexamples
across random mid-market deals, not just one fixture, since the generator will sample widely."""
import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from acqlab.engine import Company, Deal, Financing, Params, Policy, covenant_safe_debt, is_go, walk_away
from acqlab.engine.lbo import passes_covenants, returns
from acqlab.engine.walkaway import PRICE_FLOOR
from tests.conftest import make_full

TOL = 1e-3  # bisection tolerance on walk-away


@st.composite
def cases(draw) -> tuple[Deal, Params]:
    rev, margin = draw(st.floats(50, 500)), draw(st.floats(0.08, 0.30))
    cov, step = draw(st.floats(4.0, 7.0)), draw(st.floats(0, 0.5))
    deal = Deal(
        company=Company(revenue_ltm=rev, reported_adj_ebitda=rev * margin, growth=draw(st.floats(-0.05, 0.15)),
                        capex_pct=draw(st.floats(0.01, 0.08)), nwc_pct=draw(st.floats(0, 0.25)),
                        da_pct=draw(st.floats(0.01, 0.05)), tax_rate=draw(st.floats(0.21, 0.30))),
        financing=Financing(max_leverage=draw(st.floats(3, 6.5)), interest_rate=draw(st.floats(0.06, 0.12)),
                            amortization_pct=draw(st.floats(0, 0.10)), cash_sweep=draw(st.floats(0, 0.75)),
                            covenant_max_leverage=[max(2.0, cov - step * i) for i in range(5)],
                            fees_pct=draw(st.floats(0.01, 0.04))),
        policy=Policy(exit_multiple=draw(st.floats(6, 12)), irr_hurdle=draw(st.floats(0.15, 0.25))),
        asking_price=rev * margin * draw(st.floats(6, 12)),
    )
    params = Params(ebitda_adjustment=rev * margin * draw(st.floats(-0.3, 0.1)), debt_like=draw(st.floats(0, 20)),
                    revenue_haircut=draw(st.floats(0, 0.3)), nwc_adjustment=draw(st.floats(0, 10)),
                    capex_adjustment_pct=draw(st.floats(-0.01, 0.03)))
    return deal, params


def worse(p: Params, name: str, delta: float) -> Params:
    return p.model_copy(update={name: getattr(p, name) + delta})


@settings(max_examples=40, deadline=None)
@given(c=cases())
def test_irr_falls_as_price_rises(c):
    """Walk-away bisects on price, so this must hold."""
    deal, p = c
    safe = covenant_safe_debt(deal, p)
    irrs = [returns(deal, p, x, safe)[0] for x in np.linspace(1, 3 * deal.asking_price, 50)]
    assert all(b <= a for a, b in zip(irrs, irrs[1:]))


@settings(max_examples=40, deadline=None)
@given(c=cases())
def test_more_debt_never_eases_covenants(c):
    """Covenant-safe debt bisects on opening debt, so this must hold."""
    deal, p = c
    ok = [passes_covenants(deal, p, x) for x in np.linspace(0, 6.5 * deal.company.reported_adj_ebitda, 50)]
    assert ok == sorted(ok, reverse=True)


@settings(max_examples=40, deadline=None)
@given(c=cases())
def test_is_go_agrees_with_walk_away(c):
    deal, p = c
    w = walk_away(deal, p)
    for ask in (w - TOL, w + TOL):
        if ask > PRICE_FLOOR:
            assert is_go(deal.model_copy(update={"asking_price": ask}), p) == (ask <= w)


@settings(max_examples=40, deadline=None)
@given(c=cases(), frac=st.floats(0.01, 0.2))
def test_worse_ebitda_never_raises_walk_away(c, frac):
    deal, p = c
    assert walk_away(deal, worse(p, "ebitda_adjustment", -frac * deal.company.reported_adj_ebitda)) \
        <= walk_away(deal, p) + TOL


@settings(max_examples=40, deadline=None)
@given(c=cases(), extra=st.floats(0.5, 10))
def test_more_debt_like_items_lower_walk_away(c, extra):
    deal, p = c
    more, base = walk_away(deal, worse(p, "debt_like", extra)), walk_away(deal, p)
    assert more < base or more == base == PRICE_FLOOR


@settings(max_examples=40, deadline=None)
@given(c=cases(), bump=st.floats(0.01, 0.1))
def test_higher_hurdle_never_raises_walk_away(c, bump):
    deal, p = c
    stricter = deal.model_copy(update={"policy": deal.policy.model_copy(
        update={"irr_hurdle": deal.policy.irr_hurdle + bump})})
    assert walk_away(stricter, p) <= walk_away(deal, p) + TOL


@settings(max_examples=40, deadline=None)
@given(p=st.builds(Params, ebitda_adjustment=st.floats(-8, 4), debt_like=st.floats(0, 20),
                   revenue_haircut=st.floats(0, 0.2), nwc_adjustment=st.floats(0, 10),
                   capex_adjustment_pct=st.floats(0, 0.02)),
       bump=st.floats(0.01, 0.1))
def test_higher_revenue_haircut_never_raises_walk_away(p, bump):
    """Checked on the full fixture only. It is false for thin, cash-hungry businesses (capex or NWC heavy
    relative to margin): shrinking revenue frees cash in year 1, which eases the downside covenant and
    allows more cheap debt. E.g. revenue 50, margin 6.7%, capex 7.8%, NWC 12.5%, covenant binding:
    a 6.25% haircut raises walk-away 4.770 -> 4.834. The generator must keep deals out of that regime."""
    deal = make_full()
    assert walk_away(deal, worse(p, "revenue_haircut", bump)) <= walk_away(deal, p) + TOL


@settings(max_examples=40, deadline=None)
@given(c=cases(), bump=st.floats(0.001, 0.02))
def test_higher_capex_adjustment_never_raises_walk_away(c, bump):
    deal, p = c
    assert walk_away(deal, worse(p, "capex_adjustment_pct", bump)) <= walk_away(deal, p) + TOL


@settings(max_examples=40, deadline=None)
@given(c=cases(), bump=st.floats(0.5, 10))
def test_higher_nwc_adjustment_never_raises_walk_away(c, bump):
    deal, p = c
    assert walk_away(deal, worse(p, "nwc_adjustment", bump)) <= walk_away(deal, p) + TOL

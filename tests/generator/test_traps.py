import numpy as np
import pytest

from acqlab.generator.sample import sample_base
from acqlab.generator.traps import TEST_ONLY, TRAPS, params_for, sample_variant, worst_amount


def test_addback_worst_case_never_exceeds_what_was_claimed():
    for seed in range(30):
        b = sample_base(np.random.default_rng(seed))
        assert worst_amount("addback", b) <= min(b.teaser.claimed_addbacks, 0.25 * b.teaser.adj_ebitda) + 1e-9


def test_params_for_converts_dollar_amounts_to_engine_units():
    b = sample_base(np.random.default_rng(0))
    rev = b.teaser.revenue_ltm
    p = params_for({"addback": 2, "debt_like": 3, "concentration": 10, "nwc": 1, "capex": 5}, b)
    assert (p.ebitda_adjustment, p.debt_like, p.nwc_adjustment) == (-2, 3, 1)
    assert p.revenue_haircut == pytest.approx(10 / rev) and p.capex_adjustment_pct == pytest.approx(5 / rev)


def test_dev_deals_never_draw_test_only_variants():
    rng = np.random.default_rng(0)
    for trap in TRAPS:
        dev = {sample_variant(rng, trap, "manufacturing", dev=True) for _ in range(300)}
        test = {sample_variant(rng, trap, "manufacturing", dev=False) for _ in range(300)}
        assert TEST_ONLY[trap] not in dev and TEST_ONLY[trap] in test


def test_debt_like_variants_follow_the_industry():
    rng = np.random.default_rng(0)
    services = [sample_variant(rng, "debt_like", "services", dev=False) for _ in range(500)]
    assert services.count("deferred_revenue") > 3 * services.count("pension")

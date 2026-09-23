import numpy as np
import pytest

from acqlab.generator.industries import INDUSTRIES
from acqlab.generator.sample import FISCAL_YEARS, REAL_NAMES, sample_base, with_asking


def test_capex_and_da_are_derived_from_damodaran_ratios():
    m = next(i for i in INDUSTRIES if i.name == "Machinery")
    assert m.da_pct == pytest.approx(0.1962 - 0.1586)
    assert m.capex_pct == pytest.approx((0.1962 - 0.1586) * 0.6786)


def test_every_industry_clears_the_margin_rule_at_face_value():
    assert all(i.ebitda_margin >= i.capex_pct + 0.05 for i in INDUSTRIES)


def test_same_seed_gives_the_same_deal():
    assert sample_base(np.random.default_rng(3)) == sample_base(np.random.default_rng(3))


def test_teaser_and_engine_inputs_agree_and_stay_in_sourced_ranges():
    for seed in range(50):
        b = sample_base(np.random.default_rng(seed))
        t, c = b.teaser, b.deal.company
        assert t.adj_ebitda == pytest.approx(t.reported_ebitda + t.claimed_addbacks)
        assert (c.reported_adj_ebitda, c.revenue_ltm) == (t.adj_ebitda, t.revenue_ltm)
        assert 50 <= t.asking_price <= 500 and 6 <= b.market_multiple <= 10
        assert 3 <= b.deal.financing.max_leverage <= 5
        cov = b.deal.financing.covenant_max_leverage
        assert [round(x - y, 9) for x, y in zip(cov, cov[1:])] == [0.25] * 4
        assert b.history[-1].fiscal_year == FISCAL_YEARS[-1] and b.history[-1].revenue == t.revenue_ltm
        assert not any(real in t.name.lower() for real in REAL_NAMES)


def test_with_asking_updates_teaser_and_deal_together():
    b = with_asking(sample_base(np.random.default_rng(0)), 99.0)
    assert b.deal.asking_price == b.teaser.asking_price == 99.0

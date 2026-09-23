import warnings
from collections import Counter

import numpy as np

from acqlab.generator.traps import TEST_ONLY, TRAPS
from acqlab.generator.truth import generate, prior_draws, simulate, value_of_knowing


def test_same_seed_gives_the_same_answer_key():
    assert generate("x", "test", 5, mc=40) == generate("x", "test", 5, mc=40)


def test_every_deal_has_one_fact_per_trap_with_rounded_amounts():
    t = generate("x", "test", 1, mc=40)
    assert [f.trap for f in t.facts] == list(TRAPS)
    assert all(f.amount == round(f.amount, 1) and 0 <= f.amount <= f.worst + 0.05 for f in t.facts)


def test_forced_case_types_come_out_as_labelled():
    for case in ("clean", "flip", "interaction"):
        t = generate("x", "test", 7, mc=40, force_case=case)
        assert t.case_type == case
        if case == "clean":
            assert t.go == t.face_go and all(f.amount == 0 for f in t.facts)
        else:
            assert t.face_go and not t.go


def test_unresolvable_amount_is_the_documented_midpoint_and_realized_is_inside():
    facts = [f for s in range(40) for f in generate("x", "test", s, mc=20).facts if f.role == "unresolvable"]
    assert facts
    for f in facts:
        low, high = f.documented
        assert abs(f.amount - (low + high) / 2) <= 0.051 and low <= f.realized <= high


def test_margin_rule_and_dev_rules_hold():
    for s in range(20):
        t = generate("x", "dev", s, mc=20)
        tz, by = t.base.teaser, {f.trap: f for f in t.facts}
        margin = (tz.adj_ebitda - by["addback"].amount) / tz.revenue_ltm
        assert margin >= tz.capex_pct + by["capex"].amount / tz.revenue_ltm + 0.05
        assert t.style == "A" and not any(f.variant == TEST_ONLY[f.trap] for f in t.facts)


def test_batch_mix_is_near_the_targets():
    ts = [generate(f"d{s}", "test", s, mc=20) for s in range(60)]
    assert 0.35 <= np.mean([t.go for t in ts]) <= 0.65
    assert set(Counter(t.case_type for t in ts)) == {"clean", "flip", "interaction", "unresolvable", "decoy"}
    assert all(f.decision_value >= 0 for t in ts for f in t.facts)


def test_a_placebo_fact_has_little_decision_value_next_to_a_flipper():
    """Columns that cannot move walk-away should be worth almost nothing; in-sample binning made them look useful
    (on these seeds the old method gave placebos 14-22% of the flipper's value on average)."""
    for seed in (2, 3, 6):
        t = generate("x", "test", seed, mc=20, force_case="flip")
        flipper = next(i for i, f in enumerate(t.facts) if f.role == "flipper")
        rng = np.random.default_rng(seed)
        draws, reg_go, reg_no = simulate(t.base, {f.trap: f.worst for f in t.facts}, 400, rng)
        values = value_of_knowing(np.hstack([draws, prior_draws(rng, len(draws), 20)]), reg_go, reg_no)
        assert values[flipper] > 0 and np.mean(values[5:]) <= 0.10 * values[flipper], (seed, values)


def test_fewer_draws_than_bins_gives_finite_decision_values():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # an empty bin used to average nothing (NaN), silently clipped to 0
        t = generate("x", "test", 3, mc=5)
    assert all(np.isfinite(f.decision_value) and f.decision_value >= 0 for f in t.facts)

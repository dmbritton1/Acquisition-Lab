import json
import math

import numpy as np
import pytest

import acqlab.routers.track_a as ta
from acqlab.dataroom.tools import BUDGET_SHARE
from acqlab.generator.batch import build, run as run_batch
from acqlab.generator.traps import TRAPS
from acqlab.routers.beliefs import Issue
from acqlab.routers.track_a import (ALL_ROUTERS, Setting, bootstrap_ci, grid, investigate, oracle_table, priors, run,
                                    run_deal, run_oracle, self_consistent, summarize)


@pytest.fixture(autouse=True)
def few_worlds(monkeypatch):
    """No assertion here depends on the number of simulated worlds; 60 keeps the file fast."""
    monkeypatch.setattr(ta, "N_WORLDS", 60)


@pytest.fixture(scope="module")
def keys():
    out = []
    for i in range(6):
        key, docs, _ = build(f"t-{i:03d}", "test", 300 + i, mc=20)
        key.budget = float(math.ceil(BUDGET_SHARE * sum(d.pages for d in docs)))
        out.append(key)
    return out


def test_priors_are_noisy_deterministic_and_never_the_generator_prior(keys):
    k = keys[0]
    a, b = priors(k, "medium"), priors(k, "medium")
    assert a == b and set(a) == set(TRAPS)
    assert any(abs(a[f.trap].hi - f.worst) > 1e-6 for f in k.truth.facts)
    assert any(abs(i.p_real - 0.30) > 1e-6 for i in a.values())
    assert all(i.proposed for i in priors(k, "low").values())


def test_no_hint_at_clue_one_half_and_strong_hints_point_at_real_problems(keys):
    assert all(priors(k, "medium") == priors(k, "medium", 0.5) for k in keys)
    gap = []
    for k in keys:
        base, hinted = priors(k, "medium"), priors(k, "medium", 0.9)
        for f in k.truth.facts:
            assert hinted[f.trap].hi == base[f.trap].hi
            gap.append((hinted[f.trap].p_real - base[f.trap].p_real) * (1 if f.role != "clean" else -1))
    assert np.mean(gap) > 0


def test_investigator_variants(keys):
    facts = [f for k in keys for f in k.truth.facts]
    rng = np.random.default_rng(0)
    for f in facts:
        want = tuple(f.documented) if f.documented else (f.amount, f.amount)
        assert investigate(f, "perfect", rng) == want
        noisy = investigate(f, "noisy", rng)
        assert noisy[0] <= (f.documented[0] if f.documented else f.amount) + 1e-9
        assert noisy[1] >= (f.documented[1] if f.documented else f.amount) - 1e-9
        if f.amount == 0 and not f.documented:
            assert noisy == (0.0, 0.0)
    fails = sum(investigate(facts[0], "failure", rng) is None for _ in range(2000))
    assert abs(fails / 2000 - 0.25) < 0.04


def test_a_run_is_deterministic_within_budget_and_records_what_it_read(keys):
    for r in ALL_ROUTERS[:-1]:
        s = Setting(r, "failure", "high", 0.5)
        a, b = run(keys[1], s), run(keys[1], s)
        assert a == b
        assert a["pages"] <= 0.5 * keys[1].budget + 1e-9
        assert a["pages"] == sum(keys[1].retrieval_cost[x] for x in a["reads"])
        assert a["regret"] >= 0 and (a["regret"] == 0 or not a["correct"])  # regret only for a wrong call


def test_the_sweep_finds_a_forgotten_problem(keys, monkeypatch):
    key = next(k for k in keys if any(f.role != "clean" for f in k.truth.facts))
    problem = next(f.trap for f in key.truth.facts if f.role != "clean")
    real = ta.priors
    monkeypatch.setattr(ta, "priors", lambda k, level, clue=0.5: {
        t: i._replace(proposed=t != problem) for t, i in real(k, level, clue).items()})
    row = run(key, Setting("checklist", "perfect", "low", 1.0))
    assert problem in row["reads"] and row["found_by_sweep"]


def test_the_oracle_is_never_worse_than_any_router(keys):
    for k in keys:
        table = oracle_table(k, "medium")
        for share in (0.25, 0.5):
            best = run_oracle(k, Setting("oracle", "perfect", "medium", share), table)["regret"]
            for r in ("checklist", "random", "sensitivity", "flip", "regret"):
                assert best <= run(k, Setting(r, "perfect", "medium", share))["regret"] + 1e-12


def test_self_consistent_truth_is_drawn_from_the_priors(keys):
    k = keys[2]
    s = self_consistent(k, "medium")
    assert s.truth.base == k.truth.base and s.truth.face_go == k.truth.face_go
    assert {f.role for f in s.truth.facts} <= {"clean", "problem"}
    b = priors(k, "medium")
    assert all(f.amount == 0 or f.amount <= b[f.trap].hi for f in s.truth.facts)
    assert s == self_consistent(k, "medium")


def test_grids():
    assert len(grid("headline")) == 7 * 3 * 2
    assert len(grid("full")) == 7 * 3 * 3 * 3
    assert len(grid("hints")) == 7 * 3 * 2 and {s.clue for s in grid("hints")} == {0.7, 0.9}


def test_bootstrap_ci_and_summary():
    lo, hi = bootstrap_ci(np.array([-1.0, -2.0, -1.5, -0.5]))
    assert lo < hi < 0
    rows = [{"deal": f"d{i}", **Setting(r, "perfect", "medium", 0.5)._asdict(), "regret": reg, "flip": True,
             "has_decoy": False, "has_interaction": False, "prior_inside": 1.0, "found_by_sweep": False}
            for i in range(20) for r, reg in (("regret", 0.0), ("sensitivity", 0.1), ("flip", 0.1),
                                              ("checklist", 0.1))]
    cell = next(c for c in summarize(rows)["cells"] if c["slice"] == "all")
    assert cell["mean_regret"]["regret"] == 0.0 and cell["regret_minus_sensitivity"]["router6_wins"]
    assert cell["regret_minus_checklist"]["router6_wins"]


def test_sweep_find_rate_ignores_the_oracle():
    rows = [{"deal": "d0", **Setting(r, "perfect", "medium", 0.5)._asdict(), "regret": 0.0, "flip": False,
             "has_decoy": False, "has_interaction": False, "prior_inside": None, "found_by_sweep": r == "regret"}
            for r in ("regret", "oracle")]
    assert summarize(rows)["sweep_find_rate"] == 1.0


def test_the_veto_stops_routing_and_leaves_the_rest_to_the_sweep(keys, monkeypatch):
    monkeypatch.setattr(ta, "VETO", 1e9)
    differs = False
    for k in keys:
        s = Setting("regret+veto", "perfect", "medium", 0.5)
        want, left = [], 0.5 * k.budget
        while cand := [x for x in TRAPS if x not in want and k.retrieval_cost[x] <= left + 1e-9]:
            want.append(min(cand, key=lambda x: (k.retrieval_cost[x], TRAPS.index(x))))
            left -= k.retrieval_cost[want[-1]]
        assert run(k, s)["reads"] == want
        differs |= run(k, s._replace(router="regret"))["reads"] != want
    assert differs


def test_a_failed_read_is_charged_again_on_retry(keys, monkeypatch):
    monkeypatch.setattr(ta, "FAIL_P", 1.0)
    k = keys[0]
    row = run(k, Setting("checklist", "failure", "low", 1.0))
    first = row["reads"][0]
    assert row["reads"][:2] == [first, first]
    assert row["pages"] == sum(k.retrieval_cost[x] for x in row["reads"]) >= 2 * k.retrieval_cost[first]


def test_self_consistent_caps_concentration_at_haircut(keys, monkeypatch):
    """Verify that self_consistent applies HAIRCUT_CAP to concentration to avoid ValidationError."""
    k = keys[0]
    revenue = k.truth.base.teaser.revenue_ltm
    # Monkeypatch priors to return concentration with high hi to force a draw >= 1.0 * revenue
    real_priors = ta.priors
    monkeypatch.setattr(ta, "priors", lambda key, level, clue=0.5: {
        t: (Issue(p_real=0.95, hi=10 * revenue) if t == "concentration" else i)
        for t, i in real_priors(key, level, clue).items()
    })
    # self_consistent should not raise even with high concentration draws
    result = self_consistent(k, "medium")
    # Check that the concentration fact amount is capped at 0.95 * revenue
    conc_fact = next(f for f in result.truth.facts if f.trap == "concentration")
    assert conc_fact.amount <= 0.95 * revenue + 1e-9


def test_run_deal_caches_by_level_for_self_truth(keys, tmp_path):
    """Verify that run_deal maintains separate caches for different levels with truth='self'."""
    k = keys[0]
    # Write the deal to a file
    deal_path = tmp_path / "test_deal.json"
    deal_path.write_text(k.model_dump_json())
    # Run with two settings at different levels with truth='self'
    settings = [
        Setting("checklist", "perfect", "low", 1.0, truth="self"),
        Setting("checklist", "perfect", "medium", 1.0, truth="self"),
    ]
    rows = run_deal(deal_path, settings)
    assert len(rows) == 2 and all("error" not in r for r in rows)
    # Verify each row matches what running with the correct level's self-consistent key produces
    for s in settings:
        self_key = self_consistent(k, s.level)
        expected = run(self_key, s)
        actual = next(r for r in rows if r["level"] == s.level)
        assert actual["regret"] == expected["regret"]
        assert actual["correct"] == expected["correct"]


def test_main_writes_resumes_and_skips_broken_deals(tmp_path, monkeypatch, capsys):
    # --workers 1 runs in-process, so the few_worlds patch applies
    run_batch(tmp_path, {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, mc=20)
    argv = ["--deals", str(tmp_path), "--grid", "headline", "--workers", "1"]
    assert ta.main(argv) == 0
    lines = (tmp_path / "results.jsonl").read_text().splitlines()
    assert len(lines) == 2 * 7 * 3 * 2
    assert ta.main(argv) == 0
    assert (tmp_path / "results.jsonl").read_text().splitlines() == lines
    assert json.loads((tmp_path / "summary_headline.json").read_text())["cells"]
    (tmp_path / "truth" / "dev-999.json").write_text("{not json")
    assert ta.main(argv) == 1
    assert "SKIPPED dev-999" in capsys.readouterr().err
    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == len(lines)

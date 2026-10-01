import json
import math

import pytest

from acqlab.bench import simrun, testset
from acqlab.generator.traps import TRAPS

MODEL = {t: {"chance": 0.4, "high_ratio": 1.0, "kinds": ["qoe"]} for t in TRAPS}


def _rows(regrets, go=None, pages=10.0):
    return {f"d{i}": {"regret": r, "go": True if go is None else go[i], "correct": r == 0, "pages": pages,
                      "nofact_pages": 2.0, "real_reached": 0.5} for i, r in enumerate(regrets)}


def test_clashes_checks_the_split_s_own_seeds():
    assert testset.clashes(100, 5, {103}, split="dev") == [103]
    assert testset.clashes(100, 5, {103}) == []  # the test split adds its offset, as before
    assert testset.clashes(100, 5, {10_103}) == [10_103]


def test_template_deals_are_refused_on_a_seed_clash_and_made_otherwise(tmp_path, data):
    used = testset.used_seeds([data])
    clash = min(used)
    assert clash in simrun.make_deals(tmp_path / "x", 2, clash, [data], mc=20)
    assert not (tmp_path / "x").exists()
    base = max(used) + 1000
    assert simrun.make_deals(tmp_path / "y", 2, base, [data], mc=20) == []
    assert json.loads((tmp_path / "y" / "seed.json").read_text()) == {"base": base, "n": 2, "split": "dev"}
    assert len(list((tmp_path / "y" / "truth").glob("*.json"))) == 2


def test_runs_are_made_once_and_resume(data, tmp_path):
    runs = tmp_path / "runs"
    assert simrun.run(data, ["baseline", "no_sweep"], "model", runs, jobs=1, model=MODEL) == 4
    assert simrun.run(data, ["baseline", "no_sweep"], "model", runs, jobs=1, model=MODEL) == 0
    got = simrun.load(runs, data, "no_sweep")
    assert sorted(got) == ["dev-000", "dev-001"] and got["dev-000"]["system"] == "no_sweep"


def test_logged_openings_take_only_deals_with_a_real_s4_trace(data):
    assert simrun.deals_of(data, "model") == ["dev-000", "dev-001"]
    assert simrun.deals_of(data, "logged") == []


def test_faithfulness_measures_agreement_and_applies_the_pass_bars():
    real = _rows([0.0] * 20, go=[True] * 20)
    docs = {d: ["a", "b"] for d in real}
    same = simrun.faithfulness(real, real, docs, docs)
    assert same["agree"] == 1.0 and same["jaccard"] == 1.0 and same["passes"]
    flipped = _rows([0.0] * 20, go=[i >= 4 for i in range(20)])  # 4 of 20 differ: 80% < 85%
    assert simrun.faithfulness(flipped, real, docs, docs)["passes"] is False
    worse = _rows([0.004] * 20, go=[True] * 20)  # agree, but regret off by 0.004 >= 0.003
    assert simrun.faithfulness(worse, real, docs, docs)["passes"] is False
    other = {d: ["a", "c"] for d in real}
    f = simrun.faithfulness(real, real, other, docs)
    assert f["jaccard"] == pytest.approx(1 / 3) and f["first_divergence_median"] == 1


def test_the_table_pairs_every_strategy_with_the_baseline():
    by = {"baseline": _rows([0.01, 0.02, 0.03]), "regret": _rows([0.0, 0.01, 0.02])}
    tab = simrun.table(by)
    assert tab["baseline"]["minus_base"] is None
    assert tab["regret"]["minus_base"]["diff"] == pytest.approx(-0.01)
    assert tab["regret"]["nofact_share"] == pytest.approx(0.2)


def test_greedy_keeps_only_additions_that_clearly_help():
    n = 40
    base = [0.02] * n
    by = {name: _rows(base) for name in simrun.SINGLES}
    by["regret"] = _rows([0.01] * n)  # clearly better alone
    by["base_rate"] = _rows([0.015] * n)
    by["no_sweep"] = _rows([0.019] * n)
    tab = simrun.table(by)
    tried = []

    def run_combo(name):
        tried.append(name)
        return _rows([0.005] * n) if name == "regret+base_rate" else _rows([0.006] * n)

    out = simrun.greedy(tab, by, run_combo)
    assert out["combo"] == "regret+base_rate"
    assert tried[0] == "regret+base_rate" and all(t.startswith("regret+base_rate+") for t in tried[1:])
    assert [s["kept"] for s in out["steps"]] == [True] + [False] * (len(tried) - 1)


def test_greedy_falls_back_to_the_baseline_when_nothing_helps():
    by = {name: _rows([0.02] * 10) for name in simrun.SINGLES}
    assert simrun.greedy(simrun.table(by), by, lambda name: pytest.fail("no combination to run")) == {
        "combo": "baseline", "steps": []}


def test_deals_needed_matches_the_closed_form():
    assert simrun.deals_needed(1.0, sd=1.0, power=0.5) == math.ceil(1.959963984540054 ** 2)
    assert simrun.deals_needed(0.0038) == math.ceil(((1.959963984540054 + 0.8416212335729143) * 0.0368 / 0.0038) ** 2)


def test_sizing_adds_the_simulated_gain_and_its_half():
    s = simrun.sizing(-0.002)
    assert s["full"]["gap"] == pytest.approx(-0.0058) and s["half"]["gap"] == pytest.approx(-0.0048)
    assert s["full"]["power_80"] < s["half"]["power_80"] < s["half"]["power_90"]
    assert simrun.sizing(0.001)["full"]["gap"] == pytest.approx(-0.0038)  # a loss in simulation adds nothing


def test_a_run_interrupted_before_its_result_is_redone(data, tmp_path):
    runs = tmp_path / "runs"
    stray = runs / data.name / "baseline" / "dev-000.trace.jsonl"
    stray.parent.mkdir(parents=True)
    stray.write_text('{"tool": "half a run"}\n')
    assert simrun.run(data, ["baseline"], "model", runs, jobs=1, model=MODEL) == 2
    assert "half a run" not in stray.read_text()


def test_faithfulness_counts_only_deals_both_sides_ran():
    real = _rows([0.0] * 21, go=[True] * 21)
    sim_rows = {d: r for d, r in real.items() if d != "d20"}
    docs = {d: ["a"] for d in real}
    assert simrun.faithfulness(sim_rows, real, docs, docs)["n"] == 20

import json
import subprocess

import numpy as np
import pytest

import acqlab.agents.panel as panel_mod
from acqlab.agents.panel import Config, Panel
from acqlab.agents.record import load_face
from acqlab.bench import sim
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS


def _key(data, deal="dev-000") -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())


def _room(data, deal="dev-000"):
    return data / "deals" / deal / "room"


def _plan(chance=0.4):
    return [{"type": t, "name": t, "chance": chance, "low": 0.0, "high": 5.0, "docs": []} for t in TRAPS]


def _panel(data, tmp_path, s=sim.Strategy(), name="t.jsonl"):
    key = _key(data)
    return sim.SimPanel(_room(data), key.budget, tmp_path / name, key, _plan(), s)


def _rows(trace):
    return [json.loads(x) for x in trace.read_text().splitlines()]


def test_a_fact_is_revealed_by_the_last_document_of_its_evidence_only(data):
    key = _key(data)
    e = key.evidence[0]
    e.docs = ["cim", "qoe"]
    assert e.trap not in {c["type"] for c in sim.reveal(key, "cim")}
    got = [c for c in sim.reveal(key, "qoe") if c["type"] == e.trap]
    f = next(f for f in key.truth.facts if f.trap == e.trap)
    assert got == [{"type": e.trap, "kind": "quoted", "chance": 1.0, "low": f.realized, "high": f.realized,
                    "quotes": [], "docs": ["qoe"]}]


def test_an_unresolvable_fact_commits_its_documented_range(data):
    key = _key(data)
    e = key.evidence[0]
    f = next(f for f in key.truth.facts if f.trap == e.trap)
    f.documented = (1.0, 3.0)
    c = next(c for c in sim.reveal(key, e.docs[-1]) if c["type"] == e.trap)
    assert (c["kind"], c["low"], c["high"]) == ("range", 1.0, 3.0)


def test_strategies_combine_their_changes_from_the_baseline():
    assert sim.strategy("baseline") == sim.Strategy()
    assert sim.strategy("regret+no_sweep") == sim.Strategy(scorer="regret", sweep=False)
    assert sim.strategy("pages_0.5+cut_0.25+base_rate") == sim.Strategy(page_power=0.5, absence_cut=0.25,
                                                                        opening="base_rate")


def test_the_simulator_never_calls_claude(data, tmp_path):
    with pytest.raises(RuntimeError, match="never calls Claude"):
        sim.no_claude()
    p = _panel(data, tmp_path)
    assert p.session is sim.no_claude
    p.run()  # the session raises if any role turn is reached
    assert _rows(tmp_path / "t.jsonl")[-1]["tool"] == "submit"


def test_reads_charge_pages_and_report_what_they_settle(data, tmp_path):
    p = _panel(data, tmp_path)
    p.lead()
    key = _key(data)
    d = key.evidence[0].docs[-1]
    p.read_doc(d)
    rows = _rows(tmp_path / "t.jsonl")
    assert any(r["tool"] == "open_document" and r["args"]["doc_id"] == d and r["cost"] == p.pages[d] for r in rows)
    assert p.read() == {d}
    assert p.record.entries[key.evidence[0].trap].known is not None


def test_the_baseline_routes_like_the_real_panel(data, tmp_path):
    p = _panel(data, tmp_path)
    p.lead()
    assert p.route() == Panel.route(p) is not None


def test_page_power_rescales_scores_by_pages_only(data, tmp_path):
    for scorer in ("move", "regret"):
        one, half = (_panel(data, tmp_path, sim.Strategy(scorer=scorer, page_power=pw), f"{scorer}{pw}.jsonl")
                     for pw in (1.0, 0.5))
        one.lead(), half.lead()
        cands = sorted(one.pages)
        a, b = one.scores(set(), cands), half.scores(set(), cands)
        assert all(b[d] == pytest.approx(a[d] * one.pages[d] ** 0.5) for d in cands)


def test_the_regret_scorer_values_a_document_by_the_decision_regret_it_removes():
    n = 2000
    rng = np.random.default_rng(0)
    addback = np.where(rng.random(n) < 0.5, 0.0, 10.0)  # about half the worlds have the problem
    values = np.zeros((n, len(TRAPS)))
    values[:, TRAPS.index("addback")] = addback
    w = np.where(addback > 0, 80.0, 100.0)  # walk-away 100 without it, 80 with it; asking 90
    u = rng.random(values.shape)
    s = sim.score_docs_regret(values, w, 90.0, {"settles": {"addback": 1.0}, "blank": {}}, ["addback"], u)
    assert s["settles"] == pytest.approx(5.0, abs=0.5)  # either call now costs about 5 in expectation
    assert s["blank"] == 0.0


def test_absence_cut_lowers_only_issues_the_read_could_settle(data, tmp_path):
    key = _key(data)
    p = _panel(data, tmp_path, sim.Strategy(absence_cut=0.5))
    p.lead()
    wts = p.record.weights(p.pages, set())
    d = next(d for d in sorted(wts) if not sim.reveal(key, d))  # a read that settles nothing
    p.read_doc(d)
    for t in TRAPS:
        assert p.record.entries[t].chance == pytest.approx(0.2 if t in wts[d] else 0.4)


def test_base_rate_replaces_only_the_opening_chances(data, tmp_path):
    p = _panel(data, tmp_path, sim.Strategy(opening="base_rate"))
    p.lead()
    for t in TRAPS:
        e = p.record.entries[t]
        assert (e.chance, e.high) == (sim.BASE_RATE[t], 5.0)


def test_no_sweep_keeps_no_reserve_and_never_sweeps(data, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(sim.SimPanel, "sweep", lambda self: called.append(1))
    p = _panel(data, tmp_path, sim.Strategy(sweep=False))
    assert p.reserve == 0
    p.run()
    assert called == []


def test_the_sweep_picks_what_the_real_sweep_picks(data, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(panel_mod.prompts, "sweep_prompt", lambda teaser, docs, sweep, read, budget:
                        seen.append(list(sweep)) or "")
    key = _key(data)
    Panel(_room(data), key.budget, tmp_path / "real.jsonl", Config(challenger=False), lambda *a: None).sweep()
    assert seen and _panel(data, tmp_path).sweep_picks() == seen[0]


def test_a_simulated_run_is_repeatable_and_graded_like_a_real_one(data, tmp_path):
    a = sim.simulate(data, "dev-000", sim.Strategy(), "baseline", _plan(), tmp_path / "a" / "dev-000.json")
    b = sim.simulate(data, "dev-000", sim.Strategy(), "baseline", _plan(), tmp_path / "b" / "dev-000.json")
    assert _rows(tmp_path / "a" / "dev-000.trace.jsonl") == _rows(tmp_path / "b" / "dev-000.trace.jsonl")
    assert a == b
    rows = _rows(tmp_path / "a" / "dev-000.trace.jsonl")
    assert a["pages"] == sum(r["cost"] for r in rows if r["tool"] == "open_document")
    assert a["opened"] == [r["args"]["doc_id"] for r in rows if r["tool"] == "open_document"]
    assert a["answered"] and a["system"] == "baseline"
    assert json.loads((tmp_path / "a" / "dev-000.json").read_text()) == a


def test_the_modelled_lead_takes_medians_and_kinds_named_in_half_the_plans(data):
    face = load_face(_room(data))
    th = {t: sim.typical_high(t, face.teaser) for t in TRAPS}

    def plan(c, r, docs):
        return [{"type": t, "chance": c, "low": 0, "high": r * th[t], "docs": docs} for t in TRAPS]

    model = sim.fit_lead([(plan(0.2, 1.0, ["qoe", "contract_2"]), face), (plan(0.4, 2.0, ["qoe"]), face),
                          (plan(0.6, 3.0, ["legal", "contract_1"]), face)])
    assert model["nwc"] == {"chance": 0.4, "high_ratio": 2.0, "kinds": ["contract", "qoe"]}
    issues = sim.model_plan(model, face, ["qoe", "contract_1", "contract_2", "legal"])
    nwc = next(i for i in issues if i["type"] == "nwc")
    assert nwc["docs"] == ["qoe", "contract_1", "contract_2"] and nwc["high"] == pytest.approx(2.0 * th["nwc"])
    assert [i["type"] for i in issues] == list(TRAPS)


def test_reading_stats_count_pages_on_documents_with_no_fact(data):
    key = _key(data)
    holding = {d for e in key.evidence for d in e.docs}
    empty = next(d for d in ["insurance", "hr_policy", "it_policy", "whistleblowing"] if d not in holding)
    last = key.evidence[0].docs[-1]
    st = sim.reading_stats(key, [empty, last], {empty: 3.0, last: 9.0})
    assert st["nofact_pages"] == 3.0
    real = [e for e in key.evidence if next(f for f in key.truth.facts if f.trap == e.trap).amount > 0]
    if real:
        assert st["real_reached"] == pytest.approx(sum(e.docs[-1] == last for e in real) / len(real))


def test_s4_s_files_are_unchanged_from_the_freeze_tag():
    tag = subprocess.run(["git", "rev-parse", "-q", "--verify", "s4-frozen-plan5"], capture_output=True)
    if tag.returncode:
        pytest.skip("no freeze tag in this checkout")
    assert subprocess.run(["git", "diff", "--quiet", "s4-frozen-plan5", "--", "acqlab/agents",
                           "acqlab/routers"]).returncode == 0


def test_an_unknown_strategy_name_is_refused():
    with pytest.raises(KeyError, match="nope"):
        sim.strategy("regret+nope")


def test_a_budget_too_small_for_any_document_still_submits(data, tmp_path):
    key = _key(data)
    sim.SimPanel(_room(data), 1.0, tmp_path / "t.jsonl", key, _plan(), sim.Strategy()).run()
    rows = _rows(tmp_path / "t.jsonl")
    assert rows[-1]["tool"] == "submit" and not any(r["tool"] == "open_document" for r in rows)


def test_the_logged_plan_is_the_first_accepted_proposal(tmp_path):
    t = tmp_path / "s4.trace.jsonl"
    rows = [{"tool": "propose", "refused": True, "args": {"issues": ["refused"]}},
            {"tool": "propose", "refused": False, "args": {"issues": ["first"]}},
            {"tool": "propose", "refused": False, "args": {"issues": ["later"]}}]
    t.write_text("\n".join(json.dumps(r) for r in rows))
    assert sim.logged_plan(t) == ["first"]


def test_without_the_midpoint_the_first_pass_may_pick_a_long_document(data, tmp_path):
    p = _panel(data, tmp_path, sim.Strategy(midpoint=False))
    p.lead()
    half = 0.5 * p.budget
    assert p.route(half) == p.route()
    q = _panel(data, tmp_path, name="mid.jsonl")
    q.lead()
    assert all(q.pages[d] <= half for d in [q.route(half)] if d)


def test_named_boost_doubles_named_documents_then_renormalizes(data, tmp_path):
    p, q = _panel(data, tmp_path), _panel(data, tmp_path, sim.Strategy(named_boost=2.0), "b.jsonl")
    p.lead(), q.lead()
    t = TRAPS[0]
    named = sorted(p.pages)[:1]
    for r in (p, q):
        r.record.entries[t].docs = named
    a, b = p.record.weights(p.pages, set()), q.record.weights(q.pages, set())
    raw = {d: a[d][t] * (2 if d in named else 1) for d in a if t in a[d]}
    assert sum(b[d][t] for d in b if t in b[d]) == pytest.approx(1.0)
    assert all(b[d][t] == pytest.approx(raw[d] / sum(raw.values())) for d in raw)
    assert q.record.rank_docs(q.pages, set(), sorted(q.pages)) != p.record.rank_docs(p.pages, set(), sorted(p.pages))

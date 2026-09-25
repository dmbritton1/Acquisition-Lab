import json
import shutil
from functools import partial

import pytest

import acqlab.bench.pilot as pilot
from acqlab.agents.server import MAX_CALLS
from acqlab.agents.solver import RunTimeout, solve
from acqlab.bench.pilot import decoy_docs, relevant_docs, run, score, summarize
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable


@pytest.fixture
def fresh(data, tmp_path):
    """A private copy of the shared deals, so runs written by one test never make another test resume."""
    return shutil.copytree(data, tmp_path / "data")


def _key(data, deal="dev-000") -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())


def _row(tool, args, cost=0.0, refused=False):
    return {"tool": tool, "args": args, "cost": cost, "refused": refused}


def test_a_submitted_run_is_scored_against_the_answer_key(data):
    key = _key(data)
    t, ask = key.truth, key.truth.deal.asking_price
    doc = sorted(relevant_docs(key) or {"cim"})[0]
    # dev-000's debt_like fact is non-clean (unresolvable, realized 18.3): a note on it is what prior_inside counts.
    trace = [_row("open_document", {"doc_id": doc}, 7.0), _row("open_document", {"doc_id": "cim"}, 0, True),
             _row("note_issue", {"type": "debt_like", "chance": 1.0, "low": 0, "high": 1e9, "docs": []}),
             _row("submit", {"go": t.go, "walk_away": t.walk_away + 0.1 * ask, "reason": "r"})]
    cli = {"usage": {"input_tokens": 5, "output_tokens": 2}, "num_turns": 4}
    r = score(key, "s1b", trace, cli, "ok")
    assert r["answered"] and r["correct"] and r["regret"] == 0
    assert r["walk_away_error"] == pytest.approx(0.1)
    assert r["pages"] == 7.0 and r["prior_inside"] == 1.0 and r["tokens"]["input_tokens"] == 5
    assert r["opened_relevant"] == (True if relevant_docs(key) else None)
    assert r["flip"] == (t.go != t.face_go) and r["floors"]["b0"] == pilot.regret(key, t.face_go) / ask


def test_prior_inside_ignores_notes_on_clean_facts(data):
    """F3: prior_inside must match Track A's definition (routers/track_a.py ~line 145), which counts only non-clean
    facts. dev-000's capex fact is clean (amount 0, realized 0): a note on it must not move prior_inside at all."""
    key = _key(data)
    t = key.truth
    assert {f.trap: f.role for f in t.facts}["capex"] == "clean"
    trace = [_row("note_issue", {"type": "capex", "chance": 0.4, "low": 5, "high": 10, "docs": []}),
             _row("submit", {"go": t.face_go, "walk_away": t.face_walk_away, "reason": "r"})]
    r = score(key, "s1b", trace, None, "ok")
    assert r["prior_inside"] is None  # no non-clean note: nothing to average


def test_a_run_that_never_submits_gets_b0s_decision(data):
    key = _key(data)
    r = score(key, "s1b", [], None, "timeout")
    assert not r["answered"] and r["go"] == key.truth.face_go and r["regret"] == r["floors"]["b0"]
    assert r["tokens"]["output_tokens"] == 0


def test_the_model_keys_the_cli_reports_are_recorded(data):
    key = _key(data)
    cli = {"usage": {}, "modelUsage": {"claude-opus-5-5": {"inputTokens": 5}, "claude-haiku-5": {}}}
    r = score(key, "s1b", [], cli, "ok")
    assert r["models"] == ["claude-haiku-5", "claude-opus-5-5"]
    assert score(key, "s1b", [], None, "timeout")["models"] == []


def test_decoy_documents_never_include_decision_relevant_ones(data):
    for deal in ("dev-000", "dev-001"):
        key = _key(data, deal)
        assert not decoy_docs(key) & relevant_docs(key)


def test_runs_are_saved_resumed_and_timeouts_are_scored(fresh):
    calls = []

    def solver(room, budget, trace, router):
        calls.append(router)
        if router:
            raise RunTimeout("slow")
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}

    rows = run(fresh, 2, ["s1b", "s1b_router"], solver=solver)
    assert calls == [False, True, False, True] and len(rows) == 4
    assert {r["status"] for r in rows if r["system"] == "s1b_router"} == {"timeout"}
    assert (fresh / "runs" / "s1b" / "dev-001.json").exists()
    assert run(fresh, 2, ["s1b", "s1b_router"], solver=solver) == [] and len(calls) == 4  # resumed: nothing re-run


def test_a_run_with_no_trace_stops_the_batch(fresh):
    with pytest.raises(LLMUnavailable, match="never ran"):
        run(fresh, 1, ["s1b"], solver=lambda *a: {"usage": {}})


def test_end_to_end_with_a_fake_claude(fresh, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    solver = partial(solve, claude=fake_claude)
    rows = run(fresh, 1, ["s1b", "s1b_router"], solver=solver)
    assert [r["answered"] for r in rows] == [True, True]
    assert rows[0]["rank_calls"] == 0 and rows[1]["rank_calls"] == 1 and rows[0]["pages"] > 0
    assert rows[0]["tokens"]["cache_read_input_tokens"] == 50 and rows[0]["cost_usd"] == 0.5


def test_a_run_that_never_submits_is_scored_ok_and_unanswered_end_to_end(fresh, fake_claude, monkeypatch):
    """F9: FAKE_CLAUDE=nosubmit calls list_documents but never submit — the no-answer path, end to end through the
    real server (not just score() on a hand-built trace)."""
    monkeypatch.setenv("FAKE_CLAUDE", "nosubmit")
    solver = partial(solve, claude=fake_claude)
    rows = run(fresh, 1, ["s1b"], solver=solver)
    assert rows[0]["answered"] is False and rows[0]["status"] == "ok"


def test_a_usage_limit_exits_2_and_keeps_finished_runs(fresh, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    monkeypatch.setenv("CLAUDE_BIN", fake_claude)
    assert pilot.main(["--data", str(fresh), "--n", "2", "--confirm-claude"]) == 2


def test_claude_is_never_called_without_the_confirm_flag(data, monkeypatch):
    monkeypatch.setattr(pilot, "run", lambda *a, **k: pytest.fail("ran without --confirm-claude"))
    assert pilot.main(["--data", str(data), "--n", "1"]) == 3


def _fake_row(deal, system, regret, relevant, flip=True):
    return {"deal": deal, "system": system, "regret": regret, "opened_relevant": relevant, "flip": flip,
            "answered": True, "correct": regret == 0, "walk_away_error": 0.1, "pages": 10, "decoy_pages": 0,
            "prior_inside": None, "rank_calls": 0, "case_type": "flip", "cost_usd": None, "tokens": dict.fromkeys(
                ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"), 0),
            "floors": {"always_go": 0.2, "always_no": 0.2, "b0": 0.1, "b0_walk_away_error": 0.1,
                       "ask_walk_away_error": 0.1, "headroom": 0.05}}


@pytest.mark.parametrize("router_regret, router_relevant, verdict", [
    (0.0, True, "keep"), (0.2, False, "reframe"), (0.0, False, "mixed"), (0.2, True, "mixed")])
def test_the_checkpoint_rule(router_regret, router_relevant, verdict):
    rows = []
    for i in range(4):
        rows += [_fake_row(f"d{i}", "s1b", 0.1, i < 2), _fake_row(f"d{i}", "s1b_router", router_regret,
                                                                   router_relevant or i < 1)]
    s = summarize(rows)
    assert s["checkpoint"]["verdict"] == verdict and s["checkpoint"]["n_flip"] == 4
    assert s["b0_warning"]  # s1b's regret (0.1) does not beat B0's (0.1)


def test_timed_out_runs_are_excluded_from_the_token_and_cost_means(data):
    """F5: a timeout scores with zero usage (no cli result); averaging it in with real runs would drag the token
    and cost means toward zero and make the checkpoint's cost numbers meaningless."""
    key0, key1 = _key(data, "dev-000"), _key(data, "dev-001")
    ok_cli = {"usage": {"input_tokens": 10, "output_tokens": 10, "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 10}, "total_cost_usd": 0.5}

    def submitted(key):
        t = key.truth
        return [_row("submit", {"go": t.face_go, "walk_away": t.face_walk_away, "reason": "r"})]

    rows = [score(key0, "s1b", submitted(key0), ok_cli, "ok"), score(key1, "s1b", [], None, "timeout"),
            score(key0, "s1b_router", submitted(key0), ok_cli, "ok"),
            score(key1, "s1b_router", submitted(key1), ok_cli, "ok")]
    s = summarize(rows)
    assert s["systems"]["s1b"]["tokens"]["input_tokens"] == 10.0  # not 5.0: the timeout row is excluded, not averaged
    assert s["systems"]["s1b"]["cost_usd"] == 0.5


def test_report_writes_a_summary_without_claude(fresh, monkeypatch):
    def solver(room, budget, trace, router):
        trace.write_text(json.dumps(_row("submit", {"go": router, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}
    run(fresh, 2, ["s1b", "s1b_router"], solver=solver)
    monkeypatch.setattr(pilot, "run", lambda *a, **k: pytest.fail("report must not run anything"))
    assert pilot.main(["--data", str(fresh), "--report"]) == 0
    summary = json.loads((fresh / "runs" / "summary.json").read_text())
    assert summary["n_deals"] == 2 and summary["systems"]["s1b_router"]["correct"] is not None


def test_the_margin_rule_picks_the_best_hindsight_threshold():
    # thin-margin deals are the bad ones: going costs 0.3 there and nothing on the wide-margin deals
    fl = [{"headroom": h, "always_go": g, "always_no": n} for h, g, n in
          [(0.01, 0.3, 0.0), (0.03, 0.3, 0.0), (0.10, 0.0, 0.2), (0.20, 0.0, 0.2)]]
    assert pilot.margin_rule(fl) == (0.10, 0.0)
    assert pilot.margin_rule(fl[2:]) == (0.0, 0.0)  # no thin deals: plain B0 (threshold 0) is already perfect


def test_the_report_carries_the_margin_floor():
    rows = [_fake_row(f"d{i}", s, 0.1, True) for i in range(2) for s in ("s1b", "s1b_router")]
    s = summarize(rows)
    assert s["floors"]["margin_rule"] == 0.2 and s["margin_warning"] is False


def test_s0_reads_with_the_whole_room_plus_max_calls_as_budget_and_flip_only_skips_the_rest(fresh):
    """F1: S0's budget must cover the whole room's pages *and* leave room for every search along the way (each costs
    1 unit), or an S0 that searches can't actually open every document."""
    got = []

    def solver(room, budget, trace, router, unbudgeted=False):
        got.append((room.parent.name, budget, unbudgeted))
        trace.write_text(json.dumps(_row("submit", {"go": False, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}
    keys = {d: _key(fresh, d) for d in ("dev-000", "dev-001")}
    run(fresh, 2, ["s0"], solver=solver, flip_only=True)
    flips = [d for d, k in keys.items() if k.truth.go != k.truth.face_go]
    assert [d for d, _, _ in got] == flips
    for d, budget, unbudgeted in got:
        index = json.loads((fresh / "deals" / d / "room" / "index.json").read_text())
        assert budget == sum(x["pages"] for x in index["documents"]) + MAX_CALLS > keys[d].budget
        assert unbudgeted is True


def test_repeats_are_saved_apart_and_resumed(fresh):
    calls = []

    def solver(room, budget, trace, router):
        calls.append(trace.name)
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}
    rows = run(fresh, 1, ["s1b"], solver=solver, reps=3)
    assert [r["rep"] for r in rows] == [0, 1, 2]
    assert calls == ["dev-000.trace.jsonl", "dev-000.r1.trace.jsonl", "dev-000.r2.trace.jsonl"]
    assert run(fresh, 1, ["s1b"], solver=solver, reps=3) == [] and len(calls) == 3


def test_s3_is_the_majority_decision_of_s1b_runs_with_summed_costs():
    fl = {"always_go": 0.3, "always_no": 0.0, "b0": 0.3, "b0_walk_away_error": 0.1, "ask_walk_away_error": 0.1,
          "headroom": 0.02, "ask": 100.0, "true_walk_away": 90.0}  # a bad deal: going costs 0.3

    def rep(k, go, wa):
        return _fake_row("d0", "s1b", 0.3 if go else 0.0, True) | {
            "rep": k, "go": go, "walk_away": wa, "status": "ok", "floors": fl, "cost_usd": 0.1,
            "tokens": dict.fromkeys(("input_tokens", "output_tokens", "cache_read_input_tokens",
                                     "cache_creation_input_tokens"), 5)}
    rows = [rep(0, True, 95.0), rep(1, False, 88.0), rep(2, False, 91.0)]
    s3 = pilot.s3_rows(rows, 3)["d0"]
    assert s3["go"] is False and s3["regret"] == 0.0 and s3["correct"] and s3["walk_away"] == 91.0
    assert s3["walk_away_error"] == pytest.approx(0.01) and s3["tokens"]["input_tokens"] == 15
    assert s3["cost_usd"] == pytest.approx(0.3) and s3["pages"] == 30
    assert pilot.s3_rows(rows[:2], 2)["d0"]["go"] is False  # a 1-1 tie is the cautious no-go
    assert pilot.s3_rows(rows, 4) == {}  # not enough runs
    s = summarize(rows, s3_n=3)
    assert s["systems"]["s3"]["regret"] == 0.0 and s["systems"]["s1b"]["regret"] == 0.3  # s1b: its first run only


def test_a_summary_with_only_s1b_has_floors_but_no_checkpoint():
    s = summarize([_fake_row(f"d{i}", "s1b", 0.05, True) for i in range(3)])
    assert s["n_deals"] == 3 and set(s["systems"]) == {"s1b"} and "checkpoint" not in s
    assert s["floors"]["b0"] == pytest.approx(0.1) and not s["b0_warning"]

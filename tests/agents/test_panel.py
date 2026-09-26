import json
import math
import re

import pytest

import acqlab.agents.panel as panel
from acqlab.agents.panel import STAGES, Config, Panel, solve
from acqlab.agents.record import on_map
from acqlab.agents.server import ROLES, Session
from acqlab.agents.solver import RunTimeout
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable


def _room(data, deal="dev-000"):
    return data / "deals" / deal / "room"


def _budget(data, deal="dev-000") -> float:
    return AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text()).budget


def _rows(trace) -> list[dict]:
    return [json.loads(x) for x in trace.read_text().splitlines()]


def _issue(t, chance=0.5, high=2.0, docs=()):
    return {"type": t, "name": t, "chance": chance, "low": 0, "high": high, "docs": list(docs)}


def scripted(**roles):
    """A stand-in for run_session: each turn runs a real tool Session in-process and hands it to the role's script
    (session, prompt). Records (role, prompt, budget) for every turn."""
    turns = []

    def session(room, budget, trace, prompt, system, tools, args):
        a = dict(zip(args[::2], args[1::2]))
        assert tools == ROLES[a["--role"]]
        s = Session(room, budget, trace, False, a["--role"], tuple(d for d in a["--paid"].split(",") if d),
                    tuple(map(tuple, json.loads(a.get("--pairs", "[]")))))
        turns.append((a["--role"], prompt, budget))
        roles[a["--role"]](s, prompt)
        return {"usage": {"output_tokens": 7}, "total_cost_usd": 0.01, "num_turns": 2, "duration_ms": 5,
                "modelUsage": {"claude-opus-5-5": {}}, "env_keys": ["HOME"]}

    session.turns = turns
    return session


def lead_says(*plans):
    """The Deal Lead proposes each plan in turn (the last one repeats); a plan is (issues, stop)."""
    plans = list(plans)

    def lead(s, prompt):
        issues, stop = plans.pop(0) if len(plans) > 1 else plans[0]
        s.call("propose", {"issues": issues, "stop": stop, "reason": "r"})
    return lead


def finds_nothing(s, prompt):
    """An Investigator that reads the first suggested document it can afford (a document brief's one document) and
    settles nothing."""
    looked = re.search(r"Look first at: ([^.]*)\.", prompt) or re.search(r"Brief: read (\S+) \(", prompt)
    for doc in (looked.group(1).split(", ") if looked else []):
        if not s.call("open_document", {"doc_id": doc})["isError"]:
            s.call("report", {"findings": [{"type": "addback", "status": "not_found", "docs": [doc]}]})
            return
    s.call("report", {"findings": []})


def no_objections(s, prompt):
    s.call("challenge", {"objections": [], "pairs": [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                     for a, b in s.pairs]})


def _briefed(turns) -> list[str]:
    return [re.search(r"Find out: (\w+)", p).group(1) for r, p, _ in turns if r == "investigator" and "Find out" in p]


@pytest.mark.parametrize("stage", list(STAGES))
def test_every_build_step_runs_end_to_end_and_the_engine_decides(data, tmp_path, fake_claude, monkeypatch, stage):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    trace, budget = tmp_path / "t.jsonl", _budget(data)
    cli = solve(_room(data), budget, trace, STAGES[stage], claude=fake_claude)
    rows = _rows(trace)
    assert rows[-1]["tool"] == "submit" and rows[-1]["args"]["reason"] == "engine"
    assert sum(r["cost"] for r in rows) <= budget
    assert cli["usage"]["output_tokens"] == 20 * cli["sessions"] and cli["total_cost_usd"] == 0.5 * cli["sessions"]
    tools = {r["tool"] for r in rows}
    assert ("propose" in tools) == STAGES[stage].lead and ("challenge" in tools) == STAGES[stage].challenger
    if stage == "s4_1":
        assert cli["sessions"] == 1


def test_without_the_router_issues_go_in_the_lead_s_order_until_the_lead_says_stop(data, tmp_path):
    plan = [_issue("nwc", docs=["qoe"]), _issue("debt_like", docs=["legal"]), _issue("addback", docs=["qoe"])]
    s = scripted(lead=lead_says((plan, False), (plan, False), (plan, True)), investigator=finds_nothing)
    Panel(_room(data), 40, tmp_path / "t.jsonl", STAGES["s4_2"], s).run()
    assert _briefed(s.turns) == ["nwc", "debt_like"]  # the Lead said stop after the second
    assert [r for r, _, _ in s.turns] == ["lead", "investigator", "lead", "investigator", "lead"]


def _routes(trace) -> list[dict]:
    return [r["args"] for r in _rows(trace) if r["tool"] == "route"]


def test_the_router_reads_the_document_that_moves_the_walk_away_most_per_page_one_investigator_each(data, tmp_path):
    plan = [_issue("nwc", 0.3), _issue("debt_like", 0.6)]
    s = scripted(lead=lead_says((plan, True)), investigator=finds_nothing)
    p = Panel(_room(data), 40, tmp_path / "a.jsonl", Config(challenger=False, sweep=False), s)
    p.record.plan(plan)
    cands = list(p.record.weights(p.pages, set()))
    scores = p.record.rank_docs(p.pages, set(), cands)
    first = min(cands, key=lambda d: (-scores[d], p.pages[d], d))
    p.run()
    routes = _routes(tmp_path / "a.jsonl")
    assert routes[0]["doc"] == first and len(routes) >= 2  # the Lead's stop is ignored
    role, prompt, budget = s.turns[1]
    assert role == "investigator" and f"Brief: read {first} ({p.pages[first]:g} pages)." in prompt
    assert budget == p.pages[first] + 1 and "including ones not listed" in prompt  # a spare unit for a search
    assert all(f"- {t} ({t}): Current belief" in prompt for t in routes[0]["issues"])
    assert [r for r, _, _ in s.turns].count("lead") == 1  # nothing was committed, so no re-plan
    assert p.spent() == sum(p.pages[d] for d in p.read())  # route and submit rows are free, and not reads


def test_a_search_first_still_leaves_enough_to_open_the_document(data, tmp_path, monkeypatch):
    """The document budget used to be exactly its pages, so a search first left too little to open it, and the
    document was lost to `tried` for the rest of the run."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: float(d == "qoe" and not read) for d in docs})

    def searches_first(s, prompt):
        doc = re.search(r"Brief: read (\S+) \(", prompt).group(1)
        s.call("search", {"query": "customer contract"})
        s.call("open_document", {"doc_id": doc})
        s.call("report", {"findings": []})

    s = scripted(investigator=searches_first)
    p = Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s)
    p.record.plan([_issue("nwc", 0.5)])
    p.directed()
    assert "qoe" in p.read()
    assert f"Your reading budget: {p.pages['qoe'] + 1:g} units." in s.turns[0][1]


def test_when_no_document_can_move_the_walk_away_directed_reading_ends(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: dict.fromkeys(docs, 0.0))
    s = scripted(lead=lead_says(([_issue("nwc", 0.3)], False)), investigator=finds_nothing)
    Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s).run()
    assert [r for r, _, _ in s.turns] == ["lead"] and _routes(tmp_path / "t.jsonl") == []


def test_the_lead_re_plans_only_after_a_read_commits_something(data, tmp_path, monkeypatch):
    plan = [_issue("nwc", 0.5)]
    s = scripted(lead=lead_says((plan, False)), investigator=finds_nothing)
    Panel(_room(data), 30, tmp_path / "a.jsonl", Config(challenger=False, sweep=False), s).run()
    roles = [r for r, _, _ in s.turns]
    assert roles[0] == "lead" and roles.count("lead") == 1 and roles.count("investigator") >= 2
    monkeypatch.setattr(panel.Record, "apply", lambda self, commits: True)  # every read commits something
    s2 = scripted(lead=lead_says((plan, False)), investigator=finds_nothing)
    Panel(_room(data), 30, tmp_path / "b.jsonl", Config(challenger=False, sweep=False), s2).run()
    roles = [r for r, _, _ in s2.turns]
    assert roles == ["lead"] + ["investigator", "lead"] * roles.count("investigator")


def test_the_router_may_spend_the_sweep_s_reserve_on_the_document_it_ranks_first(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs",
                        lambda self, pages, read, docs, seed=0: {d: float(d == "audited") for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing)
    p = Panel(_room(data), 14, tmp_path / "t.jsonl", Config(challenger=False), s)
    assert p.avail() < p.pages["audited"] == p.budget
    p.run()
    role, prompt, budget = s.turns[1]
    assert role == "investigator" and budget == 14 and "Brief: read audited (14 pages)." in prompt


def test_with_the_router_an_objection_is_read_where_it_points_and_then_clears(data, tmp_path, monkeypatch):
    """Only credit, and only while debt_like's objection points there, moves the walk-away (a stand-in score)."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: float(d == "credit" and bool(self.entries["debt_like"].objections)) for d in docs})
    rounds = [{"objections": [{"type": "debt_like", "kind": "elsewhere", "chance": 0.9, "low": 0, "high": 90,
                               "docs": ["credit"], "reason": "the credit agreement lists a guarantee"}]},
              {"objections": []}]

    def challenger(sess, prompt):
        sess.call("challenge", rounds.pop(0) | {"pairs": [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                          for a, b in sess.pairs]})

    s = scripted(lead=lead_says(([_issue("debt_like", 0.2)], False)), investigator=finds_nothing,
                 challenger=challenger)
    Panel(_room(data), 60, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    # cleared by the read: no free re-check ("Find out") follows, and the second round has nothing to object to
    assert [r for r, _, _ in s.turns] == ["lead", "challenger", "investigator", "challenger"]
    assert [r["doc"] for r in _routes(tmp_path / "t.jsonl")] == ["credit"]
    prompt = s.turns[2][1]
    assert "Brief: read credit" in prompt and "The Challenger objects (elsewhere): the credit agreement" in prompt


def test_an_objection_on_documents_already_read_gets_one_free_look(data, tmp_path, monkeypatch):
    s = scripted(investigator=finds_nothing)
    p = Panel(_room(data), 0, tmp_path / "t.jsonl", STAGES["s4"], s)
    p.record.challenge([{"type": "debt_like", "kind": "elsewhere", "chance": 0.5, "low": 0, "high": 9,
                         "docs": ["legal"], "reason": "the letter lists a claim"}])
    monkeypatch.setattr(p, "read", lambda: {"legal"})
    p.directed()
    role, prompt, budget = s.turns[0]
    assert role == "investigator" and budget == 0 and "Find out: debt_like." in prompt
    assert "The Challenger objects (elsewhere): the letter lists a claim" in prompt
    assert "Look first at: legal." in prompt
    assert p.record.entries["debt_like"].objections == [] and len(s.turns) == 1


def test_the_brief_carries_the_flip_amount_where_to_look_and_a_sub_budget(data, tmp_path):
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5, docs=["legal"])], True)), investigator=finds_nothing)
    p = Panel(_room(data), 30, tmp_path / "t.jsonl", STAGES["s4_2"], s)
    p.run()
    role, prompt, budget = s.turns[1]
    assert role == "investigator" and "The engine's call flips if this issue is at least $" in prompt
    assert "Look first at: legal, audited." in prompt  # the Lead's document, then the diligence map's first
    assert budget == min(30, max(p.pages["legal"] + 2, math.ceil(0.5 * 30)))
    assert f"Your reading budget: {budget:g} units." in prompt


def test_an_objection_buys_one_more_look_and_a_checked_pair_becomes_two(data, tmp_path):
    plan = [_issue("debt_like", 0.5, docs=["legal"]), _issue("nwc", 0.5, docs=["qoe"])]
    rounds = [
        {"objections": [{"type": "debt_like", "kind": "elsewhere", "chance": 0.4, "low": 0, "high": 9,
                         "docs": ["audited"], "reason": "the notes list commitments"}],
         "pairs": [{"a": "debt_like", "b": "nwc", "answer": "check", "reason": "together"}]},
        {"objections": [], "pairs": []}]

    def challenger(sess, prompt):
        r = rounds.pop(0)
        sess.call("challenge", r | {"pairs": r["pairs"] or [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                             for a, b in sess.pairs]})

    s = scripted(lead=lead_says((plan, False)), investigator=finds_nothing, challenger=challenger)
    Panel(_room(data), 60, tmp_path / "t.jsonl", STAGES["s4_3"], s).run()
    assert _briefed(s.turns) == ["debt_like", "nwc", "debt_like", "nwc"]  # each once, then once more
    second = [p for r, p, _ in s.turns if r == "investigator"][2]
    assert "The Challenger objects (elsewhere): the notes list commitments" in second
    assert "Look first at: audited" in second
    assert [r for r, _, _ in s.turns].count("challenger") == 2


def test_the_sweep_reads_map_documents_in_untouched_domains_first_with_what_is_left(data, tmp_path):
    """S2: the sweep used to spend its pages on filler (it_policy, environmental) that never holds an issue."""
    s = scripted(lead=lead_says(([_issue("debt_like", docs=["legal"])], True)), investigator=finds_nothing)
    p = Panel(_room(data), 20, tmp_path / "t.jsonl", Config(challenger=False, router=False), s)
    p.run()
    role, prompt, budget = s.turns[-1]
    assert role == "investigator" and "which the panel has not read" in prompt
    picked = re.search(r"Brief: read (.*), which the panel", prompt).group(1).split(", ")
    domains = {d["id"]: d["domain"] for d in p.docs}
    assert "legal" not in picked and sum(p.pages[d] for d in picked) <= budget
    assert domains[picked[0]] != "legal"
    assert budget >= 0.1 * 20
    assert all(on_map(d) for d in picked) and not all(on_map(d) for d in p.pages)
    p.read = lambda: {d for d in p.pages if on_map(d)}  # the map is all read: no sweep turn
    n = len(s.turns)
    p.sweep()
    assert len(s.turns) == n


def test_an_objection_on_an_issue_nobody_proposed_is_due_its_look(data, tmp_path):
    p = Panel(_room(data), 20, tmp_path / "t.jsonl", STAGES["s4"], scripted())
    p.record.challenge([{"type": "capex", "kind": "elsewhere", "chance": 0.3, "low": 0, "high": 9, "docs": [],
                         "reason": "r"}])
    assert p.candidates() == ["capex"]


def test_a_timed_out_turn_is_skipped_and_a_usage_limit_stops_the_run(data, tmp_path):
    def timeout(*a):
        raise RunTimeout("slow")

    cli = Panel(_room(data), 20, tmp_path / "t.jsonl", STAGES["s4"], timeout).run()
    assert cli["timeouts"] >= 1 and _rows(tmp_path / "t.jsonl")[-1]["tool"] == "submit"

    def limit(*a):
        raise LLMUnavailable("usage limit")

    with pytest.raises(LLMUnavailable):
        Panel(_room(data), 20, tmp_path / "u.jsonl", STAGES["s4"], limit).run()


def test_the_tried_guard_holds_when_every_investigator_times_out(data, tmp_path):
    """Unlike a timed-out Lead (no plan, so nothing to route), a working Lead with every Investigator timing out
    must still route a different document each time, never the same one twice."""
    def times_out(s, prompt):
        raise RunTimeout("slow")

    s = scripted(lead=lead_says(([_issue("nwc", 0.5), _issue("debt_like", 0.5)], False)), investigator=times_out)
    cli = Panel(_room(data), 20, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s).run()
    docs = [r["doc"] for r in _routes(tmp_path / "t.jsonl")]
    assert docs and len(docs) == len(set(docs))
    assert cli["timeouts"] == len(docs)


def test_the_panel_sums_usage_over_its_turns(data, tmp_path):
    s = scripted(lead=lead_says(([_issue("nwc", docs=["qoe"])], True)), investigator=finds_nothing)
    cli = Panel(_room(data), 30, tmp_path / "t.jsonl", STAGES["s4_2"], s).run()
    assert cli["sessions"] == len(s.turns) == 3 and cli["usage"]["output_tokens"] == 21
    assert cli["num_turns"] == 6 and cli["modelUsage"] == {"claude-opus-5-5": {}} and cli["env_keys"] == ["HOME"]


def test_the_prompts_say_what_code_does_with_inputs_the_lead_s_list_and_stop():
    """F2: the op meanings and input order, exactly two inputs. F3: an issue left out is dropped. M1: code may reorder
    the reading and override stop."""
    from acqlab.agents import panel_prompts as prompts
    from acqlab.agents.server import PANEL_TOOLS
    for text in (prompts.INVESTIGATOR, PANEL_TOOLS["report"][0]):
        flat = " ".join(text.split())
        assert "exactly two" in flat and "two or more" not in flat
        assert all(s in flat for s in ("difference: [amount, amount subtracted]",
                                       "product: [amount in $M, percent or fraction]",
                                       "divide: [total, number of years]"))
    lead = " ".join(prompts.LEAD.split())
    assert "in the order you give" not in lead and "reorder" in lead and "override" in lead
    assert "left out is dropped" in lead


def test_an_objection_clears_only_when_its_document_is_actually_read(data, tmp_path, monkeypatch):
    """The objection used to clear once the router briefed its document, even if the Investigator never opened it."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: float(d == "qoe" and bool(self.entries["nwc"].objections)) for d in docs})

    def opens_nothing(s, prompt):
        s.call("report", {"findings": []})

    s = scripted(investigator=opens_nothing)
    p = Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s)
    p.record.challenge([{"type": "nwc", "kind": "elsewhere", "chance": 0.5, "low": 0, "high": 9,
                         "docs": ["qoe"], "reason": "r"}])
    p.directed()
    assert [r for r, _, _ in s.turns] == ["investigator"] and "Brief: read qoe" in s.turns[0][1]
    assert "qoe" not in p.read()
    assert p.record.entries["nwc"].objections != []  # unread: still pending, and no free re-check ran


def test_with_the_router_a_pair_objection_clears_on_any_read_that_may_settle_its_issue(data, tmp_path, monkeypatch):
    """A pair objection names no documents: any read with weight on its issue answers it, and it never gets the free
    re-check."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: float(d == "qoe" and bool(self.entries["nwc"].objections)) for d in docs})
    s = scripted(investigator=finds_nothing)
    p = Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s)
    p.record.challenge([{"type": "nwc", "kind": "pair", "chance": 0.5, "low": 0, "high": 9, "docs": [],
                         "reason": "with debt_like, it could flip the call"}])
    p.directed()
    assert [r for r, _, _ in s.turns] == ["investigator"] and "Brief: read qoe" in s.turns[0][1]
    assert p.record.entries["nwc"].objections == []


def test_with_the_challenger_the_first_pass_reads_only_the_first_half_and_objections_are_read_after(data, tmp_path,
                                                                                                    monkeypatch):
    """D3: cheap documents first (a stand-in score), only what fits in half the budget; then the Challenger objects and
    the document it names is read with the other half."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: 5.0 if d == "audited" and self.entries["debt_like"].objections else 1 / pages[d] for d in docs})
    rounds = [{"objections": [{"type": "debt_like", "kind": "elsewhere", "chance": 0.9, "low": 0, "high": 90,
                               "docs": ["audited"], "reason": "the notes list a guarantee"}]}, {"objections": []}]

    def challenger(sess, prompt):
        sess.call("challenge", rounds.pop(0) | {"pairs": [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                          for a, b in sess.pairs]})

    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing,
                 challenger=challenger)
    Panel(_room(data), 40, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    rows = _rows(tmp_path / "t.jsonl")
    first = next(i for i, r in enumerate(rows) if r["tool"] == "challenge")
    assert 18 <= sum(r["cost"] for r in rows[:first] if r["tool"] == "open_document") <= 20  # the first half, filled
    after = [r["args"]["doc"] for r in rows[first:] if r["tool"] == "route"]
    assert after[0] == "audited"  # the objection's document, read with the second half


def test_a_document_that_does_not_fit_the_first_half_waits_for_the_second(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs",
                        lambda self, pages, read, docs, seed=0: {d: float(d == "audited") for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing,
                 challenger=no_objections)
    Panel(_room(data), 20, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    assert [r for r, _, _ in s.turns][:3] == ["lead", "challenger", "investigator"]  # audited (14) > half of 20
    assert "Reading budget left: 20 units." in s.turns[1][1] and "Brief: read audited (14 pages)" in s.turns[2][1]


def test_without_the_challenger_directed_reading_runs_to_the_end(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: 1 / pages[d] for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing)
    p = Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s)
    p.run()
    assert p.spent() > 0.5 * 40 and "challenger" not in [r for r, _, _ in s.turns]


def test_without_the_challenger_the_router_keeps_the_two_pass_schedule(data, tmp_path, monkeypatch):
    """D3 addendum: the −Challenger ablation reads in the same order as S4 before the Challenger speaks, so H3
    compares only the objections: the first pass reads only what fits in half the budget, even with a bigger document
    scoring higher, and the bigger one is read in the second pass."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: {"audited": 5.0, "legal": 1.0}.get(d, 0.0) for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing)
    Panel(_room(data), 26, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s).run()
    routed = [r["args"]["doc"] for r in _rows(tmp_path / "t.jsonl") if r["tool"] == "route"]
    assert routed == ["legal", "audited"]  # audited (14) > half of 26: it waits for the second pass

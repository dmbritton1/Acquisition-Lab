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
    """An Investigator that reads the first suggested document it can afford and settles nothing."""
    looked = re.search(r"Look first at: ([^.]*)\.", prompt)
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


def test_the_router_ranks_by_regret_per_page_and_stops_below_the_veto(data, tmp_path, monkeypatch):
    plan = [_issue("nwc", 0.3), _issue("debt_like", 0.6)]
    s = scripted(lead=lead_says((plan, True)), investigator=finds_nothing, challenger=no_objections)
    p = Panel(_room(data), 40, tmp_path / "a.jsonl", Config(challenger=False, sweep=False), s)
    p.record.plan(plan)
    costs = {t: p.first_cost(t) for t in ("nwc", "debt_like")}
    scores = p.record.rank(["nwc", "debt_like"], costs)
    p.run()
    assert _briefed(s.turns)[0] == max(scores, key=scores.get)  # the Lead's stop doesn't end a router run
    monkeypatch.setattr(panel, "VETO", 1.0)  # nothing removes a whole asking price of regret per page
    s2 = scripted(lead=lead_says((plan, False)), investigator=finds_nothing)
    Panel(_room(data), 40, tmp_path / "b.jsonl", Config(challenger=False, sweep=False), s2).run()
    assert _briefed(s2.turns) == []


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


def test_with_the_router_an_objected_issue_the_lead_leaves_out_still_gets_its_extra_look(data, tmp_path):
    """R1: once the Challenger has objected, the Lead re-plans without nwc; nwc's objection still gets its look."""
    both = [_issue("debt_like", 0.5, docs=["legal"]), _issue("nwc", 0.5, docs=["qoe"])]
    rounds = [{"objections": [{"type": "debt_like", "kind": "bigger", "chance": 0.9, "low": 0, "high": 90, "docs": [],
                               "reason": "r"},
                              {"type": "nwc", "kind": "bigger", "chance": 0.7, "low": 0, "high": 60, "docs": [],
                               "reason": "r"}]},
              {"objections": []}]

    def challenger(sess, prompt):
        sess.call("challenge", rounds.pop(0) | {"pairs": [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                          for a, b in sess.pairs]})

    def lead(sess, prompt):
        issues = both if len(rounds) == 2 else [_issue("debt_like", 0.1, docs=["legal"])]  # nwc left out
        sess.call("propose", {"issues": issues, "stop": False, "reason": "r"})

    s = scripted(lead=lead, investigator=finds_nothing, challenger=challenger)
    Panel(_room(data), 80, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    roles = [r for r, _, _ in s.turns]
    after = _briefed(s.turns[roles.index("challenger"):])
    assert after == ["debt_like", "nwc"]  # the Lead dropped nwc after debt_like's look; its objection stands


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

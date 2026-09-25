import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import acqlab.agents.committer as committer
import acqlab.agents.record as record
import acqlab.agents.server as server
from acqlab.agents.knowledge import typical_high
from acqlab.agents.server import MAX_CALLS, ROLES, Session, tool_names
from acqlab.engine import walk_away
from acqlab.generator.batch import AnswerKey
from acqlab.generator.render import span
from acqlab.generator.traps import params_for
from acqlab.routers.beliefs import Issue, draw, walk_aways
from acqlab.routers.routers import score_regret

# F10: an audit hook, installed once (they can't be removed), that records `open` events only while _RECORDING is
# set. Used by test_the_server_only_opens_files_in_its_room to prove Session touches nothing outside its room.
_OPENED: list[str] = []
_RECORDING = False


def _audit(event: str, args: tuple) -> None:
    if _RECORDING and event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENED.append(os.fsdecode(args[0]))


sys.addaudithook(_audit)


def _key(data: Path) -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())


def _session(data, tmp_path, router=True, budget=None):
    key = _key(data)
    return Session(data / "deals" / "dev-000" / "room", budget or key.budget, tmp_path / "t.jsonl", router)


def _out(reply: dict):
    text = reply["content"][0]["text"]
    return text if reply["isError"] else json.loads(text)


def _trace(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "t.jsonl").read_text().splitlines()]


def test_the_server_speaks_mcp_over_stdio(data, tmp_path):
    room, trace = data / "deals" / "dev-000" / "room", tmp_path / "t.jsonl"
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_documents", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "submit", "arguments": {"go": True, "walk_away": 100, "reason": "r"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"}]
    proc = subprocess.run([sys.executable, "-m", "acqlab.agents.server", "--room", str(room), "--budget", "10",
                           "--trace", str(trace)], input="".join(json.dumps(m) + "\n" for m in msgs),
                          capture_output=True, text=True, timeout=60)
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5]  # the notification got no reply
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert [t["name"] for t in replies[1]["result"]["tools"]] == tool_names(router=False)
    assert "rank_issues" not in tool_names(router=False) and "rank_issues" in tool_names(router=True)
    assert json.loads(replies[2]["result"]["content"][0]["text"])[0]["id"] == "cim"
    assert replies[4]["error"]["code"] == -32601
    # F7: initialize now writes its own trace row first, so the pilot can tell "ran but called no tool" from
    # "never started" by whether the trace file is non-empty, even before any real tool call happens.
    assert [r["tool"] for r in map(json.loads, trace.read_text().splitlines())] == \
        ["initialize", "list_documents", "submit"]


def test_reading_is_charged_and_over_budget_calls_are_refused(data, tmp_path):
    s = _session(data, tmp_path, router=False, budget=5)
    opened = s.call("open_document", {"doc_id": "legal"})
    assert not opened["isError"] and "Litigation" in opened["content"][0]["text"]
    refused = s.call("open_document", {"doc_id": max(s.pages, key=s.pages.get)})
    assert refused["isError"] and "left" in _out(refused)
    rows = _trace(tmp_path)
    assert rows[0]["cost"] == s.pages["legal"] and rows[0]["remaining"] == 5 - s.pages["legal"]
    assert "result" not in rows[0]  # document text is not copied into the trace
    assert rows[1]["refused"] and rows[1]["cost"] == 0


def test_search_costs_one_unit_and_returns_document_ids_but_no_text(data, tmp_path):
    s = _session(data, tmp_path, router=False)
    assert "search" in tool_names(router=False) and "search" in tool_names(router=True)
    got = _out(s.call("search", {"query": "working capital peg"}))
    assert got and all(d in s.pages for d in got) and len(got) == len(set(got)) <= 5
    assert _trace(tmp_path)[0]["cost"] == 1.0 and "$" not in json.dumps(got)


def test_after_the_call_limit_only_submit_is_accepted_and_submit_ends_the_run(data, tmp_path):
    s = _session(data, tmp_path)
    for _ in range(MAX_CALLS):
        assert not s.call("list_documents", {})["isError"]
    assert "limit" in _out(s.call("list_documents", {}))
    assert _out(s.call("submit", {"go": False, "walk_away": 90.5, "reason": "r"})) == {"submitted": True}
    assert "over" in _out(s.call("evaluate", {"adjustments": {}}))


def test_evaluate_prices_dollar_adjustments_with_the_engine(data, tmp_path):
    key, s = _key(data), _session(data, tmp_path)
    face = _out(s.call("evaluate", {"adjustments": {}}))
    assert face["walk_away"] == pytest.approx(key.truth.face_walk_away, abs=0.01) and face["go"] == key.truth.face_go
    got = _out(s.call("evaluate", {"adjustments": {"debt_like": 5.0, "concentration": 3.0}}))
    want = walk_away(key.truth.deal, params_for({"debt_like": 5.0, "concentration": 3.0}, key.truth.base))
    assert got["walk_away"] == pytest.approx(want, abs=0.01)
    for bad in ({"debt_like": -1}, {"goodwill": 2}, {"nwc": "big"}):
        assert s.call("evaluate", {"adjustments": bad})["isError"]


def test_rank_issues_is_router_6_on_the_agents_own_notes(data, tmp_path):
    s = _session(data, tmp_path)
    s.call("note_issue", {"name": "add-back", "type": "addback", "chance": 0.4, "low": 0, "high": 8,
                          "docs": ["qoe", "audited"]})
    assert not s.call("open_document", {"doc_id": "contract_1"})["isError"]  # allowed: an open note exists
    s.call("note_issue", {"name": "big client", "type": "concentration", "chance": 0.3, "low": 0, "high": 30,
                          "docs": ["contract_1", "cim"]})
    s.call("note_issue", {"name": "debt", "type": "debt_like", "chance": 1, "low": 2, "high": 4, "docs": ["legal"]})
    got = _out(s.call("rank_issues", {}))
    beliefs = {t: Issue(proposed=False) for t in ("addback", "debt_like", "concentration", "nwc", "capex")}
    hi = {t: max(h, typical_high(t, s.face.teaser)) for t, h in (("addback", 8), ("concentration", 30))}
    beliefs |= {"addback": Issue(p_real=0.4, hi=hi["addback"]), "concentration": Issue(p_real=0.3, hi=hi["concentration"]),
                "debt_like": Issue(known=(2, 4))}  # router v4: open ranges widen to the usual size
    values = draw(beliefs, server.N_WORLDS, np.random.default_rng(0))
    w = walk_aways(s.face, values)
    # router v3: each cost is the next unread document on the diligence map; contract_1 is read, so contract_2 is next
    costs = {"addback": s.pages["qoe"], "concentration": s.pages["contract_2"]}
    want = score_regret(values, w, s.face.deal.asking_price, costs, ["addback", "concentration"])
    assert {r["type"]: r["regret_removed_per_page"] for r in got["ranking"]} == {
        t: round(v, 4) for t, v in want.items()}
    assert {r["type"]: r["pages_to_check"] for r in got["ranking"]} == costs
    assert {r["type"]: r["next_doc"] for r in got["ranking"]} == {"addback": "qoe", "concentration": "contract_2"}
    assert {r["type"]: r["size_high_used"] for r in got["ranking"]} == {t: round(h, 2) for t, h in hi.items()}
    assert "rank_issues" in {r["tool"] for r in _trace(tmp_path)}


def test_rank_issues_is_refused_without_the_router(data, tmp_path):
    assert _session(data, tmp_path, router=False).call("rank_issues", {})["isError"]


def test_bad_notes_and_bad_arguments_are_tool_errors(data, tmp_path):
    s = _session(data, tmp_path)
    assert s.call("note_issue", {"name": "x", "type": "goodwill", "chance": 0.5, "low": 0, "high": 1, "docs": []})[
        "isError"]
    assert s.call("note_issue", {"name": "x", "type": "nwc", "chance": 0.5, "low": 3, "high": 1, "docs": []})[
        "isError"]
    assert s.call("open_document", {"doc_id": 12})["isError"]
    assert s.call("open_document", {"doc_id": "../../truth/dev-000"})["isError"]
    assert s.call("submit", {"go": "yes", "walk_away": 1, "reason": "r"})["isError"]
    assert s.call("delete_everything", {})["isError"]


def test_the_server_needs_nothing_outside_its_room(data, tmp_path):
    """Isolation: no answer-key types or paths in the source, and it runs on a room copied away from any keys."""
    for mod in (server, committer, record):  # the Committer and the Deal Record run inside the server
        source = Path(mod.__file__).read_text()
        assert not any(word in source for word in ("AnswerKey", "DealTruth", "truth")), mod.__name__
    room = shutil.copytree(data / "deals" / "dev-000" / "room", tmp_path / "alone" / "room")
    s = Session(room, 10, tmp_path / "t.jsonl", router=True)
    assert not s.call("evaluate", {"adjustments": {"capex": 1}})["isError"]


def test_a_malformed_evaluate_argument_is_a_tool_error_not_a_crash(data, tmp_path):
    """F2: {"adjustments": None} and {"adjustments": []} both reach `.items()` inside _amounts and used to raise an
    uncaught AttributeError, which would kill serve()'s loop and get scored by the pilot as B0 with status "ok"."""
    s = _session(data, tmp_path)
    assert s.call("evaluate", {"adjustments": None})["isError"]
    assert s.call("evaluate", {"adjustments": []})["isError"]
    assert not s.call("evaluate", {"adjustments": {}})["isError"]  # the session survives: a later call still works


def test_the_server_only_opens_files_in_its_room(data, tmp_path):
    """F10: an audit hook proves isolation directly, instead of only grepping the source for answer-key names."""
    global _RECORDING
    room = data / "deals" / "dev-000" / "room"
    trace = tmp_path / "t.jsonl"
    s = Session(room, 20, trace, router=True)
    _OPENED.clear()
    _RECORDING = True
    try:
        docs = _out(s.call("list_documents", {}))
        s.call("open_document", {"doc_id": docs[0]["id"]})
        s.call("evaluate", {"adjustments": {}})
        s.call("note_issue", {"name": "x", "type": "addback", "chance": 0.5, "low": 0, "high": 5, "docs": []})
        s.call("rank_issues", {})
        s.call("submit", {"go": True, "walk_away": 1.0, "reason": "r"})
    finally:
        _RECORDING = False
    assert _OPENED  # sanity: we actually captured some opens
    room_real, trace_real = os.path.realpath(room), os.path.realpath(trace)
    bases = tuple(os.path.realpath(b) + os.sep for b in (sys.prefix, sys.base_prefix))
    for p in _OPENED:
        if p.endswith((".py", ".pyc")):
            continue
        real = os.path.realpath(p)
        if real.startswith(bases):  # stdlib/interpreter imports, not room data
            continue
        assert real == trace_real or real == room_real or real.startswith(room_real + os.sep), p


def test_the_router_system_reads_only_with_an_open_note_and_sees_the_ranking(data, tmp_path):
    s = _session(data, tmp_path)
    assert "note_issue" in _out(s.call("open_document", {"doc_id": "legal"}))  # gated: nothing for the router to price
    s.call("note_issue", {"name": "debt", "type": "debt_like", "chance": 1, "low": 2, "high": 4, "docs": ["legal"]})
    assert s.call("open_document", {"doc_id": "legal"})["isError"]  # a confirmed note is not an open one
    noted = _out(s.call("note_issue", {"name": "add-back", "type": "addback", "chance": 0.4, "low": 0, "high": 8,
                                       "docs": ["qoe"]}))
    assert noted["router"]["ranking"][0]["type"] == "addback"
    text = s.call("open_document", {"doc_id": "legal"})["content"][0]["text"]
    assert "Litigation" in text and "Router ranking now:" in text
    (tmp_path / "plain").mkdir()
    plain = _session(data, tmp_path / "plain", router=False)
    assert "router" not in _out(plain.call("note_issue", {"name": "a", "type": "addback", "chance": 0.4, "low": 0,
                                                          "high": 8, "docs": ["qoe"]}))
    assert "Router" not in plain.call("open_document", {"doc_id": "legal"})["content"][0]["text"]


def _role(data, tmp_path, role, budget=10, paid=(), pairs=()):
    return Session(data / "deals" / "dev-000" / "room", budget, tmp_path / "t.jsonl", False, role, paid, pairs)


def test_each_panel_role_is_offered_only_its_own_tools(data, tmp_path):
    room, trace = data / "deals" / "dev-000" / "room", tmp_path / "t.jsonl"
    for role, tools in ROLES.items():
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
        proc = subprocess.run([sys.executable, "-m", "acqlab.agents.server", "--room", str(room), "--budget", "0",
                               "--trace", str(trace), "--role", role], input=json.dumps(msgs[0]) + "\n",
                              capture_output=True, text=True, timeout=60)
        assert [t["name"] for t in json.loads(proc.stdout)["result"]["tools"]] == tools
    assert tool_names(False, "lead") == ["propose"] and "submit" not in tool_names(False, "investigator")
    assert _session(data, tmp_path, router=False).call("report", {"findings": []})["isError"]  # not an S1b tool
    assert _role(data, tmp_path, "lead").call("open_document", {"doc_id": "legal"})["isError"]


def test_a_document_already_paid_for_in_the_panel_run_is_free(data, tmp_path):
    s = _role(data, tmp_path, "investigator", budget=1, paid=("legal", "no_such_doc"))
    assert "Litigation" in s.call("open_document", {"doc_id": "legal"})["content"][0]["text"]
    assert _trace(tmp_path)[-1]["cost"] == 0 and s.room.remaining == 1
    assert s.call("open_document", {"doc_id": "cim"})["isError"]  # not paid for, and over this budget


def test_report_goes_through_the_committer_and_ends_the_turn_only_when_accepted(data, tmp_path):
    ev = next(e for e in _key(data).evidence if e.trap == "debt_like")  # dev-000: an unresolvable range
    assert ev.formula == "range"
    s = _role(data, tmp_path, "investigator", budget=40)
    for d in ev.docs:  # contradicted: one document states the range, the other claims there is nothing
        s.call("open_document", {"doc_id": d})
    stated = span(ev.values["low"], ev.values["high"])
    doc, line = next((d, x.strip()) for d in ev.docs for x in s.room._text(d).splitlines() if stated in x)
    bad = s.call("report", {"findings": [{"type": "debt_like", "status": "value", "value": 1.0,
                                          "quotes": [{"doc_id": doc, "text": "a sentence that is not there"}]}]})
    assert bad["isError"] and "Committer refused" in _out(bad) and not s.submitted
    assert s.call("report", {"findings": [{"type": "nwc", "status": "open", "chance": 0.1, "low": 0, "high": 1},
                                          {"type": "nwc", "status": "open", "chance": 0.1, "low": 0, "high": 1}]})[
        "isError"]  # one finding per type
    good = _out(s.call("report", {"findings": [
        {"type": "debt_like", "status": "range", "low": ev.values["low"], "high": ev.values["high"],
         "quotes": [{"doc_id": doc, "text": line}]},
        {"type": "nwc", "status": "not_found", "docs": [doc]}]}))
    assert [c["kind"] for c in good["commits"]] == ["range", "not_found"]
    assert (good["commits"][0]["low"], good["commits"][0]["high"]) == (ev.values["low"], ev.values["high"])
    assert s.submitted and "over" in _out(s.call("list_documents", {}))
    assert _trace(tmp_path)[-2]["result"]["commits"] == good["commits"]


def test_propose_checks_the_issue_list(data, tmp_path):
    s = _role(data, tmp_path, "lead")
    issue = {"type": "nwc", "name": "peg", "chance": 0.3, "low": 0, "high": 4, "docs": ["qoe"]}
    assert s.call("propose", {"issues": [issue, issue], "stop": False, "reason": "r"})["isError"]
    assert s.call("propose", {"issues": [issue | {"low": 5}], "stop": False, "reason": "r"})["isError"]
    assert s.call("propose", {"issues": [issue | {"type": "fraud"}], "stop": False, "reason": "r"})["isError"]
    assert _out(s.call("propose", {"issues": [issue], "stop": True, "reason": "r"})) == {"planned": 1}
    assert s.submitted


def test_the_challenger_must_answer_every_flagged_pair(data, tmp_path):
    s = _role(data, tmp_path, "challenger", pairs=(("debt_like", "nwc"),))
    objection = {"type": "nwc", "kind": "bigger", "chance": 0.3, "low": 0, "high": 9, "docs": ["audited"],
                 "reason": "r"}
    missing = s.call("challenge", {"objections": [objection], "pairs": []})
    assert missing["isError"] and "debt_like+nwc" in _out(missing)
    assert s.call("challenge", {"objections": [objection | {"kind": "vibes"}], "pairs": []})["isError"]
    assert not s.call("evaluate", {"adjustments": {"nwc": 9}})["isError"]  # the engine, to test what flips
    got = _out(s.call("challenge", {"objections": [objection], "pairs": [
        {"a": "nwc", "b": "debt_like", "answer": "check", "reason": "r"}]}))
    assert got == {"objections": 1, "checks": 1} and s.submitted


def test_after_the_call_limit_a_panel_role_can_still_make_its_closing_call(data, tmp_path):
    s = _role(data, tmp_path, "investigator")
    for _ in range(MAX_CALLS):
        s.call("list_documents", {})
    assert "call report now" in _out(s.call("list_documents", {}))
    assert not s.call("report", {"findings": []})["isError"]

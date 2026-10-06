import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.agents.knowledge import typical_high
from acqlab.bench import pilot, recon
from acqlab.generator.batch import AnswerKey


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _note(t, chance, low, high):
    return {"name": t, "type": t, "chance": chance, "low": low, "high": high, "docs": []}


def _session(go, reads=(), cost=4.0, notes=()):
    rows = [_row("open_document", {"doc_id": d}, cost) for d in reads] + [_row("note_issue", n) for n in notes]
    return rows + ([_row("submit", {"go": go, "walk_away": 100.0, "reason": "r"})] if go is not None else [])


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


@pytest.fixture
def fakes(monkeypatch, room):
    """Every step replaced by one that writes a scripted trace (scripts[step]; none scripted = a timeout) and records
    its arguments (calls[step]); `engine` is the engine-priced analyst's call."""
    f = {"docs": [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]],
         "scripts": {}, "calls": {}, "engine": None}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        f["calls"][name] = (args, kw)
        if name not in f["scripts"]:
            raise recon.RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        return {"total_cost_usd": 0.1, "usage": {"output_tokens": 5}}

    for fn in ("draft", "second", "judge"):
        monkeypatch.setattr(recon, fn, run)
    monkeypatch.setattr(recon, "engine_call", lambda room_, trace: f["engine"])
    return f


def test_notes_become_a_record_as_the_team_prices_them(room):
    trace = [_row("note_issue", _note("addback", 0.5, 1, 2)), _row("note_issue", _note("addback", 0.4, 0, 3)),
             _row("note_issue", _note("debt_like", 1.0, 4, 6))]
    rec = recon.notes_record(room, trace)
    add, debt, nwc = (rec.issue(t) for t in ("addback", "debt_like", "nwc"))
    assert add.p_real == 0.4 and add.known is None and add.hi == max(3.0, typical_high("addback", rec.face.teaser))
    assert debt.known == (4.0, 6.0)
    assert not nwc.proposed  # no note: no problem


def test_the_engine_call_is_the_record_s_and_needs_a_submit(room):
    trace = [_row("note_issue", _note("concentration", 1.0, 30, 30))]
    assert recon.engine_call(room, trace) is None
    trace.append(_row("submit", {"go": True, "walk_away": 1.0, "reason": "x"}))
    go, wa = recon.notes_record(room, trace).decide()
    assert recon.engine_call(room, trace) == {"go": go, "walk_away": wa, "reason": "the engine, on the analyst's notes"}


def test_c_gives_the_drafter_70_percent_and_the_referee_what_is_left(fakes, room, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"draft": _session(True, d[:2]), "second": _session(False), "referee": _session(False)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, _ = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["draft"][0][1] == pytest.approx(14.0)
    _, views, read, deal, left = fakes["calls"]["referee"][0]
    assert read == d[:2] and left == pytest.approx(12.0) and deal == "dev-000"
    assert recon.spent(trace) <= 20.0


def test_a_gives_each_scout_half_scout_2_the_router_and_the_referee_what_is_left(fakes, room, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"scout1": _session(True, d[:2]), "scout2": _session(False, d[1:3]),
                         "referee": _session(True)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    recon.run_a(room, 20.0, "dev-000", tmp_path / "x.json")
    (_, b1), kw1 = fakes["calls"]["scout1"]
    (_, b2), kw2 = fakes["calls"]["scout2"]
    assert b1 == b2 == pytest.approx(10.0) and kw2.get("router") is True and not kw1.get("router")
    _, views, read, deal, left = fakes["calls"]["referee"][0]
    assert read == d[:3] and left == pytest.approx(4.0)  # a page both scouts read counts twice


def test_a_referee_with_nothing_left_still_decides(fakes, room, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"scout1": _session(True, d[:2], cost=5.0), "scout2": _session(False, d[2:4], cost=5.0),
                         "referee": _session(False)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, _ = recon.run_a(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["referee"][0][4] == 0.0 and recon.call_of(trace)["go"] is False


def test_the_second_opinion_gets_the_drafter_s_documents_never_its_work(fakes, room, tmp_path):
    d = fakes["docs"]
    secret = _note("addback", 0.5, 0, 9) | {"name": "SECRET"}
    fakes["scripts"] |= {"draft": _session(True, d[:1], notes=[secret]), "second": _session(True)}
    fakes["engine"] = {"go": True, "walk_away": 1.0}
    recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["second"] == ((room, d[:1]), {})
    system, user = recon.second_prompts(room, d[:1])
    assert f"({d[0]})" in user and f"({d[1]})" not in user and "SECRET" not in system + user


def test_an_agreement_stands_without_a_referee(fakes, room, tmp_path):
    fakes["scripts"] |= {"draft": _session(True), "second": _session(False)}
    fakes["engine"] = {"go": True, "walk_away": 90.0}
    trace, cli = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    assert "referee" not in fakes["calls"] and cli["sessions"] == 2
    assert recon.call_of(trace) == {"go": True, "walk_away": 100.0, "reason": "the analysts agree"}


def test_a_disagreement_or_any_missing_call_goes_to_the_referee(fakes, room, tmp_path):
    cases = [({"draft": _session(False), "second": _session(True)}, {"go": True, "walk_away": 1.0}),
             ({"second": _session(True)}, {"go": True, "walk_away": 1.0}),  # the drafter timed out
             ({"draft": _session(True), "second": _session(None, notes=[_note("nwc", 0.5, 0, 1)])}, None)]  # the second opinion never submitted
    for scripts, engine in cases:
        fakes["calls"].clear()
        fakes["scripts"] = scripts | {"referee": _session(False)}
        fakes["engine"] = engine
        trace, _ = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
        assert "referee" in fakes["calls"] and recon.call_of(trace)["go"] is False


def test_the_combined_trace_scores_like_one_run(fakes, room, data, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"draft": _session(True, d[:2]), "second": _session(False),
                         "referee": _session(False, d[2:3], cost=3.0)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, cli = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    row = pilot.score(key, "recon_c", trace, cli, "ok")
    assert row["pages"] == 11.0 and row["go"] is False and row["answered"]
    assert sum(r["tool"] == "submit" for r in trace) == 1 and sum(r["tool"] == "step_submit" for r in trace) == 3
    assert row["cost_usd"] == pytest.approx(0.3) and row["sessions"] == 3 and row["tokens"]["output_tokens"] == 15


def test_a_referee_without_a_call_leaves_the_deal_unanswered(fakes, room, data, tmp_path):
    fakes["scripts"] |= {"draft": _session(True), "second": _session(False)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, cli = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    assert not pilot.score(key, "recon_c", trace, cli, "no_call")["answered"]
    assert cli["sessions"] == 3 and cli["timeouts"] == 1


def test_the_runner_refuses_without_confirmation_and_rejects_unknown_designs(tmp_path):
    assert recon.main(["--data", str(tmp_path)]) == 3
    assert recon.main(["--data", str(tmp_path), "--designs", "recon_b", "--confirm-claude"]) == 1


def test_both_designs_run_end_to_end_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    engine = recon.engine_call  # every engine-priced call flipped, so every deal reaches the referee's real session
    monkeypatch.setattr(recon, "engine_call", lambda room, trace: c and c | {"go": not c["go"]}
                        if (c := engine(room, trace)) else c)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    rows = recon.run(d, list(recon.DESIGNS), split="dev", claude=fake_claude)
    assert len(rows) == 2 * len(json.loads((d / "splits.json").read_text())["dev"])
    for r in rows:
        trace = recon.referee.rows(d / "runs" / r["system"] / f"{r['deal']}.trace.jsonl")
        assert r["answered"] and r["spent"] <= r["budget"]
        assert r["disputed"] and r["sessions"] == 3 and any(x["step"] == "referee" for x in trace)
    assert recon.run(d, list(recon.DESIGNS), split="dev", claude=fake_claude) == []  # finished runs are skipped


def test_no_step_reads_the_answer_key():
    source = Path(recon.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))


def test_the_pick_follows_the_fixed_rules():
    def rows(regret, cost=0.2, answered=40, spent=10.0):
        return {f"d{i}": {"regret": regret, "cost_usd": cost, "answered": i < answered, "spent": spent,
                          "budget": 20.0} for i in range(40)}

    base = {"s1b": rows(0.02), "s4": rows(0.015)}
    p = recon.pick(base | {"recon_c": rows(0.010), "recon_a": rows(0.012)})
    assert p["chosen"] == "recon_c" and p["go"] and not p["tied"]
    p = recon.pick(base | {"recon_c": rows(0.010), "recon_a": rows(0.0104, cost=0.1)})
    assert p["tied"] and p["chosen"] == "recon_a"  # within 0.0005: the cheaper one
    assert not recon.pick(base | {"recon_c": rows(0.016), "recon_a": rows(0.017)})["go"]  # not below the team
    p = recon.pick(base | {"recon_c": rows(0.010, answered=37), "recon_a": rows(0.012)})
    assert not p["mechanics"]["recon_c"]["passes"] and not p["go"]  # fewer than 38 of 40 answered
    p = recon.pick(base | {"recon_c": rows(0.010), "recon_a": rows(0.012, spent=20.5)})
    assert p["mechanics"]["recon_a"]["over_budget"] == 40 and not p["go"]


def test_claude_stopping_mid_deal_writes_no_row_and_exits_2(data, tmp_path, monkeypatch):
    d = tmp_path / "d"
    shutil.copytree(data, d)

    def stop(*a, **kw):
        raise recon.LLMUnavailable("usage limit")

    monkeypatch.setitem(recon.RUN, "recon_c", stop)
    assert recon.main(["--data", str(d), "--designs", "recon_c", "--split", "dev", "--confirm-claude"]) == 2
    assert not list((d / "runs" / "recon_c").glob("*.json"))  # a rerun redoes the whole deal


def test_the_analysis_script_reads_a_finished_pilot(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    d = tmp_path / "d"
    shutil.copytree(data, d)
    recon.run(d, list(recon.DESIGNS), split="dev", claude=fake_claude)
    for s in ("s1b", "s4"):  # stand-ins for the baselines: the design's own runs
        shutil.copytree(d / "runs" / "recon_c", d / "runs" / s)
    script = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "recon_pilot.py"))
    out = script["analyse"](d)
    assert out["deals"] == 2 and out["pick"]["chosen"] in recon.DESIGNS and not out["pick"]["go"]
    assert set(out["systems"]) == {"s1b", "s4", *recon.DESIGNS} and out["versus"]["recon_c"]["s1b"]["n"] == 2
    assert "scout1_real_reached" in out["designs"]["recon_a"] and "scout1_real_reached" not in out["designs"]["recon_c"]
    assert "nothing to size" in out["sizing"]["note"]
    assert "by_case" in out["systems"]["recon_c"] and sum(out["systems"]["recon_c"]["by_case"][ct]["n"] for ct in out["systems"]["recon_c"]["by_case"]) == 2
    assert script["main"](["--data", str(d), "--out", str(tmp_path / "x.json")]) == 0
    assert script["main"](["--data", str(d), "--out", str(tmp_path / "x.json")]) == 1  # never overwrites

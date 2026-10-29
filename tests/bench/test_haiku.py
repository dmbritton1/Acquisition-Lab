import hashlib
import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.agents.solver import RunTimeout
from acqlab.bench import haiku, pilot
from acqlab.bench.recon import notes_record
from acqlab.generator.batch import AnswerKey

RATES = {"addback": 0.3, "debt_like": 0.2, "concentration": 0.4, "nwc": 0.1, "capex": 0.2}


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _note(trap, chance, low=0.0, high=4.0):
    return _row("note_issue", {"name": trap, "type": trap, "chance": chance, "low": low, "high": high, "docs": []})


def _submit(go=True, wa=100.0):
    return _row("submit", {"go": go, "walk_away": wa, "reason": "r"})


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


@pytest.fixture
def docs(room):
    return [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]]


def _argv(fake_claude, room, tmp_path, effort=None):
    """The argv one solver.solve call (under on_haiku unless effort is False) hands the fake claude."""
    if effort is False:
        solver.solve(room, 5, tmp_path / "t.jsonl", False, claude=fake_claude)
    else:
        with haiku.on_haiku(effort):
            solver.solve(room, 5, tmp_path / "t.jsonl", False, claude=fake_claude)
    return json.loads((tmp_path / "args.json").read_text())["argv"]


# --- the model switch ----------------------------------------------------------------------------------------------

def test_on_haiku_runs_every_session_on_haiku_and_restores_opus(fake_claude, room, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    argv = _argv(fake_claude, room, tmp_path, None)
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5" and "--effort" not in argv
    argv = _argv(fake_claude, room, tmp_path, "low")
    assert argv[argv.index("--effort") + 1] == "low"
    argv = _argv(fake_claude, room, tmp_path, False)
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5" and "--effort" not in argv


def test_on_haiku_restores_opus_after_an_error():
    original = solver.command
    with pytest.raises(RuntimeError):
        with haiku.on_haiku():
            assert solver.command is not original
            raise RuntimeError("boom")
    assert solver.command is original


# --- the runner and its refusals -----------------------------------------------------------------------------------

def test_the_held_out_sets_are_refused_before_the_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(haiku, "FINAL", None)  # as before the freeze
    for name in haiku.TEST_SETS:
        with pytest.raises(haiku.Refused, match="held out"):
            haiku.run(tmp_path / name, ["haiku_solo"], split="dev")
    (tmp_path / "test-r2").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "test-r2")
    for path in (tmp_path / "alias", Path(f"{tmp_path / 'test-r2'}/")):
        with pytest.raises(haiku.Refused, match="held out"):
            haiku.run(path, ["haiku_solo"], split="dev")
    with pytest.raises(haiku.Refused, match="held out"):
        haiku.run(tmp_path / "cal-r2", ["haiku_solo"], split="test")  # a copy under another name keeps its split
    with pytest.raises(haiku.Refused, match="no frozen winner"):
        haiku.run(tmp_path / "test-r2", ["haiku_solo"], split="test", final=True)
    monkeypatch.setattr(haiku, "FINAL", "haiku_team")
    with pytest.raises(haiku.Refused, match="haiku_solo, haiku_team and haiku_team"):
        haiku.run(tmp_path / "test-r2", ["haiku_team", "haiku_other"], split="test", final=True)
    with pytest.raises(haiku.Refused, match="test split"):
        haiku.run(tmp_path / "test-r2", ["haiku_team"], split="dev", final=True)
    assert haiku.main(["--data", str(tmp_path / "pilot-r2u"), "--split", "test", "--confirm-claude"]) == 3


def test_the_runner_refuses_without_confirmation_and_rejects_unknown_systems(tmp_path):
    assert haiku.main(["--data", str(tmp_path / "cal-r2")]) == 3
    assert haiku.main(["--data", str(tmp_path), "--systems", "haiku_x", "--confirm-claude"]) == 1


def test_claude_stopping_mid_deal_writes_no_row_and_exits_2(data, tmp_path, monkeypatch):
    d = tmp_path / "d"
    shutil.copytree(data, d)

    def stop(*a, **kw):
        raise haiku.LLMUnavailable("usage limit")

    monkeypatch.setitem(haiku.CANDIDATES, "haiku_solo", haiku.Candidate(stop, ()))
    monkeypatch.setattr(haiku, "cli_version", lambda: "2.1.291")
    assert haiku.main(["--data", str(d), "--systems", "haiku_solo", "--confirm-claude"]) == 2
    assert not list((d / "runs" / "haiku_solo").glob("*.json"))


def test_solo_and_team_run_end_to_end_on_haiku_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    d = tmp_path / "d"
    shutil.copytree(data, d)
    rows = haiku.run(d, ["haiku_solo", "haiku_team"], deals=["dev-001"], claude=fake_claude)
    assert [(r["system"], r["deal"]) for r in rows] == [("haiku_solo", "dev-001"), ("haiku_team", "dev-001")]
    for r in rows:
        assert r["answered"] and r["status"] == "ok" and r["spent"] <= r["budget"] + 1e-9
        assert r["prompts"] == haiku.prompt_sha(r["system"]) and r["effort"] is None
    assert rows[0]["sessions"] == 1 and rows[1]["sessions"] > 1  # the team's own session count is kept
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert solver.command.__module__ == "acqlab.agents.solver"  # restored
    assert haiku.run(d, ["haiku_solo", "haiku_team"], deals=["dev-001"], claude=fake_claude) == []


def test_a_timed_out_solo_run_is_scored_as_a_timeout(data, tmp_path, monkeypatch):
    def late(*a, trace, **kw):
        trace.write_text(json.dumps(_row("open_document", {"doc_id": "qoe"}, 3.0)) + "\n")
        raise RunTimeout("late")

    monkeypatch.setattr(haiku, "draft", late)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    [row] = haiku.run(d, ["haiku_solo"], deals=["dev-000"])
    assert row["status"] == "timeout" and not row["answered"] and row["pages"] == 3.0


def test_each_candidate_records_its_own_prompt_fingerprint():
    shas = {n: haiku.prompt_sha(n) for n in haiku.CANDIDATES}
    assert len(set(shas.values())) == len(shas) and all(len(s) == 64 for s in shas.values())


def test_a_settings_or_effort_change_is_a_new_fingerprint(monkeypatch):
    lean = haiku.CANDIDATES["haiku_lean"]
    monkeypatch.setitem(haiku.CANDIDATES, "lean_w", haiku.Candidate(lean.run, lean.prompts,
                                                                     settings={"w": 0.3, "pricers": 3}))
    monkeypatch.setitem(haiku.CANDIDATES, "lean_low", haiku.Candidate(lean.run, lean.prompts, effort="low",
                                                                       settings=lean.settings))
    shas = {haiku.prompt_sha(n) for n in ("haiku_lean", "lean_w", "lean_low")}
    assert len(shas) == 3


def test_the_runner_refuses_an_old_cli_and_records_the_version(data, tmp_path, monkeypatch):
    d = tmp_path / "d"
    shutil.copytree(data, d)
    monkeypatch.setattr(haiku, "cli_version", lambda: "2.1.280")
    assert haiku.main(["--data", str(d), "--systems", "haiku_solo", "--confirm-claude"]) == 3
    assert haiku.too_old("garbage") and not haiku.too_old("2.1.291") and not haiku.too_old("2.2.0")

    def solo(room, budget, deal, out, **kw):
        return [_submit(True)], {"total_cost_usd": 0.01, "modelUsage": {"claude-haiku-5-5": {}}}

    monkeypatch.setitem(haiku.CANDIDATES, "haiku_solo", haiku.Candidate(solo, ()))
    [row] = haiku.run(d, ["haiku_solo"], deals=["dev-000"], cli="2.1.291")
    assert row["cli"] == "2.1.291"
    assert not list((d / "runs" / "haiku_solo").glob("*.tmp"))  # item 5: the row write leaves no temp file


def test_list_cost_prices_tokens_at_published_rates():
    tokens = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
              "cache_creation_input_tokens": 1_000_000}
    assert haiku.list_cost({"models": ["claude-haiku-5-5"], "tokens": tokens}) == pytest.approx(0.10 + 0.50 + 0.01 + 0.20)
    assert haiku.list_cost({"models": ["claude-opus-5-5"], "tokens": tokens}) == pytest.approx(4 + 20 + 0.20 + 8)  # Opus 5.5 cache reads are $0.20
    assert haiku.list_cost({"models": [], "tokens": tokens}) is None  # a run with no CLI result
    assert haiku.list_cost({"models": ["claude-opus-5-5", "claude-haiku-5-5"], "tokens": tokens}) is None


def test_no_step_reads_the_answer_key():
    source = Path(haiku.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))


# --- the lean pipeline ---------------------------------------------------------------------------------------------

def test_open_chances_are_pulled_toward_the_base_rate_and_settled_issues_are_not(room):
    trace = [_note("nwc", 0.4), _note("addback", 1.0, 2.0, 2.0), _note("capex", 0.0), _submit()]
    rec = haiku.calibrated_record(room, trace, RATES, 0.5)
    assert rec.entries["nwc"].chance == pytest.approx(0.5 * 0.4 + 0.5 * 0.1)
    assert rec.entries["capex"].chance == pytest.approx(0.5 * 0.2)
    assert rec.entries["addback"].known == (2.0, 2.0)
    assert haiku.calibrated_record(room, trace, RATES, 1.0).decide() == notes_record(room, trace).decide()


def test_a_pricer_without_a_call_gives_no_engine_call(room):
    assert haiku.calibrated_call(room, [_note("nwc", 0.4)], RATES, 0.5) is None
    call = haiku.calibrated_call(room, [_note("nwc", 0.4), _submit(False, 1.0)], RATES, 0.5)
    go, wa = haiku.calibrated_record(room, [_note("nwc", 0.4)], RATES, 0.5).decide()
    assert call["go"] == go and call["walk_away"] == pytest.approx(wa)  # the engine's, not the pricer's own


def test_the_vote_is_the_majority_at_the_median_walk_away():
    def c(go, wa):
        return {"go": go, "walk_away": wa, "reason": ""}

    assert haiku.vote([c(True, 90.0), c(True, 120.0), c(False, 80.0)]) | {"reason": ""} == c(True, 90.0)
    assert haiku.vote([c(True, 90.0), None, c(False, 80.0)])["go"] is False  # a tie is NO-GO
    assert haiku.vote([None, None, None]) is None


@pytest.fixture
def fakes(monkeypatch):
    """The reader and pricers replaced by sessions that write a scripted trace (scripts[step]; none scripted = a
    timeout) and record their arguments (calls[step])."""
    f = {"scripts": {}, "calls": {}}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        f["calls"][name] = (args, kw)
        if name not in f["scripts"]:
            raise RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        return {"total_cost_usd": 0.01, "usage": {"output_tokens": 5}, "modelUsage": {"claude-haiku-5-5": {}}}

    monkeypatch.setattr(haiku, "draft", run)
    monkeypatch.setattr(haiku, "second", run)
    return f


def test_lean_reads_once_at_the_full_budget_and_each_pricer_sees_what_was_read(fakes, room, docs, data, tmp_path):
    reads = [_row("open_document", {"doc_id": d}, 4.0) for d in docs[:2]]
    fakes["scripts"] |= {"reader": [*reads, _submit(False)], "pricer1": [_note("nwc", 0.9), _submit()],
                         "pricer2": [_note("nwc", 0.0), _submit()], "pricer3": [_note("nwc", 0.0), _submit()]}
    trace, cli = haiku.run_lean(room, 20.0, "dev-000", tmp_path / "x.json", w=0.5, pricers=3, rates=RATES)
    assert fakes["calls"]["reader"][0][1] == 20.0
    assert all(fakes["calls"][f"pricer{i}"][0][1] == docs[:2] for i in (1, 2, 3))
    calls = [haiku.calibrated_call(room, fakes["scripts"][f"pricer{i}"], RATES, 0.5) for i in (1, 2, 3)]
    assert cli["calls"] == {"reader": fakes["scripts"]["reader"][-1]["args"], "pricer1": calls[0],
                            "pricer2": calls[1], "pricer3": calls[2]}
    assert haiku.call_of(trace) == haiku.vote(calls) and cli["sessions"] == 4
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    row = pilot.score(key, "haiku_lean", trace, cli, "ok")
    assert row["pages"] == 8.0 and haiku.spent(trace) <= 20.0 and row["models"] == ["claude-haiku-5-5"]


def test_lean_without_any_pricer_call_leaves_the_deal_unanswered(fakes, room, tmp_path):
    fakes["scripts"] |= {"reader": [_submit(True)], "pricer2": [_note("nwc", 0.5)]}  # 1 and 3 time out
    trace, cli = haiku.run_lean(room, 20.0, "dev-000", tmp_path / "x.json", w=0.5, pricers=3, rates=RATES)
    assert haiku.call_of(trace) is None and cli["timeouts"] == 2
    assert cli["calls"] == {"reader": fakes["scripts"]["reader"][0]["args"], "pricer1": None, "pricer2": None,
                            "pricer3": None}


def test_lean_runs_end_to_end_on_haiku_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    monkeypatch.setattr(haiku, "load_rates", lambda: RATES)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    [row] = haiku.run(d, ["haiku_lean"], deals=["dev-001"], claude=fake_claude)
    assert row["answered"] and row["sessions"] == 4 and row["spent"] <= row["budget"] + 1e-9
    assert row["settings"] == {"w": 0.5, "pricers": 3} and set(row["calls"]) == {"reader", "pricer1", "pricer2",
                                                                                 "pricer3"}


# --- the base rates ------------------------------------------------------------------------------------------------

def test_base_rates_are_the_share_of_deals_where_each_problem_is_real(data, tmp_path):
    from acqlab.generator.traps import TRAPS
    d = tmp_path / "cal-r2"
    shutil.copytree(data, d)
    keys = [AnswerKey.model_validate_json(p.read_text()) for p in sorted((d / "truth").glob("*.json"))]
    out = haiku.base_rates([d])
    assert out["deals"] == ["cal-r2/dev-000", "cal-r2/dev-001"]
    for t in TRAPS:
        real = [f.amount > 0 for k in keys for f in k.truth.facts if f.trap == t]
        assert out["rates"][t] == pytest.approx(sum(real) / len(real))
    with pytest.raises(haiku.Refused, match="practice deals only"):
        haiku.base_rates([d, tmp_path / "pilot-r2u"])


def test_the_committed_base_rates_come_from_the_90_practice_deals_only():
    from acqlab.generator.traps import TRAPS
    out = json.loads(haiku.RATES.read_text())
    assert set(out["rates"]) == set(TRAPS) and all(0 < r < 1 for r in out["rates"].values())
    assert len(out["deals"]) == 90 and {d.split("/")[0] for d in out["deals"]} == set(haiku.PRACTICE)


# --- tuning round 1: pricers settle an issue at zero when a document finds no problem ------------------------------

def test_the_zero_rule_adds_one_sentence_to_the_pricers_prompt(room, docs, tmp_path, monkeypatch):
    from acqlab.bench.recon import SECOND_SYSTEM, second_prompts
    sentence = haiku.ZERO_RULE + " "
    assert "settles it at zero" in haiku.SECOND_ZERO and haiku.SECOND_ZERO.replace(sentence, "") == SECOND_SYSTEM
    seen = {}
    monkeypatch.setattr(haiku, "run_session", lambda *a, **kw: seen.update(a=a, kw=kw) or {})
    haiku.second_zero(room, docs[:2], trace=tmp_path / "t.jsonl", claude="x")
    room_, budget, trace, user, system, tools, server_args = seen["a"]
    assert budget == 0 and tools == ["note_issue", "submit"] and server_args == [] and seen["kw"] == {"claude": "x"}
    assert user == second_prompts(room, docs[:2])[1] and "settles it at zero" in system and haiku.GUIDE in system


def test_lean_zero_prices_with_the_zero_rule_and_keeps_lean_s_fingerprint(fakes, room, docs, tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("the original pricer must not run")

    monkeypatch.setattr(haiku, "second_zero", haiku.second)  # the fake session
    monkeypatch.setattr(haiku, "second", boom)
    fakes["scripts"] |= {"reader": [_submit(True)], **{f"pricer{i}": [_note("nwc", 1.0, 0, 0), _submit()]
                                                         for i in (1, 2, 3)}}
    lean = haiku.CANDIDATES["haiku_lean_zero"]
    trace, cli = haiku.run_lean(room, 20.0, "dev-000", tmp_path / "x.json", rates=RATES, **lean.settings)
    assert cli["sessions"] == 4 and haiku.call_of(trace) is not None
    assert lean.settings == {"w": 0.5, "pricers": 3, "zero": True}
    assert lean.prompts == haiku.SOLO + (haiku.SECOND_ZERO,)
    assert haiku.CANDIDATES["haiku_lean"].settings == {"w": 0.5, "pricers": 3}  # round 0's rows stay valid


def test_round_2_prices_open_issues_at_the_base_rate():
    zero, w0 = haiku.CANDIDATES["haiku_lean_zero"], haiku.CANDIDATES["haiku_lean_zero_w0"]
    assert w0.settings == zero.settings | {"w": 0.0} and w0.prompts == zero.prompts and w0.run is zero.run
    assert haiku.prompt_sha("haiku_lean_zero_w0") != haiku.prompt_sha("haiku_lean_zero")


# --- tuning round 3: the reader settles a disclosed exposure first -------------------------------------------------

def test_the_flag_reader_adds_one_instruction_and_otherwise_matches_single_claude(room, tmp_path, monkeypatch):
    from acqlab.agents.prompts import user_prompt
    from acqlab.agents.server import tool_names
    assert haiku.READER_FLAG.replace(haiku.FLAG_RULE, "") == haiku.SOLO[0] and "worst case" in haiku.FLAG_RULE
    seen = {}
    monkeypatch.setattr(haiku, "run_session", lambda *a, **kw: seen.update(a=a, kw=kw) or {})
    haiku.draft_flag(room, 21.0, trace=tmp_path / "t.jsonl", claude="x")
    room_, budget, trace, user, system, tools, server_args = seen["a"]
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    assert budget == 21.0 and user == user_prompt(teaser, 21.0) and system == haiku.READER_FLAG
    assert tools == tool_names(False) and server_args == [] and seen["kw"] == {"claude": "x"}


def test_lean_flag_reads_with_the_flag_reader(fakes, room, tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("the plain reader must not run")

    monkeypatch.setattr(haiku, "draft_flag", haiku.draft)  # the fake session
    monkeypatch.setattr(haiku, "draft", boom)
    monkeypatch.setattr(haiku, "second_zero", haiku.second)
    fakes["scripts"] |= {"reader": [_submit(True)], **{f"pricer{i}": [_submit()] for i in (1, 2, 3)}}
    lean = haiku.CANDIDATES["haiku_lean_flag"]
    _, cli = haiku.run_lean(room, 20.0, "dev-000", tmp_path / "x.json", rates=RATES, **lean.settings)
    assert cli["sessions"] == 4 and fakes["calls"]["reader"][0][1] == 20.0
    assert lean.settings == haiku.CANDIDATES["haiku_lean_zero_w0"].settings | {"flag_first": True}
    assert lean.prompts == (haiku.READER_FLAG, haiku.SECOND_ZERO)


# --- the freeze (docs/results/haiku-team-prereg.md) ----------------------------------------------------------------

def _rendered(room):
    """Every prompt the frozen winner's steps send on a fixed room: the reader's and a pricer's (system, user)."""
    from acqlab.agents.prompts import user_prompt
    from acqlab.bench.recon import second_prompts
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    reader = (haiku.SOLO_SYSTEM, user_prompt(teaser, 20))
    pricer = (haiku.SECOND_ZERO.format(guide=haiku.GUIDE), second_prompts(room, ["qoe", "legal", "audited"])[1])
    return [hashlib.sha256("\x00".join(p).encode()).hexdigest() for p in (reader, pricer)]


def test_the_frozen_winner_and_its_prompts_are_unchanged(s4_fake_run):
    room, _ = s4_fake_run
    assert haiku.FINAL == "haiku_lean_zero_w0"
    assert {n: haiku.prompt_sha(n) for n in ("haiku_solo", "haiku_team", haiku.FINAL)} == {
        "haiku_solo": "61a5b3c4b56351dbde8482c919746f86c3ce7b252dd50635950677f35f2a61a1",
        "haiku_team": "8cc19f35fa1749bd54212d4593562b3ba995a593a5541a5e8d666e91d03d5372",
        "haiku_lean_zero_w0": "e46bcea53f89772f2616b3bd43f6d77c8519929e698fd558b0da4aef05763feb"}
    assert hashlib.sha256(haiku.RATES.read_bytes()).hexdigest() == \
        "88a261b3d60411b17081c9b9c9a445ae6c8dcffa94e21d2d0f7d3728c8435616"
    assert _rendered(room) == ["768614d8b453c4ba1b9dfea119e2d1c036fbb06d7e4f47ebd01fd6b42058b9d6",
                               "a0b6e914355b122f9c2ebb41744ae11a8c9728c4dc005b96443a41a9f4fa1ffb"]

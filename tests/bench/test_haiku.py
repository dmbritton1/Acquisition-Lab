import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.agents.solver import RunTimeout
from acqlab.bench import haiku


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


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


def test_no_step_reads_the_answer_key():
    source = Path(haiku.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))

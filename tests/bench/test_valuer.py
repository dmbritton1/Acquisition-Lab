import json
from pathlib import Path

import pytest

from acqlab.bench import valuer


def test_the_replay_rebuilds_s4_s_final_record_and_its_call(s4_fake_run):
    room, trace = s4_fake_run
    rec = valuer.replay(room, trace)
    submit = next(r for r in trace if r["tool"] == "submit")["args"]
    assert rec.decide() == (submit["go"], pytest.approx(submit["walk_away"]))
    assert all(not e.objections for e in rec.entries.values())  # cleared, as Panel.run clears them


def test_the_no_engine_prompt_holds_no_engine_output_and_llm_decides_gets_the_engine_s_walk_away(s4_fake_run):
    room, trace = s4_fake_run
    rec = valuer.replay(room, trace)
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    median = f"${rec.decide()[1]:,.1f}M"
    system, user = valuer.prompts(rec, teaser, "s4_noengine")
    assert teaser in user and "engine" not in (system + user).lower() and median not in user
    assert "- addback" in user and "- capex" in user  # the team's findings, one line per issue type
    system, user = valuer.prompts(rec, teaser, "s4_llmdecides")
    assert f"median ${rec.decide()[1]:,.1f}M" in user and "engine's median" in system


def test_the_valuer_reads_no_answer_key():
    source = Path(valuer.__file__).read_text()
    assert not any(word in source for word in ("AnswerKey", "DealTruth", "truth"))


def test_a_valuer_turn_may_only_submit_and_has_no_reading_budget(s4_fake_run, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    room, trace = s4_fake_run
    out = tmp_path / "v.trace.jsonl"
    cli = valuer.value(room, valuer.replay(room, trace), "s4_noengine", out, claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--allowedTools") + 1] == "mcp__room__submit" and cli["total_cost_usd"] == 0.5
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert any(r["tool"] == "submit" for r in rows) and not any(r["cost"] and not r["refused"] for r in rows)

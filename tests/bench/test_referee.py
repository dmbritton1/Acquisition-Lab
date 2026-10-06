import json
from pathlib import Path

from acqlab.bench import referee


def _solo(doc="qoe", go=True):
    return [{"tool": "open_document", "args": {"doc_id": doc}, "cost": 9.0, "refused": False},
            {"tool": "note_issue", "args": {"type": "addback", "name": "one-offs", "chance": 0.5, "low": 1, "high": 4,
                                            "docs": [doc]}, "refused": False},
            {"tool": "evaluate", "args": {"adjustments": {"addback": 2}}, "result": {"walk_away": 101.5},
             "refused": False},
            {"tool": "submit", "args": {"go": go, "walk_away": 101.5, "reason": "solo reason"}, "refused": False}]


def test_the_referee_sees_both_analysts_and_every_document_either_read(s4_fake_run):
    room, team = s4_fake_run
    titles = {d["id"]: d["title"] for d in json.loads((room / "index.json").read_text())["documents"]}
    solo_doc = next(d for d in titles if d not in referee.opened(team))
    system, user = referee.prompts(room, team, _solo(solo_doc), "dev-000")
    for d in set(referee.opened(team)) | {solo_doc}:
        assert f"## {titles[d]} ({d})" in user
    assert not any(f"({d})\n" in user for d in titles if d not in set(referee.opened(team)) | {solo_doc})
    assert "solo reason" in user and "Engine's current call" in user and "# Analyst 1" in user
    assert "opposite calls" in system


def test_the_analysts_order_is_fixed_per_deal_and_varies_across_deals(s4_fake_run):
    room, team = s4_fake_run
    first = [referee.prompts(room, team, _solo(), f"test-{i:03d}")[1].split("# Analyst 2")[0] for i in range(20)]
    solo_first = ["solo reason" in f for f in first]
    assert 0 < sum(solo_first) < 20
    assert referee.prompts(room, team, _solo(), "test-007")[1] == referee.prompts(room, team, _solo(), "test-007")[1]


def test_the_referee_prompt_reads_no_answer_key():
    source = Path(referee.__file__).read_text()
    body = source.split("def run(")[0]  # everything before scoring
    assert not any(word in body for word in ("AnswerKey(", "truth", "model_validate"))


def test_a_referee_turn_may_only_evaluate_and_submit(s4_fake_run, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    room, team = s4_fake_run
    referee.judge(room, team, _solo(), "dev-000", tmp_path / "r.trace.jsonl", claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--allowedTools") + 1] == "mcp__room__evaluate,mcp__room__submit"


def test_only_deals_where_the_calls_differ_are_disputed(tmp_path):
    for s, calls in (("s4", {"a": True, "b": False, "c": True}), ("s1b", {"a": True, "b": True})):
        (tmp_path / "runs" / s).mkdir(parents=True)
        for d, go in calls.items():
            (tmp_path / "runs" / s / f"{d}.json").write_text(json.dumps({"go": go}))
    assert referee.disputed(tmp_path) == ["b"]


def test_without_confirmation_nothing_runs(tmp_path):
    assert referee.main(["--data", str(tmp_path)]) == 1


def test_a_solo_run_that_never_submitted_says_so():
    assert "ended without submitting" in referee.solo_view(_solo()[:-1])


def test_a_reading_referee_is_told_its_budget_and_the_kill_test_s_is_not(s4_fake_run):
    room, team = s4_fake_run
    views = [referee.solo_view(_solo()), referee.solo_view(_solo(go=False))]
    closed, _ = referee.build(room, views, ["qoe"], "dev-000")
    reading, user = referee.build(room, views, ["qoe"], "dev-000", left=6.5)
    assert referee.NO_READING in closed and referee.NO_READING not in reading
    assert "a budget of 6.5 units" in reading and reading.replace(referee.READING.format(left=6.5), "") == \
        closed.replace(referee.NO_READING, "")
    assert "## " in user and "(qoe)" in user


def test_a_reading_referee_gets_its_budget_the_reading_tools_and_the_paid_documents(s4_fake_run, tmp_path,
                                                                                     monkeypatch):
    room, team = s4_fake_run
    seen = {}
    monkeypatch.setattr(referee, "run_session", lambda *a, **kw: seen.update(a=a, kw=kw) or {"total_cost_usd": 0})
    referee.judge_reading(room, ["one", "two"], ["qoe", "cim", "qoe"], "dev-000", 7.0, tmp_path / "t.jsonl",
                          claude="x")
    room_, budget, trace, user, system, tools, server_args = seen["a"]
    assert budget == 7.0 and tools == referee.READ_TOOLS and server_args == ["--paid", "qoe,cim"]
    assert seen["kw"] == {"claude": "x"}

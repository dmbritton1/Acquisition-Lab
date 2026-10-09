import functools
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents.solver import RunTimeout, solve
from acqlab.bench import debate, pilot
from acqlab.generator.batch import AnswerKey


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _session(go, reads=(), cost=4.0, reason="r"):
    rows = [_row("open_document", {"doc_id": d}, cost) for d in reads]
    return rows + ([_row("submit", {"go": go, "walk_away": 100.0, "reason": reason})] if go is not None else [])


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


@pytest.fixture
def docs(room):
    return [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]]


@pytest.fixture
def seen(monkeypatch):
    """run_session replaced by one that records its arguments and returns a CLI result."""
    out = {}
    monkeypatch.setattr(debate, "run_session", lambda *a, **kw: out.update(a=a, kw=kw) or {"total_cost_usd": 0})
    return out


def test_the_bull_reads_with_its_budget_and_the_reader_s_documents_are_paid(room, docs, seen, tmp_path):
    debate.bull(room, 4.5, [docs[1], docs[0], docs[1]], "VIEW", trace=tmp_path / "t.jsonl", claude="x")
    room_, budget, trace, user, system, tools, server_args = seen["a"]
    assert budget == 4.5 and tools == debate.BULL_TOOLS and server_args == ["--paid", f"{docs[1]},{docs[0]}"]
    assert "a budget of 4.5 units" in system and "VIEW" in user and seen["kw"] == {"claude": "x"}


def test_a_bull_after_a_reader_who_read_nothing_has_no_paid_documents(room, seen, tmp_path):
    debate.bull(room, 4.0, [], "VIEW", trace=tmp_path / "t.jsonl")
    assert seen["a"][6] == []


def test_the_bear_and_the_referee_have_no_budget_and_no_reading_tools(room, docs, seen, tmp_path):
    debate.bear(room, docs[:2], "READER", "CASE", trace=tmp_path / "t.jsonl")
    assert seen["a"][1] == 0 and seen["a"][5] == debate.BEAR_TOOLS and seen["a"][6] == []
    debate.judge(room, docs[:2], {"reader": "A", "bull": "B", "bear": "C"}, "dev-000", trace=tmp_path / "t.jsonl")
    assert seen["a"][1] == 0 and seen["a"][5] == debate.JUDGE_TOOLS and seen["a"][6] == []
    assert not {"list_documents", "search", "open_document"} & set(debate.BEAR_TOOLS + debate.JUDGE_TOOLS)


def test_the_bull_sees_the_reader_s_documents_and_view_and_nothing_else(room, docs):
    titles = {d["id"]: d["title"] for d in json.loads((room / "index.json").read_text())["documents"]}
    system, user = debate.bull_prompts(room, 3.0, [docs[2]], "READER VIEW")
    assert f"## {titles[docs[2]]} ({docs[2]})" in user and f"({docs[0]})\n" not in user
    assert "READER VIEW" in user and "case for buying" in user and "already paid for" in system


def test_the_bear_answers_the_case_for_buying_over_both_sides_documents(room, docs):
    system, user = debate.bear_prompts(room, [docs[0], docs[3]], "READER VIEW", "BULL CASE")
    assert f"({docs[0]})" in user and f"({docs[3]})" in user and f"({docs[1]})\n" not in user
    assert "READER VIEW" in user and "BULL CASE" in user and "cannot read anything else" in system


def test_the_referee_sees_every_document_and_all_three_summaries(room, docs):
    views = {"reader": "READER VIEW", "bull": "BULL CASE", "bear": "BEAR CASE"}
    system, user = debate.judge_prompts(room, docs[:3], views, "dev-000")
    assert all(f"({d})" in user for d in docs[:3]) and all(v in user for v in views.values())
    assert all(f"# {t}" in user for t in debate.TITLES.values()) and "no case" in system


def test_the_summaries_order_is_fixed_per_deal_and_varies_across_deals(room):
    views = {"reader": "READER VIEW", "bull": "BULL CASE", "bear": "BEAR CASE"}

    def first(deal):
        user = debate.judge_prompts(room, [], views, deal)[1]
        return min(views.values(), key=user.index)

    firsts = [first(f"test-{i:03d}") for i in range(30)]
    assert set(firsts) == set(views.values())  # each side is first on some deal
    assert first("test-007") == first("test-007")


def test_every_prompt_carries_the_shared_rules():
    for template, fields in ((debate.BULL, {"budget": 2}), (debate.BEAR, {}), (debate.REFEREE, {})):
        text = debate.system(template, **fields)
        assert "seller's marketing" in text and "costs the difference" in text and debate.GUIDE in text
    assert set(debate.PROMPT_SHA) == {"shared", "bull", "bear", "referee"}
    assert all(len(h) == 64 for h in debate.PROMPT_SHA.values())


def test_the_frozen_prompts_are_unchanged(s4_fake_run):
    """The debate pilot's freeze (docs/results/debate-pilot-prereg.md): the four templates and everything each step
    sees around them, rendered on a fixed room. The views come from referee.solo_view, pinned by test_referee."""
    room, _ = s4_fake_run
    views = {"reader": "READER VIEW", "bull": "BULL CASE", "bear": "BEAR CASE"}

    def h(prompts):
        return hashlib.sha256("\x00".join(prompts).encode()).hexdigest()

    assert debate.PROMPT_SHA == {
        "shared": "5a90675be76cfd91e3e0a64cf09e402d905c83d47d8148e1b88362f91201f601",
        "bull": "87b139f56a22be4a9440f84aa28eee87db08bc1c8506ff0cb0d2f7f2baee9824",
        "bear": "5e0ed69d1f33616a646a020f1c3bcdd24a73a08913cdfb04bff0993b321c238e",
        "referee": "b61b9ea729dc1506358b84b908f85690ac29733f22e0cce18d0b04bba9ebd270"}
    assert h(debate.bull_prompts(room, 4.5, ["qoe", "legal"], views["reader"])) == \
        "df9b47eb98b6da4ab8f70734e42e38f85248b86ecbff7c8463a3b3cf0568e19d"
    assert h(debate.bear_prompts(room, ["qoe", "legal", "audited"], views["reader"], views["bull"])) == \
        "0b8017de1888aee165981dc7663eff4b720575ccaf4960e58fd6604f77644f28"
    assert h(debate.judge_prompts(room, ["qoe", "legal", "audited"], views, "test-007")) == \
        "9a218e0291a466d7e2e3b3995d08bb9c7ad4352289e1622fa744a6f089461ac9"

def test_no_step_reads_the_answer_key():
    source = Path(debate.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))


# --- the systems and the runner ------------------------------------------------------------------------------------

@pytest.fixture
def fakes(monkeypatch, room):
    """Every step replaced by one that writes a scripted trace (scripts[step]; none scripted = a timeout) and records
    its arguments (calls[step])."""
    f = {"scripts": {}, "calls": {}}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        f["calls"][name] = (args, kw)
        if name not in f["scripts"]:
            raise RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        return {"total_cost_usd": 0.1, "usage": {"output_tokens": 5}, "modelUsage": {"claude-opus-5-5": {}},
                "env_keys": ["HOME", "PATH"]}

    for fn in ("draft", "bull", "bear", "judge"):
        monkeypatch.setattr(debate, fn, run)
    return f


def _s1b(runs: Path, deal: str, trace: list[dict], status="ok"):
    """A finished s1b run beside the debate's runs, as pilot.run writes one; the debate's runs directory too."""
    for s in ("s1b", "debate_x"):
        (runs / s).mkdir(parents=True, exist_ok=True)
    (runs / "s1b" / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    (runs / "s1b" / f"{deal}.json").write_text(json.dumps({
        "status": status, "tokens": {"output_tokens": 7}, "cost_usd": 0.2, "num_turns": 3, "duration_ms": 10,
        "models": ["claude-opus-5-5"], "env_keys": ["HOME"]}))


def test_x_reuses_the_s1b_run_and_gives_the_bull_a_fifth_on_top(fakes, room, docs, data, tmp_path):
    runs = tmp_path / "runs"
    _s1b(runs, "dev-000", _session(False, docs[:2], cost=9.0))
    fakes["scripts"] |= {"bull": _session(True, docs[2:3], cost=4.0), "bear": _session(False),
                         "referee": _session(True)}
    trace, cli = debate.run_x(room, 20.0, "dev-000", runs / "debate_x" / "dev-000.json")
    (_, left, read, view), _ = fakes["calls"]["bull"]
    assert left == pytest.approx(4.0) and read == docs[:2] and "NO-GO" in view
    assert "draft" not in fakes["calls"]  # no new reader
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    row = pilot.score(key, "debate_x", trace, cli, "ok")
    assert row["pages"] == 22.0 and row["cost_usd"] == pytest.approx(0.5) and row["sessions"] == 4
    assert row["tokens"]["output_tokens"] == 7 + 3 * 5 and row["models"] == ["claude-opus-5-5"]
    assert {r["step"] for r in trace} == {"reader", "bull", "bear", "referee", "final"}
    assert cli["calls"]["reader"]["go"] is False and cli["calls"]["referee"]["go"] is True
    assert cli["step_cost"] == {"reader": 0.2, "bull": 0.1, "bear": 0.1, "referee": 0.1}


def test_x_stops_without_a_finished_s1b_run(fakes, room, tmp_path):
    with pytest.raises(FileNotFoundError, match="s1b"):
        debate.run_x(room, 20.0, "dev-000", tmp_path / "runs" / "debate_x" / "dev-000.json")
    assert not fakes["calls"]


def test_x_counts_a_timed_out_s1b_run_as_a_timed_out_step(fakes, room, docs, tmp_path):
    runs = tmp_path / "runs"
    _s1b(runs, "dev-000", _session(None, docs[:1]), status="timeout")
    fakes["scripts"] |= {"bull": _session(True), "bear": _session(False), "referee": _session(True)}
    _, cli = debate.run_x(room, 20.0, "dev-000", runs / "debate_x" / "dev-000.json")
    assert cli["timeouts"] == 1 and cli["calls"]["reader"] is None and cli["step_cost"]["reader"] is None


def test_s_gives_the_reader_80_percent_and_the_bull_what_is_left(fakes, room, docs, tmp_path):
    fakes["scripts"] |= {"reader": _session(True, docs[:3], cost=4.0), "bull": _session(True, docs[3:4], cost=4.0),
                         "bear": _session(False), "referee": _session(False)}
    trace, _ = debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["reader"][0][1] == pytest.approx(16.0)
    (_, left, read, _), _ = fakes["calls"]["bull"]
    assert left == pytest.approx(8.0) and read == docs[:3]
    assert debate.spent(trace) <= 20.0


def test_the_bear_and_referee_get_every_document_read_so_far(fakes, room, docs, tmp_path):
    fakes["scripts"] |= {"reader": _session(True, docs[:2]), "bull": _session(True, [docs[1], docs[4]]),
                         "bear": _session(False), "referee": _session(False)}
    debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["bear"][0][1] == [docs[0], docs[1], docs[4]]
    (_, read, views, deal), _ = fakes["calls"]["referee"]
    assert read == [docs[0], docs[1], docs[4]] and deal == "dev-000" and set(views) == {"reader", "bull", "bear"}


def test_a_missing_case_is_stated_and_the_debate_goes_on(fakes, room, docs, tmp_path):
    fakes["scripts"] |= {"reader": _session(True, docs[:1]), "bear": _session(False), "referee": _session(False)}
    trace, cli = debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")  # the bull timed out
    assert "ended without submitting" in fakes["calls"]["bear"][0][3]
    assert "ended without submitting" in fakes["calls"]["referee"][0][2]["bull"]
    assert debate.call_of(trace)["go"] is False and cli["timeouts"] == 1 and cli["calls"]["bull"] is None


def test_a_referee_without_a_call_leaves_the_deal_unanswered(fakes, room, data, tmp_path):
    fakes["scripts"] |= {"reader": _session(True), "bull": _session(True), "bear": _session(False),
                         "referee": [_row("evaluate", {"adjustments": {}})]}
    trace, cli = debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    row = pilot.score(key, "debate_s", trace, cli, "no_call")
    assert not row["answered"] and row["go"] == key.truth.face_go
    assert sum(r["tool"] == "submit" for r in trace) == 0 and sum(r["tool"] == "step_submit" for r in trace) == 3


def test_the_runner_refuses_without_confirmation_and_rejects_unknown_systems(tmp_path):
    assert debate.main(["--data", str(tmp_path)]) == 3
    assert debate.main(["--data", str(tmp_path), "--systems", "debate_y", "--confirm-claude"]) == 1


def test_claude_stopping_mid_deal_writes_no_row_and_exits_2(data, tmp_path, monkeypatch):
    d = tmp_path / "d"
    shutil.copytree(data, d)

    def stop(*a, **kw):
        raise debate.LLMUnavailable("usage limit")

    monkeypatch.setitem(debate.RUN, "debate_s", stop)
    assert debate.main(["--data", str(d), "--systems", "debate_s", "--split", "dev", "--confirm-claude"]) == 2
    assert not list((d / "runs" / "debate_s").glob("*.json"))  # a rerun redoes the whole deal


def test_both_systems_run_end_to_end_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    d = tmp_path / "d"
    shutil.copytree(data, d)
    pilot.run(d, 2, ["s1b"], solver=functools.partial(solve, claude=fake_claude), split="dev")
    rows = debate.run(d, list(debate.SYSTEMS), split="dev", deals=["dev-001"], claude=fake_claude)
    assert [(r["system"], r["deal"]) for r in rows] == [("debate_x", "dev-001"), ("debate_s", "dev-001")]
    for r in rows:
        limit = r["budget"] * (1.2 if r["system"] == "debate_x" else 1.0)
        trace = debate.referee.rows(d / "runs" / r["system"] / "dev-001.trace.jsonl")
        assert r["answered"] and r["sessions"] == 4 and r["pages"] <= limit + 1e-9
        assert r["prompts"] == debate.PROMPT_SHA and set(r["calls"]) == {"reader", "bull", "bear", "referee"}
        assert [s for s in dict.fromkeys(x["step"] for x in trace)] == ["reader", "bull", "bear", "referee", "final"]
    assert not (d / "runs" / "debate_x" / "dev-000.json").exists()  # --deals limits the run
    assert debate.run(d, list(debate.SYSTEMS), split="dev", deals=["dev-001"], claude=fake_claude) == []

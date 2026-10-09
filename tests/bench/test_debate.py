import json
from pathlib import Path

import pytest

from acqlab.bench import debate


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


def test_no_step_reads_the_answer_key():
    source = Path(debate.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))

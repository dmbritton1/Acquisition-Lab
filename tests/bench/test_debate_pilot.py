import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import debate, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "debate_pilot.py"))
DEBATES = debate.SYSTEMS


@pytest.fixture(scope="module")
def r2u(tmp_path_factory):
    """Five r2u test deals: 2 relief, 1 confirmed, 2 ordinary."""
    d = tmp_path_factory.mktemp("r2u")
    assert batch.run(d, {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u") == []
    return d


def keys(d: Path) -> dict[str, AnswerKey]:
    return {p.stem: AnswerKey.model_validate_json(p.read_text()) for p in sorted((d / "truth").glob("*.json"))}


def submit(go: bool, step: str | None = None) -> dict:
    row = {"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}
    return row | {"step": step} if step else row


def write(d: Path, system: str, deal: str, trace: list[dict], extra: dict | None = None,
          models=("claude-opus-5-5",)) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    cli = {"total_cost_usd": 0.1, "sessions": 1, "modelUsage": {m: {} for m in models}}
    (out / f"{deal}.json").write_text(json.dumps(pilot.score(key, system, trace, cli, "ok") | (extra or {})))


@pytest.fixture
def finished(r2u, tmp_path):
    """A finished fake pilot. s1b and s4 are always right. In each debate the reader passes on every deal, the bull
    opens the settling document on the relief deals, and the referee is always right."""
    d = tmp_path / "d"
    shutil.copytree(r2u, d)
    for deal, key in keys(d).items():
        t = key.truth
        for s in ("s1b", "s4"):
            write(d, s, deal, [submit(t.go)])
        doc = SCRIPT["settling_doc"](key) if t.case_type == "relief" else None
        pages = {x["id"]: x["pages"] for x in json.loads((d / "deals" / deal / "room" / "index.json").read_text())
                 ["documents"]}
        bull = [{"tool": "open_document", "args": {"doc_id": doc}, "refused": False, "cost": pages[doc],
                 "step": "bull"}] if doc else []
        trace = [submit(False, "reader") | {"tool": "step_submit"}, *bull, submit(t.go, "final")]
        for s in DEBATES:
            write(d, s, deal, trace, {"budget": 20.0, "spent": 1.0, "prompts": debate.PROMPT_SHA,
                                      "calls": {"reader": {"go": False}, "bull": None, "bear": None,
                                                "referee": {"go": t.go}},
                                      "step_cost": {"reader": 0.1, "bull": None, "bear": 0.1, "referee": 0.1}})
    return d


def test_the_reading_follows_the_fixed_rule():
    ok = {s: {"passes": True} for s in DEBATES}
    regret = {"s1b": 0.010, "s4": 0.013, "debate_x": 0.008, "debate_s": 0.009}
    fgo = {"s1b": 0, "s4": 0, "debate_x": 1, "debate_s": 1}
    assert SCRIPT["reading"](regret, fgo, ok) == "debate helps at the same budget"
    assert SCRIPT["reading"](regret | {"debate_s": 0.010}, fgo, ok) == "debate helps only with extra pages"
    assert SCRIPT["reading"](regret, fgo | {"debate_s": 2}, ok) == "debate helps only with extra pages"  # 2 > 0 + 1
    assert SCRIPT["reading"](regret, fgo, ok | {"debate_s": {"passes": False}}) == \
        "debate helps only with extra pages"
    assert SCRIPT["reading"](regret | {"debate_s": 0.011, "debate_x": 0.010}, fgo, ok) == "debate doesn't help"


def test_the_mechanics_check_needs_38_of_40_answered_and_no_deal_past_its_limit():
    rows = [{"answered": i >= 2, "spent": 20.0, "budget": 20.0} for i in range(40)]
    assert SCRIPT["mechanics"](rows, 1.0) == {"n": 40, "answered": 38, "over_limit": 0, "passes": True}
    rows[2]["answered"] = False
    assert not SCRIPT["mechanics"](rows, 1.0)["passes"]
    rows = [{"answered": True, "spent": 23.0, "budget": 20.0} for _ in range(40)]
    assert SCRIPT["mechanics"](rows, 1.2)["passes"] and SCRIPT["mechanics"](rows, 1.0)["over_limit"] == 40


def test_overturned_calls_are_split_four_ways_and_by_group():
    def row(before, go, correct):
        return {"calls": {"reader": None if before is None else {"go": before}}, "go": go, "correct": correct}

    rows = {"a": row(False, True, True), "b": row(False, True, False), "c": row(True, False, True),
            "d": row(True, False, False), "e": row(True, True, True), "f": row(None, True, True)}
    groups = {"a": "relief", "b": "relief", "c": "confirmed", "d": "ordinary", "e": "ordinary", "f": "relief"}
    out = SCRIPT["overturned"](rows, groups)
    assert out["all"] == {"nogo_to_go_right": 1, "nogo_to_go_wrong": 1, "go_to_nogo_right": 1, "go_to_nogo_wrong": 1}
    assert out["relief"]["nogo_to_go_right"] == 1 and out["confirmed"]["go_to_nogo_right"] == 1
    assert out["no_reader_call"] == 1


def test_the_bull_finds_the_good_news_only_where_the_reader_had_not():
    def opens(doc, step):
        return {"tool": "open_document", "args": {"doc_id": doc}, "refused": False, "cost": 1.0, "step": step}

    traces = {"a": [opens("minutes", "bull")], "b": [opens("minutes", "reader"), opens("minutes", "bull")],
              "c": [opens("legal", "bull")]}
    assert SCRIPT["bull_found"](traces, {"a": "minutes", "b": "minutes", "c": "minutes"}, ["a", "b", "c"]) == 1


def test_the_analysis_reads_a_finished_pilot(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    ks = keys(finished)
    relief = sum(k.truth.case_type == "relief" for k in ks.values())
    gos = sum(k.truth.go for k in ks.values())
    assert relief == 2 and gos > 0
    assert out["deals"] == 5 and out["reading"] == "debate doesn't help"  # no lower regret than an always-right s1b
    assert all(out["mechanics"][s]["passes"] for s in DEBATES)
    assert out["overturned"]["debate_s"]["all"]["nogo_to_go_right"] == gos
    assert out["bull_found"] == {"debate_x": relief, "debate_s": relief}
    assert out["versus"]["debate_s"]["s1b"]["tied"] == 5 and out["x_minus_s"]["n"] == 5
    assert out["steps"]["debate_x"]["bull"]["cost"] is None and out["steps"]["debate_x"]["bear"]["cost"] == 0.1
    assert out["systems"]["debate_x"]["relief"]["n"] == relief and "decoy_pages" in out["systems"]["s4"]["all"]
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_the_analysis_refuses_a_system_missing_a_deal(finished, tmp_path):
    (finished / "runs" / "debate_s" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="debate_s.*test-001"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--data", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()


def test_the_analysis_refuses_another_model_or_unfrozen_prompts(finished):
    write(finished, "s4", "test-002", [submit(True)], models=("claude-sonnet-5-5",))
    with pytest.raises(ValueError, match="s4/test-002"):
        SCRIPT["analyse"](finished)
    write(finished, "s4", "test-002", [submit(True)])
    path = finished / "runs" / "debate_x" / "test-003.json"
    path.write_text(json.dumps(json.loads(path.read_text()) | {"prompts": {"bull": "old"}}))
    with pytest.raises(ValueError, match="frozen prompts.*debate_x/test-003"):
        SCRIPT["analyse"](finished)

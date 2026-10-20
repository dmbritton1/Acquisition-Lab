"""The Claude-facing steps: one tool-less call per step, checked by code, written to the deal folder."""
import json
import sys
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.app import steps
from acqlab.app.steps import Incomplete
from acqlab.app.claude import ask
from acqlab.app.ingest import ingest
from acqlab.app.prompts import HAIKU, READER
from acqlab.app.store import load, write
from acqlab.app.verify import FIELDS
from acqlab.llm import LLMUnavailable
from tests.conftest import make_full

FAKE = Path(__file__).parent / "fake_answer.py"

TEASER = "Revenue of $162.8M LTM, growing 7.7% a year. Tax rate is 30% on profits."
CIM = "The top customer left in March and was 12% of revenue. Adjusted EBITDA is $31.4M after add-backs."


def q(doc, text): return {"doc_id": doc, "text": text}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A deal with two docs, the fake claude, and the answers folder: (deal, fake, answers dir, args file)."""
    monkeypatch.setattr(solver, "ENV_KEEP", solver.ENV_KEEP + ("FAKE_CLAUDE", "FAKE_ARGS", "FAKE_ANSWERS"))
    answers, args = tmp_path / "answers", tmp_path / "args.json"
    answers.mkdir()
    monkeypatch.setenv("FAKE_ANSWERS", str(answers))
    monkeypatch.setenv("FAKE_ARGS", str(args))
    (tmp_path / "t.md").write_text(TEASER)
    (tmp_path / "c.md").write_text(CIM)
    deal = ingest(tmp_path / "home", "Cedar", 230.0, {"teaser": tmp_path / "t.md", "cim": tmp_path / "c.md"})
    exe = tmp_path / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    return deal, str(exe), answers, args


def settings():
    d = make_full()
    return {"financing": d.financing.model_dump(), "policy": d.policy.model_dump()}


def entry(value, status="quoted"): return {"value": value, "status": status, "quotes": [], "calc": "none", "inputs": [], "why": ""}


def save_numbers(deal, **blank):
    write(deal / "numbers.json", {"name": "Cedar", "industry": "x", "hints": [], "cost": 0,
                                  "numbers": {f: entry(None if f in blank else 0.1) for f in FIELDS}})


def test_ask_runs_claude_without_tools_in_an_empty_folder_and_extracts_the_json(setup):
    deal, fake, answers, args = setup
    (answers / "reader.txt").write_text('Here you go: {"a": 1} hope that helps')
    answer, cli = ask("p", READER, HAIKU, claude=fake)
    got = json.loads(args.read_text())
    argv = got["argv"]
    assert answer == {"a": 1} and cli["is_error"] is False and got["files"] == []
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--model") + 1] == HAIKU


def test_ask_without_json_fails_with_claude_s_text(setup):
    deal, fake, answers, args = setup
    (answers / "reader.txt").write_text("Sorry, I can't read that.")
    with pytest.raises(LLMUnavailable, match="can't read"):
        ask("p", READER, HAIKU, claude=fake)


def test_a_usage_limit_surfaces_claude_s_message(setup, monkeypatch):
    deal, fake, answers, args = setup
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    with pytest.raises(LLMUnavailable, match="usage limit"):
        steps.read(deal, claude=fake)


def test_read_fills_checked_numbers_and_keeps_what_the_analyst_set(setup):
    deal, fake, answers, args = setup
    mine = {**entry(0.25, "you")}
    write(deal / "numbers.json", {"numbers": {"tax_rate": mine}})
    (answers / "reader.txt").write_text(json.dumps({
        "name": "Cedar Harbor", "industry": "Distribution",
        "numbers": {"revenue_ltm": {"value": 162.8, "quotes": [q("teaser", "Revenue of $162.8M LTM")]},
                    "tax_rate": {"value": 0.3, "quotes": [q("teaser", "Tax rate is 30% on profits")]},
                    "growth": {"value": 0.5, "quotes": [q("teaser", "not in the teaser at all")]}},
        "worries": [{"type": "concentration", "note": "lost a customer",
                     "quotes": [q("cim", "The top customer left in March"), q("cim", "made up line of text")]},
                    {"type": "goodwill", "note": "x", "quotes": []}]}))
    out = steps.read(deal, claude=fake)
    assert out["numbers"]["revenue_ltm"]["status"] == "quoted" and out["numbers"]["growth"]["status"] == "blank"
    assert out["numbers"]["tax_rate"] == mine and set(out["numbers"]) == set(FIELDS)
    assert [(h["type"], len(h["quotes"]), h["dropped_quotes"]) for h in out["hints"]] == [("concentration", 1, 1)]
    assert out["name"] == "Cedar Harbor" and load(deal / "numbers.json") == out


def test_price_refuses_while_a_number_or_setting_is_blank(setup):
    deal, fake, answers, args = setup
    save_numbers(deal, da_pct=1)
    with pytest.raises(Incomplete, match="da_pct"):
        steps.price(deal, settings(), claude=fake)
    save_numbers(deal)
    s = settings()
    s["policy"]["exit_multiple"] = None
    with pytest.raises(Incomplete, match="exit_multiple"):
        steps.price(deal, s, claude=fake)


PRICED = {"worries": [
    {"type": "addback", "chance": 0.4, "low": 0, "high": 3, "reason": "recurring", "quotes": []},
    {"type": "debt_like", "chance": 1.5, "low": 0, "high": 3, "reason": "bad chance", "quotes": []},
    {"type": "goodwill", "chance": 0.1, "low": 0, "high": 1, "reason": "unknown type", "quotes": []},
    {"type": "concentration", "chance": 0.2, "low": 0, "high": 40, "reason": "lost customer",
     "quotes": [q("cim", "The top customer left in March"), q("cim", "invented quote that is not there")]},
    {"type": "nwc", "chance": "high", "low": 0, "high": 1, "reason": "x", "quotes": []}]}


def test_price_keeps_valid_worries_and_marks_the_rest_not_priced(setup):
    deal, fake, answers, args = setup
    save_numbers(deal)
    (answers / "pricer.txt").write_text(json.dumps(PRICED))
    out = steps.price(deal, settings(), claude=fake)
    w = out["worries"]
    assert w["addback"]["chance"] == 0.4 and "not_priced" in w["debt_like"] and "not_priced" in w["capex"]
    assert w["nwc"] == {"not_priced": "Opus's answer for it was not valid"}
    assert w["concentration"]["dropped_quotes"] == 1 and len(w["concentration"]["quotes"]) == 1
    assert "goodwill" not in w and w["capex"] == {"not_priced": "Opus gave none"} and out["cost"] > 0
    assert load(deal / "worries.json") == out


def test_second_look_writes_its_own_files_and_leaves_the_board_s_alone(setup):
    deal, fake, answers, args = setup
    save_numbers(deal)
    (answers / "reader.txt").write_text(json.dumps({"name": "n", "industry": "i", "numbers": {}, "worries": []}))
    (answers / "pricer.txt").write_text(json.dumps(PRICED))
    before = (deal / "numbers.json").read_text()
    out = steps.second_look(deal, settings(), claude=fake)
    assert (deal / "second_numbers.json").exists() and (deal / "second_worries.json").exists()
    assert (deal / "numbers.json").read_text() == before and not (deal / "worries.json").exists()
    assert set(out) == {"numbers", "worries"}


def test_the_estimate_prices_opus_above_haiku_and_the_second_look_highest(setup):
    deal = setup[0]
    r, p, s = (steps.estimate(deal, k) for k in ("read", "price", "second"))
    assert 0 < r < p < s


def test_each_step_records_its_cost(setup):
    deal, fake, answers, args = setup
    (answers / "reader.txt").write_text('{"numbers": {}}')
    assert steps.read(deal, claude=fake)["cost"] > 0

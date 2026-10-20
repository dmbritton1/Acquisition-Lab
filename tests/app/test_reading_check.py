"""The paid reading check, run here on the fake claude only."""
import json
import runpy
import sys
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.app.store import load
from tests.app.test_steps import PRICED, q

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "board_reading_check.py"))
FAKE = Path(__file__).with_name("fake_answer.py")
TEASER_LINE = "LTM revenue: $162.2M; revenue growth: 7.8% per year"
CAPEX_LINE = "Capex: 2.1% of revenue; net working capital: 15.0% of revenue"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(solver, "ENV_KEEP", solver.ENV_KEEP + ("FAKE_CLAUDE", "FAKE_ARGS", "FAKE_ANSWERS"))
    answers = tmp_path / "answers"
    answers.mkdir()
    monkeypatch.setenv("FAKE_ANSWERS", str(answers))
    monkeypatch.delenv("FAKE_ARGS", raising=False)
    exe = tmp_path / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    (answers / "reader.txt").write_text(json.dumps({"name": "n", "industry": "i", "worries": [], "numbers": {
        "revenue_ltm": {"value": 162.2, "quotes": [q("teaser", TEASER_LINE)]},
        "growth": {"value": 0.021, "quotes": [q("teaser", CAPEX_LINE)]}}}))  # quoted, but not the growth rate
    (answers / "pricer.txt").write_text(json.dumps(PRICED))
    return str(exe), answers


def run(data, tmp_path, claude, *extra):
    return SCRIPT["main"](["--data", str(data), "--n", "1", "--out", str(tmp_path / "out.json"),
                           "--home", str(tmp_path / "home"), "--claude", claude, *extra])


def test_the_check_refuses_held_out_sets_an_existing_out_and_a_home_in_a_checkout(data, tmp_path, fake):
    for name in ("test-r2", "pilot-r2u", "mix-test-3"):
        with pytest.raises(SystemExit):
            SCRIPT["main"](["--data", str(tmp_path / name), "--out", str(tmp_path / "o.json"), "--yes"])
    (tmp_path / "out.json").write_text("{}")
    with pytest.raises(SystemExit):
        run(data, tmp_path, fake[0], "--yes")
    with pytest.raises(SystemExit):
        SCRIPT["main"](["--data", str(data), "--out", str(tmp_path / "o.json"), "--home", str(Path(__file__).parents[2] / "data" / "x")])


def test_the_check_scores_fields_and_calls_with_fake_claude(data, tmp_path, fake):
    out = run(data, tmp_path, fake[0], "--yes")
    assert load(tmp_path / "out.json") == out
    assert out["fields"]["revenue_ltm"] == {"right": 1, "wrong": 0, "blank": 0}
    assert out["fields"]["growth"] == {"right": 0, "wrong": 1, "blank": 0}
    assert all(v == {"right": 0, "wrong": 0, "blank": 1} for k, v in out["fields"].items() if k not in ("revenue_ltm", "growth"))
    assert out["calls"]["right"] + out["calls"]["wrong"] == 1 and out["cost"] > 0 and len(out["deals"]) == 1
    assert not any((tmp_path / "home" / "deals").rglob("truth*"))  # the answer key never reaches the deal folder


def test_without_yes_it_prints_the_estimate_and_calls_nothing(data, tmp_path, fake, capsys):
    run(data, tmp_path, fake[0])
    assert "$" in capsys.readouterr().out and not (tmp_path / "out.json").exists()
    (fake[1] / "reader.txt").unlink()  # a call would now crash the fake
    run(data, tmp_path, fake[0])

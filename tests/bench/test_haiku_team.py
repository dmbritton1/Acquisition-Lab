import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import haiku, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "haiku_team.py"))
OPUS = "claude-opus-5-5"


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    """The two test sets in miniature: five r2 test deals in test-r2, five r2u test deals in pilot-r2u."""
    root = tmp_path_factory.mktemp("sets")
    batch.run(root / "test-r2", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2")
    batch.run(root / "pilot-r2u", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u")
    return root


def write(d: Path, system: str, deal: str, go: bool, model: str | None = None, cost: float | None = None,
          prompts: str | None = None, refused: int = 0) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    opus = system in ("s1b", "s4")
    trace = [{"tool": "open_document", "args": {"doc_id": "x"}, "refused": True, "cost": 0.0}] * refused + [
        {"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    cli = {"total_cost_usd": cost if cost is not None else 0.1 if opus else 0.01, "sessions": 1,
           "modelUsage": {model or (OPUS if opus else haiku.MODEL): {}}}
    row = pilot.score(key, system, trace, cli, "ok")
    if not opus:
        row |= {"budget": key.budget, "spent": 1.0, "prompts": prompts or haiku.prompt_sha(system)}
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    (out / f"{deal}.json").write_text(json.dumps(row))


def every(root: Path):
    for name in haiku.TEST_SETS:
        for deal in json.loads((root / name / "splits.json").read_text())["test"]:
            yield root / name, deal, AnswerKey.model_validate_json((root / name / "truth" / f"{deal}.json").read_text())


@pytest.fixture
def finished(sets, tmp_path, monkeypatch):
    """A finished fake final test with haiku_lean frozen: everyone is right except haiku_solo, always wrong, whose
    runs each refused one tool call."""
    monkeypatch.setattr(haiku, "FINAL", "haiku_lean")
    root = tmp_path / "r"
    shutil.copytree(sets, root)
    for d, deal, key in every(root):
        for s in ("s1b", "s4", "haiku_team", "haiku_lean"):
            write(d, s, deal, key.truth.go)
        write(d, "haiku_solo", deal, not key.truth.go, refused=1)
    return root


def test_the_verdict_follows_the_fixed_wording():
    assert SCRIPT["verdict"]({"ci95": [-0.004, -0.001]}) == "better"
    assert SCRIPT["verdict"]({"ci95": [0.001, 0.004]}) == "worse"
    assert SCRIPT["verdict"]({"ci95": [-0.002, 0.0031]}) == "no clear difference: at most 0.0031 worse"
    assert SCRIPT["verdict"]({"ci95": [0.0, 0.0]}) == "no clear difference: at most 0.0000 worse"


def test_the_comparisons_skip_a_system_compared_with_itself():
    assert SCRIPT["pairs"]("haiku_lean") == [("haiku_lean", "s1b"), ("haiku_lean", "s4"),
                                              ("haiku_lean", "haiku_solo"), ("haiku_team", "s4")]
    assert SCRIPT["pairs"]("haiku_solo") == [("haiku_solo", "s1b"), ("haiku_solo", "s4"), ("haiku_team", "s4")]


def test_the_analysis_reads_a_finished_final_test(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    assert out["winner"] == "haiku_lean" and out["systems"] == ["s1b", "s4", "haiku_solo", "haiku_team", "haiku_lean"]
    assert [out["sets"][n]["n"] for n in ("test-r2", "pilot-r2u", "all")] == [5, 5, 10]
    assert out["verdicts"] == dict.fromkeys(("test-r2", "pilot-r2u", "all"), "no clear difference: at most 0.0000 worse")
    assert out["sets_agree"]
    every_set = out["sets"]["all"]
    assert set(every_set["versus"]) == {"haiku_lean-s1b", "haiku_lean-s4", "haiku_lean-haiku_solo", "haiku_team-s4"}
    assert every_set["versus"]["haiku_lean-haiku_solo"]["won"] > 0  # haiku_solo is always wrong
    assert every_set["cost_ratio"]["s1b/haiku_lean"] == pytest.approx(10.0)
    assert set(every_set["cost_ratio"]) == {f"{o}/{h}" for o in ("s1b", "s4")
                                            for h in ("haiku_solo", "haiku_team", "haiku_lean")}
    solo = every_set["systems"]["haiku_solo"]["all"]
    assert solo["correct"] == 0 and solo["refused_calls"] == 10 and "decoy_pages" in solo
    assert sum(c["n"] for c in every_set["systems"]["s1b"]["by_case"].values()) == 10
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_the_sets_can_disagree(finished):
    for d, deal, key in every(finished):
        if d.name == "pilot-r2u":
            write(d, "haiku_lean", deal, not key.truth.go)
    out = SCRIPT["analyse"](finished)
    assert out["verdicts"]["test-r2"].startswith("no clear difference") and not out["sets_agree"]


def test_the_analysis_refuses_before_the_freeze(finished, monkeypatch, tmp_path):
    monkeypatch.setattr(haiku, "FINAL", None)
    with pytest.raises(ValueError, match="no frozen winner"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()


def test_the_analysis_refuses_a_missing_deal_another_model_or_unfrozen_prompts(finished):
    (finished / "pilot-r2u" / "runs" / "haiku_team" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="pilot-r2u: haiku_team.*test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "pilot-r2u", "haiku_team", "test-001", True, model=OPUS)
    with pytest.raises(ValueError, match="wrong model.*pilot-r2u/haiku_team/test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "pilot-r2u", "haiku_team", "test-001", True)
    write(finished / "test-r2", "s1b", "test-002", True, model=haiku.MODEL)
    with pytest.raises(ValueError, match="wrong model.*test-r2/s1b/test-002"):
        SCRIPT["analyse"](finished)
    write(finished / "test-r2", "s1b", "test-002", True)
    write(finished / "test-r2", "haiku_lean", "test-003", True, prompts="old")
    with pytest.raises(ValueError, match="frozen prompts.*test-r2/haiku_lean/test-003"):
        SCRIPT["analyse"](finished)


def test_the_analysis_refuses_a_run_without_its_trace(finished, tmp_path):
    (finished / "test-r2" / "runs" / "haiku_team" / "test-004.trace.jsonl").unlink()
    with pytest.raises(ValueError, match="without a trace.*test-r2/haiku_team/test-004"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()

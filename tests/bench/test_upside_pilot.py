import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "upside_pilot.py"))


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """Five r2u test deals: 2 relief, 1 confirmed, 2 ordinary."""
    d = tmp_path_factory.mktemp("r2u")
    assert batch.run(d, {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u") == []
    return d


def keys(d: Path) -> dict[str, AnswerKey]:
    return {p.stem: AnswerKey.model_validate_json(p.read_text()) for p in sorted((d / "truth").glob("*.json"))}


def opens(d: Path, deal: str, doc: str) -> dict:
    pages = {x["id"]: x["pages"] for x in json.loads((d / "deals" / deal / "room" / "index.json").read_text())
             ["documents"]}
    return {"tool": "open_document", "args": {"doc_id": doc}, "refused": False, "cost": pages[doc]}


def submit(go: bool, key: AnswerKey) -> dict:
    return {"tool": "submit", "args": {"go": go, "walk_away": key.truth.walk_away, "reason": ""}, "refused": False}


def write(d: Path, system: str, deal: str, key: AnswerKey, trace: list[dict]) -> None:
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    row = pilot.score(key, system, trace, {"total_cost_usd": 0.1, "sessions": 1, "modelUsage": {"claude-opus-5-5": {}}}, "ok")
    (out / f"{deal}.json").write_text(json.dumps(row))


@pytest.fixture
def finished(data, tmp_path):
    """A finished fake pilot. s1b reads each flagged deal's settling document and is always right. s4 prices every
    warning at 0.8 and passes on both relief deals: on the first it read the settling document, on the second not."""
    d = tmp_path / "d"
    shutil.copytree(data, d)
    relief = 0
    for deal, key in keys(d).items():
        t = key.truth
        flag = t.flag.trap if t.flag else None
        doc = SCRIPT["settling_doc"](key) if flag else None
        note = [{"tool": "note_issue", "args": {"type": flag, "chance": 0.8, "low": 0, "high": t.flag.bound,
                                                 "name": "x", "docs": []}, "refused": False}] if flag else []
        write(d, "s1b", deal, key, note + ([opens(d, deal, doc)] if doc else []) + [submit(t.go, key)])
        propose = [{"tool": "propose", "args": {"issues": [{"type": flag, "chance": 0.8, "low": 0, "high": t.flag.bound,
                                                             "name": "x", "docs": []}], "stop": False, "reason": ""},
                    "refused": False}] if flag else []
        if t.case_type == "relief":
            relief += 1
            write(d, "s4", deal, key, propose + ([opens(d, deal, doc)] if relief == 1 else []) + [submit(False, key)])
        else:
            write(d, "s4", deal, key, propose + [submit(t.go, key)])
    return d


def test_the_free_checks_pass_on_an_r2u_batch(data):
    out = SCRIPT["free_checks"](SCRIPT["keys"](data))
    assert out["counts"] == {"relief": 2, "confirmed": 1, "ordinary": 2} and out["engine_right"] == 5
    assert out["half_right"] == {"relief": 0, "confirmed": 1} and out["ignore_right"] == {"relief": 2, "confirmed": 0}
    assert out["ok"] and SCRIPT["main"](["--data", str(data), "--check"]) == 0


def test_the_analysis_reports_the_relief_measures_the_misses_and_the_warning(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    s4, s1b = out["systems"]["s4"]["relief"], out["systems"]["s1b"]["relief"]
    assert s4["n"] == s1b["n"] == 2 and s4["false_nogo"] == 2 and s1b["false_nogo"] == 0 and s4["regret"] > 0
    assert out["systems"]["s4"]["confirmed"]["false_go"] == 0 and out["systems"]["s4"]["ordinary"]["correct"] == 1.0
    assert out["relief_misses"]["s4"] == {"never_looked": 1, "looked_not_believed": 1}
    assert out["relief_misses"]["s1b"] == {"never_looked": 0, "looked_not_believed": 0}
    assert out["looked"]["s1b"] == {"relief": 1.0, "confirmed": 1.0} and out["looked"]["s4"]["relief"] == 0.5
    assert out["warning"]["s4_median"] == 0.8 and out["warning"]["s1b_share"] == 1.0
    assert out["relief_s4_minus_s1b"]["n"] == 2 and out["relief_s4_minus_s1b"]["diff"] > 0
    assert set(out["systems"]) == {"s1b", "s4", "s1b_matched"} and out["systems"]["s4"]["all"]["n"] == 5
    assert out["reading"] == "unclear"  # 2 more false NO-GOs: short of the 3 that "leans on caution" needs
    assert sum(v["n"] for v in out["by_case"]["s4"].values()) == 5
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_the_reading_rule_follows_the_spec():
    def r(fn, regret):
        return {"false_nogo": fn, "regret": regret}
    assert SCRIPT["reading"](r(5, 0.02), r(2, 0.01)) == "team leans on caution"
    assert SCRIPT["reading"](r(5, 0.01), r(2, 0.02)) == "unclear"  # more misses but not costlier
    assert SCRIPT["reading"](r(2, 0.03), r(2, 0.01)) == "team weighs evidence fine"
    assert SCRIPT["reading"](r(3, 0.03), r(1, 0.01)) == "unclear"


def test_a_missing_trace_or_a_team_that_never_proposed_still_analyses(finished):
    flagged = next(d for d, k in keys(finished).items() if k.truth.flag)
    (finished / "runs" / "s4" / f"{flagged}.trace.jsonl").unlink()
    out = SCRIPT["analyse"](finished)
    assert out["warning"]["s4_opening_chance"][flagged] is None and out["warning"]["s4_median"] == 0.8


def test_the_analysis_refuses_runs_that_do_not_cover_the_split(finished, tmp_path):
    (finished / "runs" / "s4" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="s4.*test-001"):
        SCRIPT["analyse"](finished)
    out = tmp_path / "x.json"
    assert SCRIPT["main"](["--data", str(finished), "--out", str(out)]) == 1 and not out.exists()


def rewrite(d: Path, system: str, deal: str, **changes) -> None:
    p = d / "runs" / system / f"{deal}.json"
    p.write_text(json.dumps(json.loads(p.read_text()) | changes))


def test_an_unanswered_relief_run_is_counted_and_makes_the_reading_provisional(finished):
    relief = next(d for d, k in keys(finished).items() if k.truth.case_type == "relief")
    assert SCRIPT["analyse"](finished)["reading_provisional"] is False
    write(finished, "s4", relief, keys(finished)[relief], [])  # no submit: scored at face value, answered=False
    out = SCRIPT["analyse"](finished)
    assert out["systems"]["s4"]["relief"]["no_answer"] == 1 and out["systems"]["s1b"]["relief"]["no_answer"] == 0
    assert out["systems"]["s4"]["confirmed"]["no_answer"] == 0 and out["reading_provisional"] is True


def test_the_analysis_refuses_a_row_from_the_wrong_model(finished, tmp_path):
    deal = next(iter(keys(finished)))
    rewrite(finished, "s1b", deal, models=["claude-sonnet-5-5"])
    with pytest.raises(ValueError, match=f"s1b/{deal}"):
        SCRIPT["analyse"](finished)
    out = tmp_path / "x.json"
    assert SCRIPT["main"](["--data", str(finished), "--out", str(out)]) == 1 and not out.exists()


def test_a_timed_out_row_may_show_no_model_but_is_counted(finished):
    deal = next(iter(keys(finished)))
    rewrite(finished, "s4", deal, models=[], status="timeout")
    assert SCRIPT["analyse"](finished)["systems"]["s4"]["all"]["timeouts"] == 1
    rewrite(finished, "s4", deal, models=[], status="ok")
    with pytest.raises(ValueError, match=f"s4/{deal}"):
        SCRIPT["analyse"](finished)


def test_missing_traces_are_listed_per_system(finished):
    flagged = next(d for d, k in keys(finished).items() if k.truth.flag)
    (finished / "runs" / "s4" / f"{flagged}.trace.jsonl").unlink()
    assert SCRIPT["analyse"](finished)["missing_traces"] == {"s1b": [], "s4": [flagged]}


def test_the_cost_mean_leaves_out_runs_with_no_cost(finished):
    deal = next(iter(keys(finished)))
    rewrite(finished, "s1b", deal, cost_usd=None)
    all_ = SCRIPT["analyse"](finished)["systems"]["s1b"]["all"]
    assert all_["cost"] == pytest.approx(0.1)
    assert SCRIPT["stats"]([{**json.loads((finished / "runs" / "s1b" / f"{deal}.json").read_text())}])["cost"] is None


def test_settling_docs_has_one_entry_per_flagged_deal(finished):
    out = SCRIPT["analyse"](finished)
    ks = keys(finished)
    assert out["settling_docs"] == {d: SCRIPT["settling_doc"](k) for d, k in ks.items() if k.truth.flag}
    assert len(out["settling_docs"]) == 3

import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import mix, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "mix_final.py"))
FROZEN = ("mix_h_opus1", "cascade:mix_haiku_solo>mix_opus_low@pass")
OUT = {"s1b": 5_000, "s4": 25_000, "mix_haiku_solo": 20_000, "mix_opus_low": 2_500}  # output tokens per deal


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    """The two fresh sets in miniature: five r2 test deals and five r2u test deals."""
    root = tmp_path_factory.mktemp("fresh")
    batch.run(root / "mix-test-r2", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2")
    batch.run(root / "mix-test-r2u", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u")
    return root


def write(d: Path, system: str, deal: str, go: bool, models=None, prompts=None) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    trace = [{"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    base = system in ("s1b", "s4")
    want = models or ([mix.OPUS] if base else mix.models_of(system))
    cli = {"total_cost_usd": 1.0, "sessions": 1, "modelUsage": {m: {} for m in want},
           "usage": {"output_tokens": OUT.get(system, 0)}}
    row = pilot.score(key, system, trace, cli, "ok")
    if not base:
        steps = ([{"step": "solo", "models": want, "tokens": row["tokens"]}] if system != "mix_h_opus1" else
                 [{"step": "reader", "models": [mix.HAIKU], "tokens": {"output_tokens": 20_000}},
                  {"step": "pricer1", "models": [mix.OPUS], "tokens": {"output_tokens": 1_000}}])
        row |= {"steps": steps, "prompts": prompts or mix.fingerprint(system)}
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text(json.dumps(trace[0]) + "\n")
    (out / f"{deal}.json").write_text(json.dumps(row))


def every(root: Path):
    for name in mix.TEST_SETS:
        for deal in json.loads((root / name / "splits.json").read_text())["test"]:
            yield root / name, deal, AnswerKey.model_validate_json((root / name / "truth" / f"{deal}.json").read_text())


@pytest.fixture
def finished(sets, tmp_path, monkeypatch):
    """A finished fake final test: everything right except single Haiku, which always passes."""
    monkeypatch.setattr(mix, "FINAL", FROZEN)
    root = tmp_path / "r"
    shutil.copytree(sets, root)
    for d, deal, key in every(root):
        for s in ("s1b", "s4", "mix_opus_low", "mix_h_opus1"):
            write(d, s, deal, key.truth.go)
        write(d, "mix_haiku_solo", deal, False)
    return root


def test_the_parts_are_the_baselines_the_reference_and_each_mix_s_parts(monkeypatch):
    monkeypatch.setattr(mix, "FINAL", FROZEN)
    assert SCRIPT["parts"]() == ("s1b", "s4", "mix_haiku_solo", "mix_h_opus1", "mix_opus_low")
    monkeypatch.setattr(mix, "FINAL", ())
    with pytest.raises(ValueError, match="no frozen mixes"):
        SCRIPT["parts"]()


def test_the_analysis_reads_a_finished_final_test(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    assert out["frozen"] == list(FROZEN) and [out["sets"][n]["n"] for n in (*mix.TEST_SETS, "all")] == [5, 5, 10]
    every_set = out["sets"]["all"]
    assert every_set["verdicts"] == dict.fromkeys([f"{m}-{b}" for m in FROZEN for b in ("s1b", "s4")],
                                                  "no clear difference: at most 0.0000 worse")
    cascade = every_set["systems"][FROZEN[1]]
    assert cascade["escalated"] == 1 and cascade["cost"] == pytest.approx(0.01 + 0.05) and cascade["regret"] == 0
    assert every_set["systems"]["mix_h_opus1"]["cost"] == pytest.approx(0.01 + 0.02)
    assert every_set["cost_ratio"]["s1b/mix_h_opus1"] == pytest.approx(0.10 / 0.03)
    assert out["readings"]["all"] == {"cheaper_and_not_worse_than_s1b": list(FROZEN),
                                      "cheaper_and_not_worse_than_s4": list(FROZEN)}
    assert every_set["systems"]["mix_haiku_solo"]["false_nogo"] > 0  # the reference is in the table
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_a_mix_worse_than_a_baseline_is_not_read_as_matching_it(finished):
    for d, deal, key in every(finished):
        write(d, "mix_h_opus1", deal, not key.truth.go)
    out = SCRIPT["analyse"](finished)
    assert "mix_h_opus1" not in out["readings"]["all"]["cheaper_and_not_worse_than_s1b"]


def test_the_analysis_refuses_what_was_not_preregistered(finished, tmp_path):
    (finished / "mix-test-r2u" / "runs" / "mix_opus_low" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="mix-test-r2u: mix_opus_low.*test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "mix-test-r2u", "mix_opus_low", "test-001", True)
    (finished / "mix-test-r2" / "runs" / "s4" / "test-002.trace.jsonl").unlink()
    with pytest.raises(ValueError, match="without a trace.*mix-test-r2/s4/test-002"):
        SCRIPT["analyse"](finished)
    write(finished / "mix-test-r2", "s4", "test-002", True)
    write(finished / "mix-test-r2", "mix_h_opus1", "test-003", True, models=[mix.HAIKU, mix.SONNET])
    with pytest.raises(ValueError, match="wrong models.*mix-test-r2/mix_h_opus1/test-003"):
        SCRIPT["analyse"](finished)
    write(finished / "mix-test-r2", "mix_h_opus1", "test-003", True, prompts="old")
    with pytest.raises(ValueError, match="frozen mixes.*mix-test-r2/mix_h_opus1/test-003"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()

import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import mix
from tests.bench.test_mix_confirm import SETS, every, sets  # noqa: F401 (sets is the fixture)
from tests.bench.test_mix_final import write

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "mix_benchmark.py"))


def duration(d: Path, system: str, deal: str, ms: int) -> None:
    p = d / "runs" / system / f"{deal}.json"
    p.write_text(json.dumps(json.loads(p.read_text()) | {"duration_ms": ms}))


@pytest.fixture
def finished(sets, tmp_path):  # noqa: F811
    """A finished fake benchmark: everything right, except single Haiku and the Haiku team, which always pass; each
    Haiku-team run takes 2 minutes and each s1b run 1."""
    root = tmp_path / "r"
    shutil.copytree(sets, root)
    for name, d, deal, key in every(root):
        for s in ("s1b", "s4", "mix_h_opus1", "mix_opus_low", "mix_sonnet_solo"):
            write(d, s, deal, key.truth.go)
        held = name in mix.CONFIRM_SETS
        for s in ("mix_haiku_solo", "mix_h_haiku3"):
            run = SCRIPT["run_name"](s, name)
            write(d, run, deal, False, models=[mix.HAIKU] if held else None, prompts="haiku track" if held else None)
        duration(d, SCRIPT["run_name"]("mix_h_haiku3", name), deal, 120_000)
        duration(d, "s1b", deal, 60_000)
    return root


def test_the_benchmark_reads_every_system_on_all_four_sets(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    assert [out["sets"][n]["n"] for n in ("all", "held_out", "fresh")] == [16, 8, 8]
    every_set = out["sets"]["all"]
    assert set(every_set["systems"]) == set(out["systems"]) and len(out["systems"]) == 10
    assert set(every_set["verdicts"]) == set(out["systems"]) - {"s1b", "s4"}
    assert every_set["verdicts"]["mix_sonnet_solo"] == {"s1b": "no clear difference: at most 0.0000 worse",
                                                        "s4": "no clear difference: at most 0.0000 worse"}
    team = every_set["systems"]["mix_h_haiku3"]
    assert team["false_nogo"] > 0 and team["minutes_median"] == pytest.approx(2.0)
    assert 2.0 <= every_set["systems"][mix.FINAL[0]]["minutes_median"] <= 3.0  # the team, then s1b if escalated
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_a_cascade_waits_for_its_strong_system_only_when_it_escalates():
    cheap = {"go": False, "correct": False, "regret": 0.1, "walk_away": 10.0, "duration_ms": 60_000,
             "models": [mix.HAIKU], "tokens": {}, "answered": True, "case_type": "clean"}
    strong = cheap | {"go": True, "correct": True, "regret": 0.0, "duration_ms": 30_000, "models": [mix.OPUS]}
    by = {"mix_haiku_solo": {"a": cheap, "b": cheap | {"walk_away": 1.0}}, "mix_sonnet_solo": {"a": strong, "b": strong}}
    tz = dict.fromkeys("ab", "Asking price: $10.0M")
    res = SCRIPT["results"](by, tz, "cascade:mix_haiku_solo>mix_sonnet_solo@close:0.02")
    assert (res["a"]["escalated"], res["a"]["minutes"]) == (True, pytest.approx(1.5))
    assert (res["b"]["escalated"], res["b"]["minutes"]) == (False, pytest.approx(1.0))


def test_the_benchmark_refuses_missing_or_unfrozen_runs(finished, tmp_path):
    (finished / "test-r2" / "runs" / "mix_opus_low" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="test-r2: mix_opus_low.*test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "test-r2", "mix_opus_low", "test-001", True, prompts="old")
    with pytest.raises(ValueError, match="frozen mixes.*test-r2/mix_opus_low/test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "test-r2", "mix_opus_low", "test-001", True)
    (finished / "pilot-r2u" / "runs" / "haiku_solo" / "test-002.json").unlink()
    with pytest.raises(ValueError, match="pilot-r2u: \\['mix_haiku_solo'\\]"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()

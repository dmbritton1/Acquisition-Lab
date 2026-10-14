import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import mix
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey
from tests.bench.test_mix_final import write

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "mix_confirm.py"))
SETS = (*mix.CONFIRM_SETS, *mix.TEST_SETS)


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    """The two held-out sets and the two fresh sets in miniature, four test deals each."""
    root = tmp_path_factory.mktemp("confirm")
    for name in SETS:
        batch.run(root / name, {"dev": 0, "test": 4, "hand": 0, "showcase": 0}, mc=20,
                  profile="r2u" if name.endswith("r2u") else "r2")
    return root


def every(root: Path):
    for name in SETS:
        for deal in json.loads((root / name / "splits.json").read_text())["test"]:
            yield name, root / name, deal, AnswerKey.model_validate_json((root / name / "truth" / f"{deal}.json")
                                                                         .read_text())


@pytest.fixture
def finished(sets, tmp_path):
    """A finished fake confirmation test: everything right, except the Haiku team, which always passes."""
    root = tmp_path / "r"
    shutil.copytree(sets, root)
    for name, d, deal, key in every(root):
        for s in ("s1b", "s4", "mix_h_opus1"):
            write(d, s, deal, key.truth.go)
        write(d, SCRIPT["TEAM"][name], deal, False, models=[mix.HAIKU], prompts="haiku track")
    return root


def test_the_analysis_reads_a_finished_confirmation_test(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    assert [out["lead1"][n]["n"] for n in (*mix.CONFIRM_SETS, "all", "with_discovery")] == [4, 4, 8, 16]
    assert out["lead1"]["all"]["verdicts"] == {"s1b": "no clear difference: at most 0.0000 worse",
                                               "s4": "no clear difference: at most 0.0000 worse"}
    assert out["lead1"]["all"]["systems"]["mix_h_opus1"]["cost"] == pytest.approx(0.01 + 0.02)
    assert out["lead1_matches_s4_for_less"] is True
    assert [out["lead2"][n]["n"] for n in ("held_out", "fresh", "all")] == [8, 8, 16]
    assert out["lead2"]["all"]["systems"]["team"]["false_nogo"] > 0
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_a_lead_worse_than_the_opus_team_is_not_read_as_matching_it(finished):
    for name, d, deal, key in every(finished):
        if name in mix.CONFIRM_SETS:
            write(d, "mix_h_opus1", deal, not key.truth.go)
    out = SCRIPT["analyse"](finished)
    assert out["lead1"]["all"]["verdicts"]["s4"] == "worse" and out["lead1_matches_s4_for_less"] is False


def test_the_analysis_refuses_missing_or_unfrozen_runs(finished, tmp_path):
    (finished / "pilot-r2u" / "runs" / "mix_h_opus1" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="pilot-r2u: mix_h_opus1.*test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "pilot-r2u", "mix_h_opus1", "test-001", True, prompts="old")
    with pytest.raises(ValueError, match="frozen mixes.*pilot-r2u/mix_h_opus1/test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "pilot-r2u", "mix_h_opus1", "test-001", True)
    (finished / "test-r2" / "runs" / "haiku_lean_zero_w0" / "test-002.json").unlink()
    with pytest.raises(ValueError, match="test-r2: \\['team'\\]"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()

import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import haiku, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "haiku_practice.py"))


@pytest.fixture(scope="module")
def practice(tmp_path_factory, data):
    """The three practice sets in miniature: two r2 dev deals each in cal-r2 and heldout-r2, five r2u dev deals in
    practice-r2u."""
    root = tmp_path_factory.mktemp("practice")
    shutil.copytree(data, root / "cal-r2")
    shutil.copytree(data, root / "heldout-r2")
    # the batch's word-presence check can flag a set this small; the scorecard doesn't care
    batch.run(root / "practice-r2u", {"dev": 5, "test": 0, "hand": 0, "showcase": 0}, mc=20, profile="r2u")
    return root


def write(d: Path, system: str, deal: str, go: bool, cost: float = 0.01, spent: float | None = None) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    trace = [{"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    cli = {"total_cost_usd": cost, "sessions": 1, "modelUsage": {"claude-haiku-5-5": {}},
           "usage": {"output_tokens": 20_000}}  # $0.01 at Haiku's list price
    row = pilot.score(key, system, trace, cli, "ok") | {"budget": key.budget, "spent": key.budget if spent is None
                                                        else spent}
    (d / "runs" / system).mkdir(parents=True, exist_ok=True)
    (d / "runs" / system / f"{deal}.json").write_text(json.dumps(row))


def every(root: Path):
    for s in haiku.PRACTICE:
        for deal in json.loads((root / s / "splits.json").read_text())["dev"]:
            yield root / s, deal, AnswerKey.model_validate_json((root / s / "truth" / f"{deal}.json").read_text())


def test_the_scorecard_covers_every_practice_deal_by_set_and_type(practice, tmp_path):
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    for d, deal, key in every(root):
        write(d, "right", deal, key.truth.go)
        write(d, "wrong", deal, not key.truth.go, spent=key.budget + 1)
    write(root / "cal-r2", "partial", "dev-000", True)
    cards = SCRIPT["scorecard"](root, ["right", "wrong", "partial"])
    assert cards["right"]["all"]["n"] == 9 and cards["right"]["all"]["regret"] == 0 and cards["right"]["missing"] == 0
    assert cards["right"]["sets"]["practice-r2u"]["n"] == 5 and cards["right"]["all"]["models"] == ["claude-haiku-5-5"]
    assert cards["right"]["all"]["total_cost"] == pytest.approx(0.09) and cards["right"]["all"]["session_timeouts"] == 0
    assert cards["right"]["all"]["list_cost"] == pytest.approx(0.01)
    assert cards["right"]["all"]["list_total"] == pytest.approx(0.09)
    assert cards["wrong"]["all"]["correct"] == 0 and cards["wrong"]["all"]["over_budget"] == 9
    assert sum(c["n"] for c in cards["right"]["by_case"].values()) == 9
    assert cards["partial"]["missing"] == 8
    assert "missing runs: 8" in SCRIPT["table"](cards)


def test_a_change_is_kept_only_if_regret_falls_without_more_relief_or_confirmed_misses():
    def e(regret, relief_fnogo=0, confirmed_fgo=0, missing=0):
        return {"missing": missing, "all": {"regret": regret},
                "by_case": {"relief": {"n": 3, "false_nogo": relief_fnogo},
                            "confirmed": {"n": 2, "false_go": confirmed_fgo}}}

    keeps = SCRIPT["keeps"]
    assert keeps(e(0.010), e(0.011))
    assert not keeps(e(0.011), e(0.011))  # regret must fall
    assert not keeps(e(0.009, relief_fnogo=2), e(0.011, relief_fnogo=1))
    assert not keeps(e(0.009, confirmed_fgo=1), e(0.011))
    assert not keeps(e(0.009, missing=1), e(0.011))  # an unfinished round decides nothing
    assert keeps({"missing": 0, "all": {"regret": 0.01}, "by_case": {"relief": {"n": 0}, "confirmed": {"n": 0}}},
                 e(0.011))


def test_main_prints_the_scorecard_and_the_keep_verdict(practice, tmp_path, capsys):
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    for d, deal, key in every(root):
        write(d, "old", deal, True)
        write(d, "new", deal, key.truth.go)
    assert SCRIPT["main"](["--root", str(root), "--systems", "old,new"]) == 0
    assert "old" in capsys.readouterr().out
    assert SCRIPT["main"](["--root", str(root), "--keep", "new", "--over", "old"]) == 0
    assert capsys.readouterr().out.rstrip().endswith("keep new over old: True")


def test_old_single_claude_rows_without_session_counts_still_score(practice, tmp_path):
    """data/cal-r2's s1b rows predate the sessions and timeouts fields: a single run is one session."""
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    write(root / "cal-r2", "s1b", "dev-000", True)
    path = root / "cal-r2" / "runs" / "s1b" / "dev-000.json"
    row = json.loads(path.read_text())
    path.write_text(json.dumps({k: v for k, v in row.items() if k not in ("sessions", "timeouts")}))
    c = SCRIPT["scorecard"](root, ["s1b"])["s1b"]["all"]
    assert c["n"] == 1 and c["sessions"] == 1 and c["session_timeouts"] == 0

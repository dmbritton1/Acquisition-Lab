import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import haiku, mix, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "mix_practice.py"))
OUT = {"s1b": 5_000, "s4": 25_000, "haiku_solo": 20_000, "mix_opus_low": 2_500}  # output tokens per deal
MODEL = {"s1b": mix.OPUS, "s4": mix.OPUS, "haiku_solo": mix.HAIKU, "mix_opus_low": mix.OPUS}


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


def write(d: Path, system: str, deal: str, go: bool) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    trace = [{"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    cli = {"total_cost_usd": 1.0, "sessions": 1, "modelUsage": {MODEL[system]: {}},
           "usage": {"output_tokens": OUT[system]}}
    (d / "runs" / system).mkdir(parents=True, exist_ok=True)
    (d / "runs" / system / f"{deal}.json").write_text(json.dumps(pilot.score(key, system, trace, cli, "ok")))


@pytest.fixture
def finished(practice, tmp_path):
    """s1b, mix_opus_low and s4 always right (s4 not on practice-r2u); single Haiku always passes (under its
    Haiku-track name)."""
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    for s in haiku.PRACTICE:
        for deal in json.loads((root / s / "splits.json").read_text())["dev"]:
            key = AnswerKey.model_validate_json((root / s / "truth" / f"{deal}.json").read_text())
            for system in ("s1b", "mix_opus_low", *(("s4",) if s != "practice-r2u" else ())):
                write(root / s, system, deal, key.truth.go)
            write(root / s, "haiku_solo", deal, False)
    return root


def test_rows_read_a_candidate_under_its_haiku_track_name(finished):
    assert len(SCRIPT["rows"](finished, "mix_haiku_solo")) == 9 and len(SCRIPT["rows"](finished, "s4")) == 4
    assert SCRIPT["rows"](finished, "mix_sonnet_solo") == {}


def test_the_scorecard_scores_systems_and_cascades_and_flags_partial_ones(finished):
    card = SCRIPT["scorecard"](finished)
    assert card["s1b"]["regret"] == 0 and card["s1b"]["cost"] == pytest.approx(0.10) and not card["s1b"]["partial"]
    assert card["mix_haiku_solo"]["cost"] == pytest.approx(0.01) and card["mix_haiku_solo"]["false_go"] == 0
    up = card["cascade:mix_haiku_solo>mix_opus_low@pass"]
    assert up["regret"] == 0 and up["escalated"] == 1 and up["cost"] == pytest.approx(0.01 + 0.05)
    assert card["cascade:mix_haiku_solo>s4@pass"]["partial"] and card["cascade:mix_haiku_solo>s4@pass"]["n"] == 4
    assert "cascade:mix_opus_low>s1b@pass" in card and "cascade:mix_opus_low>s4@pass" in card  # CHEAP has mix_opus_low
    assert card["s1b"]["no_answer"] == 0 and card["s1b"]["timeouts"] == 0 and card["s1b"]["models"] == [mix.OPUS]
    assert card["mix_haiku_solo"]["models"] == [mix.HAIKU] \
        and card["mix_haiku_solo"]["relief_false_nogo"] == 2
    assert up["models"] == [mix.OPUS] and up["no_answer"] == 0 and up["confirmed_false_go"] == 0
    assert "mix_sonnet_solo" not in card and not any("mix_sonnet_solo" in n for n in card)  # never run


def test_the_frontier_picks_full_coverage_candidates_only(finished):
    card = SCRIPT["scorecard"](finished)
    chosen = SCRIPT["picks"](card)
    # escalating only the flagged (r2u) deals, where single Haiku errs, to Opus at low effort reaches regret 0 at
    # $0.027 a deal, beating mix_opus_low ($0.05); single Haiku is the cheapest point; its clones count once
    assert chosen == ["cascade:mix_haiku_solo>mix_opus_low@flag", "mix_haiku_solo"]
    assert card["mix_opus_low"]["regret"] == 0 and card["mix_opus_low"]["cost"] == pytest.approx(0.05)


def test_a_rejected_variant_is_shown_but_never_picked(finished, monkeypatch):
    card = SCRIPT["scorecard"](finished)
    assert "mix_haiku_solo" in SCRIPT["picks"](card)
    monkeypatch.setitem(SCRIPT["picks"].__globals__, "REJECTED", ("mix_haiku_solo",))
    assert "mix_haiku_solo" not in SCRIPT["picks"](card)


def test_main_prints_the_table_and_the_picks(finished, capsys):
    assert SCRIPT["main"](["--root", str(finished)]) == 0
    out = capsys.readouterr().out
    assert "frontier picks (*): ['cascade:mix_haiku_solo>mix_opus_low@flag', 'mix_haiku_solo']" in out
    assert "(partial)" in out and "rNOGO" in out and "noans" in out
    assert "haiku,opus" in out  # the cascade's models, short names


def test_keep_reads_an_aliased_candidate_under_its_haiku_track_name(finished, capsys):
    assert SCRIPT["main"](["--root", str(finished), "--keep", "mix_opus_low", "--over", "mix_haiku_solo"]) == 0
    assert capsys.readouterr().out.strip() == "keep mix_opus_low over mix_haiku_solo: True"

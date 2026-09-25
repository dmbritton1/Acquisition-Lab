import json
import math
import shutil

import pytest

from acqlab.bench import calibrate
from acqlab.bench.pilot import run
from acqlab.generator.batch import AnswerKey


def test_deals_needed_follows_the_fix_a_quarter_model():
    # regret 0.1 on one deal in four: E[r] = 0.025, E[r^2] = 0.0025, so n = Z^2 (0.0025 / (0.25 * 0.025^2) - 1)
    assert calibrate.deals_needed([0, 0, 0, 0.1]) == math.ceil(calibrate.Z ** 2 * 15)
    assert calibrate.deals_needed([0.05, 0.05]) < calibrate.deals_needed([0, 0.1])  # rarer, bigger misses need more
    assert calibrate.deals_needed([0.0, 0.0]) == math.inf


def _stub(go_for):
    """A solver that submits go_for(room, budget) and reads nothing."""
    def solver(room, budget, trace, router, unbudgeted=False):
        trace.write_text(json.dumps({"tool": "submit", "args": {"go": go_for(room, budget), "walk_away": 1.0,
                                                                 "reason": "r"}, "cost": 0.0, "refused": False}) + "\n")
        return {"usage": {}}
    return solver


@pytest.fixture
def round_dir(data, tmp_path):
    """The two shared dev deals as a calibration round, with S1b always wrong and S0 always right."""
    d = shutil.copytree(data, tmp_path / "round")
    truth = {k.truth.id: k.truth for k in calibrate._keys(d)}
    run(d, 2, ["s1b"], solver=_stub(lambda room, b: not truth[room.parent.name].go))
    run(d, 2, ["s0"], solver=_stub(lambda room, b: truth[room.parent.name].go), flip_only=True)
    return d


def test_a_round_is_checked_against_every_target(round_dir):
    result = calibrate.check(round_dir, round_dir)  # the round doubles as a (too small) audit batch
    met = {t["target"]: t["met"] for t in result["targets"]}
    assert met["S1b wrong on flip deals"] is (result["n_s1b_flip"] > 0)
    assert met["S0 right on flip deals"] is (result["n_s0"] > 0)
    assert not met["audit deals"]  # 2 deals, not 500
    assert met["audit batch problems (incl. word leaks)"]  # the fixture's batch saved problems.json = []
    assert not met["S1b regret minus B0's"] or not met["S1b regret minus the margin rule's"]  # always wrong loses
    assert result["passed"] is False and len(result["targets"]) == 8


def test_the_cli_writes_the_result_and_exits_1_when_a_target_is_missed(round_dir):
    (round_dir / "problems.json").write_text('["word leak: something"]')
    assert calibrate.main(["--data", str(round_dir), "--audit", str(round_dir)]) == 1
    saved = json.loads((round_dir / "calibration.json").read_text())
    assert not next(t for t in saved["targets"] if t["target"].startswith("audit batch problems"))["met"]


def test_margin_auc_is_one_when_thin_margins_are_exactly_the_flip_deals(data):
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    ask = key.truth.deal.asking_price

    def variant(headroom, flip):
        t = key.truth.model_copy(update={"face_walk_away": ask * (1 + headroom), "face_go": True, "go": not flip})
        return key.model_copy(update={"truth": t})
    keys = [variant(0.01, True), variant(0.02, True), variant(0.2, False), variant(0.3, False)]
    assert calibrate.margin_auc(keys) == 1.0
    assert math.isnan(calibrate.margin_auc(keys[:2]))  # no non-flip deals: nothing to compare

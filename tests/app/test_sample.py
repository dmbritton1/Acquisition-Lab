"""The free sample deal: a benchmark room on the board with no Claude call."""
import runpy
from pathlib import Path

import pytest

from acqlab.app import board, steps
from acqlab.app.store import deals, load

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "board_sample.py"))


def test_the_sample_deal_prices_on_the_board(data, tmp_path, capsys):
    home = tmp_path / "home"
    SCRIPT["main"](["--room", str(data / "deals" / "dev-000" / "room"), "--home", str(home)])
    [d] = deals(home)
    assert capsys.readouterr().out.strip() == d["id"]
    deal = home / "deals" / d["id"]
    nums, settings = load(deal / "numbers.json")["numbers"], load(home / "settings.json")
    assert {v["status"] for v in nums.values()} == {"you"} and steps._missing(nums, settings) == []
    worries = load(deal / "worries.json")["worries"]
    face = board.face(steps.values(nums), settings, d["price"], d["name"], "")
    out = board.compute(face, worries, set())
    assert isinstance(out["go"], bool) and len(out["flips"]) == 5
    with pytest.raises(SystemExit):  # never into the repo's data folder
        SCRIPT["main"](["--room", str(data / "deals" / "dev-000" / "room"),
                        "--home", str(Path(__file__).parents[2] / "data" / "x")])

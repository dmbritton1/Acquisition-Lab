import json
import math

import pytest

from acqlab.dataroom.tools import BUDGET_SHARE, BudgetExceeded, DataRoom, write_room
from acqlab.generator.render import render, teaser_text
from acqlab.generator.truth import generate


@pytest.fixture
def room(tmp_path):
    t = generate("d0", "test", 0, mc=20)
    docs, _ = render(t)
    budget = write_room(tmp_path / "deals" / "d0" / "room", teaser_text(t), docs)
    (tmp_path / "truth").mkdir()
    (tmp_path / "truth" / "d0.json").write_text("{}")
    return tmp_path / "deals" / "d0" / "room", docs, budget


def test_default_budget_buys_a_share_of_the_room(room):
    path, docs, budget = room
    assert budget == math.ceil(BUDGET_SHARE * sum(d.pages for d in docs))
    assert DataRoom(path).budget == budget


def test_listing_and_teaser_are_free_and_opening_costs_pages(room):
    path, docs, _ = room
    dr = DataRoom(path, budget=100)
    listing = dr.list_documents()
    assert {d["id"] for d in listing} == {d.id for d in docs} and dr.spent == 0 and dr.teaser()
    pages = next(d["pages"] for d in listing if d["id"] == "cim")
    assert "Adjusted EBITDA" in dr.open_document("cim") and dr.spent == pages


def test_search_costs_one_unit_and_returns_short_snippets(room):
    dr = DataRoom(room[0], budget=100)
    hits = dr.search("working capital peg")
    assert dr.spent == 1 and 0 < len(hits) <= 5
    assert all(len(h["snippet"]) <= 150 and h["doc_id"] for h in hits)
    assert dr.search("0 2025") == []  # letters only: numbers such as a clean fact's $0.0M can't be searched for


def test_over_budget_calls_are_refused_and_logged(room):
    dr = DataRoom(room[0], budget=1)
    dr.search("debt")
    with pytest.raises(BudgetExceeded):
        dr.open_document("cim")
    assert dr.log[-1]["refused"] and dr.spent == 1


def test_only_indexed_documents_can_be_opened(room):
    dr = DataRoom(room[0], budget=100)
    for bad in ("../../truth/d0", "../index", "index.json"):
        with pytest.raises(KeyError):
            dr.open_document(bad)
    assert dr.spent == 0


def test_engine_file_is_written_only_when_given(tmp_path):
    t = generate("d1", "test", 1, mc=20)
    docs, _ = render(t)
    write_room(tmp_path / "a", teaser_text(t), docs)
    face = {"teaser": t.base.teaser.model_dump(), "deal": t.deal.model_dump()}
    write_room(tmp_path / "b", teaser_text(t), docs, engine=face)
    assert not (tmp_path / "a" / "engine.json").exists()
    assert json.loads((tmp_path / "b" / "engine.json").read_text()) == face

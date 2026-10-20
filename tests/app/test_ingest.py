"""Ingest and storage: PDFs and text into local deal folders."""
import pytest

from acqlab.app.ingest import Unreadable, ingest, pages, texts
from acqlab.app.store import load, new_deal, write
from tests.app.pdfs import write_pdf


def test_pdf_pages_reads_text_and_an_image_only_page_reads_empty(tmp_path):
    p = write_pdf(tmp_path / "t.pdf", ["Revenue was 162.8 million dollars", None])
    got = pages(p)
    assert len(got) == 2 and "162.8" in got[0] and got[1].strip() == ""


def test_ingest_writes_the_docs_and_the_deal(tmp_path):
    t = tmp_path / "teaser.md"; t.write_text("Teaser text with LTM revenue of $162.8M")
    c = write_pdf(tmp_path / "cim.pdf", ["CIM page one, long enough to read", None, "page three text here ok"])
    deal = ingest(tmp_path / "home", "Cedar Harbor", 221.5, {"teaser": t, "cim": c})
    assert load(deal / "deal.json")["price"] == 221.5
    cim = load(deal / "docs" / "cim.json")
    assert cim["unreadable"] == [2] and len(cim["pages"]) == 3
    assert texts(deal)["teaser"].startswith("[page 1]\n")


def test_ingest_stops_when_most_of_the_cim_is_unreadable(tmp_path):
    c = write_pdf(tmp_path / "cim.pdf", [None, None, "only this page has text on it"])
    t = tmp_path / "t.md"; t.write_text("teaser")
    with pytest.raises(Unreadable):
        ingest(tmp_path / "home", "X", 100.0, {"teaser": t, "cim": c})
    assert not (tmp_path / "home" / "deals").exists() or not any((tmp_path / "home" / "deals").iterdir())


def test_two_deals_with_the_same_name_get_their_own_folders(tmp_path):
    a, b = new_deal(tmp_path, "Cedar Harbor"), new_deal(tmp_path, "Cedar Harbor")
    assert a != b and a.name == "cedar-harbor" and b.name == "cedar-harbor-2"


def test_write_is_atomic_and_load_falls_back_to_the_default(tmp_path):
    write(tmp_path / "x.json", {"a": 1})
    assert load(tmp_path / "x.json") == {"a": 1} and load(tmp_path / "y.json", {}) == {}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_a_failed_write_leaves_no_listed_or_half_written_deal(tmp_path, monkeypatch):
    from acqlab.app import ingest as mod
    from acqlab.app.store import deals, write as real_write
    t = tmp_path / "t.md"; t.write_text("teaser text that is long enough")
    c = tmp_path / "c.md"; c.write_text("cim text that is long enough to read")

    def flaky(path, obj):
        if path.name == "cim.json":
            raise OSError("disk full")
        real_write(path, obj)
    monkeypatch.setattr(mod, "write", flaky)
    with pytest.raises(OSError):
        ingest(tmp_path / "home", "X", 1.0, {"teaser": t, "cim": c})
    assert deals(tmp_path / "home") == [] and list((tmp_path / "home" / "deals").iterdir()) == []


def test_a_corrupt_pdf_is_unreadable_not_a_raw_pypdf_error(tmp_path):
    bad = tmp_path / "cim.pdf"; bad.write_bytes(b"not a pdf")
    t = tmp_path / "t.md"; t.write_text("teaser")
    with pytest.raises(Unreadable):
        ingest(tmp_path / "home", "X", 1.0, {"teaser": t, "cim": bad})


def test_a_cim_with_no_pages_is_unreadable(tmp_path):
    empty = write_pdf(tmp_path / "cim.pdf", [])
    t = tmp_path / "t.md"; t.write_text("teaser")
    with pytest.raises(Unreadable):
        ingest(tmp_path / "home", "X", 1.0, {"teaser": t, "cim": empty})
    assert not (tmp_path / "home" / "deals").exists()

"""Reads a teaser and a CIM (PDF, .md or .txt) into a local deal folder, page by page."""
import shutil
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from acqlab.app.store import load, new_deal, write

UNREADABLE_CHARS = 20  # a page with fewer stripped characters is unreadable
TITLES = {"teaser": "Teaser", "cim": "Confidential Information Memorandum"}


class Unreadable(Exception):
    """Most of the CIM has no text (scanned images)."""


def pages(path: Path) -> list[str]:
    """Page texts: one per PDF page, or the whole file as one page."""
    if path.suffix.lower() == ".pdf":
        try:
            return [p.extract_text() or "" for p in PdfReader(path).pages]
        except PyPdfError as e:  # corrupt, truncated or password-protected
            raise Unreadable(f"{path.name} is not a readable PDF (corrupt or password-protected)") from e
    return [path.read_text()]


def _unreadable(texts_: list[str]) -> list[int]:
    return [i for i, t in enumerate(texts_, 1) if len(t.strip()) < UNREADABLE_CHARS]


def ingest(home: Path, name: str, price: float, files: dict[str, Path]) -> Path:
    """Write deal.json and docs/<id>.json; raise Unreadable (leaving no folder) if the CIM is empty or mostly blank, or a file is not readable."""
    read = {doc: pages(files[doc]) for doc in TITLES}
    if not read["cim"] or len(_unreadable(read["cim"])) * 2 > len(read["cim"]):
        raise Unreadable("more than half of the CIM's pages have no readable text")
    deal = new_deal(home, name)
    try:
        for doc, texts_ in read.items():
            write(deal / "docs" / f"{doc}.json",
                  {"id": doc, "title": TITLES[doc], "pages": texts_, "unreadable": _unreadable(texts_)})
        # deal.json goes last: it is what lists the deal, so a failed ingest never leaves a half deal
        write(deal / "deal.json", {"name": name, "price": price, "created": datetime.now().isoformat()})
    except BaseException:
        shutil.rmtree(deal, ignore_errors=True)
        raise
    return deal


def texts(deal: Path) -> dict[str, str]:
    """Doc id to its pages joined, each page preceded by "[page N]"."""
    out = {}
    for f in sorted((deal / "docs").glob("*.json")):
        out[f.stem] = "\n".join(f"[page {i}]\n{t}" for i, t in enumerate(load(f)["pages"], 1))
    return out

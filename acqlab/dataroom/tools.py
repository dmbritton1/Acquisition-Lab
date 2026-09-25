"""Budgeted data room: the only way any system reads a deal's documents. It reads nothing outside its room folder."""
import json
import math
import re
from pathlib import Path

from acqlab.generator.documents import Doc

SEARCH_COST = 1.0
SNIPPET_CHARS = 150
BUDGET_SHARE = 0.25  # the default budget covers every evidence document in ~21% of deals (Plan 4a design §1)


class BudgetExceeded(Exception):
    pass


def write_room(room: Path, teaser: str, docs: list[Doc], budget_share: float = BUDGET_SHARE,
               engine: dict | None = None) -> float:
    """Write documents and index (and, given it, engine.json: the face-value deal the engine tool prices);
    return the default budget."""
    room.mkdir(parents=True, exist_ok=True)
    budget = float(math.ceil(budget_share * sum(d.pages for d in docs)))
    for d in docs:
        (room / f"{d.id}.md").write_text(d.render())
    index = {"teaser": teaser, "default_budget": budget,
             "documents": [{"id": d.id, "title": d.title, "domain": d.domain, "pages": d.pages} for d in docs]}
    (room / "index.json").write_text(json.dumps(index, indent=2))
    if engine is not None:
        (room / "engine.json").write_text(json.dumps(engine, indent=2))
    return budget


def _words(text: str) -> set[str]:
    """Letters only: search sees what validate.doc_words audits, so a number (such as a clean fact's $0.0M) can't be
    searched for."""
    return set(re.findall(r"[a-z]+", text.lower()))


class DataRoom:
    def __init__(self, room: Path, budget: float | None = None):
        self._room = room
        index = json.loads((room / "index.json").read_text())
        self._teaser = index["teaser"]
        self._docs = {d["id"]: d for d in index["documents"]}
        self.budget = index["default_budget"] if budget is None else budget
        self.spent = 0.0
        self.log: list[dict] = []

    @property
    def remaining(self) -> float:
        return self.budget - self.spent

    def _charge(self, tool: str, arg: str, cost: float) -> None:
        if cost > self.remaining:
            self.log.append({"tool": tool, "arg": arg, "cost": 0.0, "remaining": self.remaining, "refused": True})
            raise BudgetExceeded(f"{tool}({arg!r}) costs {cost}, {self.remaining} left")
        self.spent += cost
        self.log.append({"tool": tool, "arg": arg, "cost": cost, "remaining": self.remaining, "refused": False})

    def _text(self, doc_id: str) -> str:
        return (self._room / f"{doc_id}.md").read_text()  # doc_id is always an index key, never user text

    def teaser(self) -> str:
        return self._teaser

    def list_documents(self) -> list[dict]:
        self.log.append({"tool": "list_documents", "arg": "", "cost": 0.0, "remaining": self.remaining,
                         "refused": False})
        return [dict(d) for d in self._docs.values()]

    def search(self, query: str) -> list[dict]:
        """Top 5 paragraphs by number of query words they contain."""
        self._charge("search", query, SEARCH_COST)
        terms = _words(query)
        hits = []
        for order, doc_id in enumerate(self._docs):
            for para in self._text(doc_id).split("\n\n"):
                score = len(terms & _words(para))
                if score:
                    hits.append((-score, order, doc_id, para[:SNIPPET_CHARS]))
        return [{"doc_id": d, "snippet": s} for _, _, d, s in sorted(hits)[:5]]

    def open_document(self, doc_id: str) -> str:
        if doc_id not in self._docs:
            raise KeyError(f"no document {doc_id!r}")
        self._charge("open_document", doc_id, float(self._docs[doc_id]["pages"]))
        return self._text(doc_id)

"""The Deal Record (main spec §3, the blackboard): what S4 believes about each issue type, and the evidence behind it.
Code holds it; LLMs only propose. The engine prices it: the decision, each issue's flip amount, the pairs that
flip together, and router 6's ranking (reframe design §5).

It reads the room's engine.json and index.json only, never an answer key."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import numpy as np

from acqlab.agents.knowledge import DILIGENCE_MAP, typical_high
from acqlab.engine import Deal, is_go
from acqlab.generator.sample import Teaser
from acqlab.generator.traps import TRAPS, params_for
from acqlab.routers.beliefs import HAIRCUT_CAP, Issue, draw, walk_aways
from acqlab.routers.routers import decide, score_regret

N_WORLDS = 400
PAIR_TOP = 3  # the pair screen looks at the top open issues by chance x size
FLIP_STEPS = 30  # bisection steps for a flip amount


class Face(NamedTuple):
    """The deal at face value, from visible numbers only. Stands in for BaseDeal in params_for and walk_aways, which
    read only .teaser and .deal."""
    teaser: Teaser
    deal: Deal


def load_face(room: Path) -> Face:
    engine = json.loads((room / "engine.json").read_text())
    return Face(Teaser(**engine["teaser"]), Deal(**engine["deal"]))


def next_doc(trap: str, pages: dict[str, float], read: set[str]) -> str | None:
    """The first unread document on the diligence map for this issue type, or None once all are read."""
    for kind in DILIGENCE_MAP[trap]:
        for d in sorted(x for x in pages if x == kind or x.startswith(kind + "_")):
            if d not in read:
                return d
    return None


@dataclass
class Entry:
    """One issue type. `known` is a committed (low, high); otherwise the Deal Lead's belief (chance, low, high)
    stands, priced over at least the usual size range."""
    trap: str
    name: str = ""
    proposed: bool = False
    chance: float = 0.0
    low: float = 0.0
    high: float = 0.0
    docs: list[str] = field(default_factory=list)
    known: tuple[float, float] | None = None
    kind: str | None = None  # quoted | computed | range
    quotes: list[dict] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    tries: int = 0
    objections: list[dict] = field(default_factory=list)  # unanswered Challenger objections

    @property
    def open(self) -> bool:
        return self.proposed and self.known is None


class Record:
    def __init__(self, face: Face):
        self.face = face
        self.entries = {t: Entry(t) for t in TRAPS}
        self.priority: list[str] = []  # the Deal Lead's order, most important first

    def plan(self, issues: list[dict]) -> None:
        """A Deal Lead proposal. Committed values stand; beliefs about the rest are replaced."""
        self.priority = [i["type"] for i in issues]
        for i in issues:
            e = self.entries[i["type"]]
            e.proposed, e.name, e.docs = True, i.get("name", ""), list(i.get("docs", []))
            if e.known is None:
                e.chance, e.low, e.high = float(i["chance"]), float(i["low"]), float(i["high"])

    def apply(self, commits: list[dict]) -> bool:
        """Committed findings; True if any narrowed what is known."""
        narrowed = False
        for c in commits:
            e = self.entries[c["type"]]
            e.proposed = True
            if c["kind"] in ("quoted", "computed", "range"):
                narrowed |= e.known != (c["low"], c["high"])
                e.known, e.kind, e.quotes = (c["low"], c["high"]), c["kind"], c["quotes"]
            elif c["kind"] == "not_found":
                e.searched = sorted(set(e.searched) | set(c["docs"]))
            elif e.known is None:  # open: a belief without evidence
                e.chance, e.low, e.high = c["chance"], c["low"], c["high"]
        return narrowed

    def challenge(self, objections: list[dict]) -> None:
        """Each objection reopens its issue for one more investigation. For an open issue it also widens the belief:
        the higher chance and the larger size stand."""
        for o in objections:
            e = self.entries[o["type"]]
            e.proposed = True
            e.objections.append(o)
            e.docs = list(dict.fromkeys(list(o.get("docs", [])) + e.docs))
            if e.known is None:
                e.chance, e.high = max(e.chance, o["chance"]), max(e.high, o["high"])

    def issue(self, t: str) -> Issue:
        e = self.entries[t]
        if e.known is not None and e.objections:  # in doubt until checked: priced as open
            return Issue(p_real=max(o["chance"] for o in e.objections),
                         hi=max([o["high"] for o in e.objections] + [e.known[1]]))
        if e.known is not None:
            return Issue(known=e.known)
        if not e.proposed:
            return Issue(proposed=False)
        return Issue(p_real=e.chance, hi=max(e.high, typical_high(t, self.face.teaser)))

    def worlds(self) -> tuple[np.ndarray, np.ndarray]:
        values = draw({t: self.issue(t) for t in TRAPS}, N_WORLDS, np.random.default_rng(0))
        return values, walk_aways(self.face, values)

    def decide(self) -> tuple[bool, float]:
        """The engine's call at the committed beliefs (main spec §3: code decides): go if its expected regret is no
        higher than passing, and the median walk-away."""
        return decide(self.worlds()[1], self.face.deal.asking_price)

    def point(self) -> dict[str, float]:
        """Committed values at their midpoints; open issues at 0 (face value)."""
        return {t: (e.known[0] + e.known[1]) / 2 if e.known else 0.0 for t, e in self.entries.items()}

    def _go(self, amounts: dict[str, float]) -> bool:
        a = dict(amounts)
        a["concentration"] = min(a.get("concentration", 0.0), HAIRCUT_CAP * self.face.teaser.revenue_ltm)
        return is_go(self.face.deal, params_for(a, self.face))

    def size_limit(self, t: str) -> float:
        return max(self.entries[t].high, typical_high(t, self.face.teaser))

    def flip_amount(self, t: str) -> float | None:
        """$M of issue t at which the decision flips, the others at their point values; None if no size up to twice
        the usual range flips it."""
        base = self.point()
        lo, hi = 0.0, 2 * self.size_limit(t)
        go_lo = self._go(base | {t: lo})
        if self._go(base | {t: hi}) == go_lo:
            return None
        for _ in range(FLIP_STEPS):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if self._go(base | {t: mid}) == go_lo else (lo, mid)
        return hi

    def flagged_pairs(self) -> list[tuple[str, str]]:
        """Pairs of the top open issues that flip the decision together at the top of their size ranges, when neither
        does alone (reframe design §5: "these two together flip it")."""
        open_ = sorted((t for t, e in self.entries.items() if e.open and e.chance > 0),
                       key=lambda t: -self.entries[t].chance * self.size_limit(t))[:PAIR_TOP]
        base = self.point()
        now = self._go(base)
        alone = {t: self._go(base | {t: self.size_limit(t)}) != now for t in open_}
        return [(a, b) for i, a in enumerate(open_) for b in open_[i + 1:]
                if not alone[a] and not alone[b]
                and self._go(base | {a: self.size_limit(a), b: self.size_limit(b)}) != now]

    def rank(self, candidates: list[str], costs: dict[str, float]) -> dict[str, float]:
        """Router 6: expected $M of decision regret removed per page, for each candidate issue."""
        values, w = self.worlds()
        return score_regret(values, w, self.face.deal.asking_price, costs, candidates)

    def view(self, reasons: bool = True) -> str:
        """The record as text, for the Deal Lead (and, without the Lead's issue names, the Challenger)."""
        go, wa = self.decide()
        lines = [f"Engine's current call at these beliefs: {'GO' if go else 'NO-GO'} (median walk-away "
                 f"${wa:,.1f}M vs asking ${self.face.deal.asking_price:,.1f}M)."]
        for t, e in self.entries.items():
            head = f"- {t}" + (f" ({e.name})" if reasons and e.name else "")
            if e.known is not None:
                lo, hi = e.known
                amount = f"${lo:,.1f}M" if lo == hi else f"${lo:,.1f}–${hi:,.1f}M"
                src = "; ".join(f'{q["doc_id"]}: "{q["text"]}"' for q in e.quotes)
                lines.append(f"{head}: committed {amount} ({e.kind}) from {src}")
            elif e.proposed:
                lines.append(f"{head}: open, chance {e.chance:.2f}, size ${e.low:,.1f}–${e.high:,.1f}M"
                             + (f"; read without settling it: {', '.join(e.searched)}" if e.searched else ""))
            else:
                lines.append(f"{head}: not proposed (treated as no problem)")
        return "\n".join(lines)

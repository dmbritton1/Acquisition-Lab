"""The Deal Record (main spec §3, the blackboard): what S4 believes about each issue type, and the evidence behind it.
Code holds it; LLMs only propose. The engine prices it: the decision, each issue's flip amount, the pairs that
flip together, and the document router's ranking (reframe design §5; D2).

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
from acqlab.routers.routers import decide, score_docs

N_WORLDS = 400
ROUTE_WORLDS = 4000  # the document router's sample (D2 §2): at N_WORLDS, thin groups overstate low-weight (e.g.
# filler) documents 2-5x; decide() stays at N_WORLDS
MAP_WEIGHTS = (0.45, 0.25, 0.15)  # the chance a map document is where an issue is settled, by place on the map.
# ponytail: hand-set from the map's order (the order S1b's guide states in words), not measured; tune here if the
# order dominates the router
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


def is_kind(doc: str, kind: str) -> bool:
    return doc == kind or doc.startswith(kind + "_")


def on_map(doc: str) -> bool:
    """True if the diligence map names this document's kind for some issue type."""
    return any(is_kind(doc, k) for kinds in DILIGENCE_MAP.values() for k in kinds)


def settle_weights(trap: str, pages: dict[str, float], read: set[str], named: list[str]) -> dict[str, float]:
    """The chance each unread document is where issue `trap` is settled (D2 §1). Map places get MAP_WEIGHTS, split
    evenly among documents of one kind; the rest goes to the named documents off the map, or else to every other
    document. Every issue is settled somewhere (a clean fact states $0.0M), so read documents drop out and the rest
    renormalize: a read that misses moves where the evidence is, not whether the issue is real."""
    w = dict.fromkeys(pages, 0.0)
    for kind, share in zip(DILIGENCE_MAP[trap], MAP_WEIGHTS):
        docs = [d for d in pages if is_kind(d, kind)]
        for d in docs:
            w[d] += share / len(docs)
    left = 1.0 - sum(w.values())
    rest = [d for d in dict.fromkeys(named) if w.get(d) == 0.0] or [d for d in pages if w[d] == 0.0]
    for d in rest:
        w[d] = left / len(rest)
    unread = {d: v for d, v in w.items() if d not in read and v > 0}
    total = sum(unread.values())
    return {d: v / total for d, v in unread.items()}


def next_doc(trap: str, pages: dict[str, float], read: set[str]) -> str | None:
    """The first unread document on the diligence map for this issue type, or None once all are read."""
    for kind in DILIGENCE_MAP[trap]:
        for d in sorted(x for x in pages if is_kind(x, kind)):
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
        """A Deal Lead proposal, the whole plan. Committed values stand; beliefs about the rest are replaced, and an
        open issue left out is dropped (chance 0; what was read about it stays). A pending objection still prices its
        issue (see issue())."""
        self.priority = [i["type"] for i in issues]
        for t, e in self.entries.items():
            if e.open and t not in self.priority:
                e.chance = 0.0
        for i in issues:
            e = self.entries[i["type"]]
            e.proposed, e.name, e.docs = True, i.get("name", ""), list(i.get("docs", []))
            if e.known is None:
                e.chance, e.low, e.high = float(i["chance"]), float(i["low"]), float(i["high"])

    def apply(self, commits: list[dict]) -> bool:
        """Committed findings; True if any commit changed a value. A commit that disagrees with what is already known
        widens it to a range covering both, keeping every quote."""
        changed = False
        for c in commits:
            e = self.entries[c["type"]]
            e.proposed = True
            if c["kind"] in ("quoted", "computed", "range"):
                k = (c["low"], c["high"]) if e.known is None else (min(e.known[0], c["low"]),
                                                                    max(e.known[1], c["high"]))
                if k != e.known:
                    e.kind = c["kind"] if e.known is None else "range"
                    changed = True
                e.known = k
                e.quotes = e.quotes + [q for q in c["quotes"] if q not in e.quotes]
            elif c["kind"] == "not_found":
                e.searched = sorted(set(e.searched) | set(c["docs"]))
            elif e.known is None:  # open: a belief without evidence
                e.chance, e.low, e.high = c["chance"], c["low"], c["high"]
        return changed

    def challenge(self, objections: list[dict]) -> None:
        """Each objection reopens its issue for one more investigation, and prices it while pending (see issue()); the
        Deal Lead's belief is untouched, so an objection nobody checks changes nothing once cleared."""
        for o in objections:
            e = self.entries[o["type"]]
            e.objections.append(o)
            e.docs = list(dict.fromkeys(list(o.get("docs", [])) + e.docs))

    def issue(self, t: str) -> Issue:
        """How the engine prices issue t. A pending objection counts where it is higher than the Lead's belief, so the
        router can rank its check and the Lead can't drop it."""
        e = self.entries[t]
        if e.known is not None and e.objections:  # in doubt until checked: the committed floor stands, the top widens
            return Issue(known=(e.known[0], max([o["high"] for o in e.objections] + [e.known[1]])))
        if e.known is not None:
            return Issue(known=e.known)
        if e.objections:
            return Issue(p_real=max([e.chance if e.proposed else 0.0] + [o["chance"] for o in e.objections]),
                         hi=max([e.high if e.proposed else 0.0, typical_high(t, self.face.teaser)]
                                + [o["high"] for o in e.objections]))
        if not e.proposed:
            return Issue(proposed=False)
        return Issue(p_real=e.chance, hi=max(e.high, typical_high(t, self.face.teaser)))

    def worlds(self, seed: int = 0, n: int = N_WORLDS) -> tuple[np.ndarray, np.ndarray]:
        values = draw({t: self.issue(t) for t in TRAPS}, n, np.random.default_rng(seed))
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

    def targets(self) -> list[str]:
        """Issues a read can still settle: open ones with a chance, and any with a pending objection."""
        return [t for t, e in self.entries.items() if e.objections or (e.open and e.chance > 0)]

    def named(self, t: str) -> list[str]:
        """Documents the Deal Lead or a pending objection named for issue t."""
        e = self.entries[t]
        return list(dict.fromkeys(e.docs + [d for o in e.objections for d in o.get("docs", [])]))

    def weights(self, pages: dict[str, float], read: set[str]) -> dict[str, dict[str, float]]:
        """Per unread document, the chance it settles each target issue (D2 §1)."""
        out: dict[str, dict[str, float]] = {}
        for t in self.targets():
            for d, v in settle_weights(t, pages, read, self.named(t)).items():
                out.setdefault(d, {})[t] = v
        return out

    def rank_docs(self, pages: dict[str, float], read: set[str], docs: list[str], seed: int = 0) -> dict[str, float]:
        """The document router (D2 §2): expected $M the mean walk-away moves per page by reading each document."""
        values, w = self.worlds(seed, ROUTE_WORLDS)
        u = np.random.default_rng(seed + 1).random(values.shape)
        wts = self.weights(pages, read)
        return score_docs(values, w, {d: wts.get(d, {}) for d in docs}, pages, self.targets(), u)

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

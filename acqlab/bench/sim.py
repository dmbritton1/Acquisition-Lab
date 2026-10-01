"""The reading simulator (spec 2026-10-01-reading-simulator-design.md): S4's own loop, Deal Record, router and engine,
with the AI turns replaced by rules, so reading strategies can be compared offline. Reading is perfect: opening a
document reveals every fact whose answer-key evidence ends in it. Never calls Claude.

The answer key drives only the simulated reader; the Lead, the router and the engine see what S4 would see."""
import json
from pathlib import Path
from typing import NamedTuple

import numpy as np

from acqlab.agents.knowledge import typical_high
from acqlab.agents.panel import Config, Panel
from acqlab.agents.record import ROUTE_WORLDS, Face, on_map
from acqlab.bench import pilot
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS
from acqlab.generator.truth import cross_fit
from acqlab.routers.routers import DOC_BINS, _labels, regrets

# spec §1: how often each issue type is real (amount > 0) in the 60 practice deals' answer keys (cal-r2, heldout-r2)
BASE_RATE = {"addback": 0.25, "debt_like": 0.37, "concentration": 0.38, "nwc": 0.15, "capex": 0.28}


class Strategy(NamedTuple):
    scorer: str = "move"  # "move": today's router (walk-away move); "regret": decision regret removed
    page_power: float = 1.0  # a document's score is divided by pages ** page_power
    opening: str = "lead"  # "lead": the logged or modelled opening plan; "base_rate": its chances set to BASE_RATE
    absence_cut: float = 0.0  # an open issue a read could settle but didn't: chance *= 1 - absence_cut
    sweep: bool = True


STRATEGIES = {"baseline": Strategy(), "regret": Strategy(scorer="regret"), "pages_0.5": Strategy(page_power=0.5),
              "pages_0": Strategy(page_power=0.0), "base_rate": Strategy(opening="base_rate"),
              "cut_0.25": Strategy(absence_cut=0.25), "cut_0.5": Strategy(absence_cut=0.5),
              "no_sweep": Strategy(sweep=False)}


def strategy(name: str) -> Strategy:
    """A named strategy, or a combination "a+b": each part's changes from the baseline, applied together."""
    out = Strategy()._asdict()
    for part in name.split("+"):
        out |= {k: v for k, v in STRATEGIES[part]._asdict().items() if v != getattr(Strategy(), k)}
    return Strategy(**out)


def no_claude(*args, **kwargs):
    """The simulated panel's session: S4's loop must never reach a real role turn."""
    raise RuntimeError("the simulator never calls Claude")


def reveal(key: AnswerKey, d: str) -> list[dict]:
    """Committer-shaped commits for every fact whose evidence ends in document d."""
    facts = {f.trap: f for f in key.truth.facts}
    out = []
    for e in key.evidence:
        if e.docs[-1] != d:
            continue
        f = facts[e.trap]
        lo, hi = f.documented if f.documented is not None else (f.realized, f.realized)
        out.append({"type": e.trap, "kind": "range" if f.documented is not None else "quoted", "chance": 1.0,
                    "low": float(lo), "high": float(hi), "quotes": [], "docs": [d]})
    return out


def score_docs_regret(values, w, ask, weights, open_, u) -> dict[str, float]:
    """Expected decision regret ($M) removed by reading each document, not per page. The worlds are grouped as in
    routers.score_docs (what the reader would learn); the decision is chosen within each group, cross-fitted as in
    routers.score_regret."""
    reg_go, reg_no = regrets(w, ask)
    now = cross_fit([np.arange(len(w))], reg_go, reg_no)[0]
    labels = {t: _labels(values[:, TRAPS.index(t)], DOC_BINS) for t in open_}
    out = {}
    for d, wd in weights.items():
        key = np.zeros(len(w), dtype=np.int64)
        for t in open_:
            seen = u[:, TRAPS.index(t)] < wd.get(t, 0.0)
            key = key * (DOC_BINS + 2) + np.where(seen, labels[t], DOC_BINS + 1)
        groups = [np.flatnonzero(key == k) for k in np.unique(key)]
        out[d] = max(0.0, float(now - cross_fit(groups, reg_go, reg_no)[0]))
    return out


class SimPanel(Panel):
    """S4 without the Challenger, its AI turns replaced by rules (spec §2)."""

    def __init__(self, room: Path, budget: float, trace: Path, key: AnswerKey, plan: list[dict], s: Strategy):
        super().__init__(room, budget, trace, Config(challenger=False, sweep=s.sweep), no_claude)
        self.key, self.strategy = key, s
        self.opening = [i | {"chance": BASE_RATE[i["type"]]} for i in plan] if s.opening == "base_rate" else plan
        self.planned = False

    def lead(self) -> bool:
        """The opening plan once; afterwards the current beliefs, unchanged."""
        if self.planned:
            issues = [{"type": t, "name": e.name, "chance": e.chance, "low": e.low, "high": e.high, "docs": e.docs}
                      for t in self.record.priority for e in [self.record.entries[t]]]
        else:
            issues, self.planned = self.opening, True
        self.note("propose", {"issues": issues, "stop": False, "reason": "simulated"},
                  result={"planned": len(issues)})
        self.record.plan(issues)
        return False

    def open(self, docs: list[str], could: list[str]) -> bool:
        """Open each document (charging its pages) and report what it settles; `could` gets not_found for any it
        doesn't. True if a commit changed the record."""
        commits = []
        for d in docs:
            self.note("open_document", {"doc_id": d}, cost=float(self.pages[d]))
            commits += reveal(self.key, d)
        settled = {c["type"] for c in commits}
        commits += [{"type": t, "kind": "not_found", "chance": 1.0, "low": None, "high": None, "quotes": [],
                     "docs": list(docs)} for t in could if t not in settled]
        self.note("report", {"findings": []}, result={"commits": commits})
        return self.record.apply(commits)

    def read_doc(self, d: str) -> None:
        could = sorted(self.record.weights(self.pages, self.read())[d])
        self.tried.add(d)
        changed = self.open([d], could)
        if self.strategy.absence_cut:
            for t in could:
                e = self.record.entries[t]
                if e.open:
                    e.chance *= 1 - self.strategy.absence_cut
        if changed:
            self.lead()

    def sweep_picks(self) -> list[str]:
        """Panel.sweep's choice: unread documents on the diligence map, untouched domains first, then the shortest."""
        left, read = self.budget - self.spent(), self.read()
        touched = {d["domain"] for d in self.docs if d["id"] in read}
        picked: list[str] = []
        for d in sorted((d for d in self.docs if d["id"] not in read and on_map(d["id"])),
                        key=lambda d: (d["domain"] in touched, d["pages"], d["id"])):
            if sum(self.pages[p] for p in picked) + d["pages"] <= left:
                picked.append(d["id"])
        return picked

    def sweep(self) -> None:
        if picked := self.sweep_picks():
            self.open(picked, [])

    def scores(self, read: set[str], cands: list[str]) -> dict[str, float]:
        p = self.strategy.page_power
        if self.strategy.scorer == "move":  # rank_docs is already per page
            s = self.record.rank_docs(self.pages, read, cands)
            return {d: s[d] * self.pages[d] ** (1 - p) for d in cands}
        values, w = self.record.worlds(0, ROUTE_WORLDS)  # rank_docs' seeds, so both scorers see the same worlds
        u = np.random.default_rng(1).random(values.shape)
        wts = self.record.weights(self.pages, read)
        raw = score_docs_regret(values, w, self.record.face.deal.asking_price,
                                {d: wts.get(d, {}) for d in cands}, self.record.targets(), u)
        return {d: raw[d] / self.pages[d] ** p for d in cands}

    def route(self, until: float | None = None) -> str | None:
        """Panel.route with the strategy's scores."""
        read, left = self.read(), (self.budget if until is None else until) - self.spent()
        wts, skip = self.record.weights(self.pages, read), read | self.tried
        cands = [d for d in wts if d not in skip and self.pages[d] <= left]
        if not cands:
            return None
        scores = self.scores(read, cands)
        order = sorted(cands, key=lambda d: (-scores[d], self.pages[d], d))
        if scores[order[0]] <= 0:
            return None
        self.note("route", {"doc": order[0], "issues": sorted(wts[order[0]]),
                            "scores": {d: scores[d] for d in order[:5]}})
        return order[0]


def logged_plan(trace: Path) -> list[dict]:
    """The real Deal Lead's first accepted plan in an S4 trace."""
    rows = [json.loads(x) for x in trace.read_text().splitlines()]
    return next(r for r in rows if r["tool"] == "propose" and not r["refused"])["args"]["issues"]


def kind(doc: str) -> str:
    return "contract" if doc.startswith("contract_") else doc


def fit_lead(plans: list[tuple[list[dict], Face]]) -> dict[str, dict]:
    """The modelled Lead (spec §2), from logged opening plans: per issue type, the median chance, the median ratio of
    its high to typical_high, and the document kinds named in at least half the plans."""
    model = {}
    for t in TRAPS:
        its = [(i, f) for plan, f in plans for i in plan if i["type"] == t]
        kinds = sorted({kind(d) for i, _ in its for d in i["docs"]})
        model[t] = {"chance": float(np.median([i["chance"] for i, _ in its])),
                    "high_ratio": float(np.median([i["high"] / typical_high(t, f.teaser) for i, f in its])),
                    "kinds": [k for k in kinds if 2 * sum(k in {kind(d) for d in i["docs"]} for i, _ in its)
                              >= len(its)]}
    return model


def model_plan(model: dict[str, dict], face: Face, docs: list[str]) -> list[dict]:
    """The modelled Lead's opening plan for one deal: every issue type, in TRAPS order."""
    return [{"type": t, "name": t, "chance": m["chance"], "low": 0.0,
             "high": m["high_ratio"] * typical_high(t, face.teaser),
             "docs": [d for d in docs if kind(d) in m["kinds"]]}
            for t, m in model.items()]


def reading_stats(key: AnswerKey, opened: list[str], pages: dict[str, float]) -> dict:
    """Pages on documents holding no fact at all, and the share of real facts (amount > 0) whose last evidence
    document was opened (None if the deal has none)."""
    facts = {f.trap: f for f in key.truth.facts}
    holding = {d for e in key.evidence for d in e.docs}
    real = [e for e in key.evidence if facts[e.trap].amount > 0]
    return {"nofact_pages": float(sum(pages[d] for d in opened if d not in holding)),
            "real_reached": float(np.mean([e.docs[-1] in opened for e in real])) if real else None}


def simulate(data: Path, deal: str, s: Strategy, name: str, plan: list[dict], out: Path) -> dict:
    """One simulated run, scored like a real one; writes <out> and its trace beside it."""
    key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
    room = (data / "deals" / deal / "room").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    trace = out.with_suffix(".trace.jsonl")
    trace.unlink(missing_ok=True)
    panel = SimPanel(room, key.budget, trace.resolve(), key, plan, s)
    panel.run()
    rows = [json.loads(x) for x in trace.read_text().splitlines()]
    opened = [r["args"]["doc_id"] for r in rows if r["tool"] == "open_document"]
    row = pilot.score(key, name, rows, None, "ok") | {"rep": 0, "opened": opened}
    row |= reading_stats(key, opened, panel.pages)
    out.write_text(json.dumps(row, indent=2))
    return row

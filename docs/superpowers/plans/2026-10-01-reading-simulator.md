# Reading Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A free, offline simulator that runs S4's real loop, Deal Record, router and engine with the AI turns replaced
by rules, checks that it reproduces the real team, compares seven reading strategies on 300 template deals, and sizes
the next real test.

**Architecture:** `acqlab/bench/sim.py` subclasses the frozen `Panel` as `SimPanel`, overriding only the Lead, the
reader, the sweep and the router's scoring; the reader reveals what the answer key says a document holds. Runs are
written in the real trace format and graded by `pilot.score`. `acqlab/bench/simrun.py` makes template deals, runs
strategies in a process pool (resumable), builds the greedy combination and writes the report JSON.

**Tech Stack:** Python 3.12, numpy, pydantic, pytest; `uv run`. Standard library `concurrent.futures` and
`statistics.NormalDist`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-01-reading-simulator-design.md`

## Global Constraints

- **No Claude or Codex calls.** The simulated panel's session is `sim.no_claude`, which raises
  `RuntimeError("the simulator never calls Claude")`. Template deals use template prose (no `--llm`).
- **S4 is frozen:** `acqlab/agents` and `acqlab/routers` stay byte-identical to tag `s4-frozen-plan5`; new code lives in
  `acqlab/bench`.
- **Answer keys** drive only the simulated reader and the scoring, never the simulated Lead, the router or the engine.
- **Tuning limits:** at most 3 values per strategy setting (the baseline's included); at most one fix to the simulator
  after a failed faithfulness check, then one re-check; a second failure stops for the user's decision.
- **Pass bars (spec §2):** calls agree on ≥ 85%, |mean regret sim − real| < 0.003 and the paired CI includes zero,
  checked separately on the 60 practice deals, the 160 test deals and the 40 `s4_nochal` deals (stricter than pooling
  the 220).
- **The 160 test deals** are used only in the faithfulness check, never to judge a strategy.
- **Results are exploratory;** any real run is a separate plan that needs the user's OK.
- **Conventions:** complete code, TDD, lines ≤ 120 characters, commits end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The suite has 337 tests before Task 1.

## Review Focus

- **A run interrupted between its trace and its result:** the next `run` redoes it (the stray trace is replaced).
  Test: `test_a_run_interrupted_before_its_result_is_redone` (Task 2).
- **A misspelt strategy name on the command line:** refused with a `KeyError` naming it, not run as the baseline.
  Test: `test_an_unknown_strategy_name_is_refused` (Task 1).
- **A deal whose budget fits no document:** the simulated team still submits the engine's call.
  Test: `test_a_budget_too_small_for_any_document_still_submits` (Task 1).
- **A real S4 trace whose first proposal was refused:** the logged opening is the first accepted one.
  Test: `test_the_logged_plan_is_the_first_accepted_proposal` (Task 1).
- **A deal present on only one side of the faithfulness check:** only deals both sides ran are compared.
  Test: `test_faithfulness_counts_only_deals_both_sides_ran` (Task 2).

## Files

- Create `acqlab/bench/sim.py`: `Strategy`, `STRATEGIES`, `strategy()`, `no_claude`, `reveal`, `score_docs_regret`,
  `SimPanel`, `logged_plan`, `kind`, `fit_lead`, `model_plan`, `reading_stats`, `simulate`.
- Create `acqlab/bench/simrun.py`: `make_deals`, `deals_of`, `fitted`, `run`, `load`, `paired`, `opened`,
  `faithfulness`, `table`, `best_of`, `greedy`, `deals_needed`, `sizing`, `combine`, `report`, `main`.
- Modify `acqlab/bench/testset.py:37-40`: `clashes` takes the split (default `"test"`, unchanged behaviour).
- Create `tests/bench/test_sim.py` (19 tests) and `tests/bench/test_simrun.py` (12 tests).
- Task 3 writes `docs/results/reading-simulator.json`, `docs/results/reading-simulator.md` and updates
  `docs/HANDOFF.md`. Simulated runs and template deals go to `data/sim-r2/` (git-ignored, like all `data/`).

---

### Task 1: The simulator core (`sim.py`)

**Files:**
- Create: `acqlab/bench/sim.py`
- Test: `tests/bench/test_sim.py`

**Interfaces:**
- Consumes (frozen, unchanged): `acqlab.agents.panel.Panel(room, budget, trace, cfg, session)` with `run()`,
  `read()`, `spent()`, `note(tool, args, **extra)`, `route(until)`, attributes `pages`, `docs`, `record`, `tried`,
  `reserve`, `budget`, `cfg`, `session`; `Config(challenger=..., sweep=...)`; `Record.plan/apply/weights/rank_docs/
  worlds/targets/priority/entries/face`; `routers.routers.DOC_BINS, _labels, regrets`; `generator.truth.cross_fit`;
  `record.ROUTE_WORLDS, Face, load_face, on_map`; `knowledge.typical_high`; `pilot.score(key, system, trace, cli,
  status)`.
- Produces (Task 2 relies on these exact names):
  - `Strategy(scorer="move", page_power=1.0, opening="lead", absence_cut=0.0, sweep=True)` (NamedTuple)
  - `STRATEGIES: dict[str, Strategy]` with keys `baseline, regret, pages_0.5, pages_0, base_rate, cut_0.25, cut_0.5,
    no_sweep`; `strategy(name: str) -> Strategy` (parses `"a+b"`)
  - `logged_plan(trace: Path) -> list[dict]`; `fit_lead(plans: list[tuple[list[dict], Face]]) -> dict[str, dict]`;
    `model_plan(model: dict, face: Face, docs: list[str]) -> list[dict]`
  - `simulate(data: Path, deal: str, s: Strategy, name: str, plan: list[dict], out: Path) -> dict` — writes
    `out` (the scored row plus `opened`, `nofact_pages`, `real_reached`) and `out.with_suffix(".trace.jsonl")`.

**Notes for the implementer:**
- Read the spec §1–§2 first. Do not edit anything under `acqlab/agents` or `acqlab/routers`.
- The reader rule is "revealed by the last document of the fact's evidence": on the 220 real S4 runs, all 173
  two-document commits came from that document alone (spec §2).
- `score_docs_regret` repeats `routers.score_docs`' world-grouping loop on purpose: `routers` is frozen, so it cannot
  be refactored to share it.
- The tests use the session-scoped `data` fixture from `tests/conftest.py` (two generated dev deals).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_sim.py`:

```python
import json
import subprocess

import numpy as np
import pytest

import acqlab.agents.panel as panel_mod
from acqlab.agents.panel import Config, Panel
from acqlab.agents.record import load_face
from acqlab.bench import sim
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS


def _key(data, deal="dev-000") -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())


def _room(data, deal="dev-000"):
    return data / "deals" / deal / "room"


def _plan(chance=0.4):
    return [{"type": t, "name": t, "chance": chance, "low": 0.0, "high": 5.0, "docs": []} for t in TRAPS]


def _panel(data, tmp_path, s=sim.Strategy(), name="t.jsonl"):
    key = _key(data)
    return sim.SimPanel(_room(data), key.budget, tmp_path / name, key, _plan(), s)


def _rows(trace):
    return [json.loads(x) for x in trace.read_text().splitlines()]


def test_a_fact_is_revealed_by_the_last_document_of_its_evidence_only(data):
    key = _key(data)
    e = key.evidence[0]
    e.docs = ["cim", "qoe"]
    assert e.trap not in {c["type"] for c in sim.reveal(key, "cim")}
    got = [c for c in sim.reveal(key, "qoe") if c["type"] == e.trap]
    f = next(f for f in key.truth.facts if f.trap == e.trap)
    assert got == [{"type": e.trap, "kind": "quoted", "chance": 1.0, "low": f.realized, "high": f.realized,
                    "quotes": [], "docs": ["qoe"]}]


def test_an_unresolvable_fact_commits_its_documented_range(data):
    key = _key(data)
    e = key.evidence[0]
    f = next(f for f in key.truth.facts if f.trap == e.trap)
    f.documented = (1.0, 3.0)
    c = next(c for c in sim.reveal(key, e.docs[-1]) if c["type"] == e.trap)
    assert (c["kind"], c["low"], c["high"]) == ("range", 1.0, 3.0)


def test_strategies_combine_their_changes_from_the_baseline():
    assert sim.strategy("baseline") == sim.Strategy()
    assert sim.strategy("regret+no_sweep") == sim.Strategy(scorer="regret", sweep=False)
    assert sim.strategy("pages_0.5+cut_0.25+base_rate") == sim.Strategy(page_power=0.5, absence_cut=0.25,
                                                                        opening="base_rate")


def test_the_simulator_never_calls_claude(data, tmp_path):
    with pytest.raises(RuntimeError, match="never calls Claude"):
        sim.no_claude()
    p = _panel(data, tmp_path)
    assert p.session is sim.no_claude
    p.run()  # the session raises if any role turn is reached
    assert _rows(tmp_path / "t.jsonl")[-1]["tool"] == "submit"


def test_reads_charge_pages_and_report_what_they_settle(data, tmp_path):
    p = _panel(data, tmp_path)
    p.lead()
    key = _key(data)
    d = key.evidence[0].docs[-1]
    p.read_doc(d)
    rows = _rows(tmp_path / "t.jsonl")
    assert any(r["tool"] == "open_document" and r["args"]["doc_id"] == d and r["cost"] == p.pages[d] for r in rows)
    assert p.read() == {d}
    assert p.record.entries[key.evidence[0].trap].known is not None


def test_the_baseline_routes_like_the_real_panel(data, tmp_path):
    p = _panel(data, tmp_path)
    p.lead()
    assert p.route() == Panel.route(p) is not None


def test_page_power_rescales_scores_by_pages_only(data, tmp_path):
    for scorer in ("move", "regret"):
        one, half = (_panel(data, tmp_path, sim.Strategy(scorer=scorer, page_power=pw), f"{scorer}{pw}.jsonl")
                     for pw in (1.0, 0.5))
        one.lead(), half.lead()
        cands = sorted(one.pages)
        a, b = one.scores(set(), cands), half.scores(set(), cands)
        assert all(b[d] == pytest.approx(a[d] * one.pages[d] ** 0.5) for d in cands)


def test_the_regret_scorer_values_a_document_by_the_decision_regret_it_removes():
    n = 2000
    rng = np.random.default_rng(0)
    addback = np.where(rng.random(n) < 0.5, 0.0, 10.0)  # about half the worlds have the problem
    values = np.zeros((n, len(TRAPS)))
    values[:, TRAPS.index("addback")] = addback
    w = np.where(addback > 0, 80.0, 100.0)  # walk-away 100 without it, 80 with it; asking 90
    u = rng.random(values.shape)
    s = sim.score_docs_regret(values, w, 90.0, {"settles": {"addback": 1.0}, "blank": {}}, ["addback"], u)
    assert s["settles"] == pytest.approx(5.0, abs=0.5)  # either call now costs about 5 in expectation
    assert s["blank"] == 0.0


def test_absence_cut_lowers_only_issues_the_read_could_settle(data, tmp_path):
    key = _key(data)
    p = _panel(data, tmp_path, sim.Strategy(absence_cut=0.5))
    p.lead()
    wts = p.record.weights(p.pages, set())
    d = next(d for d in sorted(wts) if not sim.reveal(key, d))  # a read that settles nothing
    p.read_doc(d)
    for t in TRAPS:
        assert p.record.entries[t].chance == pytest.approx(0.2 if t in wts[d] else 0.4)


def test_base_rate_replaces_only_the_opening_chances(data, tmp_path):
    p = _panel(data, tmp_path, sim.Strategy(opening="base_rate"))
    p.lead()
    for t in TRAPS:
        e = p.record.entries[t]
        assert (e.chance, e.high) == (sim.BASE_RATE[t], 5.0)


def test_no_sweep_keeps_no_reserve_and_never_sweeps(data, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(sim.SimPanel, "sweep", lambda self: called.append(1))
    p = _panel(data, tmp_path, sim.Strategy(sweep=False))
    assert p.reserve == 0
    p.run()
    assert called == []


def test_the_sweep_picks_what_the_real_sweep_picks(data, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(panel_mod.prompts, "sweep_prompt", lambda teaser, docs, sweep, read, budget:
                        seen.append(list(sweep)) or "")
    key = _key(data)
    Panel(_room(data), key.budget, tmp_path / "real.jsonl", Config(challenger=False), lambda *a: None).sweep()
    assert seen and _panel(data, tmp_path).sweep_picks() == seen[0]


def test_a_simulated_run_is_repeatable_and_graded_like_a_real_one(data, tmp_path):
    a = sim.simulate(data, "dev-000", sim.Strategy(), "baseline", _plan(), tmp_path / "a" / "dev-000.json")
    b = sim.simulate(data, "dev-000", sim.Strategy(), "baseline", _plan(), tmp_path / "b" / "dev-000.json")
    assert _rows(tmp_path / "a" / "dev-000.trace.jsonl") == _rows(tmp_path / "b" / "dev-000.trace.jsonl")
    assert a == b
    rows = _rows(tmp_path / "a" / "dev-000.trace.jsonl")
    assert a["pages"] == sum(r["cost"] for r in rows if r["tool"] == "open_document")
    assert a["opened"] == [r["args"]["doc_id"] for r in rows if r["tool"] == "open_document"]
    assert a["answered"] and a["system"] == "baseline"
    assert json.loads((tmp_path / "a" / "dev-000.json").read_text()) == a


def test_the_modelled_lead_takes_medians_and_kinds_named_in_half_the_plans(data):
    face = load_face(_room(data))
    th = {t: sim.typical_high(t, face.teaser) for t in TRAPS}

    def plan(c, r, docs):
        return [{"type": t, "chance": c, "low": 0, "high": r * th[t], "docs": docs} for t in TRAPS]

    model = sim.fit_lead([(plan(0.2, 1.0, ["qoe", "contract_2"]), face), (plan(0.4, 2.0, ["qoe"]), face),
                          (plan(0.6, 3.0, ["legal", "contract_1"]), face)])
    assert model["nwc"] == {"chance": 0.4, "high_ratio": 2.0, "kinds": ["contract", "qoe"]}
    issues = sim.model_plan(model, face, ["qoe", "contract_1", "contract_2", "legal"])
    nwc = next(i for i in issues if i["type"] == "nwc")
    assert nwc["docs"] == ["qoe", "contract_1", "contract_2"] and nwc["high"] == pytest.approx(2.0 * th["nwc"])
    assert [i["type"] for i in issues] == list(TRAPS)


def test_reading_stats_count_pages_on_documents_with_no_fact(data):
    key = _key(data)
    holding = {d for e in key.evidence for d in e.docs}
    empty = next(d for d in ["insurance", "hr_policy", "it_policy", "whistleblowing"] if d not in holding)
    last = key.evidence[0].docs[-1]
    st = sim.reading_stats(key, [empty, last], {empty: 3.0, last: 9.0})
    assert st["nofact_pages"] == 3.0
    real = [e for e in key.evidence if next(f for f in key.truth.facts if f.trap == e.trap).amount > 0]
    if real:
        assert st["real_reached"] == pytest.approx(sum(e.docs[-1] == last for e in real) / len(real))


def test_s4_s_files_are_unchanged_from_the_freeze_tag():
    tag = subprocess.run(["git", "rev-parse", "-q", "--verify", "s4-frozen-plan5"], capture_output=True)
    if tag.returncode:
        pytest.skip("no freeze tag in this checkout")
    assert subprocess.run(["git", "diff", "--quiet", "s4-frozen-plan5", "--", "acqlab/agents",
                           "acqlab/routers"]).returncode == 0


def test_an_unknown_strategy_name_is_refused():
    with pytest.raises(KeyError, match="nope"):
        sim.strategy("regret+nope")


def test_a_budget_too_small_for_any_document_still_submits(data, tmp_path):
    key = _key(data)
    sim.SimPanel(_room(data), 1.0, tmp_path / "t.jsonl", key, _plan(), sim.Strategy()).run()
    rows = _rows(tmp_path / "t.jsonl")
    assert rows[-1]["tool"] == "submit" and not any(r["tool"] == "open_document" for r in rows)


def test_the_logged_plan_is_the_first_accepted_proposal(tmp_path):
    t = tmp_path / "s4.trace.jsonl"
    rows = [{"tool": "propose", "refused": True, "args": {"issues": ["refused"]}},
            {"tool": "propose", "refused": False, "args": {"issues": ["first"]}},
            {"tool": "propose", "refused": False, "args": {"issues": ["later"]}}]
    t.write_text("\n".join(json.dumps(r) for r in rows))
    assert sim.logged_plan(t) == ["first"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/bench/test_sim.py -q`
Expected: collection error, `ImportError: cannot import name 'sim' from 'acqlab.bench'`.

- [ ] **Step 3: Write the implementation**

Create `acqlab/bench/sim.py`:

```python
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
        raw = score_docs_regret(values, w, self.record.face.deal.asking_price, {d: wts.get(d, {}) for d in cands},
                                self.record.targets(), u)
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
             "high": m["high_ratio"] * typical_high(t, face.teaser), "docs": [d for d in docs if kind(d) in m["kinds"]]}
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/bench/test_sim.py -q`
Expected: 19 passed (about 2–3 minutes; the engine is slow by design). In a checkout without the
`s4-frozen-plan5` tag, the freeze test skips (18 passed, 1 skipped).

- [ ] **Step 5: Run the full suite and the freeze check**

Run: `uv run pytest -q` — expected: 356 passed.
Run: `git diff --quiet s4-frozen-plan5 -- acqlab/agents acqlab/routers && echo frozen` — expected: `frozen`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/bench/sim.py tests/bench/test_sim.py
git commit -m "feat(bench): the reading simulator core, S4's loop with rule-based turns (reading simulator, Task 1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The runner (`simrun.py`) and the seed check by split

**Files:**
- Create: `acqlab/bench/simrun.py`
- Modify: `acqlab/bench/testset.py:37-40` (`clashes`)
- Test: `tests/bench/test_simrun.py`

**Interfaces:**
- Consumes: Task 1's `sim.STRATEGIES`, `sim.strategy`, `sim.logged_plan`, `sim.fit_lead`, `sim.model_plan`,
  `sim.simulate`; `testset.used_seeds(roots)`; `generator.batch.run(out, counts, *, seed, mc, profile)`;
  `routers.track_a.bootstrap_ci(d)`; `record.load_face(room)`.
- Produces (Task 3 uses the CLI):
  - `testset.clashes(base, n, used, split="test") -> list[int]`
  - `simrun.make_deals(out, n, base, roots, mc=400) -> list[int]` (clashing seeds; generates nothing if any)
  - `simrun.run(data, names, opening, runs=RUNS, jobs=None, model=None) -> int` (runs made)
  - `simrun.faithfulness(sim_rows, real_rows, sim_docs, real_docs) -> dict` with `passes`
  - `simrun.table(by) -> dict`, `simrun.greedy(tab, by, run_combo) -> {"combo", "steps"}`,
    `simrun.deals_needed(gap, sd=SD, power=0.8, alpha=0.05) -> int`, `simrun.sizing(sim_gain) -> dict`
  - CLI: `deals --base B [--n 300]`, `run --data D --strategies a,b --opening logged|model [--jobs N]`,
    `combine [--data data/sim-r2]`, `report --json PATH`.

**Notes for the implementer:**
- The process pool needs `_one` at module level (it is pickled). `run` skips any strategy-deal whose `.json` exists;
  `simulate` replaces a stray trace, so an interrupted run is redone.
- `report()` returns early (faithfulness only) until every single strategy has template runs: spec §2 compares
  strategies only after the faithfulness check.
- `clashes`' new `split` argument defaults to `"test"`, so `testset seeds` (Plan 6) behaves exactly as before.

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_simrun.py`:

```python
import json
import math

import pytest

from acqlab.bench import simrun, testset
from acqlab.generator.traps import TRAPS

MODEL = {t: {"chance": 0.4, "high_ratio": 1.0, "kinds": ["qoe"]} for t in TRAPS}


def _rows(regrets, go=None, pages=10.0):
    return {f"d{i}": {"regret": r, "go": True if go is None else go[i], "correct": r == 0, "pages": pages,
                      "nofact_pages": 2.0, "real_reached": 0.5} for i, r in enumerate(regrets)}


def test_clashes_checks_the_split_s_own_seeds():
    assert testset.clashes(100, 5, {103}, split="dev") == [103]
    assert testset.clashes(100, 5, {103}) == []  # the test split adds its offset, as before
    assert testset.clashes(100, 5, {10_103}) == [10_103]


def test_template_deals_are_refused_on_a_seed_clash_and_made_otherwise(tmp_path, data):
    used = testset.used_seeds([data])
    clash = min(used)
    assert clash in simrun.make_deals(tmp_path / "x", 2, clash, [data], mc=20)
    assert not (tmp_path / "x").exists()
    base = max(used) + 1000
    assert simrun.make_deals(tmp_path / "y", 2, base, [data], mc=20) == []
    assert json.loads((tmp_path / "y" / "seed.json").read_text()) == {"base": base, "n": 2, "split": "dev"}
    assert len(list((tmp_path / "y" / "truth").glob("*.json"))) == 2


def test_runs_are_made_once_and_resume(data, tmp_path):
    runs = tmp_path / "runs"
    assert simrun.run(data, ["baseline", "no_sweep"], "model", runs, jobs=1, model=MODEL) == 4
    assert simrun.run(data, ["baseline", "no_sweep"], "model", runs, jobs=1, model=MODEL) == 0
    got = simrun.load(runs, data, "no_sweep")
    assert sorted(got) == ["dev-000", "dev-001"] and got["dev-000"]["system"] == "no_sweep"


def test_logged_openings_take_only_deals_with_a_real_s4_trace(data):
    assert simrun.deals_of(data, "model") == ["dev-000", "dev-001"]
    assert simrun.deals_of(data, "logged") == []


def test_faithfulness_measures_agreement_and_applies_the_pass_bars():
    real = _rows([0.0] * 20, go=[True] * 20)
    docs = {d: ["a", "b"] for d in real}
    same = simrun.faithfulness(real, real, docs, docs)
    assert same["agree"] == 1.0 and same["jaccard"] == 1.0 and same["passes"]
    flipped = _rows([0.0] * 20, go=[i >= 4 for i in range(20)])  # 4 of 20 differ: 80% < 85%
    assert simrun.faithfulness(flipped, real, docs, docs)["passes"] is False
    worse = _rows([0.004] * 20, go=[True] * 20)  # agree, but regret off by 0.004 >= 0.003
    assert simrun.faithfulness(worse, real, docs, docs)["passes"] is False
    other = {d: ["a", "c"] for d in real}
    f = simrun.faithfulness(real, real, other, docs)
    assert f["jaccard"] == pytest.approx(1 / 3) and f["first_divergence_median"] == 1


def test_the_table_pairs_every_strategy_with_the_baseline():
    by = {"baseline": _rows([0.01, 0.02, 0.03]), "regret": _rows([0.0, 0.01, 0.02])}
    tab = simrun.table(by)
    assert tab["baseline"]["minus_base"] is None
    assert tab["regret"]["minus_base"]["diff"] == pytest.approx(-0.01)
    assert tab["regret"]["nofact_share"] == pytest.approx(0.2)


def test_greedy_keeps_only_additions_that_clearly_help():
    n = 40
    base = [0.02] * n
    by = {name: _rows(base) for name in simrun.SINGLES}
    by["regret"] = _rows([0.01] * n)  # clearly better alone
    by["base_rate"] = _rows([0.015] * n)
    by["no_sweep"] = _rows([0.019] * n)
    tab = simrun.table(by)
    tried = []

    def run_combo(name):
        tried.append(name)
        return _rows([0.005] * n) if name == "regret+base_rate" else _rows([0.006] * n)

    out = simrun.greedy(tab, by, run_combo)
    assert out["combo"] == "regret+base_rate"
    assert tried[0] == "regret+base_rate" and all(t.startswith("regret+base_rate+") for t in tried[1:])
    assert [s["kept"] for s in out["steps"]] == [True] + [False] * (len(tried) - 1)


def test_greedy_falls_back_to_the_baseline_when_nothing_helps():
    by = {name: _rows([0.02] * 10) for name in simrun.SINGLES}
    assert simrun.greedy(simrun.table(by), by, lambda name: pytest.fail("no combination to run")) == {
        "combo": "baseline", "steps": []}


def test_deals_needed_matches_the_closed_form():
    assert simrun.deals_needed(1.0, sd=1.0, power=0.5) == math.ceil(1.959963984540054 ** 2)
    assert simrun.deals_needed(0.0038) == math.ceil(((1.959963984540054 + 0.8416212335729143) * 0.0368 / 0.0038) ** 2)


def test_sizing_adds_the_simulated_gain_and_its_half():
    s = simrun.sizing(-0.002)
    assert s["full"]["gap"] == pytest.approx(-0.0058) and s["half"]["gap"] == pytest.approx(-0.0048)
    assert s["full"]["power_80"] < s["half"]["power_80"] < s["half"]["power_90"]
    assert simrun.sizing(0.001)["full"]["gap"] == pytest.approx(-0.0038)  # a loss in simulation adds nothing


def test_a_run_interrupted_before_its_result_is_redone(data, tmp_path):
    runs = tmp_path / "runs"
    stray = runs / data.name / "baseline" / "dev-000.trace.jsonl"
    stray.parent.mkdir(parents=True)
    stray.write_text('{"tool": "half a run"}\n')
    assert simrun.run(data, ["baseline"], "model", runs, jobs=1, model=MODEL) == 2
    assert "half a run" not in stray.read_text()


def test_faithfulness_counts_only_deals_both_sides_ran():
    real = _rows([0.0] * 21, go=[True] * 21)
    sim_rows = {d: r for d, r in real.items() if d != "d20"}
    docs = {d: ["a"] for d in real}
    assert simrun.faithfulness(sim_rows, real, docs, docs)["n"] == 20
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/bench/test_simrun.py -q`
Expected: collection error, `ImportError: cannot import name 'simrun' from 'acqlab.bench'`.

- [ ] **Step 3: Let `clashes` check any split**

In `acqlab/bench/testset.py`, replace `clashes` (lines 37–40) with:

```python
def clashes(base: int, n: int, used: set[int], split: str = "test") -> list[int]:
    """Used seeds equal to one of the n deals' seeds in this split or to one of its retries (retries add multiples
    of RETRY_SEED, so a clash is a match modulo RETRY_SEED)."""
    mine = {(base + SEED_OFFSET[split] + i) % RETRY_SEED for i in range(n)}
```

(the function's last line, `return sorted(s for s in used if s % RETRY_SEED in mine)`, is unchanged).

- [ ] **Step 4: Write the runner**

Create `acqlab/bench/simrun.py`:

```python
"""The reading simulator's runner (spec 2026-10-01-reading-simulator-design.md §3): template deals, simulated runs
in a process pool, the greedy combination, and the report. Offline: no Claude or Codex call anywhere.

  uv run python -m acqlab.bench.simrun deals --out data/sim-r2 --n 300 --base 7000000
  uv run python -m acqlab.bench.simrun run --data data/cal-r2 --strategies baseline --opening logged
  uv run python -m acqlab.bench.simrun run --data data/sim-r2 --strategies baseline,regret,... --opening model
  uv run python -m acqlab.bench.simrun combine --data data/sim-r2
  uv run python -m acqlab.bench.simrun report --json docs/results/reading-simulator.json

Runs go to <runs>/<data dir name>/<strategy>/<deal>.json (default runs: data/sim-r2/runs); finished runs are skipped.
Exit codes: 0 done; 1 refused (a seed clash, or a missing input)."""
import argparse
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import NormalDist

import numpy as np

from acqlab.agents.record import load_face
from acqlab.bench import sim, testset
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey
from acqlab.routers.track_a import bootstrap_ci

RUNS = Path("data/sim-r2/runs")
PRACTICE = (Path("data/cal-r2"), Path("data/heldout-r2"))
TEST = Path("data/test-r2")
SINGLES = list(sim.STRATEGIES)
FAMILIES = {"regret": ["regret"], "pages": ["pages_0.5", "pages_0"], "base_rate": ["base_rate"],
            "cut": ["cut_0.25", "cut_0.5"], "no_sweep": ["no_sweep"]}  # spec §3: a family enters at its best value
AGREE, REGRET_GAP = 0.85, 0.003  # spec §2's pass bars
SD, H1_GAP = 0.0368, -0.0038  # Plan 6: per-deal SD of S4 − S1b regret, and its mean


# --- deals -------------------------------------------------------------------------------------------------------

def make_deals(out: Path, n: int, base: int, roots: list[Path], mc: int = 400) -> list[int]:
    """Template-prose r2 deals as split dev (seeds base..base+n-1). Returns the clashing used seeds; generates
    nothing if there are any."""
    bad = testset.clashes(base, n, testset.used_seeds(roots), split="dev")
    if not bad:
        batch.run(out, {"dev": n}, seed=base, mc=mc, profile="r2")
        (out / "seed.json").write_text(json.dumps({"base": base, "n": n, "split": "dev"}))
    return bad


# --- runs --------------------------------------------------------------------------------------------------------

def deals_of(data: Path, opening: str) -> list[str]:
    """Logged openings need a real S4 trace; modelled ones take every deal."""
    deals = [d for ds in json.loads((data / "splits.json").read_text()).values() for d in ds]
    return [d for d in deals if opening == "model" or (data / "runs" / "s4" / f"{d}.trace.jsonl").exists()]


def fitted() -> dict:
    """The modelled Lead, fitted on the practice deals' logged opening plans (spec §2)."""
    plans = [(sim.logged_plan(t), load_face(p / "deals" / t.name.split(".")[0] / "room"))
             for p in PRACTICE for t in sorted((p / "runs" / "s4").glob("*.trace.jsonl"))]
    return sim.fit_lead(plans)


def _one(job: tuple) -> str:
    data, deal, name, opening, model, out = job
    room = data / "deals" / deal / "room"
    docs = [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]]
    plan = (sim.logged_plan(data / "runs" / "s4" / f"{deal}.trace.jsonl") if opening == "logged"
            else sim.model_plan(model, load_face(room), docs))
    sim.simulate(data, deal, sim.strategy(name), name, plan, out)
    return deal


def run(data: Path, names: list[str], opening: str, runs: Path = RUNS, jobs: int | None = None,
        model: dict | None = None) -> int:
    """Every missing run of these strategies on this deal set; returns how many were made. A modelled opening uses
    `model`, or the Lead fitted on the practice deals."""
    if opening == "model" and model is None:
        model = fitted()
    todo = [(data, d, name, opening, model, runs / data.name / name / f"{d}.json")
            for name in names for d in deals_of(data, opening)]
    todo = [j for j in todo if not j[-1].exists()]
    with ProcessPoolExecutor(jobs or os.cpu_count()) as pool:
        for i, _ in enumerate(pool.map(_one, todo), 1):
            if i % 50 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} runs")
    return len(todo)


def load(runs: Path, data: Path, name: str) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted((runs / data.name / name).glob("*.json"))}


# --- analysis ----------------------------------------------------------------------------------------------------

def paired(a: dict, b: dict, field: str = "regret") -> dict:
    """a − b on the deals both have: n, mean, paired bootstrap CI."""
    ds = sorted(set(a) & set(b))
    d = np.array([a[x][field] - b[x][field] for x in ds], dtype=float)
    return {"n": len(ds), "diff": float(d.mean()), "ci95": [float(x) for x in bootstrap_ci(d)]}


def opened(trace: Path) -> list[str]:
    rows = [json.loads(x) for x in trace.read_text().splitlines()]
    return [r["args"]["doc_id"] for r in rows if r["tool"] == "open_document" and not r["refused"]]


def faithfulness(sim_rows: dict, real_rows: dict, sim_docs: dict, real_docs: dict) -> dict:
    """Simulated baseline against the real system, deal by deal (spec §2)."""
    ds = sorted(set(sim_rows) & set(real_rows))
    jac = [len(set(sim_docs[d]) & set(real_docs[d])) / max(1, len(set(sim_docs[d]) | set(real_docs[d]))) for d in ds]
    diverge = [next((i for i, (a, b) in enumerate(zip(sim_docs[d], real_docs[d])) if a != b),
                    min(len(sim_docs[d]), len(real_docs[d]))) for d in ds]
    out = {"n": len(ds), "agree": float(np.mean([sim_rows[d]["go"] == real_rows[d]["go"] for d in ds])),
           "regret_sim": float(np.mean([sim_rows[d]["regret"] for d in ds])),
           "regret_real": float(np.mean([real_rows[d]["regret"] for d in ds])),
           "sim_minus_real": paired(sim_rows, real_rows),
           "pages_sim": float(np.mean([sim_rows[d]["pages"] for d in ds])),
           "pages_real": float(np.mean([real_rows[d]["pages"] for d in ds])),
           "jaccard": float(np.mean(jac)), "same_reads": float(np.mean([sim_docs[d] == real_docs[d] for d in ds])),
           "first_divergence_median": float(np.median(diverge))}
    ci = out["sim_minus_real"]["ci95"]
    out["passes"] = (out["agree"] >= AGREE and abs(out["sim_minus_real"]["diff"]) < REGRET_GAP
                     and ci[0] <= 0 <= ci[1])
    return out


def table(by: dict[str, dict], base: str = "baseline") -> dict:
    """Per strategy: means, and the paired difference from the baseline."""
    out = {}
    for name, rows in by.items():
        rs = list(rows.values())
        reached = [r["real_reached"] for r in rs if r["real_reached"] is not None]
        out[name] = {"n": len(rs), "regret": float(np.mean([r["regret"] for r in rs])),
                     "correct": float(np.mean([r["correct"] for r in rs])),
                     "nofact_share": float(sum(r["nofact_pages"] for r in rs) / max(1e-9, sum(r["pages"] for r in rs))),
                     "real_reached": float(np.mean(reached)) if reached else None,
                     "minus_base": paired(rows, by[base]) if name != base else None}
    return out


def best_of(tab: dict, names: list[str]) -> str:
    return min(names, key=lambda n: tab[n]["regret"])


def greedy(tab: dict, by: dict[str, dict], run_combo) -> dict:
    """Spec §3's combination: start from the best single strategy whose CI against the baseline lies below zero; add
    each other family at its best value, in order of regret, keeping it only if (with) − (without) has a CI below
    zero. run_combo(name) -> deal -> row runs a combination ("a+b") on the template deals."""
    reps = {f: best_of(tab, ms) for f, ms in FAMILIES.items()}
    good = sorted((n for n in reps.values() if tab[n]["minus_base"]["ci95"][1] < 0), key=lambda n: tab[n]["regret"])
    if not good:
        return {"combo": "baseline", "steps": []}
    combo, rows, steps = good[0], by[good[0]], []
    for n in sorted((n for n in reps.values() if n != good[0]), key=lambda n: tab[n]["regret"]):
        trial = f"{combo}+{n}"
        new = run_combo(trial)
        c = paired(new, rows)
        keep = c["ci95"][1] < 0
        steps.append({"tried": trial, "with_minus_without": c, "kept": keep})
        if keep:
            combo, rows = trial, new
    return {"combo": combo, "steps": steps}


def deals_needed(gap: float, sd: float = SD, power: float = 0.8, alpha: float = 0.05) -> int:
    """Paired deals for a two-sided test at level alpha to detect a mean difference `gap` with this power."""
    z = NormalDist().inv_cdf
    return math.ceil(((z(1 - alpha / 2) + z(power)) * sd / gap) ** 2)


def sizing(sim_gain: float) -> dict:
    """Spec §3: a real test of the winner against S1b, at the full and at half the simulated gain (gain < 0 is
    better)."""
    out = {}
    for label, g in (("full", sim_gain), ("half", sim_gain / 2)):
        gap = H1_GAP + min(0.0, g)
        out[label] = {"gap": gap, "power_80": deals_needed(abs(gap), power=0.8),
                      "power_90": deals_needed(abs(gap), power=0.9)}
    return out


# --- commands ----------------------------------------------------------------------------------------------------

def combine(data: Path, runs: Path = RUNS) -> dict:
    by = {n: load(runs, data, n) for n in SINGLES}
    tab = table(by)

    def run_combo(name: str) -> dict:
        run(data, [name], "model", runs)
        return load(runs, data, name)

    result = greedy(tab, by, run_combo)
    (runs / data.name / "combination.json").write_text(json.dumps(result, indent=2))
    return result


def report(runs: Path = RUNS, sim_data: Path = Path("data/sim-r2")) -> dict:
    out: dict = {"seed": json.loads((sim_data / "seed.json").read_text())}
    faith = {}
    for label, sets, real in (("practice", PRACTICE, "s4"), ("test", (TEST,), "s4"),
                              ("test_nochal", (TEST,), "s4_nochal")):
        srows, rrows, sdocs, rdocs = {}, {}, {}, {}
        for data in sets:
            s = load(runs, data, "baseline")
            for d, row in s.items():
                rp = data / "runs" / real / f"{d}.json"
                if not rp.exists():
                    continue
                key = f"{data.name}/{d}"
                srows[key], rrows[key] = row, json.loads(rp.read_text())
                sdocs[key], rdocs[key] = row["opened"], opened(rp.with_suffix(".trace.jsonl"))
        faith[label] = faithfulness(srows, rrows, sdocs, rdocs)
    out["faithfulness"] = faith
    out["passes"] = all(f["passes"] for f in faith.values())
    by = {n: load(runs, sim_data, n) for n in SINGLES}
    if not all(by.values()):  # spec §2: the strategies are compared only after the faithfulness check
        return out
    out["strategies"] = table(by)
    comb = runs / sim_data.name / "combination.json"
    if comb.exists():
        c = json.loads(comb.read_text())
        out["combination"] = c
        out["combination_minus_base"] = paired(load(runs, sim_data, c["combo"]), by["baseline"])
        conf = {n: {f"{p.name}/{d}": r for p in PRACTICE for d, r in load(runs, p, n).items()}
                for n in ("baseline", c["combo"])}
        if conf[c["combo"]]:
            m = paired(conf[c["combo"]], conf["baseline"])
            out["confirmation"] = {"minus_base": m, "passes": m["diff"] <= 0}
        out["sizing"] = sizing(out["combination_minus_base"]["diff"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deals")
    d.add_argument("--out", type=Path, default=Path("data/sim-r2"))
    d.add_argument("--n", type=int, default=300)
    d.add_argument("--base", type=int, required=True)
    r = sub.add_parser("run")
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--strategies", default="baseline")
    r.add_argument("--opening", choices=("logged", "model"), required=True)
    r.add_argument("--jobs", type=int)
    c = sub.add_parser("combine")
    c.add_argument("--data", type=Path, default=Path("data/sim-r2"))
    p = sub.add_parser("report")
    p.add_argument("--json", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "deals":
        bad = make_deals(args.out, args.n, args.base, [*PRACTICE, TEST])
        if bad:
            print(f"Refusing: base {args.base} clashes with used seeds {bad[:10]}")
            return 1
        return 0
    if args.cmd == "run":
        print(f"{run(args.data, args.strategies.split(','), args.opening, jobs=args.jobs)} runs made")
        return 0
    if args.cmd == "combine":
        print(json.dumps(combine(args.data), indent=2))
        return 0
    result = report()
    args.json.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("passes", "faithfulness")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/bench/test_simrun.py tests/bench/test_testset.py -q`
Expected: all pass (12 in `test_simrun.py`; `test_testset.py` unchanged and green).

- [ ] **Step 6: Run the full suite and the freeze check**

Run: `uv run pytest -q` — expected: 368 passed.
Run: `git diff --quiet s4-frozen-plan5 -- acqlab/agents acqlab/routers && echo frozen` — expected: `frozen`.

- [ ] **Step 7: Commit**

```bash
git add acqlab/bench/simrun.py acqlab/bench/testset.py tests/bench/test_simrun.py
git commit -m "feat(bench): the simulator runner: template deals, pooled runs, combination, report (reading simulator, Task 2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The simulator run and its results (controller; offline, no Claude)

This task runs the simulator. It costs nothing but CPU time (about 3 hours in all on 8 cores) and makes no Claude or
Codex call. The controller runs it, not an implementer subagent, because it contains the faithfulness gate.

**Files:**
- Create: `docs/results/reading-simulator.json` (written by `simrun report`)
- Create: `docs/results/reading-simulator.md`
- Modify: `docs/HANDOFF.md` ("Resume here")

- [ ] **Step 1: Make the template deals (seed check first)**

Run: `uv run python -m acqlab.bench.simrun deals --n 300 --base 7000000`
Expected: exit 0, `data/sim-r2/truth/` holds 300 answer keys and `data/sim-r2/seed.json` is
`{"base": 7000000, "n": 300, "split": "dev"}`. If it prints `Refusing: base 7000000 clashes ...`, rerun with
`--base 8000000` and record the base used.

- [ ] **Step 2: Simulate the baseline on every deal with a real S4 run (logged openings)**

```bash
uv run python -m acqlab.bench.simrun run --data data/cal-r2 --strategies baseline --opening logged
uv run python -m acqlab.bench.simrun run --data data/heldout-r2 --strategies baseline --opening logged
uv run python -m acqlab.bench.simrun run --data data/test-r2 --strategies baseline --opening logged
```

Expected: 30, 30 and 160 runs made (about 15 minutes in all).

- [ ] **Step 3: The faithfulness gate**

Run: `uv run python -m acqlab.bench.simrun report --json docs/results/reading-simulator.json`
Expected: the printed JSON has `"passes": true`, with each of `practice`, `test` and `test_nochal` passing (spec §2's
bars). If `passes` is false: stop comparing strategies. Report the divergences (`agree`, `sim_minus_real`,
`first_divergence_median`) to the user with one proposed fix, apply it only with the user's OK, delete
`data/sim-r2/runs/*/baseline`, rerun Steps 2–3 once. A second failure stops the plan for the user's decision.

- [ ] **Step 4: Run the seven strategies and the baseline on the template deals (modelled Lead)**

Run: `uv run python -m acqlab.bench.simrun run --data data/sim-r2 --strategies baseline,regret,pages_0.5,pages_0,base_rate,cut_0.25,cut_0.5,no_sweep --opening model`
Expected: 2400 runs made (about 2 hours; resumable: rerun the same command if interrupted).

- [ ] **Step 5: Build the combination**

Run: `uv run python -m acqlab.bench.simrun combine`
Expected: prints `{"combo": ..., "steps": [...]}` and writes `data/sim-r2/runs/sim-r2/combination.json`. Each step runs
one combination on the 300 template deals (about 15 minutes each, at most 4 steps).
If any step's CI straddles zero (spec §3: a comparison too close to call on 300 deals), finish this task on the 300
deals, and say so in Step 8's page: extending toward 1,000 deals is then a follow-up for the user to decide.

- [ ] **Step 6: Confirm on the practice deals (logged openings)**

If the combo is not `baseline`, with COMBO the printed combo name:

```bash
uv run python -m acqlab.bench.simrun run --data data/cal-r2 --strategies COMBO --opening logged
uv run python -m acqlab.bench.simrun run --data data/heldout-r2 --strategies COMBO --opening logged
```

Expected: 30 and 30 runs made.

- [ ] **Step 7: Write the report**

Run: `uv run python -m acqlab.bench.simrun report --json docs/results/reading-simulator.json`
Expected: the JSON now holds `faithfulness`, `passes`, `strategies`, `combination`, `combination_minus_base`,
`confirmation` (if the combo is not the baseline) and `sizing`.

- [ ] **Step 8: Write `docs/results/reading-simulator.md`**

A plain-language page from the JSON, labelled exploratory at the top, in the style of
`docs/results/plan-6-posthoc.md`, with these sections and every number taken from the JSON:
1. What the simulator is and what it assumes (perfect reading; logged or modelled opening plans; no Challenger).
2. Faithfulness: the three checks' agreement, regret sim vs real with CI, pages, Jaccard; pass or fail.
3. Strategies on the 300 template deals: a table with regret, % correct, share of pages on documents with no facts,
   share of real facts reached, and the paired difference from the baseline with its CI.
4. The combination: each step tried, kept or not, and the final combo against the baseline.
5. Confirmation on the 60 practice deals.
6. Sizing: deals for 80% and 90% power at the full and half simulated gain.
7. Recommendation: the design for a real test, or "nothing beats today's team". State that any real run is a separate
   plan needing the user's OK.

- [ ] **Step 9: Update the handoff and commit**

In `docs/HANDOFF.md` "Resume here": the reading simulator is done; one line on the result (pass/fail, the winning
combo or "none", the deal count); next step is the user's decision on a real test (or Plan 7).

```bash
git add docs/results/reading-simulator.json docs/results/reading-simulator.md docs/HANDOFF.md
git commit -m "docs: the reading simulator's results, faithfulness and strategies (reading simulator, Task 3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

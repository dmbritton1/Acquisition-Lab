# Plan 5 D2: The Document Router — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** S4's router picks **documents**, not issues: each pick is the unread document whose reading is expected to move the engine's walk-away most per page, and one Investigator reads exactly that document.

**Architecture:** `record.settle_weights` turns the diligence map's order into the chance each document settles each open issue. `routers.score_docs` scores a document by router 3's sensitivity over the record's 400 simulated deals, grouped by what the document would reveal. `Panel.route`/`read_doc`/`recheck` replace the issue-by-issue router loop when `Config.router` is on; the non-router build steps are untouched. A `route` trace row records each pick, and `acqlab/bench/audit.py` reads traces to show where pages went.

**Tech Stack:** Python 3.12, numpy, pytest, uv. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-25-doc-router-design.md` (approved 2026-09-25, §2 revised to sensitivity after pre-verification, §8).

**Branch:** `claude/plan-4b-freeze-preregistration-0908fa` (worktree `.claude/worktrees/plan-4b-freeze-preregistration-0908fa`), at `bdb4937` = `plan-5` + D1 + the spec. 277 tests pass there.

**Pre-verified.** Every code block below was run in a scratch copy (`<scratchpad>/d2`, from this branch). Task 1 alone: 280 passed. All three tasks: 285 passed. The offline checks in Task 4 were run on the scratch build; their expected outputs are quoted there.

## Global Constraints

- Ponytail: minimal code, stdlib/numpy only, no speculative abstractions. Match the surrounding comment density and idiom.
- **No answer-key information in S4 code** (`acqlab/agents/*`, `acqlab/routers/*`). The audit tool (`acqlab/bench/audit.py`) is bench code and may read answer keys.
- **S1b is byte-for-byte unchanged:** do not edit `acqlab/agents/prompts.py`, `acqlab/agents/knowledge.py` or `acqlab/agents/solver.py`.
- `MAP_WEIGHTS = (0.45, 0.25, 0.15)`; the router uses `N_WORLDS = 400` (no separate router sample size).
- Line length at most 120.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never make a real Claude or Codex call without the user's OK in this session. Never modify settings or permissions files. If a git operation is blocked, stop and report.

## Review Focus

1. **An Investigator session that times out or never reports** — the document must not be picked again in a loop. `Panel.tried` holds every briefed document; Task 2's timeout test (`test_a_timed_out_turn_is_skipped_and_a_usage_limit_stops_the_run`, unchanged) runs the router config and must still end.
2. **A Lead or Challenger naming a document that isn't in the room** — `settle_weights` ignores it (`w.get(d) == 0.0` is False for a missing id). Task 1's test names `"nowhere"`.
3. **Every document read, or a room missing a map kind** (no `assets`) — `settle_weights` returns `{}` or gives the missing kind's share to the leftover; no division by zero. Task 1's test covers the all-read case.
4. **A pair objection (no named documents)** — it must clear once any document that may settle its issue is read, and never trigger the free re-check. The filter in `read_doc` and the `all(o["docs"] ...)` guard in `recheck` implement it; review both against spec §3.
5. **S4's `route` rows in the pilot's scoring** — they must not count as tool calls or pages. Task 2 adds `test_s4_s_route_rows_are_not_tool_calls`.

## File map

| File | Task | Change |
|---|---|---|
| `acqlab/agents/record.py` | 1, 2 | `MAP_WEIGHTS`, `settle_weights`; `Record.worlds(seed)`, `targets`, `named`, `weights`, `rank_docs` (1); remove `Record.rank` (2) |
| `acqlab/routers/routers.py` | 1 | `DOC_BINS`, `score_docs` |
| `acqlab/agents/panel_prompts.py` | 2 | `_about` (split out of `brief`), `doc_brief` |
| `acqlab/agents/panel.py` | 2 | `tried`, `pick` (non-router only), `note`, `route`, `read_doc`, `recheck`, `directed` |
| `acqlab/bench/pilot.py` | 2 | route rows are not tool calls |
| `acqlab/bench/audit.py` (new) | 3 | page-spend audit |
| tests: `tests/agents/test_record.py`, `tests/routers/test_routers.py` (1); `tests/agents/test_record.py`, `tests/agents/test_panel.py`, `tests/bench/test_pilot.py` (2); `tests/bench/test_audit.py` (3) | | |
| docs (Task 4) | 4 | `plan-5-prompt-log.md` (new), Plan 5 plan D2, `plan-5-dev-checks.md`, `HANDOFF.md` |

---

### Task 1: Settle weights and the document scorer

**Files:**
- Modify: `acqlab/agents/record.py`
- Modify: `acqlab/routers/routers.py`
- Test: `tests/agents/test_record.py`, `tests/routers/test_routers.py`

**Interfaces:**
- Produces:
  - `record.MAP_WEIGHTS: tuple[float, float, float]`
  - `record.settle_weights(trap: str, pages: dict[str, float], read: set[str], named: list[str]) -> dict[str, float]` — unread document → chance, summing to 1 (or `{}`).
  - `Record.worlds(seed: int = 0) -> tuple[np.ndarray, np.ndarray]`
  - `Record.targets() -> list[str]`, `Record.named(t: str) -> list[str]`
  - `Record.weights(pages, read) -> dict[str, dict[str, float]]` — document → {issue → chance}
  - `Record.rank_docs(pages, read, docs, seed=0) -> dict[str, float]` — document → score ($M of mean walk-away move per page)
  - `routers.DOC_BINS = 2`, `routers.score_docs(values, w, weights, pages, open_, u) -> dict[str, float]`
- `Record.rank` stays in this task (Task 2 removes it with its last caller).

- [ ] **Step 1: Write the failing tests**

In `tests/agents/test_record.py`, change the imports at the top from:

```python
import pytest

import acqlab.agents.record as record_mod
from acqlab.agents.knowledge import typical_high
from acqlab.agents.record import Record, load_face, next_doc
```

to:

```python
import json

import pytest

import acqlab.agents.record as record_mod
from acqlab.agents.knowledge import typical_high
from acqlab.agents.record import Record, load_face, next_doc, settle_weights
```

and add these two tests directly above `def test_next_doc_walks_the_diligence_map():`:

```python
def test_settle_weights_follow_the_map_split_a_kind_and_move_after_a_miss():
    pages = {"qoe": 8, "audited": 14, "cim": 11, "legal": 2, "board_minutes": 2, "contract_1": 3, "contract_2": 2}
    w = settle_weights("addback", pages, set(), [])
    assert (w["qoe"], w["audited"], w["cim"]) == pytest.approx((0.45, 0.25, 0.15))
    assert w["legal"] == w["board_minutes"] == pytest.approx(0.15 / 4)  # the rest: every other document
    assert sum(w.values()) == pytest.approx(1.0)
    named = settle_weights("addback", pages, set(), ["board_minutes", "qoe", "nowhere"])
    assert named["board_minutes"] == pytest.approx(0.15) and "legal" not in named  # a named off-map document takes it
    c = settle_weights("concentration", pages, set(), [])
    assert c["contract_1"] == c["contract_2"] == pytest.approx(0.45 / 2)  # one kind's share, split among its documents
    miss = settle_weights("addback", pages, {"qoe"}, [])  # read without settling it: the evidence is elsewhere
    assert "qoe" not in miss and miss["audited"] == pytest.approx(0.25 / 0.55)
    assert sum(miss.values()) == pytest.approx(1.0)
    assert settle_weights("nwc", {"qoe": 8, "audited": 14}, {"qoe", "audited"}, []) == {}


def test_the_document_router_prices_what_each_document_may_settle_per_page(data):
    r = _record(data)
    index = json.loads((data / "deals" / "dev-000" / "room" / "index.json").read_text())
    pages = {d["id"]: d["pages"] for d in index["documents"]}
    r.plan([_issue("debt_like", 0.6, 0, 1.0, docs=["board_minutes"]), _issue("capex", 0.0, 0, 0.1)])
    r.challenge([{"type": "nwc", "kind": "elsewhere", "chance": 0.5, "low": 0, "high": 5, "docs": ["credit"],
                  "reason": "r"}])
    assert r.targets() == ["debt_like", "nwc"]  # capex has no chance; nwc has a pending objection
    assert r.named("debt_like") == ["board_minutes"] and r.named("nwc") == ["credit"]
    w = r.weights(pages, {"legal"})
    assert "legal" not in w and set(w["audited"]) == {"debt_like", "nwc"}
    assert w["board_minutes"] == pytest.approx({"debt_like": 0.15 / 0.75})
    scores = r.rank_docs(pages, {"legal"}, ["audited", "travel"])
    assert scores["audited"] > 0 == scores["travel"]  # travel may settle nothing open
    assert scores == r.rank_docs(pages, {"legal"}, ["audited", "travel"])
```

In `tests/routers/test_routers.py`, change the import from:

```python
from acqlab.routers.routers import (ROUTERS, checklist, decide, random_order, score_flip, score_regret,
                                    score_sensitivity)
```

to:

```python
from acqlab.routers.routers import (ROUTERS, checklist, decide, random_order, score_docs, score_flip,
                                    score_regret, score_sensitivity)
```

and add this test directly above `def test_ordering_rules():`:

```python
def test_the_document_router_scores_how_far_a_read_moves_the_walk_away_per_page():
    """D2 §2: router 3's sensitivity per document. Two issues, each 0, 3 or 9 in equal thirds; walk-away 110 less both.
    Learning one moves the mean walk-away (102) by (4 + 1 + 5) / 3; learning both, by the mean of |a + b - 8| = 40 / 9.
    """
    grid = np.array([(a, b) for a in (0.0, 3.0, 9.0) for b in (0.0, 3.0, 9.0)] * 100)
    values = np.zeros((len(grid), len(TRAPS)))
    values[:, TRAPS.index("addback")], values[:, TRAPS.index("nwc")] = grid[:, 0], grid[:, 1]
    w = 110.0 - grid.sum(axis=1)
    u = np.random.default_rng(1).random(values.shape)
    both = {"addback": 1.0, "nwc": 1.0}
    weights = {"both": both, "both_long": both, "one": {"addback": 1.0}, "none": {}}
    pages = {"both": 2.0, "both_long": 4.0, "one": 1.0, "none": 1.0}
    s = score_docs(values, w, weights, pages, ["addback", "nwc"], u)
    assert s["one"] == pytest.approx(10 / 3) and s["both"] == pytest.approx(40 / 9 / 2) and s["none"] == 0
    assert s["both_long"] == pytest.approx(s["both"] / 2)  # twice the pages, half the score
    assert s == score_docs(values, w, weights, pages, ["addback", "nwc"], u)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/agents/test_record.py tests/routers/test_routers.py`
Expected: collection errors: `ImportError: cannot import name 'settle_weights'` and `cannot import name 'score_docs'`.

- [ ] **Step 3: Add `score_docs` to `acqlab/routers/routers.py`**

After the line `PAIR_BINS = 4  # size groups per issue when two issues are grouped jointly`, add:

```python
DOC_BINS = 2  # settled sizes per issue for the document router: below or above the median (0 is its own label)
```

Directly above `def score_flip(`, add:

```python
def score_docs(values, w, weights, pages, open_, u) -> dict[str, float]:
    """Document router (D2 §2): router 3's sensitivity per document, per page. In each world a document settles open
    issue t where u < its weight for t; worlds are grouped by what the reader would learn (each issue settled at 0,
    small, large, or not here), and the score is the expected absolute move of the mean walk-away from learning the
    group. One table u for every document, so noise can't reorder them."""
    labels = {t: _labels(values[:, TRAPS.index(t)], DOC_BINS) for t in open_}
    m, out = w.mean(), {}
    for d, wd in weights.items():
        key = np.zeros(len(w), dtype=np.int64)
        for t in open_:
            seen = u[:, TRAPS.index(t)] < wd.get(t, 0.0)
            key = key * (DOC_BINS + 2) + np.where(seen, labels[t], DOC_BINS + 1)
        groups = [np.flatnonzero(key == k) for k in np.unique(key)]
        out[d] = float(sum(len(g) * abs(w[g].mean() - m) for g in groups) / len(w)) / pages[d]
    return out


```

- [ ] **Step 4: Add the weights and `Record` methods to `acqlab/agents/record.py`**

Change the import line:

```python
from acqlab.routers.routers import decide, score_regret
```

to:

```python
from acqlab.routers.routers import decide, score_docs, score_regret
```

After the line `N_WORLDS = 400`, add:

```python
MAP_WEIGHTS = (0.45, 0.25, 0.15)  # the chance a map document is where an issue is settled, by place on the map.
# ponytail: hand-set from the map's order (the order S1b's guide states in words), not measured; tune here if the
# order dominates the router
```

Directly above `def next_doc(`, add:

```python
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


```

Replace `Record.worlds`:

```python
    def worlds(self) -> tuple[np.ndarray, np.ndarray]:
        values = draw({t: self.issue(t) for t in TRAPS}, N_WORLDS, np.random.default_rng(0))
```

with:

```python
    def worlds(self, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
        values = draw({t: self.issue(t) for t in TRAPS}, N_WORLDS, np.random.default_rng(seed))
```

Directly above `    def view(self, reasons: bool = True) -> str:` (after `rank`), add:

```python
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
        values, w = self.worlds(seed)
        u = np.random.default_rng(seed + 1).random(values.shape)
        wts = self.weights(pages, read)
        return score_docs(values, w, {d: wts.get(d, {}) for d in docs}, pages, self.targets(), u)

```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/agents/test_record.py tests/routers/test_routers.py`
Expected: all pass.

Run: `uv run pytest -q`
Expected: `280 passed`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/agents/record.py acqlab/routers/routers.py tests/agents/test_record.py tests/routers/test_routers.py
git commit -m "feat(agents,routers): settle weights and the document scorer (Plan 5, D2 Task 1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The document reading loop

**Files:**
- Modify: `acqlab/agents/panel_prompts.py`, `acqlab/agents/panel.py`, `acqlab/agents/record.py`, `acqlab/bench/pilot.py`
- Test: `tests/agents/test_panel.py`, `tests/agents/test_record.py`, `tests/bench/test_pilot.py`

**Interfaces:**
- Consumes (Task 1): `Record.weights(pages, read)`, `Record.rank_docs(pages, read, docs, seed=0)`, `Record.named(t)`.
- Produces:
  - `panel_prompts.doc_brief(teaser, docs, record, doc, issues, read, pages) -> str`; its text starts `Brief: read <doc> (<pages> pages). It may settle these open issues:` and ends `Report every issue type this document settles, including ones not listed.`
  - `Panel.route() -> str | None`, `Panel.read_doc(d)`, `Panel.recheck()`, `Panel.note(tool, args, **extra)`, `Panel.tried: set[str]`
  - Trace row `{"i": 0, "tool": "route", "args": {"doc": str, "issues": [str], "scores": {doc: float} (top 5)}, "cost": 0.0, "remaining": float, "refused": false, "error": null}`
- Removes `Record.rank` (its last caller, the router branch of `Panel.pick`, goes here).

- [ ] **Step 1: Write the failing tests**

In `tests/agents/test_panel.py`, replace `finds_nothing`:

```python
def finds_nothing(s, prompt):
    """An Investigator that reads the first suggested document it can afford and settles nothing."""
    looked = re.search(r"Look first at: ([^.]*)\.", prompt)
```

with:

```python
def finds_nothing(s, prompt):
    """An Investigator that reads the first suggested document it can afford (a document brief's one document) and
    settles nothing."""
    looked = re.search(r"Look first at: ([^.]*)\.", prompt) or re.search(r"Brief: read (\S+) \(", prompt)
```

(the rest of the function is unchanged).

Replace the whole test `test_the_router_ranks_by_regret_per_page_and_falls_back_to_the_lead_s_order_when_nothing_scores` (from its `def` line down to the line before `def test_the_brief_carries_the_flip_amount_where_to_look_and_a_sub_budget`) with:

```python
def _routes(trace) -> list[dict]:
    return [r["args"] for r in _rows(trace) if r["tool"] == "route"]


def test_the_router_reads_the_document_that_moves_the_walk_away_most_per_page_one_investigator_each(data, tmp_path):
    plan = [_issue("nwc", 0.3), _issue("debt_like", 0.6)]
    s = scripted(lead=lead_says((plan, True)), investigator=finds_nothing)
    p = Panel(_room(data), 40, tmp_path / "a.jsonl", Config(challenger=False, sweep=False), s)
    p.record.plan(plan)
    cands = list(p.record.weights(p.pages, set()))
    scores = p.record.rank_docs(p.pages, set(), cands)
    first = min(cands, key=lambda d: (-scores[d], p.pages[d], d))
    p.run()
    routes = _routes(tmp_path / "a.jsonl")
    assert routes[0]["doc"] == first and len(routes) >= 2  # the Lead's stop is ignored
    role, prompt, budget = s.turns[1]
    assert role == "investigator" and f"Brief: read {first} ({p.pages[first]:g} pages)." in prompt
    assert budget == p.pages[first] and "including ones not listed" in prompt
    assert all(f"- {t} ({t}): Current belief" in prompt for t in routes[0]["issues"])
    assert [r for r, _, _ in s.turns].count("lead") == 1  # nothing was committed, so no re-plan
    assert p.spent() == sum(p.pages[d] for d in p.read())  # route and submit rows are free, and not reads


def test_when_no_document_can_move_the_walk_away_directed_reading_ends(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: dict.fromkeys(docs, 0.0))
    s = scripted(lead=lead_says(([_issue("nwc", 0.3)], False)), investigator=finds_nothing)
    Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s).run()
    assert [r for r, _, _ in s.turns] == ["lead"] and _routes(tmp_path / "t.jsonl") == []


def test_the_lead_re_plans_only_after_a_read_commits_something(data, tmp_path, monkeypatch):
    plan = [_issue("nwc", 0.5)]
    s = scripted(lead=lead_says((plan, False)), investigator=finds_nothing)
    Panel(_room(data), 30, tmp_path / "a.jsonl", Config(challenger=False, sweep=False), s).run()
    roles = [r for r, _, _ in s.turns]
    assert roles[0] == "lead" and roles.count("lead") == 1 and roles.count("investigator") >= 2
    monkeypatch.setattr(panel.Record, "apply", lambda self, commits: True)  # every read commits something
    s2 = scripted(lead=lead_says((plan, False)), investigator=finds_nothing)
    Panel(_room(data), 30, tmp_path / "b.jsonl", Config(challenger=False, sweep=False), s2).run()
    roles = [r for r, _, _ in s2.turns]
    assert roles == ["lead"] + ["investigator", "lead"] * roles.count("investigator")


def test_the_router_may_spend_the_sweep_s_reserve_on_the_document_it_ranks_first(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs",
                        lambda self, pages, read, docs, seed=0: {d: float(d == "audited") for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing)
    p = Panel(_room(data), 14, tmp_path / "t.jsonl", Config(challenger=False), s)
    assert p.avail() < p.pages["audited"] == p.budget
    p.run()
    role, prompt, budget = s.turns[1]
    assert role == "investigator" and budget == 14 and "Brief: read audited (14 pages)." in prompt


def test_with_the_router_an_objection_is_read_where_it_points_and_then_clears(data, tmp_path, monkeypatch):
    """Only credit, and only while debt_like's objection points there, moves the walk-away (a stand-in score)."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: float(d == "credit" and bool(self.entries["debt_like"].objections)) for d in docs})
    rounds = [{"objections": [{"type": "debt_like", "kind": "elsewhere", "chance": 0.9, "low": 0, "high": 90,
                               "docs": ["credit"], "reason": "the credit agreement lists a guarantee"}]},
              {"objections": []}]

    def challenger(sess, prompt):
        sess.call("challenge", rounds.pop(0) | {"pairs": [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                          for a, b in sess.pairs]})

    s = scripted(lead=lead_says(([_issue("debt_like", 0.2)], False)), investigator=finds_nothing,
                 challenger=challenger)
    Panel(_room(data), 60, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    # cleared by the read: no free re-check ("Find out") follows, and the second round has nothing to object to
    assert [r for r, _, _ in s.turns] == ["lead", "challenger", "investigator", "challenger"]
    assert [r["doc"] for r in _routes(tmp_path / "t.jsonl")] == ["credit"]
    prompt = s.turns[2][1]
    assert "Brief: read credit" in prompt and "The Challenger objects (elsewhere): the credit agreement" in prompt


def test_an_objection_on_documents_already_read_gets_one_free_look(data, tmp_path, monkeypatch):
    s = scripted(investigator=finds_nothing)
    p = Panel(_room(data), 0, tmp_path / "t.jsonl", STAGES["s4"], s)
    p.record.challenge([{"type": "debt_like", "kind": "elsewhere", "chance": 0.5, "low": 0, "high": 9,
                         "docs": ["legal"], "reason": "the letter lists a claim"}])
    monkeypatch.setattr(p, "read", lambda: {"legal"})
    p.directed()
    role, prompt, budget = s.turns[0]
    assert role == "investigator" and budget == 0 and "Find out: debt_like." in prompt
    assert "The Challenger objects (elsewhere): the letter lists a claim" in prompt
    assert "Look first at: legal." in prompt
    assert p.record.entries["debt_like"].objections == [] and len(s.turns) == 1


```

Delete the whole test `test_with_the_router_an_objected_issue_the_lead_leaves_out_still_gets_its_extra_look` (from its `def` line down to the line before `def test_the_sweep_reads_map_documents_in_untouched_domains_first_with_what_is_left`). R1 (an objected issue the Lead leaves out is still priced) stays covered in `tests/agents/test_record.py` below.

In `tests/agents/test_record.py`, in `test_a_pending_objection_outlasts_a_re_plan_until_it_is_investigated`, replace:

```python
    assert r.issue("nwc") == (0.7, 40, None, True) and r.rank(["nwc"], {"nwc": 5.0})["nwc"] > 0  # R1: not dropped
```

with:

```python
    assert r.issue("nwc") == (0.7, 40, None, True) and "nwc" in r.targets()  # R1: not dropped
```

and delete the whole test `test_the_router_ranks_open_issues_per_page` (5 lines plus its trailing blank lines).

In `tests/bench/test_pilot.py`, append:

```python


def test_s4_s_route_rows_are_not_tool_calls(data):
    key = _key(data)
    t = key.truth
    trace = [_row("initialize", {}), _row("route", {"doc": "qoe", "issues": [], "scores": {}}),
             _row("open_document", {"doc_id": "qoe"}, 8.0),
             _row("submit", {"go": t.face_go, "walk_away": t.face_walk_away, "reason": "engine"})]
    r = score(key, "s4", trace, None, "ok")
    assert r["tool_calls"] == 2 and r["pages"] == 8.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/agents/test_panel.py tests/bench/test_pilot.py -k "router or objection or re_plans or route_rows or directed_reading"`
Expected: FAIL. The router still briefs issues and writes no `route` rows, so the new router tests fail with
`IndexError` (no `routes[0]`, or no turns) or `AssertionError` on the turn roles; the free re-check test fails with
`IndexError` (no turn); and `test_s4_s_route_rows_are_not_tool_calls` fails with `assert 3 == 2`.

- [ ] **Step 3: Add the document brief to `acqlab/agents/panel_prompts.py`**

Replace the whole `brief` function:

```python
def brief(teaser: str, docs: list[dict], record: Record, trap: str, where: list[str], read: set[str],
          budget: float) -> str:
    """The intent brief (main spec §3): the issue, the current range, the engine's flip amount, where to look, and a
    sub-budget."""
    e = record.entries[trap]
    flip = record.flip_amount(trap)
    lines = [f"Find out: {trap}" + (f" ({e.name})" if e.name else "") + ".",
             f"Current belief: chance {e.chance:.2f}, size ${e.low:,.1f}–${e.high:,.1f}M." if e.known is None else
             f"Committed so far: ${e.known[0]:,.1f}–${e.known[1]:,.1f}M ({e.kind}).",
             f"The engine's call flips if this issue is at least ${flip:,.1f}M, with everything else as recorded."
             if flip is not None else
             f"No size up to ${2 * record.size_limit(trap):,.1f}M flips the call alone; it can still matter with "
             "other issues, so report what the documents say."]
    lines += [f"The Challenger objects ({o['kind']}): {o['reason']}" for o in e.objections]
    if e.searched:
        lines.append(f"Already read without settling it: {', '.join(e.searched)}.")
    lines.append(f"Look first at: {', '.join(where)}." if where else "Choose where to look.")
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\nBrief:\n" + "\n".join(lines)
            + f"\n\nYour reading budget: {budget:g} units. Report a finding for {trap}; add any other issue type "
            "the documents you read settle.")
```

with:

```python
def _about(record: Record, t: str) -> list[str]:
    """What a brief says about issue t: the current belief or committed value, the engine's flip amount, any
    objection, and where it was read without being settled."""
    e = record.entries[t]
    flip = record.flip_amount(t)
    lines = [f"Current belief: chance {e.chance:.2f}, size ${e.low:,.1f}–${e.high:,.1f}M." if e.known is None else
             f"Committed so far: ${e.known[0]:,.1f}–${e.known[1]:,.1f}M ({e.kind}).",
             f"The engine's call flips if this issue is at least ${flip:,.1f}M, with everything else as recorded."
             if flip is not None else
             f"No size up to ${2 * record.size_limit(t):,.1f}M flips the call alone; it can still matter with "
             "other issues, so report what the documents say."]
    lines += [f"The Challenger objects ({o['kind']}): {o['reason']}" for o in e.objections]
    if e.searched:
        lines.append(f"Already read without settling it: {', '.join(e.searched)}.")
    return lines


def brief(teaser: str, docs: list[dict], record: Record, trap: str, where: list[str], read: set[str],
          budget: float) -> str:
    """The intent brief (main spec §3): the issue, the current range, the engine's flip amount, where to look, and a
    sub-budget."""
    e = record.entries[trap]
    lines = [f"Find out: {trap}" + (f" ({e.name})" if e.name else "") + "."] + _about(record, trap)
    lines.append(f"Look first at: {', '.join(where)}." if where else "Choose where to look.")
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\nBrief:\n" + "\n".join(lines)
            + f"\n\nYour reading budget: {budget:g} units. Report a finding for {trap}; add any other issue type "
            "the documents you read settle.")


def doc_brief(teaser: str, docs: list[dict], record: Record, doc: str, issues: list[str], read: set[str],
              pages: float) -> str:
    """The document brief (D2 §3): one document, the open issues it may settle, and a budget of its pages."""
    lines = [f"Brief: read {doc} ({pages:g} pages). It may settle these open issues:"]
    for t in issues:
        e = record.entries[t]
        lines.append(f"- {t}" + (f" ({e.name})" if e.name else "") + ": " + " ".join(_about(record, t)))
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\n" + "\n".join(lines)
            + f"\n\nYour reading budget: {pages:g} units. Report every issue type this document settles, "
            "including ones not listed.")
```

- [ ] **Step 4: Replace the router loop in `acqlab/agents/panel.py`**

Replace the module docstring's second paragraph:

```python
The loop: the Deal Lead proposes issues; Investigators check them one at a time with intent briefs, their findings
going through the Committer; the Lead re-plans after each; the Challenger objects and the pair screen flags issues
that flip the call together; objections are investigated; a residual sweep reads what nobody opened. Build steps
(reframe design §5) are configs: STAGES."""
```

with:

```python
The loop: the Deal Lead proposes issues; Investigators check them with intent briefs, their findings going through
the Committer; the Challenger objects and the pair screen flags issues that flip the call together; objections are
investigated; a residual sweep reads what nobody opened. Without the router, Investigators take one issue at a time in
the Lead's order and the Lead re-plans after each. With it (D2), code picks the document whose reading moves the
engine's walk-away most per page, one Investigator reads that one document, and the Lead re-plans after a read that
commits something. Build steps (reframe design §5) are configs: STAGES."""
```

Replace the `router` field comment in `Config`:

```python
    router: bool = True  # True: code picks by decision value per page (the Lead's order when nothing scores) and
    # the Lead's stop is ignored. False: the Lead's order; the first investigation always runs, and the Lead's stop
    # ends later rounds
```

with:

```python
    router: bool = True  # True: code picks documents by how far they may move the walk-away per page, and the
    # Lead's stop is ignored. False: issues in the Lead's order; the first investigation always runs, and the Lead's
    # stop ends later rounds
```

In `Panel.__init__`, after `self.reserve = SWEEP_SHARE * budget if cfg.sweep else 0.0`, add:

```python
        self.tried: set[str] = set()  # documents the router has briefed, read or not
```

Replace the whole `pick` method:

```python
    def pick(self) -> str | None:
        cands = self.candidates()
        if not cands:
            return None
        if self.cfg.router:
            scores = self.record.rank(cands, {t: self.first_cost(t) for t in cands})
            best = max(cands, key=lambda t: (scores[t], -TRAPS.index(t)))
            if scores[best] > 0:
                return best
        # No router, or no single check can flip the call (dev-006: every issue at 35-50% over wide ranges). Unspent
        # budget earns nothing under the regret score, and issues that only matter together score 0 one at a time,
        # so keep reading in the Lead's order.
        order = self.record.priority
        return min(cands, key=lambda t: (order.index(t) if t in order else len(order), TRAPS.index(t)))
```

with:

```python
    def pick(self) -> str | None:
        """Without the router: the next issue in the Lead's order."""
        cands = self.candidates()
        order = self.record.priority
        return min(cands, key=lambda t: (order.index(t) if t in order else len(order), TRAPS.index(t))) \
            if cands else None

    def note(self, tool: str, args: dict, **extra) -> None:
        """A row the panel itself writes to the trace (route, submit): free, never a read."""
        with self.trace.open("a") as f:
            f.write(json.dumps({"i": 0, "tool": tool, "args": args, "cost": 0.0,
                                "remaining": self.budget - self.spent(), "refused": False, "error": None}
                               | extra) + "\n")

    def route(self) -> str | None:
        """D2 §3: the unread document whose reading moves the engine's walk-away most per page, among those that fit
        the budget left (the sweep's reserve included: unspent budget earns nothing). None once no document can move
        it: the sweep takes over."""
        read, left = self.read(), self.budget - self.spent()
        wts, skip = self.record.weights(self.pages, read), read | self.tried
        cands = [d for d in wts if d not in skip and self.pages[d] <= left]
        if not cands:
            return None
        scores = self.record.rank_docs(self.pages, read, cands)
        order = sorted(cands, key=lambda d: (-scores[d], self.pages[d], d))
        if scores[order[0]] <= 0:
            return None
        self.note("route", {"doc": order[0], "issues": sorted(wts[order[0]]),
                            "scores": {d: scores[d] for d in order[:5]}})
        return order[0]

    def read_doc(self, d: str) -> None:
        """One Investigator reads one document (budget: its pages) and reports everything it settles. Objections
        clear when a document they name is read (a pair objection names none: any document that may settle its
        issue), or when their issue is committed. The Lead re-plans only after a commit: a read that settles nothing
        says nothing about whether an issue is real."""
        wts = self.record.weights(self.pages, self.read())[d]
        self.tried.add(d)
        prompt = prompts.doc_brief(self.teaser, self.docs, self.record, d, sorted(wts), self.read(), self.pages[d])
        row = self.turn("investigator", prompt, self.pages[d])
        commits = row["result"]["commits"] if row else []
        changed = self.record.apply(commits)
        settled = {c["type"] for c in commits if c["kind"] in ("quoted", "computed", "range")}
        for t, e in self.record.entries.items():
            e.objections = [o for o in e.objections if t not in settled and d not in o["docs"]
                            and (o["docs"] or t not in wts)]
        if changed:
            self.lead()

    def recheck(self) -> None:
        """An objection whose named documents were all read claims a reader missed something: one free look (budget
        0; read documents are free) with the Challenger's reason."""
        read = self.read()
        for t, e in self.record.entries.items():
            docs = list(dict.fromkeys(d for o in e.objections for d in o["docs"]))
            if e.objections and all(o["docs"] for o in e.objections) and set(docs) <= read:
                row = self.turn("investigator", prompts.brief(self.teaser, self.docs, self.record, t, docs, read, 0),
                                0)
                e.objections = []
                self.record.apply(row["result"]["commits"] if row else [])
```

Replace the whole `directed` method:

```python
    def directed(self) -> None:
        while self.avail() >= 1 and (t := self.pick()) is not None:
            self.investigate(t)
            if self.lead() and not self.cfg.router:
                break
```

with:

```python
    def directed(self) -> None:
        if self.cfg.router:
            while (d := self.route()) is not None:
                self.read_doc(d)
            self.recheck()
            return
        while self.avail() >= 1 and (t := self.pick()) is not None:
            self.investigate(t)
            if self.lead():
                break
```

In `run`, replace:

```python
        with self.trace.open("a") as f:
            f.write(json.dumps({"i": 0, "tool": "submit", "args": {"go": go, "walk_away": wa, "reason": "engine"},
                                "cost": 0.0, "remaining": self.budget - self.spent(), "refused": False,
                                "error": None, "result": {"submitted": True}}) + "\n")
```

with:

```python
        self.note("submit", {"go": go, "walk_away": wa, "reason": "engine"}, result={"submitted": True})
```

- [ ] **Step 5: Remove `Record.rank` from `acqlab/agents/record.py`**

Change the import line:

```python
from acqlab.routers.routers import decide, score_docs, score_regret
```

to:

```python
from acqlab.routers.routers import decide, score_docs
```

and delete the whole method:

```python
    def rank(self, candidates: list[str], costs: dict[str, float]) -> dict[str, float]:
        """Router 6: expected $M of decision regret removed per page, for each candidate issue."""
        values, w = self.worlds()
        return score_regret(values, w, self.face.deal.asking_price, costs, candidates)

```

- [ ] **Step 6: Route rows are not tool calls in `acqlab/bench/pilot.py`**

In `score`, replace:

```python
        "tool_calls": sum(r["tool"] != "initialize" for r in trace),  # the initialize row (F7) is not a tool call
```

with:

```python
        # the initialize row (F7) and S4's route rows (D2) are not tool calls
        "tool_calls": sum(r["tool"] not in ("initialize", "route") for r in trace),
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest -q tests/agents tests/bench`
Expected: all pass.

Run: `uv run pytest -q`
Expected: `284 passed`.

Run: `grep -rn "\.rank(" acqlab tests | grep -v "rank_docs\|rank_issues"`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add acqlab/agents/panel.py acqlab/agents/panel_prompts.py acqlab/agents/record.py acqlab/bench/pilot.py \
        tests/agents/test_panel.py tests/agents/test_record.py tests/bench/test_pilot.py
git commit -m "feat(agents): the router reads documents, one Investigator each (Plan 5, D2 Task 2)

The router picks the unread document whose reading moves the engine's walk-away most per page; its Investigator
has exactly that document's pages. The Lead re-plans only after a commit; objections clear when a document they
name is read, with one free re-check if all were already read; the router may spend the sweep's reserve. D1's
fallback and Record.rank are gone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The page-spend audit tool

**Files:**
- Create: `acqlab/bench/audit.py`
- Test: `tests/bench/test_audit.py`

**Interfaces:**
- Consumes: pilot run files `<data>/runs/<system>/<deal>.json` (fields `deal`, `case_type`, `correct`, `regret`) and traces `<deal>.trace.jsonl`; answer keys `<data>/truth/<deal>.json` (`AnswerKey`).
- Produces: `audit(data: Path, system: str) -> list[dict]` with keys `deal, case_type, correct, regret, pages, evidence_pages, audited, missed`; CLI `uv run python -m acqlab.bench.audit --data <data> --system s4 [--system s1b]`.

- [ ] **Step 1: Write the failing test**

Create `tests/bench/test_audit.py`:

```python
import json

from acqlab.bench.audit import audit, main
from acqlab.generator.batch import AnswerKey


def test_the_audit_counts_pages_on_evidence_and_the_real_facts_never_read(data, tmp_path, capsys):
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    real = {f.trap for f in key.truth.facts if f.amount > 0}
    ev = next(e for e in key.evidence if e.trap in real)
    held = set().union(*(e.docs for e in key.evidence if e.trap in real))
    other = next(d for d in ("it_policy", "hr_policy", "travel", "marketing") if d not in held)
    runs = tmp_path / "runs" / "s4"
    runs.mkdir(parents=True)
    (tmp_path / "truth").mkdir()
    (tmp_path / "truth" / "dev-000.json").write_text(key.model_dump_json())
    (runs / "dev-000.json").write_text(json.dumps({"deal": "dev-000", "case_type": key.truth.case_type,
                                                   "correct": True, "regret": 0.0}))
    rows = [{"tool": "open_document", "args": {"doc_id": ev.docs[0]}, "cost": 5.0, "refused": False},
            {"tool": "open_document", "args": {"doc_id": other}, "cost": 2.0, "refused": False},
            {"tool": "open_document", "args": {"doc_id": "audited"}, "cost": 14.0, "refused": True},
            {"tool": "route", "args": {"doc": other}, "cost": 0.0, "refused": False}]
    (runs / "dev-000.trace.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    [row] = audit(tmp_path, "s4")
    assert row["pages"] == 7.0 and row["evidence_pages"] == 5.0 and not row["audited"]  # a refused open is no read
    docs = {e.trap: set(e.docs) for e in key.evidence}
    assert row["missed"] == sorted(t for t in real if ev.docs[0] not in docs[t]) and ev.trap not in row["missed"]
    assert main(["--data", str(tmp_path), "--system", "s4"]) == 0 and "1 runs" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/bench/test_audit.py`
Expected: `ModuleNotFoundError: No module named 'acqlab.bench.audit'`.

- [ ] **Step 3: Write the tool**

Create `acqlab/bench/audit.py`:

```python
"""Page-spend audit (document router design §5): where each run's pages went, against the answer keys. No Claude
calls: it reads a system's finished runs (pilot) and the answer keys.

  uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4 --system s1b
"""
import argparse
import json
from pathlib import Path

from acqlab.generator.batch import AnswerKey


def audit(data: Path, system: str) -> list[dict]:
    """Per run: pages read, pages on documents holding a real (nonzero) fact's evidence, whether the audited notes
    were read, and the real facts whose evidence was never read."""
    rows = []
    for path in sorted((data / "runs" / system).glob("*.json")):
        run = json.loads(path.read_text())
        key = AnswerKey.model_validate_json((data / "truth" / f"{run['deal']}.json").read_text())
        trace = [json.loads(x) for x in path.with_suffix(".trace.jsonl").read_text().splitlines()]
        reads = [(r["args"]["doc_id"], r["cost"]) for r in trace if r["tool"] == "open_document" and not r["refused"]]
        real = {f.trap for f in key.truth.facts if f.amount > 0}
        where = {e.trap: set(e.docs) for e in key.evidence if e.trap in real}
        read = {d for d, _ in reads}
        rows.append({"deal": run["deal"], "case_type": run["case_type"], "correct": run["correct"],
                     "regret": run["regret"], "pages": sum(c for _, c in reads),
                     "evidence_pages": sum(c for d, c in reads if any(d in docs for docs in where.values())),
                     "audited": "audited" in read, "missed": sorted(t for t, docs in where.items() if not docs & read)})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--system", action="append", required=True)
    args = ap.parse_args(argv)
    for system in args.system:
        rows = audit(args.data, system)
        print(f"== {system}: {len(rows)} runs, audited notes read in {sum(r['audited'] for r in rows)}, "
              f"{sum(bool(r['missed']) for r in rows)} with a real fact never read")
        for r in rows:
            print(f"{r['deal']} {r['case_type']:12} {'✓' if r['correct'] else '✗'} regret {r['regret']:.3f} "
                  f"pages {r['pages']:g} (evidence {r['evidence_pages']:g}) audited {'yes' if r['audited'] else 'no'}"
                  + (f" missed {', '.join(r['missed'])}" if r["missed"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/bench/test_audit.py`
Expected: `1 passed`.

Run: `uv run pytest -q`
Expected: `285 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/audit.py tests/bench/test_audit.py
git commit -m "feat(bench): page-spend audit of finished runs (Plan 5, D2 Task 3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Offline checks and records (controller only; no Claude calls)

**Files:**
- Create: `docs/results/plan-5-prompt-log.md`
- Modify: `docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md`, `docs/results/plan-5-dev-checks.md`, `docs/HANDOFF.md`

- [ ] **Step 1: Bring the calibration data into this worktree**

`data/` is git-ignored and `data/cal-r2` lives only in the `plan-5` worktree. Copy it (read there, write here):

```bash
cp -R /Users/dwightbritton/Developer/acquisition-lab/.claude/worktrees/plan-4b-calibration-round-1-5f0549/data/cal-r2 data/cal-r2
ls data/cal-r2/runs/s4 | wc -l
```

Expected: `20` (10 runs and 10 traces).

- [ ] **Step 2: The audit of the `c989fb1` runs (the before picture)**

Run: `uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4 --system s1b | grep "=="`
Expected:

```
== s4: 10 runs, audited notes read in 0, 5 with a real fact never read
== s1b: 30 runs, audited notes read in 18, 14 with a real fact never read
```

- [ ] **Step 3: What ranks first, and stability (spec §5.1)**

Run:

```bash
uv run python - <<'EOF'
import json
from pathlib import Path
from acqlab.agents.record import Record, load_face
D = Path("data/cal-r2")
for i in range(10):
    deal = f"dev-{i:03d}"
    room = D / "deals" / deal / "room"
    key = json.loads((D / "truth" / f"{deal}.json").read_text())
    pages = {d["id"]: d["pages"] for d in json.loads((room / "index.json").read_text())["documents"]}
    rows = [json.loads(x) for x in (D / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
    r = Record(load_face(room))
    r.plan(next(x["args"]["issues"] for x in rows if x["tool"] == "propose"))
    cands = [d for d in r.weights(pages, set()) if pages[d] <= key["budget"]]
    firsts = []
    for seed in range(5):
        s = r.rank_docs(pages, set(), cands, seed)
        order = sorted(cands, key=lambda d: (-s[d], pages[d], d))
        firsts.append(order[0])
        if seed == 0:
            top, aud = order[:3], order.index("audited") + 1
    print(deal, "top3", top, "audited rank", aud, "first-pick agreement", max(map(firsts.count, firsts)) / 5)
EOF
```

Expected (pre-verification): first-pick agreement 0.8–1.0 on every deal; the audited notes rank 2–7 on every deal; `legal` first on 9 of 10 (`board_minutes` on dev-007).

- [ ] **Step 4: The reading path (spec §5.2)**

Run:

```bash
uv run python - <<'EOF'
import json, tempfile
from pathlib import Path
from acqlab.agents.panel import Config, Panel
D, hits = Path("data/cal-r2"), 0
for i in range(10):
    deal = f"dev-{i:03d}"
    key = json.loads((D / "truth" / f"{deal}.json").read_text())
    real = {f["trap"] for f in key["truth"]["facts"] if f["amount"] > 0}
    ev = {d for e in key["evidence"] if e["trap"] in real for d in e["docs"]}
    rows = [json.loads(x) for x in (D / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
    p = Panel(D / "deals" / deal / "room", key["budget"], Path(tempfile.mkdtemp()) / "t.jsonl", Config(), None)
    p.record.plan(next(x["args"]["issues"] for x in rows if x["tool"] == "propose"))
    read, order = set(), []
    p.read, p.spent = (lambda: set(read)), (lambda: sum(p.pages[d] for d in read))
    while (d := p.route()) is not None:  # nothing found: exact until the first commit
        order.append(d)
        read.add(d)
        if d in ev:
            break
    hits += bool(set(order) & ev)
    print(deal, "evidence", sorted(ev), "path", order)
print("paths reaching evidence:", hits)
EOF
```

Expected (pre-verification): `paths reaching evidence: 6`: dev-000 (qoe), dev-003 (audited, after legal and qoe), dev-004 (board_minutes), dev-007 (audited), dev-008 (audited), dev-009 (board_minutes); dev-002 and dev-005 miss (their audited notes hold only decoys); dev-001 and dev-006 have no real evidence.

If a result differs from the pre-verification numbers, stop and report to the user before any paid run.

- [ ] **Step 5: Records**

Create `docs/results/plan-5-prompt-log.md`:

```markdown
# Plan 5 prompt log: S4's prompts after the first smoke run

Every prompt edit after the first S4 smoke run, with its reason and result (parity rule: the same tuning effort is
offered to S1b). Format of `plan-4a-prompt-log.md`.

## D2 (2026-09-25): the document brief

- **What changed.** With the router on, an Investigator gets a document brief (`panel_prompts.doc_brief`) instead of
  an issue brief: one document, its pages as the reading budget, and for each open issue it may settle the same lines
  the issue brief carries (belief or committed value, the engine's flip amount, any objection). It ends "Report every
  issue type this document settles, including ones not listed." The issue brief's wording is unchanged (its lines
  moved into `_about`).
- **Why.** The page-spend audit of the `c989fb1` runs: S4 never opened the audited notes (0 of 10), and Investigators
  kept reading after finding their answer. Spec: `docs/superpowers/specs/2026-09-25-doc-router-design.md`.
- **Parity.** An S4 architecture change, not added knowledge: the brief states only the record and the engine's
  numbers, and the router's weights use only the diligence map's order that S1b's guide already states. S1b's prompt
  is unchanged.
- **Result.** See `plan-5-dev-checks.md` (the D2 re-run).
```

In `docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md`, after the `- **D1 (10-deal dev check):** ...` line in "Post-review changes (after execution)", add:

```markdown
- **D2 (page-spend audit):** the router picks documents, not issues, by router 3's sensitivity per document per page
  over the diligence map's weights; one Investigator reads one document; the Lead re-plans only after a commit;
  objections clear when a document they name is read. Supersedes Decision 4's issue router and D1's fallback. Spec:
  `docs/superpowers/specs/2026-09-25-doc-router-design.md`; plan: `docs/superpowers/plans/2026-09-25-plan-5-d2-doc-router.md`.
```

In `docs/results/plan-5-dev-checks.md`, append:

```markdown

## The page-spend audit and D2 (2026-09-25)

An offline replay of the 10 `c989fb1` traces (`uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4
--system s1b`): S4 never opened the audited notes (0 of 10; S1b 18 of 30), which held the hidden fact in 5 of the 10
deals. On dev-003 (28% of S1b's regret on the 30 deals) the answer needed contract_1 and the audited notes, 16 of 25
pages; S4 read contract_1 and S1b read the audited notes, and both said GO.

**D2, the document router** (spec `docs/superpowers/specs/2026-09-25-doc-router-design.md`): offline, on the recorded
first Lead plans, the first pick is stable over seeds (80–100%), the audited notes rank 2–7 on every deal, and the
reading path reaches the evidence on 6 of the 8 deals that have any. A regret-based document score was tried first and
dropped (spec §8): at the Lead's first plan no single read changes the call.

**Also found (answer keys, read-only):** "not found" is no evidence against an issue (a clean fact states $0.0M), so the
Lead prompt fix deferred earlier is withdrawn. The map's order is off for `r2` (add-backs sit in the audited notes 43%
of the time, the QoE 30%), and the board minutes, off the map, hold 13–30% of each issue's evidence. Both concern the
shared guide, so they are a later fairness question.
```

In `docs/HANDOFF.md`, replace the "### Next steps" list items 1–3 with:

```markdown
1. **Done: D1 (router fallback), then D2 (the document router)**, which supersedes it. Spec
   `docs/superpowers/specs/2026-09-25-doc-router-design.md`, plan `docs/superpowers/plans/2026-09-25-plan-5-d2-doc-router.md`.
   Offline checks and the audit are in `plan-5-dev-checks.md`.
2. **Withdrawn: the Lead prompt fix.** "Not found" is no evidence against an issue, because a clean fact states
   $0.0M; the Lead holding its chance was correct. The map's order (off for `r2`) and the board minutes (off the map)
   are a later fairness question for the shared guide, which S1b also gets.
3. **Next: the paid re-run** (D2 plan, Task 5; needs the user's OK).
```

- [ ] **Step 6: Commit**

```bash
git add docs/results/plan-5-prompt-log.md docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md \
        docs/results/plan-5-dev-checks.md docs/HANDOFF.md
git commit -m "docs: D2 offline checks, prompt log, handoff (Plan 5, D2 Task 4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The paid re-run (controller only; needs the user's OK)

- [ ] **Step 1: Ask the user.** The pilot runs the first *n* dev deals only (`--n`), so the spec's 15 chosen deals would need a new flag. Propose `--n 30`: all 30 `cal-r2` dev deals, which Plan 5 Task 6 needs anyway ("`s4` on all 30"), about $15–20 notional and 60–80 minutes at an estimated 10–14 sessions per deal. The alternative is `--n 10` (about $6, 25 minutes), which leaves out S1b's other misses (dev-012, 013, 016, 025, 029). Do not run without an explicit yes.

- [ ] **Step 2: Archive the `c989fb1` runs** (the pilot skips finished runs):

```bash
mv data/cal-r2/runs/s4 data/cal-r2/s4-c989fb1
```

- [ ] **Step 3: Run S4** (CLI 2.1.280 for parity with S1b's runs):

```bash
export CLAUDE_BIN="$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude"
uv run python -m acqlab.bench.pilot --data data/cal-r2 --n 30 --systems s4 --confirm-claude
```

Exit 0 means done; exit 2 means Claude stopped (for example at a usage limit): rerun later and finished runs are skipped. The pilot's log is buffered; to watch progress, count `data/cal-r2/runs/s4/*.json`.

- [ ] **Step 4: Report**

```bash
uv run python -m acqlab.bench.pilot --data data/cal-r2 --n 30 --systems s1b,s4 --report
uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4
```

Record in `docs/results/plan-5-dev-checks.md`: correct calls and paired regret difference S4 − S1b with its 95% CI, the flip-deal and per-case-type differences, the audited-notes read rate, sessions and cost per deal, `s3_n`, and a comparison with the `c989fb1` table. Commit with the Opus trailer.

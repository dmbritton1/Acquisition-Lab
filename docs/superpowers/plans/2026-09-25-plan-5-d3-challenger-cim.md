# Plan 5 D3: The Challenger at the Midpoint, and CIM Claims — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give S4's Challenger a real budget by stopping the router's first pass at half the budget, and stop the Committer from settling an issue on the seller's CIM alone.

**Architecture:** `committer.check` wraps the existing checks (`_check`) and turns a value or range quoted only from `SELLER_DOCS = ("cim",)` into a `not_found` commit. `Panel.route`/`directed` take an optional `until`; `Panel.run` passes half the budget for the first pass when the Challenger is on, and (router mode) reads again after `challenge()`.

**Tech Stack:** Python 3.12, pytest, uv. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-25-d3-challenger-cim-design.md` (approved 2026-09-25; §1 made strict after pre-verification, §7).

**Branch:** `claude/plan-4b-freeze-preregistration-0908fa` (worktree `.claude/worktrees/plan-4b-freeze-preregistration-0908fa`), at `0fa0987`. 289 tests pass there. The full suite takes about 5 minutes.

**Pre-verified.** Every code block below was run in a scratch copy of this branch (`<scratchpad>/d3`). Task 1 alone: 290 passed. Both code tasks: 293 passed. The offline checks in Task 3 were run on the scratch build; their expected outputs are quoted there.

## Global Constraints

- Ponytail: minimal code, stdlib only, no speculative abstractions. Match the surrounding comment density and idiom.
- **No answer-key information in S4 code** (`acqlab/agents/*`, `acqlab/routers/*`).
- **No prompt change:** do not edit `acqlab/agents/prompts.py`, `acqlab/agents/panel_prompts.py`, `acqlab/agents/knowledge.py` or `acqlab/agents/solver.py`.
- `MID_SHARE = 0.5`; `SELLER_DOCS = ("cim",)`.
- **The non-router build steps (`s4_2`, `s4_3`) behave exactly as before.** With the Challenger off, directed reading runs to the end as under D2.
- Line length at most 120.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never make a real Claude or Codex call without the user's OK in this session. Never modify settings or permissions files. If a git operation is blocked, stop and report.

## Review Focus

1. **The Challenger raises nothing, or its session fails** — `challenge()` returns early; the second half of the budget must still be read (router mode). Task 2's `test_a_document_that_does_not_fit_the_first_half_waits_for_the_second` uses a Challenger with no objections and checks the second-half read.
2. **A CIM quote beside another document** — must still commit (the "calculation" and "contradicted" placements need it). Task 1's test covers it.
3. **The real-rooms Committer test** (`test_every_real_value_and_range_can_be_committed_from_its_documents`) — a contradicted add-back's amount is in both the CIM and the QoE; the test must quote the evidence document, not the CIM. Task 1 changes its `_line` helper.
4. **`s4_3` (Challenger, no router)** — `directed(until)` is ignored without the router, and the extra second-half `directed()` runs only in router mode. Covered by the unchanged `s4_3` tests.
5. **A document bigger than half the budget** (the audited notes) — waits for the second half rather than being skipped for good. Task 2's test covers it.

## File map

| File | Task | Change |
|---|---|---|
| `acqlab/agents/committer.py` | 1 | `SELLER_DOCS`; `check` wraps `_check` |
| `tests/agents/test_committer.py` | 1 | new test; `_line` prefers non-seller documents; the zero-value example quotes the legal letter |
| `acqlab/agents/panel.py` | 2 | `MID_SHARE`; `route(until)`, `directed(until)`; `run()` |
| `tests/agents/test_panel.py` | 2 | three new tests |
| docs (Task 3) | 3 | Plan 5 plan D3, `plan-5-dev-checks.md`, `HANDOFF.md` |

---

### Task 1: CIM claims never settle an issue alone

**Files:**
- Modify: `acqlab/agents/committer.py`
- Test: `tests/agents/test_committer.py`

**Interfaces:**
- Produces: `committer.SELLER_DOCS: tuple[str, ...] = ("cim",)`. `check(finding, texts)` keeps its signature; a `quoted`/`computed`/`range` commit whose `docs` are all in `SELLER_DOCS` comes back as `{**commit, "kind": "not_found", "low": None, "high": None}` with no errors (its `docs` and `quotes` kept).

- [ ] **Step 1: Write the failing tests**

In `tests/agents/test_committer.py`, change the import:

```python
from acqlab.agents.committer import check, norm, numbers
```

to:

```python
from acqlab.agents.committer import SELLER_DOCS, check, norm, numbers
```

In `test_a_value_must_appear_in_the_quotes_except_zero`, replace:

```python
    c, errs = check({"type": "debt_like", "status": "value", "value": 0,
                     "quotes": [q("cim", "The business has no earnout.")]}, TEXTS)
    assert errs == [] and c["low"] == 0.0
```

with (the test's point is that 0 needs no number in the quote; a CIM quote is now the seller's claim):

```python
    c, errs = check({"type": "debt_like", "status": "value", "value": 0,
                     "quotes": [q("legal", "We represent the Company in a pending customer lawsuit.")]}, TEXTS)
    assert errs == [] and c["low"] == 0.0
```

Directly above `def test_numbers_reads_amounts_percentages_ranges_and_number_words():`, add:

```python
def test_the_seller_s_cim_alone_never_settles_an_issue():
    """D3: a value or range quoted only from the CIM is the seller's claim, committed as read without settling it; the
    CIM beside any other document is evidence as usual."""
    c, errs = check({"type": "debt_like", "status": "value", "value": 0,
                     "quotes": [q("cim", "The business has no earnout.")]}, TEXTS)
    assert errs == [] and c["kind"] == "not_found" and c["docs"] == ["cim"] and c["low"] is None
    assert c["quotes"] == [q("cim", "The business has no earnout.")]  # kept for the evidence trail
    c, errs = check({"type": "addback", "status": "range", "low": 0, "high": 1.8,
                     "quotes": [q("cim", "Restructuring costs of $1.8M were a one-time cost")]}, TEXTS)
    assert errs == [] and c["kind"] == "not_found"
    c, errs = check({"type": "addback", "status": "value", "value": 1.2,
                     "quotes": [q("cim", "Restructuring costs of $1.8M were a one-time cost"),
                                q("qoe", "of this, $1.2M recurred in each of the last three years")]}, TEXTS)
    assert errs == [] and c["kind"] == "quoted" and c["docs"] == ["cim", "qoe"] and c["low"] == 1.2


```

Replace the start of `_line`:

```python
def _line(texts: dict[str, str], docs: list[str], needle: str) -> dict:
    for d in docs:
```

with:

```python
def _line(texts: dict[str, str], docs: list[str], needle: str) -> dict:
    """The first line holding the needle, from the documents that are evidence before the seller's CIM (a contradicted
    add-back's amount is in both: the CIM claims it is one-time, the QoE says it recurs)."""
    for d in sorted(docs, key=lambda d: d in SELLER_DOCS):
```

(the rest of `_line` is unchanged).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/agents/test_committer.py`
Expected: collection error, `ImportError: cannot import name 'SELLER_DOCS' from 'acqlab.agents.committer'`.

- [ ] **Step 3: Implement the rule in `acqlab/agents/committer.py`**

After the line `TOL = 0.051  # $M: amounts print with one decimal`, add:

```python
SELLER_DOCS = ("cim",)  # the seller's own marketing: its claims are what diligence checks, never evidence on their own
# (trust ranking: contracts and audited accounts > QoE > CIM; D3)
```

Replace the `check` function's first three lines:

```python
def check(finding: dict, texts: dict[str, str]) -> tuple[dict | None, list[str]]:
    """(commit, errors). `texts` maps each document the session may cite to its text. A commit is
    {"type", "kind": quoted|computed|range|not_found|open, "low", "high", "chance", "quotes", "docs"}."""
```

with:

```python
def check(finding: dict, texts: dict[str, str]) -> tuple[dict | None, list[str]]:
    """(commit, errors). `texts` maps each document the session may cite to its text. A commit is
    {"type", "kind": quoted|computed|range|not_found|open, "low", "high", "chance", "quotes", "docs"}. A value or
    range quoted only from the seller's documents is the seller's claim: it commits as not_found (read without
    settling it), keeping its quotes (D3)."""
    commit, errors = _check(finding, texts)
    if commit and commit["kind"] in ("quoted", "computed", "range") and set(commit["docs"]) <= set(SELLER_DOCS):
        return {**commit, "kind": "not_found", "low": None, "high": None}, []
    return commit, errors


def _check(finding: dict, texts: dict[str, str]) -> tuple[dict | None, list[str]]:
```

(the old body of `check` becomes the body of `_check`, unchanged).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/agents/test_committer.py tests/agents/test_server.py`
Expected: all pass.

Run: `uv run pytest -q`
Expected: `290 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/agents/committer.py tests/agents/test_committer.py
git commit -m "feat(agents): a CIM claim alone never settles an issue (Plan 5, D3 Task 1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The Challenger at the midpoint

**Files:**
- Modify: `acqlab/agents/panel.py`
- Test: `tests/agents/test_panel.py`

**Interfaces:**
- Produces: `panel.MID_SHARE = 0.5`; `Panel.route(until: float | None = None) -> str | None` (candidates fit `(budget if until is None else until) − spent`); `Panel.directed(until: float | None = None)` (passes `until` to `route` in router mode; ignored without the router).

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/agents/test_panel.py` (two blank lines before the first new test):

```python
def test_with_the_challenger_the_first_pass_reads_only_the_first_half_and_objections_are_read_after(data, tmp_path,
                                                                                                    monkeypatch):
    """D3: cheap documents first (a stand-in score), only what fits in half the budget; then the Challenger objects and
    the document it names is read with the other half."""
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: 5.0 if d == "audited" and self.entries["debt_like"].objections else 1 / pages[d] for d in docs})
    rounds = [{"objections": [{"type": "debt_like", "kind": "elsewhere", "chance": 0.9, "low": 0, "high": 90,
                               "docs": ["audited"], "reason": "the notes list a guarantee"}]}, {"objections": []}]

    def challenger(sess, prompt):
        sess.call("challenge", rounds.pop(0) | {"pairs": [{"a": a, "b": b, "answer": "ruled_out", "reason": "r"}
                                                          for a, b in sess.pairs]})

    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing,
                 challenger=challenger)
    Panel(_room(data), 40, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    rows = _rows(tmp_path / "t.jsonl")
    first = next(i for i, r in enumerate(rows) if r["tool"] == "challenge")
    assert 18 <= sum(r["cost"] for r in rows[:first] if r["tool"] == "open_document") <= 20  # the first half, filled
    after = [r["args"]["doc"] for r in rows[first:] if r["tool"] == "route"]
    assert after[0] == "audited"  # the objection's document, read with the second half


def test_a_document_that_does_not_fit_the_first_half_waits_for_the_second(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs",
                        lambda self, pages, read, docs, seed=0: {d: float(d == "audited") for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing,
                 challenger=no_objections)
    Panel(_room(data), 20, tmp_path / "t.jsonl", Config(sweep=False), s).run()
    assert [r for r, _, _ in s.turns][:3] == ["lead", "challenger", "investigator"]  # audited (14) > half of 20
    assert "Reading budget left: 20 units." in s.turns[1][1] and "Brief: read audited (14 pages)" in s.turns[2][1]


def test_without_the_challenger_directed_reading_runs_to_the_end(data, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.Record, "rank_docs", lambda self, pages, read, docs, seed=0: {
        d: 1 / pages[d] for d in docs})
    s = scripted(lead=lead_says(([_issue("debt_like", 0.5)], False)), investigator=finds_nothing)
    p = Panel(_room(data), 40, tmp_path / "t.jsonl", Config(challenger=False, sweep=False), s)
    p.run()
    assert p.spent() > 0.5 * 40 and "challenger" not in [r for r, _, _ in s.turns]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/agents/test_panel.py -k "first_half or waits_for_the_second or without_the_challenger"`
Expected: 2 failed, 1 passed. The first-half test fails its `<= 20` assertion (the router reads past the midpoint before the Challenger speaks); the waits test fails its turn-order assertion (the first turn after the Lead is an Investigator reading the audited notes). The without-the-Challenger test already passes (it pins behaviour that must not change).

- [ ] **Step 3: Implement the midpoint in `acqlab/agents/panel.py`**

Replace the end of the module docstring:

```python
engine's walk-away most per page, one Investigator reads that one document, and the Lead re-plans after a read that
commits something. Build steps (reframe design §5) are configs: STAGES."""
```

with:

```python
engine's walk-away most per page, one Investigator reads that one document, and the Lead re-plans after a read that
commits something; with the Challenger too, a first pass reads only the first half of the budget and the Challenger
then objects (D3), so its objections compete with the router's own picks for the rest. Build steps (reframe design §5)
are configs: STAGES."""
```

After the line `CHALLENGE_ROUNDS = 2`, add:

```python
MID_SHARE = 0.5  # with the router and the Challenger, the first directed pass reads only documents that fit in this
# share of the budget, so the Challenger's objections have the rest to compete for (D3)
```

Replace the start of `route`:

```python
    def route(self) -> str | None:
        """D2 §3: the unread document whose reading moves the engine's walk-away most per page, among those that fit
        the budget left (the sweep's reserve included: unspent budget earns nothing). None once no document can move
        it: the sweep takes over."""
        read, left = self.read(), self.budget - self.spent()
```

with:

```python
    def route(self, until: float | None = None) -> str | None:
        """D2 §3: the unread document whose reading moves the engine's walk-away most per page, among those that fit
        the budget left (the sweep's reserve included: unspent budget earns nothing), or what is left before `until`.
        None once no document can move it: the sweep takes over."""
        read, left = self.read(), (self.budget if until is None else until) - self.spent()
```

Replace the start of `directed`:

```python
    def directed(self) -> None:
        if self.cfg.router:
            while (d := self.route()) is not None:
```

with:

```python
    def directed(self, until: float | None = None) -> None:
        """Directed reading; with the router and `until`, only documents that fit before `until` is spent."""
        if self.cfg.router:
            while (d := self.route(until)) is not None:
```

In `run`, replace:

```python
            self.lead()
            self.directed()
            if self.cfg.challenger:
                self.challenge()
```

with:

```python
            self.lead()
            self.directed(MID_SHARE * self.budget if self.cfg.challenger else None)
            if self.cfg.challenger:
                self.challenge()
                if self.cfg.router:
                    self.directed()  # the second half, also when the Challenger raised nothing (D3)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/agents/test_panel.py`
Expected: all pass.

Run: `uv run pytest -q`
Expected: `293 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/agents/panel.py tests/agents/test_panel.py
git commit -m "feat(agents): the Challenger speaks at the midpoint, so its objections have budget (Plan 5, D3 Task 2)

With the router and the Challenger, the first directed pass reads only what fits in half the budget; the Challenger
then objects and the router weighs its documents against its own picks for the rest. Directed reading runs again
after the Challenger, so the second half is read even when it raises nothing.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Offline checks and records (controller only; no Claude calls)

**Files:**
- Modify: `docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md`, `docs/results/plan-5-dev-checks.md`, `docs/HANDOFF.md`

`data/cal-r2` is in this worktree already (git-ignored); `data/cal-r2/runs/s4` holds the 30 D2 runs.

- [ ] **Step 1: The Challenger's budget and the CIM conversions (spec §4)**

Run:

```bash
uv run python - <<'EOF'
import json, tempfile
from pathlib import Path
from acqlab.agents.committer import SELLER_DOCS
from acqlab.agents.panel import MID_SHARE, Config, Panel
D, left_at, conv = Path("data/cal-r2"), {}, []
for i in range(30):
    deal = f"dev-{i:03d}"
    key = json.loads((D / "truth" / f"{deal}.json").read_text())
    rows = [json.loads(x) for x in (D / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
    p = Panel(D / "deals" / deal / "room", key["budget"], Path(tempfile.mkdtemp()) / "t.jsonl", Config(), None)
    p.record.plan(next(x["args"]["issues"] for x in rows if x["tool"] == "propose"))
    read = set()
    p.read, p.spent, p.read_doc = (lambda: set(read)), (lambda: sum(p.pages[d] for d in read)), read.add
    p.directed(MID_SHARE * p.budget)  # the first pass, assuming nothing is found: exact until the first commit
    left_at[deal] = p.budget - p.spent()
    for x in rows:
        if x["tool"] == "report" and not x["refused"]:
            for c in x["result"]["commits"]:
                if c["kind"] in ("quoted", "computed", "range") and set(c["docs"]) <= set(SELLER_DOCS):
                    conv.append((deal, c["type"]))
print("pages left when the Challenger first speaks:", sorted(left_at.values()))
print("dev-003:", left_at["dev-003"], "dev-022:", left_at["dev-022"], "| deals with at least 9 left:",
      sum(v >= 9 for v in left_at.values()), "of 30")
print("D2 commits the CIM rule converts:", len(conv), conv)
EOF
```

Expected (pre-verification): pages left 10–14 on every deal; `dev-003: 13.0 dev-022: 13.0 | deals with at least 9 left: 30 of 30`; `D2 commits the CIM rule converts: 5`, all `dev-003` (addback, concentration, capex, nwc, debt_like). If a result differs, stop and report to the user before any paid run.

- [ ] **Step 2: Records**

In `docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md`, after the `- **D2 (page-spend audit):** ...` entry (its last line ends with `plan: \`docs/superpowers/plans/2026-09-25-plan-5-d2-doc-router.md\`.`), add:

```markdown
- **D3 (D2 re-run):** with the router and the Challenger, the first directed pass reads only what fits in half the
  budget, then the Challenger objects and its documents compete with the router's picks for the rest; directed reading
  runs again after the Challenger. A value or range quoted only from the CIM commits as not_found (the seller's claim).
  Spec: `docs/superpowers/specs/2026-09-25-d3-challenger-cim-design.md`; plan:
  `docs/superpowers/plans/2026-09-25-plan-5-d3-challenger-cim.md`.
```

Append to `docs/results/plan-5-dev-checks.md`:

```markdown

## D3 offline checks (2026-09-25)

Spec `docs/superpowers/specs/2026-09-25-d3-challenger-cim-design.md`. Replaying the first directed pass of the 30 D2
runs under the strict midpoint (exact until the first commit): the Challenger first speaks with 10–14 pages left on
every deal (under D2: 0–1 on 25 of 30), 13 on dev-003 and dev-022 (where the QoE, holding the $45.8M flipper, costs 9).
The CIM rule converts 5 of the D2 commits, all dev-003's five $0 claims, and none elsewhere.
```

In `docs/HANDOFF.md`, in "### Next steps", replace the last sentence of item 3:

```markdown
   (caution from unsettled issues), and dev-003 with S1b (CIM claims committed as fact). Candidate next steps: a budget
   of the Challenger's own, and a CIM claim alone never settling an issue.
```

with:

```markdown
   (caution from unsettled issues), and dev-003 with S1b (CIM claims committed as fact). D3 addresses the Challenger
   and the CIM (`docs/superpowers/specs/2026-09-25-d3-challenger-cim-design.md`); its re-run is the D3 plan's Task 4.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md docs/results/plan-5-dev-checks.md docs/HANDOFF.md
git commit -m "docs: D3 offline checks and records (Plan 5, D3 Task 3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The paid re-run (controller only; needs the user's OK)

- [ ] **Step 1: Ask the user.** `s4` on all 30 `cal-r2` dev deals: about $15 notional and 70 minutes. Do not run without an explicit yes.

- [ ] **Step 2: Archive the D2 runs** (the pilot skips finished runs):

```bash
mv data/cal-r2/runs/s4 data/cal-r2/s4-d2-059a3b4
```

- [ ] **Step 3: Run S4** (CLI 2.1.280 for parity with S1b's runs):

```bash
export CLAUDE_BIN="$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude"
uv run python -m acqlab.bench.pilot --data data/cal-r2 --n 30 --systems s4 --confirm-claude > data/cal-r2/s4-d3-run.log 2>&1
```

Exit 0 means done; exit 2 means Claude stopped (for example at a usage limit): rerun later and finished runs are skipped. To watch progress, count `data/cal-r2/runs/s4/dev-*.json` (the pilot's log is buffered).

- [ ] **Step 4: Report**

```bash
uv run python -m acqlab.bench.pilot --data data/cal-r2 --n 30 --systems s1b,s4 --report
uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4
```

Record in `docs/results/plan-5-dev-checks.md`, against S1b and against the D2 run (`data/cal-r2/s4-d2-059a3b4`): correct calls, the paired regret difference with its 95% CI, by case type, how often an objection's named document was then read, the pages left at each Challenger round (from the traces), CIM conversions in the new runs, and sessions and cost per deal. Update `docs/HANDOFF.md`. Commit with the Opus trailer.

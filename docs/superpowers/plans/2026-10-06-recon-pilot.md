# Reconciliation Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the same-budget pilot of reconciliation designs C (draft, dispute, check) and A (two scouts, one referee) against single Claude and the frozen team, on 40 fresh deals.

**Architecture:**
- **Every step is a sandboxed `claude -p` session** on the existing tool server (`solver.solve` / `run_session`). The server enforces each step's page budget, and a later step gets only what is left.
- **A new module, `acqlab/bench/recon.py`,** runs the steps:
  - It builds an engine call from an analyst's notes, using the frozen team's `Record`.
  - It sends disputes to the referee from the kill test, which now has an optional reading variant in `acqlab/bench/referee.py`.
  - It writes one combined trace that the existing `pilot.score` scores unchanged.
- **A script, `scripts/recon_pilot.py`,** applies the spec's fixed decision rule.

**Tech Stack:** Python 3.12, numpy, pytest. The Claude Code CLI (`claude -p`) is driven through the repo's MCP tool server. Tests use the fake `claude` in `tests/agents/fake_claude.py`.

**Spec:** `docs/superpowers/specs/2026-10-06-recon-pilot-design.md`

## Global Constraints

- **Model:** `claude-opus-5-5` for every session, on Claude Code CLI 2.1.291 or newer (`claude --version`).
- **Frozen files:** S4's files (`acqlab/agents`, `acqlab/routers`) stay byte-identical to tag `s4-frozen-plan5`. This is checked by `tests/bench/test_sim.py::test_s4_s_files_are_unchanged_from_the_freeze_tag`.
- **No real Claude call until the user's OK in Task 6.** Tests use only the fake `claude`. Every runner refuses to start without `--confirm-claude`.
- **Budget shares:** C's drafter gets 0.7·B and each of A's scouts gets 0.5·B. The referee gets B minus every page already paid for, and never less than 0.
- **The decision rule (spec §5):**
  - Mechanics: at least 38 of 40 deals answered, and none over budget.
  - Pick: the lower mean regret wins; within 0.0005, the lower mean cost wins.
  - Go: only if the chosen design's mean regret is below both `s1b`'s and `s4`'s.
- **The kill test's prompt stays byte-identical:** `referee.prompts` must give the same text for all 48 disputed `test-r2` deals. SHA-256 over the 48 (system + user): `919a6d49b11f979d3658403b3758de24a4ab773b1168fb898a1ea80c76519d2e`.
- **Deals:** 40, split `test`, base seed 9,000,000, profile `r2`, template prose, in `data/pilot-r2` (git-ignored).
- **Frozen before the first run:** prompts, shares and rules are frozen before the first Claude run. A later bug fix is logged and its design rerun on all 40 deals.
- **Commits** end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Test counts:** 377 tests pass now: 379 after Task 1, 389 after Task 2, 394 after Task 3 and 395 after Task 4.
- **The pre-verified code below** was run in a scratch copy of the repo at `90731de`. Use it verbatim.

## Review Focus

1. **A referee with nothing left to spend** (the scouts used the whole budget) must still decide, with a zero budget. Pinned by `test_a_referee_with_nothing_left_still_decides` (Task 2).
2. **Claude stopping mid-deal** (a usage limit) must leave no half-written row and exit 2, so a rerun redoes the whole deal. Pinned by `test_claude_stopping_mid_deal_writes_no_row_and_exits_2` (Task 3).
3. **A second opinion or scout that never submits** is a missing call, which goes to the referee rather than standing as an agreement. Pinned by `test_a_disagreement_or_any_missing_call_goes_to_the_referee` (Task 2).
4. **Rerunning the analysis** must never overwrite a result already written. Pinned in `test_the_analysis_script_reads_a_finished_pilot` (Task 4).
5. **The kill test's prompt** must not change under the referee refactor, because its committed result depends on it. Pinned by the SHA-256 check in Task 1, Steps 1 and 5, alongside the existing referee tests.

---

### Task 1: The referee's reading variant

**Files:**
- Modify: `acqlab/bench/referee.py` (whole file below)
- Test: `tests/bench/test_referee.py` (append two tests)

**Interfaces:**
- Consumes: `acqlab.agents.solver.run_session(room, budget, trace, prompt, system, tools, server_args, **kw)`, and the tool server's `--paid` option (comma-separated document ids that are free to reopen).
- Produces:
  - `referee.NO_READING: str`
  - `referee.READING: str` (format key `left`)
  - `referee.READ_TOOLS: list[str]`
  - `referee.note_lines(trace: list[dict]) -> list[str]`
  - `referee.build(room: Path, views: list[str], read: list[str], deal: str, left: float | None = None) -> tuple[str, str]`
  - `referee.judge_reading(room: Path, views: list[str], read: list[str], deal: str, left: float, trace: Path, **kw) -> dict`
  - Unchanged: `rows`, `opened`, `solo_view`, `team_view`, `prompts`, `judge`, `disputed`, `run`, `main`.

- [ ] **Step 1: Record the kill-test prompt fingerprint before changing anything**

Run:
```bash
.venv/bin/python -c "
import sys,hashlib; sys.path.insert(0,'.')
from pathlib import Path
from acqlab.bench import referee as r
data=Path('data/test-r2'); h=hashlib.sha256()
for d in r.disputed(data):
  room=data/'deals'/d/'room'; s,u=r.prompts(room, r.rows(data/'runs/s4'/f'{d}.trace.jsonl'), r.rows(data/'runs/s1b'/f'{d}.trace.jsonl'), d); h.update((s+u).encode())
print(h.hexdigest())"
```
Expected: `919a6d49b11f979d3658403b3758de24a4ab773b1168fb898a1ea80c76519d2e`

- [ ] **Step 2: Write the failing tests** (append to `tests/bench/test_referee.py`)

```python
def test_a_reading_referee_is_told_its_budget_and_the_kill_test_s_is_not(s4_fake_run):
    room, team = s4_fake_run
    views = [referee.solo_view(_solo()), referee.solo_view(_solo(go=False))]
    closed, _ = referee.build(room, views, ["qoe"], "dev-000")
    reading, user = referee.build(room, views, ["qoe"], "dev-000", left=6.5)
    assert referee.NO_READING in closed and referee.NO_READING not in reading
    assert "a budget of 6.5 units" in reading and reading.replace(referee.READING.format(left=6.5), "") == \
        closed.replace(referee.NO_READING, "")
    assert "## " in user and "(qoe)" in user


def test_a_reading_referee_gets_its_budget_the_reading_tools_and_the_paid_documents(s4_fake_run, tmp_path,
                                                                                     monkeypatch):
    room, team = s4_fake_run
    seen = {}
    monkeypatch.setattr(referee, "run_session", lambda *a, **kw: seen.update(a=a, kw=kw) or {"total_cost_usd": 0})
    referee.judge_reading(room, ["one", "two"], ["qoe", "cim", "qoe"], "dev-000", 7.0, tmp_path / "t.jsonl",
                          claude="x")
    room_, budget, trace, user, system, tools, server_args = seen["a"]
    assert budget == 7.0 and tools == referee.READ_TOOLS and server_args == ["--paid", "qoe,cim"]
    assert seen["kw"] == {"claude": "x"}
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/bench/test_referee.py -k reading_referee`
Expected: 2 failed, with `AttributeError: module 'acqlab.bench.referee' has no attribute 'build'` (or `'judge_reading'`).

- [ ] **Step 4: Replace `acqlab/bench/referee.py` with:**

```python
"""The referee kill test (docs/results/referee-kill-test-prereg.md): on a deal where the team (S4) and single Claude
(S1b) disagree, one sandboxed turn sees every document either opened and both analysts' work, prices with evaluate and
submits. It pools both runs' reading, so it screens the idea; it is not a fair result.

It reads the room and the two traces only, never an answer key.

  uv run python -m acqlab.bench.referee --data data/test-r2 --confirm-claude"""
import argparse
import json
import random
from pathlib import Path

from acqlab.agents.knowledge import GUIDE
from acqlab.agents.solver import RunTimeout, run_session
from acqlab.bench import valuer
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable

SYSTEM = """You are a private-equity analyst refereeing a disagreement about a leveraged buyout: should the sponsor \
buy the company at its asking price?

Two analysts did diligence on this deal, each with a limited reading budget, and reached opposite calls. You get the \
teaser, with the lender terms and the sponsor's policy; the full text of every document either of them read; and each \
analyst's findings. You cannot read anything else.

Find what the disagreement turns on, and settle it from the documents: a finding counts where a document supports it, \
and an issue neither analyst could check stays uncertain. All amounts are in $M: addback = claimed add-backs that are \
not really one-time (they reduce EBITDA); debt_like = debt-like items payable at closing; concentration = annual \
revenue that will be lost; nwc = how far closing net working capital falls short of normal; capex = extra capital \
expenditure needed per year.

Use evaluate to price your adjustments: it returns the walk-away price (the most the sponsor should pay) and whether \
the deal clears at the asking price. Then call submit once, with go (true to buy at the asking price), walk_away in $M \
and a one-line reason. You are judged on the decision: buying a deal worth less than its price, or passing on one \
worth more, costs the difference.

{guide}"""


NO_READING = "You cannot read anything else."
READING = ("You can also read more before deciding, with a budget of {left:g} units: list_documents shows every "
           "document, opening one costs 1 unit per page and search costs 1 unit. The documents above are already "
           "paid for.")
READ_TOOLS = ["list_documents", "search", "open_document", "evaluate", "submit"]


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


def opened(trace: list[dict]) -> list[str]:
    return [r["args"]["doc_id"] for r in trace if r["tool"] == "open_document" and not r.get("refused")]


def submitted(trace: list[dict]) -> dict:
    return next(r for r in trace if r["tool"] == "submit" and not r.get("refused"))["args"]


def team_view(room: Path, trace: list[dict]) -> str:
    """S4's final Deal Record as its own roles saw it, and its submitted call."""
    s = submitted(trace)
    return (valuer.replay(room, trace).view() +
            f"\nCall: {'GO' if s['go'] else 'NO-GO'}, walk-away ${s['walk_away']:,.1f}M.")


def note_lines(trace: list[dict]) -> list[str]:
    """An analyst's last note per issue type, one line each."""
    notes = {r["args"]["type"]: r["args"] for r in trace if r["tool"] == "note_issue" and not r.get("refused")}
    return [f"- {t}: chance {n['chance']:g}, ${n['low']:g}M to ${n['high']:g}M if real ({n.get('name', '')})"
            for t, n in notes.items()] or ["- no issues noted"]


def solo_view(trace: list[dict]) -> str:
    """S1b's last note per issue type, its last evaluate, and its submitted call and reason."""
    ok = [r for r in trace if not r.get("refused")]
    lines = note_lines(ok)
    ev = [r for r in ok if r["tool"] == "evaluate"]
    if ev:
        res = ev[-1].get("result") or {}
        lines.append(f"Last priced adjustments: {json.dumps(ev[-1]['args']['adjustments'])} -> walk-away "
                     f"${res.get('walk_away', float('nan')):,.1f}M")
    s = next((r["args"] for r in ok if r["tool"] == "submit"), None)
    lines.append(f"Call: {'GO' if s['go'] else 'NO-GO'}, walk-away ${s['walk_away']:,.1f}M. Reason: {s['reason']}"
                 if s else "Call: none; the analyst's run ended without submitting one.")
    return "\n".join(lines)


def build(room: Path, views: list[str], read: list[str], deal: str, left: float | None = None) -> tuple[str, str]:
    """(system, user) for any two analysts' views and the documents read. The views' order is fixed per deal from its
    id, so neither is always first. With `left`, the referee may also read, with that budget (the recon pilot)."""
    index = json.loads((room / "index.json").read_text())
    titles = {d["id"]: d["title"] for d in index["documents"]}
    read = [d for d in titles if d in set(read)]
    docs = "\n\n".join(f"## {titles[d]} ({d})\n\n{(room / f'{d}.md').read_text()}" for d in read)
    views = list(views)
    if random.Random(deal).random() < 0.5:
        views.reverse()
    user = (f"{index['teaser']}\n\n# Documents either analyst read\n\n{docs}\n\n# Analyst 1\n\n{views[0]}\n\n"
            f"# Analyst 2\n\n{views[1]}\n\nSettle the disagreement and submit your decision.")
    system = SYSTEM.format(guide=GUIDE)
    return (system if left is None else system.replace(NO_READING, READING.format(left=left))), user


def prompts(room: Path, team: list[dict], solo: list[dict], deal: str) -> tuple[str, str]:
    """The kill test's (system, user): the team's and single Claude's work, and every document either opened."""
    return build(room, [team_view(room, team), solo_view(solo)], opened(team) + opened(solo), deal)


def judge(room: Path, team: list[dict], solo: list[dict], deal: str, trace: Path, **kw) -> dict:
    """One referee turn: evaluate and submit only, no reading budget. Raises LLMUnavailable like any session."""
    system, user = prompts(room, team, solo, deal)
    return run_session(room, 0, trace, user, system, ["evaluate", "submit"], [], **kw)


def judge_reading(room: Path, views: list[str], read: list[str], deal: str, left: float, trace: Path,
                  **kw) -> dict:
    """A referee turn that may read with `left` units; the documents already read are paid for (the recon pilot)."""
    system, user = build(room, views, read, deal, left)
    paid = list(dict.fromkeys(read))
    return run_session(room, left, trace, user, system, READ_TOOLS, ["--paid", ",".join(paid)] if paid else [], **kw)


def disputed(data: Path) -> list[str]:
    runs = data / "runs"
    both = sorted(p.stem for p in (runs / "s4").glob("*.json") if (runs / "s1b" / p.name).exists())
    return [d for d in both if json.loads((runs / "s4" / f"{d}.json").read_text())["go"]
            != json.loads((runs / "s1b" / f"{d}.json").read_text())["go"]]


def run(data: Path, judge=judge) -> list[dict]:
    """A referee run on every disputed deal without one; raises LLMUnavailable to stop the batch."""
    from acqlab.bench.pilot import score  # scoring reads the answer key, after the referee has submitted
    out = []
    for deal in disputed(data):
        path = data / "runs" / "referee" / f"{deal}.json"
        if path.exists():
            continue
        room = data / "deals" / deal / "room"
        team, solo = (rows(data / "runs" / s / f"{deal}.trace.jsonl") for s in ("s4", "s1b"))
        path.parent.mkdir(parents=True, exist_ok=True)
        trace = path.with_suffix(".trace.jsonl")
        trace.unlink(missing_ok=True)
        try:
            cli, status = judge(room, team, solo, deal, trace), "ok"
        except RunTimeout:
            cli, status = None, "timeout"
        tr = rows(trace) if trace.exists() else []
        if status == "ok" and not tr:
            raise LLMUnavailable(f"referee/{deal}: the tool server never ran (no trace)")
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        row = score(key, "referee", tr, cli, status) | {"rep": 0}
        path.write_text(json.dumps(row, indent=2))
        out.append(row)
        print(f"referee {deal}: correct={row['correct']} regret {row['regret']:.3f} answered={row['answered']}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--confirm-claude", action="store_true", help="required: this spends real Claude usage")
    args = ap.parse_args(argv)
    if not args.confirm_claude:
        print("Refusing: pass --confirm-claude to spend real Claude usage")
        return 1
    run(args.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the referee tests and the fingerprint again**

Run: `.venv/bin/python -m pytest -q tests/bench/test_referee.py`
Expected: 9 passed.

Run the Step 1 command again. Expected: the same `919a6d49…2e`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/bench/referee.py tests/bench/test_referee.py
git commit -m "feat(bench): the referee's reading variant for the recon pilot; the kill-test prompt is unchanged

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Designs C and A (orchestration, the engine call on notes, disputes, the combined trace)

**Files:**
- Create: `acqlab/bench/recon.py` (the core below; Task 3 appends the runner)
- Test: `tests/bench/test_recon.py` (create)

**Interfaces:**
- Consumes:
  - From Task 1: `referee.rows`, `referee.opened`, `referee.solo_view`, `referee.note_lines`, `referee.judge_reading`.
  - `solver.solve(room, budget, trace, router, **kw)`, `solver.RunTimeout`, `run_session`.
  - `Record(face)`, `Record.apply`, `Record.plan`, `Record.decide()` and `load_face(room)` from `acqlab.agents.record`.
- Produces:
  - Constants: `recon.DRAFT_SHARE = 0.7`, `recon.SCOUT_SHARE = 0.5`, `recon.DESIGNS = ("recon_c", "recon_a")`, `recon.USAGE`, `recon.TIE = 0.0005`, `recon.SECOND_SYSTEM`.
  - Trace readers:
    - `spent(trace) -> float`
    - `call_of(trace) -> dict | None`
    - `notes_record(room, trace) -> Record`
    - `engine_call(room, trace) -> dict | None`
    - `engine_view(trace, call) -> str`
  - Steps, each taking keyword `trace`:
    - `draft(room, budget, *, trace, router=False, **kw)`
    - `second(room, read, *, trace, **kw)`
    - `judge(room, views, read, deal, left, *, trace, **kw)`
  - Orchestration:
    - `second_prompts(room, read) -> (system, user)`
    - `step(name, path, fn, *args, **kw) -> (rows tagged with "step", cli | None)`
    - `combine(trace, clis, final) -> (trace, cli)`
    - `settle(...) -> (trace, cli)`, where `cli` also carries `"analysts": [a, b]` and `"disputed": bool`
    - `run_c(room, budget, deal, out, **kw)` and `run_a(room, budget, deal, out, **kw)`, each returning `(trace, cli)`
    - `RUN = {"recon_c": run_c, "recon_a": run_a}`
  - Step trace files sit beside `out`: `<deal>.draft.jsonl`, `.second.jsonl`, `.scout1.jsonl`, `.scout2.jsonl` and `.referee.jsonl`.

- [ ] **Step 1: Write the failing tests** (create `tests/bench/test_recon.py`)

```python
import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.agents.knowledge import typical_high
from acqlab.bench import pilot, recon
from acqlab.generator.batch import AnswerKey


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _note(t, chance, low, high):
    return {"name": t, "type": t, "chance": chance, "low": low, "high": high, "docs": []}


def _session(go, reads=(), cost=4.0, notes=()):
    rows = [_row("open_document", {"doc_id": d}, cost) for d in reads] + [_row("note_issue", n) for n in notes]
    return rows + ([_row("submit", {"go": go, "walk_away": 100.0, "reason": "r"})] if go is not None else [])


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


@pytest.fixture
def fakes(monkeypatch, room):
    """Every step replaced by one that writes a scripted trace (scripts[step]; none scripted = a timeout) and records
    its arguments (calls[step]); `engine` is the engine-priced analyst's call."""
    f = {"docs": [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]],
         "scripts": {}, "calls": {}, "engine": None}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        f["calls"][name] = (args, kw)
        if name not in f["scripts"]:
            raise recon.RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        return {"total_cost_usd": 0.1, "usage": {"output_tokens": 5}}

    for fn in ("draft", "second", "judge"):
        monkeypatch.setattr(recon, fn, run)
    monkeypatch.setattr(recon, "engine_call", lambda room_, trace: f["engine"])
    return f


def test_notes_become_a_record_as_the_team_prices_them(room):
    trace = [_row("note_issue", _note("addback", 0.5, 1, 2)), _row("note_issue", _note("addback", 0.4, 0, 3)),
             _row("note_issue", _note("debt_like", 1.0, 4, 6))]
    rec = recon.notes_record(room, trace)
    add, debt, nwc = (rec.issue(t) for t in ("addback", "debt_like", "nwc"))
    assert add.p_real == 0.4 and add.known is None and add.hi == max(3.0, typical_high("addback", rec.face.teaser))
    assert debt.known == (4.0, 6.0)
    assert not nwc.proposed  # no note: no problem


def test_the_engine_call_is_the_record_s_and_needs_a_submit(room):
    trace = [_row("note_issue", _note("concentration", 1.0, 30, 30))]
    assert recon.engine_call(room, trace) is None
    trace.append(_row("submit", {"go": True, "walk_away": 1.0, "reason": "x"}))
    go, wa = recon.notes_record(room, trace).decide()
    assert recon.engine_call(room, trace) == {"go": go, "walk_away": wa, "reason": "the engine, on the analyst's notes"}


def test_c_gives_the_drafter_70_percent_and_the_referee_what_is_left(fakes, room, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"draft": _session(True, d[:2]), "second": _session(False), "referee": _session(False)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, _ = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["draft"][0][1] == pytest.approx(14.0)
    _, views, read, deal, left = fakes["calls"]["referee"][0]
    assert read == d[:2] and left == pytest.approx(12.0) and deal == "dev-000"
    assert recon.spent(trace) <= 20.0


def test_a_gives_each_scout_half_scout_2_the_router_and_the_referee_what_is_left(fakes, room, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"scout1": _session(True, d[:2]), "scout2": _session(False, d[1:3]),
                         "referee": _session(True)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    recon.run_a(room, 20.0, "dev-000", tmp_path / "x.json")
    (_, b1), kw1 = fakes["calls"]["scout1"]
    (_, b2), kw2 = fakes["calls"]["scout2"]
    assert b1 == b2 == pytest.approx(10.0) and kw2.get("router") is True and not kw1.get("router")
    _, views, read, deal, left = fakes["calls"]["referee"][0]
    assert read == d[:3] and left == pytest.approx(4.0)  # a page both scouts read counts twice


def test_a_referee_with_nothing_left_still_decides(fakes, room, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"scout1": _session(True, d[:2], cost=5.0), "scout2": _session(False, d[2:4], cost=5.0),
                         "referee": _session(False)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, _ = recon.run_a(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["referee"][0][4] == 0.0 and recon.call_of(trace)["go"] is False


def test_the_second_opinion_gets_the_drafter_s_documents_never_its_work(fakes, room, tmp_path):
    d = fakes["docs"]
    secret = _note("addback", 0.5, 0, 9) | {"name": "SECRET"}
    fakes["scripts"] |= {"draft": _session(True, d[:1], notes=[secret]), "second": _session(True)}
    fakes["engine"] = {"go": True, "walk_away": 1.0}
    recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    assert fakes["calls"]["second"] == ((room, d[:1]), {})
    system, user = recon.second_prompts(room, d[:1])
    assert f"({d[0]})" in user and f"({d[1]})" not in user and "SECRET" not in system + user


def test_an_agreement_stands_without_a_referee(fakes, room, tmp_path):
    fakes["scripts"] |= {"draft": _session(True), "second": _session(False)}
    fakes["engine"] = {"go": True, "walk_away": 90.0}
    trace, cli = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    assert "referee" not in fakes["calls"] and cli["sessions"] == 2
    assert recon.call_of(trace) == {"go": True, "walk_away": 100.0, "reason": "the analysts agree"}


def test_a_disagreement_or_any_missing_call_goes_to_the_referee(fakes, room, tmp_path):
    cases = [({"draft": _session(False), "second": _session(True)}, {"go": True, "walk_away": 1.0}),
             ({"second": _session(True)}, {"go": True, "walk_away": 1.0}),  # the drafter timed out
             ({"draft": _session(True), "second": _session(None, notes=[_note("nwc", 0.5, 0, 1)])}, None)]  # the second opinion never submitted
    for scripts, engine in cases:
        fakes["calls"].clear()
        fakes["scripts"] = scripts | {"referee": _session(False)}
        fakes["engine"] = engine
        trace, _ = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
        assert "referee" in fakes["calls"] and recon.call_of(trace)["go"] is False


def test_the_combined_trace_scores_like_one_run(fakes, room, data, tmp_path):
    d = fakes["docs"]
    fakes["scripts"] |= {"draft": _session(True, d[:2]), "second": _session(False),
                         "referee": _session(False, d[2:3], cost=3.0)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, cli = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    row = pilot.score(key, "recon_c", trace, cli, "ok")
    assert row["pages"] == 11.0 and row["go"] is False and row["answered"]
    assert sum(r["tool"] == "submit" for r in trace) == 1 and sum(r["tool"] == "step_submit" for r in trace) == 3
    assert row["cost_usd"] == pytest.approx(0.3) and row["sessions"] == 3 and row["tokens"]["output_tokens"] == 15


def test_a_referee_without_a_call_leaves_the_deal_unanswered(fakes, room, data, tmp_path):
    fakes["scripts"] |= {"draft": _session(True), "second": _session(False)}
    fakes["engine"] = {"go": False, "walk_away": 90.0}
    trace, cli = recon.run_c(room, 20.0, "dev-000", tmp_path / "x.json")
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    assert not pilot.score(key, "recon_c", trace, cli, "no_call")["answered"]
    assert cli["sessions"] == 3 and cli["timeouts"] == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/bench/test_recon.py`
Expected: an error at collection, `ImportError: cannot import name 'recon' from 'acqlab.bench'`.

- [ ] **Step 3: Create `acqlab/bench/recon.py`:**

```python
"""The reconciliation pilot (spec docs/superpowers/specs/2026-10-06-recon-pilot-design.md): design C (draft, dispute,
check) and design A (two scouts, one referee) at one page budget. Each step is a sandboxed `claude -p` session on our
tool server, which enforces the step's budget; a later step gets only what is left, so a deal's pages never exceed its
budget. No step reads the answer key; scoring does, after the final call.

  uv run python -m acqlab.bench.recon --data data/pilot-r2 --designs recon_c,recon_a --confirm-claude

Runs go to <data>/runs/<design>/<deal>.json, the combined trace beside it (each step's own trace too); finished runs
are skipped. Exit codes: 0 done; 1 an unknown design; 2 Claude stopped (rerun later to resume); 3 refused (no
--confirm-claude)."""
import argparse
import json
import math
from pathlib import Path

from acqlab.agents import solver
from acqlab.agents.knowledge import GUIDE
from acqlab.agents.record import Record, load_face
from acqlab.agents.solver import RunTimeout, run_session
from acqlab.bench import referee
from acqlab.llm import LLMUnavailable

DRAFT_SHARE, SCOUT_SHARE = 0.7, 0.5  # spec §2, §3
DESIGNS = ("recon_c", "recon_a")
USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
TIE = 0.0005  # spec §5: mean regrets this close pick the cheaper design
SECOND_SYSTEM = """You are a private-equity analyst pricing the risks in a leveraged buyout: should the sponsor buy \
the company at its asking price?

You get the teaser, with the lender terms and the sponsor's policy, and the full text of the deal documents another \
analyst chose to read. You cannot read anything else.

For each of the five kinds of issue, record your belief with note_issue: the chance it is real (0 to 1), its size range \
in $M if it is, and the documents that bear on it. Use chance 1 once a document settles it, with low and high the \
amount or range the document states. Where the documents say nothing either way, give your honest prior. A valuation \
engine prices your notes and makes the call, so note every kind of issue. Then call submit once with your own go and \
walk_away (they are logged, not used).

All amounts are in $M: addback = claimed add-backs that are not really one-time (they reduce EBITDA); debt_like = \
debt-like items payable at closing; concentration = annual revenue that will be lost; nwc = how far closing net \
working capital falls short of normal; capex = extra capital expenditure needed per year.

{guide}"""


# --- reading a step's trace ----------------------------------------------------------------------------------------

def spent(trace: list[dict]) -> float:
    """Budget units a trace paid for: its reads and searches."""
    return float(sum(r["cost"] for r in trace if not r.get("refused")))


def call_of(trace: list[dict]) -> dict | None:
    """A step's submitted call, or None if it never submitted."""
    return next((r["args"] for r in trace if r["tool"] == "submit" and not r.get("refused")), None)


def notes_record(room: Path, trace: list[dict]) -> Record:
    """Spec §4: a fresh Deal Record from a session's last note per issue type. Chance 1 is a committed range [low,
    high]; any other note is an open issue, priced as the team prices one; an issue type with no note counts as no
    problem."""
    notes = {r["args"]["type"]: r["args"] for r in trace if r["tool"] == "note_issue" and not r.get("refused")}
    rec = Record(load_face(room))
    rec.apply([{"type": t, "kind": "range", "low": float(n["low"]), "high": float(n["high"]), "quotes": []}
               for t, n in notes.items() if n["chance"] >= 1])
    rec.plan([{"type": t, "name": n.get("name", ""), "chance": float(n["chance"]), "low": float(n["low"]),
               "high": float(n["high"]), "docs": list(n.get("docs", []))}
              for t, n in notes.items() if n["chance"] < 1])
    return rec


def engine_call(room: Path, trace: list[dict]) -> dict | None:
    """The engine's call on a session's notes; None if the session never submitted (a missing call, spec §4)."""
    if call_of(trace) is None:
        return None
    go, wa = notes_record(room, trace).decide()
    return {"go": bool(go), "walk_away": float(wa), "reason": "the engine, on the analyst's notes"}


def engine_view(trace: list[dict], call: dict | None) -> str:
    """An engine-priced analyst as the referee sees it: its notes and the engine's call, not its own submitted one."""
    lines = referee.note_lines(trace)
    lines.append(f"Call (the valuation engine's, priced from these notes): {'GO' if call['go'] else 'NO-GO'}, "
                 f"walk-away ${call['walk_away']:,.1f}M." if call else
                 "Call: none; the analyst's run ended without submitting one.")
    return "\n".join(lines)


# --- the steps (module functions, so tests can replace them) -------------------------------------------------------

def draft(room: Path, budget: float, *, trace: Path, router: bool = False, **kw) -> dict:
    """Single Claude, unchanged, at this budget (C's drafter, A's scouts); `router` is A's Scout 2."""
    return solver.solve(room, budget, trace, router, **kw)


def second_prompts(room: Path, read: list[str]) -> tuple[str, str]:
    index = json.loads((room / "index.json").read_text())
    titles = {d["id"]: d["title"] for d in index["documents"]}
    docs = "\n\n".join(f"## {titles[d]} ({d})\n\n{(room / f'{d}.md').read_text()}" for d in titles if d in set(read))
    user = f"{index['teaser']}\n\n# Documents\n\n{docs}\n\nNote every kind of issue, then submit."
    return SECOND_SYSTEM.format(guide=GUIDE), user


def second(room: Path, read: list[str], *, trace: Path, **kw) -> dict:
    """C's second opinion: the documents the drafter read, never its notes or call; no reading budget."""
    system, user = second_prompts(room, read)
    return run_session(room, 0, trace, user, system, ["note_issue", "submit"], [], **kw)


def judge(room: Path, views: list[str], read: list[str], deal: str, left: float, *, trace: Path, **kw) -> dict:
    return referee.judge_reading(room, views, read, deal, left, trace, **kw)


def step(name: str, path: Path, fn, *args, **kw) -> tuple[list[dict], dict | None]:
    """One step: its rows tagged with the step, and its CLI result (None after a timeout, a missing call)."""
    path.unlink(missing_ok=True)
    try:
        cli = fn(*args, trace=path, **kw)
    except RunTimeout:
        cli = None
    rows = referee.rows(path) if path.exists() else []
    if cli is not None and not rows:
        raise LLMUnavailable(f"{name}: the tool server never ran (no trace)")
    return [r | {"step": name} for r in rows], cli


# --- the designs ---------------------------------------------------------------------------------------------------

def combine(trace: list[dict], clis: list[dict | None], final: dict | None) -> tuple[list[dict], dict]:
    """One trace for scoring: the steps' own submits renamed step_submit, then the design's final submit (none if the
    referee gave no call, so scoring treats the deal as unanswered); and the steps' CLI results summed."""
    out = [r | {"tool": "step_submit"} if r["tool"] == "submit" else r for r in trace]
    if final is not None:
        out.append({"i": 0, "tool": "submit", "args": final, "cost": 0.0, "refused": False, "error": None,
                    "step": "final"})
    ok = [c for c in clis if c]
    cli = {"usage": {k: sum(int(c.get("usage", {}).get(k, 0)) for c in ok) for k in USAGE},
           "total_cost_usd": sum(c.get("total_cost_usd") or 0 for c in ok),
           "num_turns": sum(c.get("num_turns") or 0 for c in ok),
           "duration_ms": sum(c.get("duration_ms") or 0 for c in ok),
           "modelUsage": {m: v for c in ok for m, v in c.get("modelUsage", {}).items()},
           "sessions": len(clis), "timeouts": sum(c is None for c in clis)}
    return out, cli


def settle(room: Path, budget: float, deal: str, out: Path, steps: list[tuple[list[dict], dict | None]],
           a: dict | None, b: dict | None, views: list[str], read: list[str], **kw) -> tuple[list[dict], dict]:
    """Spec §2-3: an agreement stands, with the first analyst's walk-away; a dispute or a missing call goes to the
    referee, who may read with what is left of the budget."""
    trace = [r for rows, _ in steps for r in rows]
    clis = [cli for _, cli in steps]
    agree = a is not None and b is not None and a["go"] == b["go"]
    if agree:
        final = {"go": a["go"], "walk_away": a["walk_away"], "reason": "the analysts agree"}
    else:
        left = max(0.0, budget - spent(trace))
        rows, cli = step("referee", out.with_suffix(".referee.jsonl"), judge, room, views, read, deal, left, **kw)
        trace, final = trace + rows, call_of(rows)
        clis.append(cli)
    trace, cli = combine(trace, clis, final)
    return trace, cli | {"analysts": [a, b], "disputed": not agree}


def run_c(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict]:
    """Design C (spec §2) on one deal: (combined trace, combined CLI result)."""
    drafted = step("draft", out.with_suffix(".draft.jsonl"), draft, room, DRAFT_SHARE * budget, **kw)
    read = referee.opened(drafted[0])
    seconded = step("second", out.with_suffix(".second.jsonl"), second, room, read, **kw)
    a, b = call_of(drafted[0]), engine_call(room, seconded[0])
    views = [referee.solo_view(drafted[0]), engine_view(seconded[0], b)]
    return settle(room, budget, deal, out, [drafted, seconded], a, b, views, read, **kw)


def run_a(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict]:
    """Design A (spec §3) on one deal: (combined trace, combined CLI result)."""
    one = step("scout1", out.with_suffix(".scout1.jsonl"), draft, room, SCOUT_SHARE * budget, **kw)
    two = step("scout2", out.with_suffix(".scout2.jsonl"), draft, room, SCOUT_SHARE * budget, router=True, **kw)
    a, b = call_of(one[0]), engine_call(room, two[0])
    views = [referee.solo_view(one[0]), engine_view(two[0], b)]
    read = list(dict.fromkeys(referee.opened(one[0]) + referee.opened(two[0])))
    return settle(room, budget, deal, out, [one, two], a, b, views, read, **kw)


RUN = {"recon_c": run_c, "recon_a": run_a}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/bench/test_recon.py`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/recon.py tests/bench/test_recon.py
git commit -m "feat(bench): recon pilot designs C and A: steps, the engine call on notes, disputes, the combined trace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The runner and the fixed decision rule

**Files:**
- Modify: `acqlab/bench/recon.py` (append the section below at the end of the file)
- Test: `tests/bench/test_recon.py` (append five tests)

**Interfaces:**
- Consumes:
  - From Task 2: `RUN`, `DESIGNS`, `TIE`, `call_of` and `spent`, plus `cli["disputed"]`, `cli["analysts"]` and `cli["timeouts"]`.
  - `pilot.score(key, system, trace, cli, status)` and `AnswerKey`.
- Produces:
  - `recon.run(data, designs, split="test", **kw) -> list[dict]`. Each row is `pilot.score`'s plus `rep`, `budget`, `spent`, `disputed`, `analysts` and `timeouts`, written to `<data>/runs/<design>/<deal>.json`, with the combined trace at `<deal>.trace.jsonl`.
  - `recon.pick(by: dict[str, dict[str, dict]]) -> dict`, with keys `n`, `mechanics`, `regret`, `cost`, `tied`, `chosen` and `go`.
  - `recon.main(argv) -> int`, with exit codes 0 done, 1 unknown design, 2 Claude stopped, 3 refused.

- [ ] **Step 1: Write the failing tests** (append to `tests/bench/test_recon.py`)

```python
def test_the_runner_refuses_without_confirmation_and_rejects_unknown_designs(tmp_path):
    assert recon.main(["--data", str(tmp_path)]) == 3
    assert recon.main(["--data", str(tmp_path), "--designs", "recon_b", "--confirm-claude"]) == 1


def test_both_designs_run_end_to_end_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    engine = recon.engine_call  # every engine-priced call flipped, so every deal reaches the referee's real session
    monkeypatch.setattr(recon, "engine_call", lambda room, trace: c and c | {"go": not c["go"]}
                        if (c := engine(room, trace)) else c)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    rows = recon.run(d, list(recon.DESIGNS), split="dev", claude=fake_claude)
    assert len(rows) == 2 * len(json.loads((d / "splits.json").read_text())["dev"])
    for r in rows:
        trace = recon.referee.rows(d / "runs" / r["system"] / f"{r['deal']}.trace.jsonl")
        assert r["answered"] and r["spent"] <= r["budget"]
        assert r["disputed"] and r["sessions"] == 3 and any(x["step"] == "referee" for x in trace)
    assert recon.run(d, list(recon.DESIGNS), split="dev", claude=fake_claude) == []  # finished runs are skipped


def test_no_step_reads_the_answer_key():
    source = Path(recon.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))


def test_the_pick_follows_the_fixed_rules():
    def rows(regret, cost=0.2, answered=40, spent=10.0):
        return {f"d{i}": {"regret": regret, "cost_usd": cost, "answered": i < answered, "spent": spent,
                          "budget": 20.0} for i in range(40)}

    base = {"s1b": rows(0.02), "s4": rows(0.015)}
    p = recon.pick(base | {"recon_c": rows(0.010), "recon_a": rows(0.012)})
    assert p["chosen"] == "recon_c" and p["go"] and not p["tied"]
    p = recon.pick(base | {"recon_c": rows(0.010), "recon_a": rows(0.0104, cost=0.1)})
    assert p["tied"] and p["chosen"] == "recon_a"  # within 0.0005: the cheaper one
    assert not recon.pick(base | {"recon_c": rows(0.016), "recon_a": rows(0.017)})["go"]  # not below the team
    p = recon.pick(base | {"recon_c": rows(0.010, answered=37), "recon_a": rows(0.012)})
    assert not p["mechanics"]["recon_c"]["passes"] and not p["go"]  # fewer than 38 of 40 answered
    p = recon.pick(base | {"recon_c": rows(0.010), "recon_a": rows(0.012, spent=20.5)})
    assert p["mechanics"]["recon_a"]["over_budget"] == 40 and not p["go"]


def test_claude_stopping_mid_deal_writes_no_row_and_exits_2(data, tmp_path, monkeypatch):
    d = tmp_path / "d"
    shutil.copytree(data, d)

    def stop(*a, **kw):
        raise recon.LLMUnavailable("usage limit")

    monkeypatch.setitem(recon.RUN, "recon_c", stop)
    assert recon.main(["--data", str(d), "--designs", "recon_c", "--split", "dev", "--confirm-claude"]) == 2
    assert not list((d / "runs" / "recon_c").glob("*.json"))  # a rerun redoes the whole deal
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/bench/test_recon.py`
Expected: 4 failed with `AttributeError: module 'acqlab.bench.recon' has no attribute 'main'` (or `'run'` or `'pick'`), and 11 passed (`test_no_step_reads_the_answer_key` passes already).

- [ ] **Step 3: Append to `acqlab/bench/recon.py`:**

```python
# --- the runner and the decision rule ------------------------------------------------------------------------------

def run(data: Path, designs: list[str], split: str = "test", **kw) -> list[dict]:
    """Every missing run of these designs on the split's deals; raises LLMUnavailable to stop the batch."""
    from acqlab.bench.pilot import score  # scoring reads the answer key, after the final call
    from acqlab.generator.batch import AnswerKey
    out = []
    for deal in json.loads((data / "splits.json").read_text())[split]:
        room = data / "deals" / deal / "room"
        budget = float(json.loads((room / "index.json").read_text())["default_budget"])
        for design in designs:
            path = data / "runs" / design / f"{deal}.json"
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            trace, cli = RUN[design](room, budget, deal, path, **kw)
            path.with_suffix(".trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
            key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
            assert key.budget == budget, f"{deal}: the room's budget is not the answer key's"
            row = score(key, design, trace, cli, "ok" if call_of(trace) else "no_call") | {
                "rep": 0, "budget": budget, "spent": spent(trace), "disputed": cli["disputed"],
                "analysts": cli["analysts"], "timeouts": cli["timeouts"]}
            path.write_text(json.dumps(row, indent=2))
            out.append(row)
            print(f"{design} {deal}: disputed={row['disputed']} correct={row['correct']} regret {row['regret']:.3f} "
                  f"pages {row['pages']:g}/{budget:g}")
    return out


def pick(by: dict[str, dict[str, dict]]) -> dict:
    """Spec §5 on the finished pilot (system -> deal -> row): each design's mechanics, the pick, and go or stop."""
    n = len(by["s1b"])
    mech = {}
    for d in DESIGNS:
        rs = list(by[d].values())
        m = {"n": len(rs), "answered": sum(r["answered"] for r in rs),
             "over_budget": sum(r["spent"] > r["budget"] + 1e-9 for r in rs)}
        mech[d] = m | {"passes": m["n"] == n and m["answered"] >= math.ceil(0.95 * n) and m["over_budget"] == 0}
    regret = {s: sum(r["regret"] for r in rows.values()) / len(rows) for s, rows in by.items()}
    cost = {d: sum(r["cost_usd"] or 0 for r in by[d].values()) / len(by[d]) for d in DESIGNS}
    tied = abs(regret[DESIGNS[0]] - regret[DESIGNS[1]]) <= TIE
    chosen = min(DESIGNS, key=lambda d: cost[d] if tied else regret[d])
    go = (all(m["passes"] for m in mech.values()) and regret[chosen] < regret["s1b"]
          and regret[chosen] < regret["s4"])
    return {"n": n, "mechanics": mech, "regret": regret, "cost": cost, "tied": tied, "chosen": chosen, "go": go}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--designs", default=",".join(DESIGNS))
    ap.add_argument("--split", default="test")
    ap.add_argument("--confirm-claude", action="store_true", help="required: this spends real Claude usage")
    args = ap.parse_args(argv)
    designs = [d for d in args.designs.split(",") if d]
    if bad := [d for d in designs if d not in RUN]:
        print(f"Unknown designs {bad}: choose from {list(RUN)}")
        return 1
    if not args.confirm_claude:
        print("Refusing: pass --confirm-claude to spend real Claude usage")
        return 3
    try:
        run(args.data, designs, args.split)
    except LLMUnavailable as e:
        print(f"Claude stopped: {e}. Rerun to resume.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/bench/test_recon.py tests/bench/test_referee.py`
Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/recon.py tests/bench/test_recon.py
git commit -m "feat(bench): the recon pilot runner and its fixed decision rule

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The analysis script

**Files:**
- Create: `scripts/recon_pilot.py`
- Test: `tests/bench/test_recon.py` (append one test)

**Interfaces:**
- Consumes:
  - From Task 3: `recon.pick`, `recon.run` and the row fields.
  - `analysis.compare(a, b)`, `simrun.deals_needed(gap, sd, power)`, `referee.opened` and `referee.rows`.
- Produces:
  - `analyse(data: Path) -> dict`, with keys `deals`, `pick`, `systems`, `versus`, `designs` and `sizing`.
  - `main(argv)`: `--data`, `--out`. It refuses to overwrite (exit 1).

- [ ] **Step 1: Write the failing test** (append to `tests/bench/test_recon.py`)

```python
def test_the_analysis_script_reads_a_finished_pilot(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    d = tmp_path / "d"
    shutil.copytree(data, d)
    recon.run(d, list(recon.DESIGNS), split="dev", claude=fake_claude)
    for s in ("s1b", "s4"):  # stand-ins for the baselines: the design's own runs
        shutil.copytree(d / "runs" / "recon_c", d / "runs" / s)
    script = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "recon_pilot.py"))
    out = script["analyse"](d)
    assert out["deals"] == 2 and out["pick"]["chosen"] in recon.DESIGNS and not out["pick"]["go"]
    assert set(out["systems"]) == {"s1b", "s4", *recon.DESIGNS} and out["versus"]["recon_c"]["s1b"]["n"] == 2
    assert "scout1_real_reached" in out["designs"]["recon_a"] and "scout1_real_reached" not in out["designs"]["recon_c"]
    assert "nothing to size" in out["sizing"]["note"]
    assert script["main"](["--data", str(d), "--out", str(tmp_path / "x.json")]) == 0
    assert script["main"](["--data", str(d), "--out", str(tmp_path / "x.json")]) == 1  # never overwrites
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/bench/test_recon.py -k analysis_script`
Expected: 1 failed, with `FileNotFoundError` (or `No such file`) for `scripts/recon_pilot.py`.

- [ ] **Step 3: Create `scripts/recon_pilot.py`:**

```python
"""The reconciliation pilot's analysis (spec docs/superpowers/specs/2026-10-06-recon-pilot-design.md §5): the fixed
pick, each design against single Claude and the team, and the C and A measures. Reads finished runs and answer keys;
never calls a model. From the repository root:

  .venv/bin/python scripts/recon_pilot.py --data data/pilot-r2 --out docs/results/recon-pilot.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.bench import analysis, recon, simrun
from acqlab.bench.referee import opened, rows as trace_rows
from acqlab.generator.batch import AnswerKey

SYSTEMS = ("s1b", "s4", *recon.DESIGNS)


def load(data: Path, system: str) -> dict[str, dict]:
    """deal -> row, first runs only (a repeat is <deal>.r<k>.json)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((data / "runs" / system).glob("*.json"))
            if "." not in p.stem}


def real_docs(key: AnswerKey) -> set[str]:
    """The documents that settle a real fact (amount > 0): the last of its evidence."""
    facts = {f.trap: f for f in key.truth.facts}
    return {e.docs[-1] for e in key.evidence if facts[e.trap].amount > 0}


def reached(key: AnswerKey, docs: list[str]) -> float | None:
    """Share of the real facts settled by these documents; None if the deal has none."""
    facts = {f.trap: f for f in key.truth.facts}
    real = [e for e in key.evidence if facts[e.trap].amount > 0]
    return float(np.mean([e.docs[-1] in set(docs) for e in real])) if real else None


def summary(rows: dict, traces: dict, keys: dict) -> dict:
    rs = list(rows.values())
    reach = [x for d in rows if (x := reached(keys[d], opened(traces[d]))) is not None]
    return {"n": len(rs), "regret": float(np.mean([r["regret"] for r in rs])),
            "correct": float(np.mean([r["correct"] for r in rs])),
            "false_go": sum(r["go"] and not r["correct"] for r in rs),
            "false_nogo": sum(not r["go"] and not r["correct"] for r in rs),
            "pages": float(np.mean([r["pages"] for r in rs])), "decoy_pages": float(np.mean([r["decoy_pages"] for r in rs])),
            "real_reached": float(np.mean(reach)) if reach else None,
            "cost": float(np.mean([r["cost_usd"] or 0 for r in rs])),
            "sessions": float(np.mean([r["sessions"] for r in rs]))}


def won_lost_tied(a: dict, b: dict) -> list[int]:
    diff = [a[d]["regret"] - b[d]["regret"] for d in sorted(set(a) & set(b))]
    return [sum(x < -1e-12 for x in diff), sum(x > 1e-12 for x in diff), sum(abs(x) <= 1e-12 for x in diff)]


def design_stats(rows: dict, traces: dict, keys: dict, pages: dict) -> dict:
    """Disputes, overrules, the referee's own reads; for A, the scouts' overlap and reach."""
    disputed = [d for d, r in rows.items() if r["disputed"]]
    over, ref_pages, ref_found = [0, 0], [], 0
    for d in disputed:
        r = rows[d]
        for i, call in enumerate(r["analysts"]):
            over[i] += bool(r["answered"] and call is not None and call["go"] != r["go"])
        paid = [x for x in traces[d] if x.get("step") == "referee" and x["tool"] == "open_document"
                and not x["refused"] and x["cost"] > 0]
        ref_pages.append(sum(x["cost"] for x in paid))
        ref_found += bool({x["args"]["doc_id"] for x in paid} & real_docs(keys[d]))
    out = {"disputes": len(disputed), "dispute_rate": len(disputed) / len(rows),
           "overruled_analyst_1": over[0], "overruled_analyst_2": over[1],
           "referee_new_pages_mean": float(np.mean(ref_pages)) if ref_pages else 0.0,
           "referee_reads_reached_a_real_fact": ref_found}
    if any(x.get("step") == "scout1" for t in traces.values() for x in t):
        scouts = {d: [opened([x for x in traces[d] if x.get("step") == s]) for s in ("scout1", "scout2")]
                  for d in rows}
        out["overlap_pages_mean"] = float(np.mean([sum(pages[d][x] for x in set(a) & set(b))
                                                   for d, (a, b) in scouts.items()]))
        for i, label in enumerate(("scout1", "scout2")):
            r = [x for d, s in scouts.items() if (x := reached(keys[d], s[i])) is not None]
            out[f"{label}_real_reached"] = float(np.mean(r)) if r else None
        r = [x for d, s in scouts.items() if (x := reached(keys[d], s[0] + s[1])) is not None]
        out["scouts_together_real_reached"] = float(np.mean(r)) if r else None
    return out


def sizing(chosen: dict, s1b: dict) -> dict:
    """Spec §5.5: deals for 80% and 90% power against single Claude, at the pilot's gap and at half of it."""
    ds = sorted(set(chosen) & set(s1b))
    diff = np.array([chosen[d]["regret"] - s1b[d]["regret"] for d in ds])
    gap, sd = float(diff.mean()), float(diff.std(ddof=1))
    if gap >= 0 or sd == 0:
        return {"gap": gap, "sd": sd, "note": "no gain over single Claude, so nothing to size"}
    return {"gap": gap, "sd": sd} | {label: {"power_80": simrun.deals_needed(g, sd, 0.8),
                                             "power_90": simrun.deals_needed(g, sd, 0.9)}
                                     for label, g in (("full", -gap), ("half", -gap / 2))}


def analyse(data: Path) -> dict:
    by = {s: load(data, s) for s in SYSTEMS}
    deals = sorted(set().union(*by.values()))
    keys = {d: AnswerKey.model_validate_json((data / "truth" / f"{d}.json").read_text()) for d in deals}
    pages = {d: {x["id"]: x["pages"] for x in json.loads((data / "deals" / d / "room" / "index.json").read_text())
                 ["documents"]} for d in deals}
    traces = {s: {d: trace_rows(data / "runs" / s / f"{d}.trace.jsonl") for d in by[s]} for s in SYSTEMS}
    out = {"deals": len(deals), "pick": recon.pick(by),
           "systems": {s: summary(by[s], traces[s], keys) for s in SYSTEMS},
           "versus": {d: {b: analysis.compare(by[d], by[b]) | {"won_lost_tied": won_lost_tied(by[d], by[b])}
                          for b in ("s1b", "s4")} for d in recon.DESIGNS},
           "designs": {d: design_stats(by[d], traces[d], keys, pages) for d in recon.DESIGNS}}
    out["sizing"] = sizing(by[out["pick"]["chosen"]], by["s1b"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot, like the Plan 6 analysis: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    out = analyse(args.data)
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["pick"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 395 passed. This includes `test_s4_s_files_are_unchanged_from_the_freeze_tag`.

- [ ] **Step 5: Commit**

```bash
git add scripts/recon_pilot.py tests/bench/test_recon.py
git commit -m "feat: the recon pilot analysis script (spec §5)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The 40 fresh deals (no model calls)

**Files:**
- Create: `data/pilot-r2/` (git-ignored; nothing to commit)

- [ ] **Step 1: Check the seeds against every used seed**

Run: `.venv/bin/python -m acqlab.bench.testset seeds --base 9000000 --n 40 --roots data/cal-r2 data/heldout-r2 data/test-r2 data/sim-r2`
Expected: a line ending `clashes with base 9000000: none`, and exit code 0. If there is a clash, stop and report it; do not pick another base without the controller's ruling.

- [ ] **Step 2: Generate the deals**

Run: `.venv/bin/python -m acqlab.generator.batch --out data/pilot-r2 --dev 0 --test 40 --hand 0 --showcase 0 --seed 9000000 --profile r2`
Expected: it finishes without listing batch problems.

- [ ] **Step 3: Verify them**

Run:
```bash
.venv/bin/python -c "
import json; from pathlib import Path
d=Path('data/pilot-r2'); s=json.loads((d/'splits.json').read_text())
print(len(s['test']), len(list((d/'truth').glob('*.json'))), sorted({json.loads((d/'deals'/x/'room'/'index.json').read_text())['default_budget'] for x in s['test']})[:3])"
```
Expected: `40 40 [...]`, with budgets around 20–25.

- [ ] **Step 4: Stop for the user's OK**

Report: the deals are ready, and the cost estimate is about $45 (`s4` about $21, `s1b` about $5, C and A about $10 each). Ask the user to OK the real Claude runs. **Do not continue to Task 6 without an explicit yes in chat.**

---

### Task 6: Run the pilot and write it up (only after the user's OK)

**Files:**
- Create: `docs/results/recon-pilot.json` (written by the script), `docs/results/recon-pilot.md`
- Modify: `docs/HANDOFF.md` ("Resume here", the research-track bullet)

- [ ] **Step 1: Check the CLI version**

Run: `claude --version`
Expected: 2.1.291 or newer. If it is older, stop and ask the user before updating.

- [ ] **Step 2: Run the two baselines** (real Claude calls; keeps the Mac awake; a rerun resumes)

Run: `caffeinate -i .venv/bin/python -m acqlab.bench.pilot --data data/pilot-r2 --split test --n 40 --systems s1b,s4 --confirm-claude`
Expected: exit 0, with 40 rows each in `data/pilot-r2/runs/s1b` and `data/pilot-r2/runs/s4`. On exit 2 (Claude stopped), report it and rerun the same command later.

- [ ] **Step 3: Run designs C and A**

Run: `caffeinate -i .venv/bin/python -m acqlab.bench.recon --data data/pilot-r2 --confirm-claude`
Expected: exit 0, with 40 rows each in `data/pilot-r2/runs/recon_c` and `data/pilot-r2/runs/recon_a`. On exit 2, rerun later.

- [ ] **Step 4: Analyse, once**

Run: `.venv/bin/python scripts/recon_pilot.py --data data/pilot-r2 --out docs/results/recon-pilot.json`
Expected: it prints the pick: `mechanics`, `regret`, `chosen` and `go`.

- [ ] **Step 5: Write `docs/results/recon-pilot.md` from the JSON**

Mark the page exploratory, and cover:
- **The setup:** the deals, the seed, the CLI version and the cost.
- **The mechanics check.**
- **A table of the four systems:** regret, correct, false GO and false NO-GO, pages, real facts reached, cost and sessions.
- **Each design against `s1b` and `s4`:** the difference, its CI, and deals won, lost and tied.
- **The C and A measures:**
  - dispute rate;
  - how often the referee overrules each analyst;
  - the referee's new pages and the real facts they reached;
  - A's overlap and per-scout reach.
- **The pick and the go or stop verdict, under the fixed rules.**
- **Sizing.**
- **Limits:** 40 deals and one run each, so a go earns only a properly sized test, which needs its own spec and the user's OK.

- [ ] **Step 6: Update `docs/HANDOFF.md` and commit**

Replace the research-track bullet's "Next:" sentence with the pilot's verdict and the next step.

```bash
git add docs/results/recon-pilot.json docs/results/recon-pilot.md docs/HANDOFF.md
git commit -m "docs: the recon pilot's results (designs C and A at the same page budget)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

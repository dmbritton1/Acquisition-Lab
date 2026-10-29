# The Haiku Team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** build the runner, the lean pipeline, the practice scorecard and the one-shot final analysis for the Haiku
team, plus the 30 practice deals and their base rates, so the paid phases (smoke test, tuning, final test) can start.

**Architecture:** one new module, `acqlab/bench/haiku.py`, runs the frozen systems on Haiku by swapping
`solver.command` at run time (never editing `acqlab/agents`), holds a registry of candidates (`haiku_solo`,
`haiku_team`, `haiku_lean`) and a runner that refuses the held-out sets before the freeze. Two scripts read finished
runs: `scripts/haiku_practice.py` (a scorecard that writes nothing) and `scripts/haiku_team.py` (the one-shot final
analysis). Everything reuses the debate/recon pilots' parts (`recon.step`, `recon.combine`, `recon.notes_record`,
`pilot.score`, `analysis.compare`, `upside_pilot.stats`, `debate_pilot.versus`).

**Tech Stack:** Python 3.12, pytest, numpy; the Claude Code CLI (`claude -p`) via `acqlab.agents.solver`; the fake
`claude` in `tests/agents/fake_claude.py` for tests.

**Spec:** `docs/superpowers/specs/2026-10-10-haiku-team-design.md`

## Global Constraints

- `acqlab/agents` and `acqlab/routers` stay byte-identical to tag `s4-frozen-plan5` (`git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers` prints nothing). The model is switched at run time, never by editing them.
- Every new session uses model `claude-haiku-5-5`; Opus baselines are `claude-opus-5-5`.
- The held-out sets are `data/test-r2` and `data/pilot-r2u`; the practice sets are `data/cal-r2`, `data/heldout-r2` and `data/practice-r2u` (dev split).
- No step reads the answer key (`truth/`); scoring does, after the final call. Base rates are the only other use.
- No real Claude call in this plan. Tests use the fake `claude`. Paid runs come after the plan, each with the user's OK.
- Run tests with `.venv/bin/python -m pytest` from the repository root. The full suite takes about 9 minutes; it has 451 tests before this plan.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Data under `data/` is git-ignored; never `git add` it.

## Review Focus

1. **The real CLI's `modelUsage` on Haiku may list more than one model** (a helper model): rows' `models` would not equal `["claude-haiku-5-5"]` and the final analysis would refuse. No fake can show this; the smoke test (Runbook step 2) checks every row's `models` before any practice round.
2. **A held-out set reached under another name** (a copy, a symlink, a trailing slash): the runner must still refuse it. Pinned in Task 1: symlinks and slashes resolve to the real name; a copy keeps its `test` split, which is refused on its own.
3. **The model switch leaking past a run** (an exception mid-run leaving `solver.command` on Haiku, so a later Opus run is silently Haiku): pinned in Task 1 (`test_on_haiku_restores_opus_after_an_error`).
4. **A pricer that times out or never submits**, or all of them: the deal must be unanswered, not crash or be scored on a partial vote's wrong side. Pinned in Task 2 (missing calls, a tie is NO-GO, no calls → unanswered).
5. **An unfinished practice round deciding a keep**: the keep rule must say no while any run is missing. Pinned in Task 3.

---

### Task 1: The model switch, the solo and team candidates, and the runner

**Files:**
- Create: `acqlab/bench/haiku.py`
- Test: `tests/bench/test_haiku.py`

**Interfaces:**
- Consumes (existing): `solver.command(claude, prompt, system, mcp_config, tools) -> list[str]` (contains `"--model", MODEL`); `solver.solve`; `panel.solve(room, budget, trace, cfg, *, claude=None)`; `panel.STAGES["s4"]`; `recon.step(name, path, fn, *args, **kw) -> (rows, cli | None)`; `recon.draft(room, budget, *, trace, router=False, **kw)`; `recon.call_of(trace) -> dict | None`; `recon.spent(trace) -> float`; `pilot.score(key, system, trace, cli, status) -> dict`; `prompts.system_prompt(router, unbudgeted=False)`; `panel_prompts.LEAD/INVESTIGATOR/CHALLENGER`.
- Produces: `haiku.MODEL = "claude-haiku-5-5"`; `haiku.TEST_SETS = ("test-r2", "pilot-r2u")`; `haiku.PRACTICE = ("cal-r2", "heldout-r2", "practice-r2u")`; `haiku.FINAL: str | None = None`; `class Refused(Exception)`; `on_haiku(effort: str | None = None)` (context manager); `run_solo(room, budget, deal, out, **kw)` and `run_team(...)` → `(trace, cli | None)`; `@dataclass Candidate(run, prompts: tuple[str, ...], effort=None, settings=dict)`; `CANDIDATES: dict[str, Candidate]`; `prompt_sha(name) -> str`; `refuse(data, systems, split, final)`; `run(data, systems, split="dev", deals=None, final=False, **kw) -> list[dict]`; `main(argv) -> int`. Each row adds `rep`, `budget`, `spent`, `calls`, `effort`, `settings`, `prompts` to `pilot.score`'s fields.

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_haiku.py`:

```python
import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.agents.solver import RunTimeout
from acqlab.bench import haiku


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


@pytest.fixture
def docs(room):
    return [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]]


def _argv(fake_claude, room, tmp_path, effort=None):
    """The argv one solver.solve call (under on_haiku unless effort is False) hands the fake claude."""
    if effort is False:
        solver.solve(room, 5, tmp_path / "t.jsonl", False, claude=fake_claude)
    else:
        with haiku.on_haiku(effort):
            solver.solve(room, 5, tmp_path / "t.jsonl", False, claude=fake_claude)
    return json.loads((tmp_path / "args.json").read_text())["argv"]


# --- the model switch ----------------------------------------------------------------------------------------------

def test_on_haiku_runs_every_session_on_haiku_and_restores_opus(fake_claude, room, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    argv = _argv(fake_claude, room, tmp_path, None)
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5" and "--effort" not in argv
    argv = _argv(fake_claude, room, tmp_path, "low")
    assert argv[argv.index("--effort") + 1] == "low"
    argv = _argv(fake_claude, room, tmp_path, False)
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5" and "--effort" not in argv


def test_on_haiku_restores_opus_after_an_error():
    original = solver.command
    with pytest.raises(RuntimeError):
        with haiku.on_haiku():
            assert solver.command is not original
            raise RuntimeError("boom")
    assert solver.command is original


# --- the runner and its refusals -----------------------------------------------------------------------------------

def test_the_held_out_sets_are_refused_before_the_freeze(tmp_path, monkeypatch):
    for name in haiku.TEST_SETS:
        with pytest.raises(haiku.Refused, match="held out"):
            haiku.run(tmp_path / name, ["haiku_solo"], split="dev")
    (tmp_path / "test-r2").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "test-r2")
    for path in (tmp_path / "alias", Path(f"{tmp_path / 'test-r2'}/")):
        with pytest.raises(haiku.Refused, match="held out"):
            haiku.run(path, ["haiku_solo"], split="dev")
    with pytest.raises(haiku.Refused, match="held out"):
        haiku.run(tmp_path / "cal-r2", ["haiku_solo"], split="test")  # a copy under another name keeps its split
    with pytest.raises(haiku.Refused, match="no frozen winner"):
        haiku.run(tmp_path / "test-r2", ["haiku_solo"], split="test", final=True)
    monkeypatch.setattr(haiku, "FINAL", "haiku_team")
    with pytest.raises(haiku.Refused, match="haiku_solo, haiku_team and haiku_team"):
        haiku.run(tmp_path / "test-r2", ["haiku_team", "haiku_other"], split="test", final=True)
    assert haiku.main(["--data", str(tmp_path / "pilot-r2u"), "--split", "test", "--confirm-claude"]) == 3


def test_the_runner_refuses_without_confirmation_and_rejects_unknown_systems(tmp_path):
    assert haiku.main(["--data", str(tmp_path / "cal-r2")]) == 3
    assert haiku.main(["--data", str(tmp_path), "--systems", "haiku_x", "--confirm-claude"]) == 1


def test_claude_stopping_mid_deal_writes_no_row_and_exits_2(data, tmp_path, monkeypatch):
    d = tmp_path / "d"
    shutil.copytree(data, d)

    def stop(*a, **kw):
        raise haiku.LLMUnavailable("usage limit")

    monkeypatch.setitem(haiku.CANDIDATES, "haiku_solo", haiku.Candidate(stop, ()))
    assert haiku.main(["--data", str(d), "--systems", "haiku_solo", "--confirm-claude"]) == 2
    assert not list((d / "runs" / "haiku_solo").glob("*.json"))


def test_solo_and_team_run_end_to_end_on_haiku_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    d = tmp_path / "d"
    shutil.copytree(data, d)
    rows = haiku.run(d, ["haiku_solo", "haiku_team"], deals=["dev-001"], claude=fake_claude)
    assert [(r["system"], r["deal"]) for r in rows] == [("haiku_solo", "dev-001"), ("haiku_team", "dev-001")]
    for r in rows:
        assert r["answered"] and r["status"] == "ok" and r["spent"] <= r["budget"] + 1e-9
        assert r["prompts"] == haiku.prompt_sha(r["system"]) and r["effort"] is None
    assert rows[0]["sessions"] == 1 and rows[1]["sessions"] > 1  # the team's own session count is kept
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert solver.command.__module__ == "acqlab.agents.solver"  # restored
    assert haiku.run(d, ["haiku_solo", "haiku_team"], deals=["dev-001"], claude=fake_claude) == []


def test_a_timed_out_solo_run_is_scored_as_a_timeout(data, tmp_path, monkeypatch):
    def late(*a, trace, **kw):
        trace.write_text(json.dumps(_row("open_document", {"doc_id": "qoe"}, 3.0)) + "\n")
        raise RunTimeout("late")

    monkeypatch.setattr(haiku, "draft", late)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    [row] = haiku.run(d, ["haiku_solo"], deals=["dev-000"])
    assert row["status"] == "timeout" and not row["answered"] and row["pages"] == 3.0


def test_each_candidate_records_its_own_prompt_fingerprint():
    shas = {n: haiku.prompt_sha(n) for n in haiku.CANDIDATES}
    assert len(set(shas.values())) == len(shas) and all(len(s) == 64 for s in shas.values())


def test_no_step_reads_the_answer_key():
    source = Path(haiku.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku.py -q`
Expected: collection error, `ImportError: cannot import name 'haiku' from 'acqlab.bench'`.

- [ ] **Step 3: Write the module**

Create `acqlab/bench/haiku.py`:

```python
"""The Haiku team (spec docs/superpowers/specs/2026-10-10-haiku-team-design.md): buy/pass systems built from Claude
Haiku, tuned on practice deals and tested once on held-out deals against single Opus. The frozen code runs unchanged:
the model is switched at run time (on_haiku), never by editing acqlab/agents. No step reads the answer key; scoring
does, after the final call.

    uv run python -m acqlab.bench.haiku --data data/cal-r2 --systems haiku_solo,haiku_team --confirm-claude
    uv run python -m acqlab.bench.haiku --data data/test-r2 --split test --systems haiku_solo --final --confirm-claude

Runs go to <data>/runs/<system>/<deal>.json, the trace beside it (each step's own trace too); finished runs are
skipped. Exit codes: 0 done; 1 an unknown system; 2 Claude stopped (rerun later to resume); 3 refused (no
--confirm-claude, a held-out set before the freeze, or a system the final test does not run)."""
import argparse
import hashlib
import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from acqlab.agents import panel, panel_prompts, prompts, solver
from acqlab.bench.recon import call_of, draft, spent, step
from acqlab.llm import LLMUnavailable

MODEL = "claude-haiku-5-5"
TEST_SETS = ("test-r2", "pilot-r2u")  # spec §2: held out until the freeze
PRACTICE = ("cal-r2", "heldout-r2", "practice-r2u")  # spec §3: the 90 practice deals
FINAL: str | None = None  # the frozen winner, set at the freeze (spec §4); until then no held-out run is allowed


class Refused(Exception):
    """A run the spec forbids: a held-out set before the freeze, or a system the final test does not run."""


@contextmanager
def on_haiku(effort: str | None = None):
    """Every session started inside runs on Haiku (and at this effort level, if given), without editing the frozen
    solver: solver.run_session builds its command with solver.command, which is swapped here and restored after."""
    original = solver.command

    def command(*args, **kw):
        cmd = original(*args, **kw)
        cmd[cmd.index("--model") + 1] = MODEL
        return cmd + (["--effort", effort] if effort else [])

    solver.command = command
    try:
        yield
    finally:
        solver.command = original


# --- the candidates ------------------------------------------------------------------------------------------------

def team(room: Path, budget: float, *, trace: Path, **kw) -> dict:
    """The frozen team, unchanged (it skips a timed-out session itself)."""
    return panel.solve(room, budget, trace, panel.STAGES["s4"], **kw)


def run_solo(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict | None]:
    """Single Claude, unchanged. The CLI result is None after a timeout."""
    return step("solo", out.with_suffix(".solo.jsonl"), draft, room, budget, **kw)


def run_team(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict | None]:
    return step("team", out.with_suffix(".team.jsonl"), team, room, budget, **kw)


SOLO = (prompts.system_prompt(False),)
TEAM = (panel_prompts.LEAD, panel_prompts.INVESTIGATOR, panel_prompts.CHALLENGER)


@dataclass
class Candidate:
    run: Callable
    prompts: tuple[str, ...]  # the system prompts it uses, fingerprinted in every row
    effort: str | None = None
    settings: dict = field(default_factory=dict)  # passed to run


CANDIDATES = {
    "haiku_solo": Candidate(run_solo, SOLO),
    "haiku_team": Candidate(run_team, TEAM),
}


def prompt_sha(name: str) -> str:
    return hashlib.sha256("\x00".join(CANDIDATES[name].prompts).encode()).hexdigest()


# --- the runner ----------------------------------------------------------------------------------------------------

def refuse(data: Path, systems: list[str], split: str, final: bool) -> None:
    """Spec §2: the held-out sets run only in the final test, and the final test runs only the systems it compares."""
    if (data.resolve().name in TEST_SETS or split == "test") and not final:
        raise Refused(f"{data.name} ({split}) is held out for the final test; tuning never runs on it")
    if final:
        if FINAL is None:
            raise Refused("no frozen winner yet: haiku.FINAL is set at the freeze")
        if bad := [s for s in systems if s not in ("haiku_solo", "haiku_team", FINAL)]:
            raise Refused(f"the final test runs only haiku_solo, haiku_team and {FINAL}, not {bad}")


def run(data: Path, systems: list[str], split: str = "dev", deals: list[str] | None = None, final: bool = False,
        **kw) -> list[dict]:
    """Every missing run of these candidates on the split's deals (or just `deals`); raises LLMUnavailable to stop."""
    from acqlab.bench.pilot import score  # scoring reads the answer key, after the final call
    from acqlab.generator.batch import AnswerKey
    refuse(data, systems, split, final)
    out = []
    for deal in deals or json.loads((data / "splits.json").read_text())[split]:
        room = data / "deals" / deal / "room"
        budget = float(json.loads((room / "index.json").read_text())["default_budget"])
        for name in systems:
            path = data / "runs" / name / f"{deal}.json"
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            c = CANDIDATES[name]
            with on_haiku(c.effort):
                trace, cli = c.run(room, budget, deal, path, **c.settings, **kw)
            path.with_suffix(".trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
            key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
            assert key.budget == budget, f"{deal}: the room's budget is not the answer key's"
            status = "timeout" if cli is None else "ok" if call_of(trace) else "no_call"
            row = score(key, name, trace, cli, status) | {
                "rep": 0, "budget": budget, "spent": spent(trace), "calls": (cli or {}).get("calls"),
                "effort": c.effort, "settings": c.settings, "prompts": prompt_sha(name)}
            path.write_text(json.dumps(row, indent=2))
            out.append(row)
            print(f"{name} {deal}: answered={row['answered']} correct={row['correct']} regret {row['regret']:.3f} "
                  f"pages {row['pages']:g}/{budget:g} ${row['cost_usd'] or 0:.3f}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--systems", default="haiku_solo,haiku_team")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--deals", default="", help="comma-separated deal ids (default: the whole split)")
    ap.add_argument("--final", action="store_true", help="the final test on a held-out set (after the freeze)")
    ap.add_argument("--confirm-claude", action="store_true", help="required: this spends real Claude usage")
    args = ap.parse_args(argv)
    systems = [s for s in args.systems.split(",") if s]
    if bad := [s for s in systems if s not in CANDIDATES]:
        print(f"Unknown systems {bad}: choose from {list(CANDIDATES)}")
        return 1
    try:
        refuse(args.data, systems, args.split, args.final)
    except Refused as e:
        print(f"Refusing: {e}")
        return 3
    if not args.confirm_claude:
        print("Refusing: pass --confirm-claude to spend real Claude usage")
        return 3
    try:
        run(args.data, systems, args.split, [d for d in args.deals.split(",") if d] or None, args.final)
    except LLMUnavailable as e:
        print(f"Claude stopped: {e}. Rerun to resume.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Check the frozen files and commit**

Run: `git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers`
Expected: no output.

```bash
git add acqlab/bench/haiku.py tests/bench/test_haiku.py
git commit -m "feat: Haiku runner: the frozen solo and team on Haiku via a run-time model switch; held-out sets refused before the freeze

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The lean pipeline, calibrated pricing and base rates

**Files:**
- Modify: `acqlab/bench/haiku.py`
- Test: `tests/bench/test_haiku.py`

**Interfaces:**
- Consumes: Task 1's module; `recon.second(room, read, *, trace, **kw)` (budget 0, tools `note_issue`, `submit`); `recon.combine(trace, clis, final) -> (trace, cli)` (cli has `sessions`, `timeouts`); `recon.notes_record(room, trace) -> Record` (`Record.entries[type].chance`, `.known`; `Record.decide() -> (go, walk_away)`); `recon.SECOND_SYSTEM`; `referee.opened(trace) -> list[str]`; `acqlab.generator.traps.TRAPS`.
- Produces: `haiku.RATES` (path of `acqlab/bench/base_rates.json`); `load_rates() -> dict[str, float]`; `calibrated_record(room, trace, rates, w) -> Record`; `calibrated_call(room, trace, rates, w) -> dict | None`; `vote(calls) -> dict | None`; `run_lean(room, budget, deal, out, *, w, pricers, rates=None, **kw) -> (trace, cli)` with `cli["calls"] = {"reader": ..., "pricer1": ..., ...}`; `CANDIDATES["haiku_lean"]` with `settings={"w": 0.5, "pricers": 3}`; `base_rates(dirs: list[Path]) -> {"rates": {type: float}, "deals": ["<set>/<deal>", ...]}`; `main(["--base-rates"])` writes `RATES` from the three practice sets.

- [ ] **Step 1: Write the failing tests**

In `tests/bench/test_haiku.py`, replace the import block and helpers at the top (everything above `@pytest.fixture` / `def room`) with:

```python
import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.agents.solver import RunTimeout
from acqlab.bench import haiku, pilot
from acqlab.bench.recon import notes_record
from acqlab.generator.batch import AnswerKey

RATES = {"addback": 0.3, "debt_like": 0.2, "concentration": 0.4, "nwc": 0.1, "capex": 0.2}


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _note(trap, chance, low=0.0, high=4.0):
    return _row("note_issue", {"name": trap, "type": trap, "chance": chance, "low": low, "high": high, "docs": []})


def _submit(go=True, wa=100.0):
    return _row("submit", {"go": go, "walk_away": wa, "reason": "r"})
```

Then append to the end of the file:

```python


# --- the lean pipeline ---------------------------------------------------------------------------------------------

def test_open_chances_are_pulled_toward_the_base_rate_and_settled_issues_are_not(room):
    trace = [_note("nwc", 0.4), _note("addback", 1.0, 2.0, 2.0), _note("capex", 0.0), _submit()]
    rec = haiku.calibrated_record(room, trace, RATES, 0.5)
    assert rec.entries["nwc"].chance == pytest.approx(0.5 * 0.4 + 0.5 * 0.1)
    assert rec.entries["capex"].chance == pytest.approx(0.5 * 0.2)
    assert rec.entries["addback"].known == (2.0, 2.0)
    assert haiku.calibrated_record(room, trace, RATES, 1.0).decide() == notes_record(room, trace).decide()


def test_a_pricer_without_a_call_gives_no_engine_call(room):
    assert haiku.calibrated_call(room, [_note("nwc", 0.4)], RATES, 0.5) is None
    call = haiku.calibrated_call(room, [_note("nwc", 0.4), _submit(False, 1.0)], RATES, 0.5)
    go, wa = haiku.calibrated_record(room, [_note("nwc", 0.4)], RATES, 0.5).decide()
    assert call["go"] == go and call["walk_away"] == pytest.approx(wa)  # the engine's, not the pricer's own


def test_the_vote_is_the_majority_at_the_median_walk_away():
    def c(go, wa):
        return {"go": go, "walk_away": wa, "reason": ""}

    assert haiku.vote([c(True, 90.0), c(True, 120.0), c(False, 80.0)]) | {"reason": ""} == c(True, 90.0)
    assert haiku.vote([c(True, 90.0), None, c(False, 80.0)])["go"] is False  # a tie is NO-GO
    assert haiku.vote([None, None, None]) is None


@pytest.fixture
def fakes(monkeypatch):
    """The reader and pricers replaced by sessions that write a scripted trace (scripts[step]; none scripted = a
    timeout) and record their arguments (calls[step])."""
    f = {"scripts": {}, "calls": {}}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        f["calls"][name] = (args, kw)
        if name not in f["scripts"]:
            raise RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        return {"total_cost_usd": 0.01, "usage": {"output_tokens": 5}, "modelUsage": {"claude-haiku-5-5": {}}}

    monkeypatch.setattr(haiku, "draft", run)
    monkeypatch.setattr(haiku, "second", run)
    return f


def test_lean_reads_once_at_the_full_budget_and_each_pricer_sees_what_was_read(fakes, room, docs, data, tmp_path):
    reads = [_row("open_document", {"doc_id": d}, 4.0) for d in docs[:2]]
    fakes["scripts"] |= {"reader": [*reads, _submit(False)], "pricer1": [_note("nwc", 0.9), _submit()],
                         "pricer2": [_note("nwc", 0.0), _submit()], "pricer3": [_note("nwc", 0.0), _submit()]}
    trace, cli = haiku.run_lean(room, 20.0, "dev-000", tmp_path / "x.json", w=0.5, pricers=3, rates=RATES)
    assert fakes["calls"]["reader"][0][1] == 20.0
    assert all(fakes["calls"][f"pricer{i}"][0][1] == docs[:2] for i in (1, 2, 3))
    calls = [haiku.calibrated_call(room, fakes["scripts"][f"pricer{i}"], RATES, 0.5) for i in (1, 2, 3)]
    assert cli["calls"] == {"reader": fakes["scripts"]["reader"][-1]["args"], "pricer1": calls[0],
                            "pricer2": calls[1], "pricer3": calls[2]}
    assert haiku.call_of(trace) == haiku.vote(calls) and cli["sessions"] == 4
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    row = pilot.score(key, "haiku_lean", trace, cli, "ok")
    assert row["pages"] == 8.0 and haiku.spent(trace) <= 20.0 and row["models"] == ["claude-haiku-5-5"]


def test_lean_without_any_pricer_call_leaves_the_deal_unanswered(fakes, room, tmp_path):
    fakes["scripts"] |= {"reader": [_submit(True)], "pricer2": [_note("nwc", 0.5)]}  # 1 and 3 time out
    trace, cli = haiku.run_lean(room, 20.0, "dev-000", tmp_path / "x.json", w=0.5, pricers=3, rates=RATES)
    assert haiku.call_of(trace) is None and cli["timeouts"] == 2
    assert cli["calls"] == {"reader": fakes["scripts"]["reader"][0]["args"], "pricer1": None, "pricer2": None,
                            "pricer3": None}


def test_lean_runs_end_to_end_on_haiku_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    monkeypatch.setattr(haiku, "load_rates", lambda: RATES)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    [row] = haiku.run(d, ["haiku_lean"], deals=["dev-001"], claude=fake_claude)
    assert row["answered"] and row["sessions"] == 4 and row["spent"] <= row["budget"] + 1e-9
    assert row["settings"] == {"w": 0.5, "pricers": 3} and set(row["calls"]) == {"reader", "pricer1", "pricer2",
                                                                                 "pricer3"}


# --- the base rates ------------------------------------------------------------------------------------------------

def test_base_rates_are_the_share_of_deals_where_each_problem_is_real(data, tmp_path):
    from acqlab.generator.traps import TRAPS
    d = tmp_path / "cal-r2"
    shutil.copytree(data, d)
    keys = [AnswerKey.model_validate_json(p.read_text()) for p in sorted((d / "truth").glob("*.json"))]
    out = haiku.base_rates([d])
    assert out["deals"] == ["cal-r2/dev-000", "cal-r2/dev-001"]
    for t in TRAPS:
        real = [f.amount > 0 for k in keys for f in k.truth.facts if f.trap == t]
        assert out["rates"][t] == pytest.approx(sum(real) / len(real))
    with pytest.raises(haiku.Refused, match="practice deals only"):
        haiku.base_rates([d, tmp_path / "pilot-r2u"])
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku.py -q`
Expected: 7 failed (`AttributeError: module 'acqlab.bench.haiku' has no attribute 'calibrated_record'` and similar), 9 passed.

- [ ] **Step 3: Add the lean pipeline to the module**

In `acqlab/bench/haiku.py`:

(a) In the docstring, after the `--final --confirm-claude` usage line, add:

```
    uv run python -m acqlab.bench.haiku --base-rates     # spec §3, from the practice deals' answer keys (free)
```

and change the first usage line's `--systems haiku_solo,haiku_team` to `--systems haiku_solo,haiku_lean`.

(b) Replace the imports with:

```python
import argparse
import hashlib
import json
import statistics
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from acqlab.agents import panel, panel_prompts, prompts, solver
from acqlab.bench import referee
from acqlab.bench.recon import SECOND_SYSTEM, call_of, combine, draft, notes_record, second, spent, step
from acqlab.llm import LLMUnavailable
```

(c) After the `FINAL: ...` line, add:

```python
RATES = Path(__file__).with_name("base_rates.json")
```

(d) Between `on_haiku` and the `# --- the candidates ---` banner, insert:

```python
# --- pricing open issues at realistic rates (spec §3) --------------------------------------------------------------

def load_rates() -> dict[str, float]:
    return json.loads(RATES.read_text())["rates"]


def calibrated_record(room: Path, trace: list[dict], rates: dict[str, float], w: float):
    """recon.notes_record with each open issue's chance pulled toward its base rate: w·chance + (1 − w)·rate. A
    settled issue (chance 1) is unchanged."""
    def pull(r: dict) -> dict:
        a = r["args"]
        if r["tool"] != "note_issue" or r.get("refused") or float(a["chance"]) >= 1:
            return r
        return r | {"args": a | {"chance": w * float(a["chance"]) + (1 - w) * rates[a["type"]]}}

    return notes_record(room, [pull(r) for r in trace])


def calibrated_call(room: Path, trace: list[dict], rates: dict[str, float], w: float) -> dict | None:
    """The engine's call on a pricer's calibrated notes; None if the pricer never submitted."""
    if call_of(trace) is None:
        return None
    go, wa = calibrated_record(room, trace, rates, w).decide()
    return {"go": bool(go), "walk_away": float(wa), "reason": "the engine, on calibrated notes"}


def vote(calls: list[dict | None]) -> dict | None:
    """The majority of the engine calls given (a tie is NO-GO, the cautious call, as S3's vote is) at the median
    walk-away; None if no pricer gave a call."""
    ok = [c for c in calls if c]
    if not ok:
        return None
    gos = sum(c["go"] for c in ok)
    return {"go": 2 * gos > len(ok), "walk_away": float(statistics.median(c["walk_away"] for c in ok)),
            "reason": f"the engine's majority: {gos} of {len(ok)} GO"}


```

(e) After `run_team`, insert:

```python


def run_lean(room: Path, budget: float, deal: str, out: Path, *, w: float, pricers: int,
             rates: dict[str, float] | None = None, **kw) -> tuple[list[dict], dict]:
    """Spec §3: one reader at the full budget, then `pricers` second opinions on the documents it read; the engine
    prices each one's calibrated notes, and the majority of those calls is final."""
    rates = rates or load_rates()
    reader = step("reader", out.with_suffix(".reader.jsonl"), draft, room, budget, **kw)
    read = referee.opened(reader[0])
    priced = [step(f"pricer{i}", out.with_suffix(f".pricer{i}.jsonl"), second, room, read, **kw)
              for i in range(1, pricers + 1)]
    calls = [calibrated_call(room, rows, rates, w) for rows, _ in priced]
    steps = [reader, *priced]
    trace, cli = combine([r for rows, _ in steps for r in rows], [c for _, c in steps], vote(calls))
    return trace, cli | {"calls": {"reader": call_of(reader[0])} | {f"pricer{i}": c for i, c in enumerate(calls, 1)}}
```

(f) Replace `CANDIDATES` with:

```python
CANDIDATES = {
    "haiku_solo": Candidate(run_solo, SOLO),
    "haiku_team": Candidate(run_team, TEAM),
    "haiku_lean": Candidate(run_lean, SOLO + (SECOND_SYSTEM,), settings={"w": 0.5, "pricers": 3}),
}
```

(g) Between `run` and `main`, insert:

```python
def base_rates(dirs: list[Path]) -> dict:
    """Spec §3: for each issue type, the share of these deals where the problem is really there (amount > 0), read
    from their answer keys, with the deals used. Refuses a held-out set."""
    from acqlab.generator.batch import AnswerKey
    from acqlab.generator.traps import TRAPS
    if bad := [d.name for d in dirs if d.resolve().name in TEST_SETS]:
        raise Refused(f"base rates come from practice deals only, not {bad}")
    keys = {f"{d.name}/{p.stem}": AnswerKey.model_validate_json(p.read_text())
            for d in dirs for p in sorted((d / "truth").glob("*.json"))}
    real = {t: [f.amount > 0 for k in keys.values() for f in k.truth.facts if f.trap == t] for t in TRAPS}
    return {"rates": {t: sum(v) / len(v) for t, v in real.items()}, "deals": sorted(keys)}


```

(h) In `main`: change `ap.add_argument("--data", type=Path, required=True)` to `ap.add_argument("--data", type=Path)`; change the `--systems` default to `"haiku_solo,haiku_team,haiku_lean"`; after the `--confirm-claude` argument add

```python
    ap.add_argument("--base-rates", action="store_true", help=f"write {RATES.name} from the practice deals")
```

and replace `args = ap.parse_args(argv)` with:

```python
    args = ap.parse_args(argv)
    if args.base_rates:
        root = Path(__file__).resolve().parents[2] / "data"
        RATES.write_text(json.dumps(base_rates([root / d for d in PRACTICE]), indent=2) + "\n")
        print(f"wrote {RATES}")
        return 0
```

and, just before `try: refuse(...)`, add:

```python
    if args.data is None:
        ap.error("--data is required")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku.py -q`
Expected: `16 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/haiku.py tests/bench/test_haiku.py
git commit -m "feat: Haiku lean pipeline: one reader, three pricers, the engine on base-rate-calibrated notes, majority vote

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The practice scorecard

**Files:**
- Create: `scripts/haiku_practice.py`
- Test: `tests/bench/test_haiku_practice.py`

**Interfaces:**
- Consumes: `haiku.PRACTICE`; `analysis.CASES`; `upside_pilot.load(data, system) -> {deal: row}` and `upside_pilot.stats(rows) -> dict` (`n`, `regret`, `correct`, `false_go`, `false_nogo`, `pages`, `no_answer`, `timeouts`, `cost`, `sessions`; `{"n": 0}` when empty).
- Produces: `scorecard(root, systems) -> {system: {"all": card, "missing": int, "sets": {set: card}, "by_case": {case: card}}}`; `card(rows)` adds `over_budget` and `models`; `keeps(new, old) -> bool`; `table(cards) -> str`; `main(argv) -> int` (`--root`, `--systems`, `--keep`, `--over`).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_haiku_practice.py`:

```python
import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import haiku, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "haiku_practice.py"))


@pytest.fixture(scope="module")
def practice(tmp_path_factory, data):
    """The three practice sets in miniature: two r2 dev deals each in cal-r2 and heldout-r2, five r2u dev deals in
    practice-r2u."""
    root = tmp_path_factory.mktemp("practice")
    shutil.copytree(data, root / "cal-r2")
    shutil.copytree(data, root / "heldout-r2")
    # the batch's word-presence check can flag a set this small; the scorecard doesn't care
    batch.run(root / "practice-r2u", {"dev": 5, "test": 0, "hand": 0, "showcase": 0}, mc=20, profile="r2u")
    return root


def write(d: Path, system: str, deal: str, go: bool, cost: float = 0.01, spent: float | None = None) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    trace = [{"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    cli = {"total_cost_usd": cost, "sessions": 1, "modelUsage": {"claude-haiku-5-5": {}}}
    row = pilot.score(key, system, trace, cli, "ok") | {"budget": key.budget, "spent": key.budget if spent is None
                                                        else spent}
    (d / "runs" / system).mkdir(parents=True, exist_ok=True)
    (d / "runs" / system / f"{deal}.json").write_text(json.dumps(row))


def every(root: Path):
    for s in haiku.PRACTICE:
        for deal in json.loads((root / s / "splits.json").read_text())["dev"]:
            yield root / s, deal, AnswerKey.model_validate_json((root / s / "truth" / f"{deal}.json").read_text())


def test_the_scorecard_covers_every_practice_deal_by_set_and_type(practice, tmp_path):
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    for d, deal, key in every(root):
        write(d, "right", deal, key.truth.go)
        write(d, "wrong", deal, not key.truth.go, spent=key.budget + 1)
    write(root / "cal-r2", "partial", "dev-000", True)
    cards = SCRIPT["scorecard"](root, ["right", "wrong", "partial"])
    assert cards["right"]["all"]["n"] == 9 and cards["right"]["all"]["regret"] == 0 and cards["right"]["missing"] == 0
    assert cards["right"]["sets"]["practice-r2u"]["n"] == 5 and cards["right"]["all"]["models"] == ["claude-haiku-5-5"]
    assert cards["wrong"]["all"]["correct"] == 0 and cards["wrong"]["all"]["over_budget"] == 9
    assert sum(c["n"] for c in cards["right"]["by_case"].values()) == 9
    assert cards["partial"]["missing"] == 8
    assert "missing runs: 8" in SCRIPT["table"](cards)


def test_a_change_is_kept_only_if_regret_falls_without_more_relief_or_confirmed_misses():
    def e(regret, relief_fnogo=0, confirmed_fgo=0, missing=0):
        return {"missing": missing, "all": {"regret": regret},
                "by_case": {"relief": {"n": 3, "false_nogo": relief_fnogo},
                            "confirmed": {"n": 2, "false_go": confirmed_fgo}}}

    keeps = SCRIPT["keeps"]
    assert keeps(e(0.010), e(0.011))
    assert not keeps(e(0.011), e(0.011))  # regret must fall
    assert not keeps(e(0.009, relief_fnogo=2), e(0.011, relief_fnogo=1))
    assert not keeps(e(0.009, confirmed_fgo=1), e(0.011))
    assert not keeps(e(0.009, missing=1), e(0.011))  # an unfinished round decides nothing
    assert keeps({"missing": 0, "all": {"regret": 0.01}, "by_case": {"relief": {"n": 0}, "confirmed": {"n": 0}}},
                 e(0.011))


def test_main_prints_the_scorecard_and_the_keep_verdict(practice, tmp_path, capsys):
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    for d, deal, key in every(root):
        write(d, "old", deal, True)
        write(d, "new", deal, key.truth.go)
    assert SCRIPT["main"](["--root", str(root), "--systems", "old,new"]) == 0
    assert "old" in capsys.readouterr().out
    assert SCRIPT["main"](["--root", str(root), "--keep", "new", "--over", "old"]) == 0
    assert capsys.readouterr().out.rstrip().endswith("keep new over old: True")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku_practice.py -q`
Expected: collection error, `FileNotFoundError` for `scripts/haiku_practice.py`.

- [ ] **Step 3: Write the script**

Create `scripts/haiku_practice.py`:

```python
"""The Haiku team's practice scorecard (spec docs/superpowers/specs/2026-10-10-haiku-team-design.md §3): each system's
runs on the 90 practice deals, by practice set and by deal type, and the rule for keeping a tuning change. Reads
answer keys and runs; writes nothing and never calls a model, so it can run as often as needed. From the repository
root:

  .venv/bin/python scripts/haiku_practice.py --systems s1b,s4,haiku_solo,haiku_team,haiku_lean
  .venv/bin/python scripts/haiku_practice.py --keep haiku_lean2 --over haiku_lean"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import analysis, haiku
from upside_pilot import load, stats

ROOT = Path(__file__).resolve().parents[1] / "data"
EPS = 1e-9


def card(rows: list[dict]) -> dict:
    """upside_pilot.stats plus the health counts: deals over budget (Haiku rows record spent) and the models seen."""
    if not rows:
        return {"n": 0}
    return stats(rows) | {"over_budget": sum(r["spent"] > r["budget"] + EPS for r in rows if "spent" in r),
                          "models": sorted({m for r in rows for m in r["models"]})}


def scorecard(root: Path, systems: list[str]) -> dict:
    """system -> its card over all practice deals, per practice set and per deal type, and its missing runs."""
    deals = {s: json.loads((root / s / "splits.json").read_text())["dev"] for s in haiku.PRACTICE}
    out = {}
    for name in systems:
        by = {s: {d: r for d, r in load(root / s, name).items() if d in deals[s]} for s in haiku.PRACTICE}
        rows = [r for s in haiku.PRACTICE for r in by[s].values()]
        out[name] = {"all": card(rows), "missing": sum(len(deals[s]) - len(by[s]) for s in haiku.PRACTICE),
                     "sets": {s: card(list(by[s].values())) for s in haiku.PRACTICE},
                     "by_case": {c: card([r for r in rows if r["case_type"] == c]) for c in analysis.CASES}}
    return out


def keeps(new: dict, old: dict) -> bool:
    """Spec §3 step 4 on two scorecard entries, both complete: lower mean practice regret, and no more relief false
    NO-GOs or confirmed false GOs."""
    def n(entry, case, field):
        return entry["by_case"][case].get(field, 0)

    return (new["missing"] == old["missing"] == 0 and new["all"]["regret"] < old["all"]["regret"]
            and n(new, "relief", "false_nogo") <= n(old, "relief", "false_nogo")
            and n(new, "confirmed", "false_go") <= n(old, "confirmed", "false_go"))


def table(card_by: dict) -> str:
    head = f"{'system':14s} {'set':13s} {'n':>3s} {'regret':>7s} {'right':>6s} {'fGO':>4s} {'fNOGO':>5s} " \
           f"{'$/deal':>7s} {'pages':>6s} {'sess':>5s} {'noans':>5s} {'t/o':>4s} {'over':>4s}"
    lines = [head]
    for name, e in card_by.items():
        for label, c in [("all", e["all"]), *e["sets"].items(), *[(f"case:{k}", v) for k, v in e["by_case"].items()]]:
            if not c["n"]:
                continue
            cost = f"{c['cost']:.4f}" if c["cost"] is not None else "-"
            lines.append(f"{name:14s} {label:13s} {c['n']:3d} {c['regret']:7.4f} {c['correct']:6.1%} "
                         f"{c['false_go']:4d} {c['false_nogo']:5d} {cost:>7s} {c['pages']:6.1f} "
                         f"{c['sessions']:5.1f} {c['no_answer']:5d} {c['timeouts']:4d} {c['over_budget']:4d}")
        lines.append(f"{name:14s} missing runs: {e['missing']}; models: {e['all'].get('models', [])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the practice sets")
    ap.add_argument("--systems", default="s1b,s4,haiku_solo,haiku_team,haiku_lean")
    ap.add_argument("--keep", help="a tuning change's system: is it kept over --over? (spec §3 step 4)")
    ap.add_argument("--over", help="the current best system")
    args = ap.parse_args(argv)
    if args.keep:
        if not args.over:
            ap.error("--keep needs --over")
        cards = scorecard(args.root, [args.keep, args.over])
        print(table(cards))
        print(f"keep {args.keep} over {args.over}: {keeps(cards[args.keep], cards[args.over])}")
        return 0
    print(table(scorecard(args.root, [s for s in args.systems.split(",") if s])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku_practice.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/haiku_practice.py tests/bench/test_haiku_practice.py
git commit -m "feat: Haiku practice scorecard and the keep rule for tuning rounds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The one-shot final analysis

**Files:**
- Create: `scripts/haiku_team.py`
- Test: `tests/bench/test_haiku_team.py`

**Interfaces:**
- Consumes: `haiku.FINAL`, `haiku.MODEL`, `haiku.TEST_SETS`, `haiku.prompt_sha(name)`; `analysis.below(c)`, `analysis.above(c)` (on `{"ci95": [lo, hi]}`); `debate_pilot.versus(a, b) -> analysis.compare(a, b) | {won, lost, tied}`; `upside_pilot.keys(data, split)`, `load`, `stats`; `referee.rows(path)`.
- Produces: `systems() -> tuple[str, ...]`; `pairs(winner) -> list[(a, b)]`; `verdict(c) -> "better" | "worse" | "no clear difference: at most X worse"`; `check(by, ks, name)`; `analyse(root) -> {"winner", "systems", "verdicts": {set: str}, "sets_agree": bool, "sets": {"test-r2"|"pilot-r2u"|"all": {"n", "verdict", "versus", "cost_ratio", "systems"}}}`; `main(argv) -> int` (`--root`, `--out`; 0 written, 1 refused).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_haiku_team.py`:

```python
import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import haiku, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "haiku_team.py"))
OPUS = "claude-opus-5-5"


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    """The two test sets in miniature: five r2 test deals in test-r2, five r2u test deals in pilot-r2u."""
    root = tmp_path_factory.mktemp("sets")
    batch.run(root / "test-r2", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2")
    batch.run(root / "pilot-r2u", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u")
    return root


def write(d: Path, system: str, deal: str, go: bool, model: str | None = None, cost: float | None = None,
          prompts: str | None = None, refused: int = 0) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    opus = system in ("s1b", "s4")
    trace = [{"tool": "open_document", "args": {"doc_id": "x"}, "refused": True, "cost": 0.0}] * refused + [
        {"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    cli = {"total_cost_usd": cost if cost is not None else 0.1 if opus else 0.01, "sessions": 1,
           "modelUsage": {model or (OPUS if opus else haiku.MODEL): {}}}
    row = pilot.score(key, system, trace, cli, "ok")
    if not opus:
        row |= {"budget": key.budget, "spent": 1.0, "prompts": prompts or haiku.prompt_sha(system)}
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    (out / f"{deal}.json").write_text(json.dumps(row))


def every(root: Path):
    for name in haiku.TEST_SETS:
        for deal in json.loads((root / name / "splits.json").read_text())["test"]:
            yield root / name, deal, AnswerKey.model_validate_json((root / name / "truth" / f"{deal}.json").read_text())


@pytest.fixture
def finished(sets, tmp_path, monkeypatch):
    """A finished fake final test with haiku_lean frozen: everyone is right except haiku_solo, always wrong, whose
    runs each refused one tool call."""
    monkeypatch.setattr(haiku, "FINAL", "haiku_lean")
    root = tmp_path / "r"
    shutil.copytree(sets, root)
    for d, deal, key in every(root):
        for s in ("s1b", "s4", "haiku_team", "haiku_lean"):
            write(d, s, deal, key.truth.go)
        write(d, "haiku_solo", deal, not key.truth.go, refused=1)
    return root


def test_the_verdict_follows_the_fixed_wording():
    assert SCRIPT["verdict"]({"ci95": [-0.004, -0.001]}) == "better"
    assert SCRIPT["verdict"]({"ci95": [0.001, 0.004]}) == "worse"
    assert SCRIPT["verdict"]({"ci95": [-0.002, 0.0031]}) == "no clear difference: at most 0.0031 worse"
    assert SCRIPT["verdict"]({"ci95": [0.0, 0.0]}) == "no clear difference: at most 0.0000 worse"


def test_the_comparisons_skip_a_system_compared_with_itself():
    assert SCRIPT["pairs"]("haiku_lean") == [("haiku_lean", "s1b"), ("haiku_lean", "s4"),
                                              ("haiku_lean", "haiku_solo"), ("haiku_team", "s4")]
    assert SCRIPT["pairs"]("haiku_solo") == [("haiku_solo", "s1b"), ("haiku_solo", "s4"), ("haiku_team", "s4")]


def test_the_analysis_reads_a_finished_final_test(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    assert out["winner"] == "haiku_lean" and out["systems"] == ["s1b", "s4", "haiku_solo", "haiku_team", "haiku_lean"]
    assert [out["sets"][n]["n"] for n in ("test-r2", "pilot-r2u", "all")] == [5, 5, 10]
    assert out["verdicts"] == dict.fromkeys(("test-r2", "pilot-r2u", "all"), "no clear difference: at most 0.0000 worse")
    assert out["sets_agree"]
    every_set = out["sets"]["all"]
    assert set(every_set["versus"]) == {"haiku_lean-s1b", "haiku_lean-s4", "haiku_lean-haiku_solo", "haiku_team-s4"}
    assert every_set["versus"]["haiku_lean-haiku_solo"]["won"] > 0  # haiku_solo is always wrong
    assert every_set["cost_ratio"]["s1b/haiku_lean"] == pytest.approx(10.0)
    assert set(every_set["cost_ratio"]) == {f"{o}/{h}" for o in ("s1b", "s4")
                                            for h in ("haiku_solo", "haiku_team", "haiku_lean")}
    solo = every_set["systems"]["haiku_solo"]["all"]
    assert solo["correct"] == 0 and solo["refused_calls"] == 10 and "decoy_pages" in solo
    assert sum(c["n"] for c in every_set["systems"]["s1b"]["by_case"].values()) == 10
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_the_sets_can_disagree(finished):
    for d, deal, key in every(finished):
        if d.name == "pilot-r2u":
            write(d, "haiku_lean", deal, not key.truth.go)
    out = SCRIPT["analyse"](finished)
    assert out["verdicts"]["test-r2"].startswith("no clear difference") and not out["sets_agree"]


def test_the_analysis_refuses_before_the_freeze(finished, monkeypatch, tmp_path):
    monkeypatch.setattr(haiku, "FINAL", None)
    with pytest.raises(ValueError, match="no frozen winner"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()


def test_the_analysis_refuses_a_missing_deal_another_model_or_unfrozen_prompts(finished):
    (finished / "pilot-r2u" / "runs" / "haiku_team" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="pilot-r2u: haiku_team.*test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "pilot-r2u", "haiku_team", "test-001", True, model=OPUS)
    with pytest.raises(ValueError, match="wrong model.*pilot-r2u/haiku_team/test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "pilot-r2u", "haiku_team", "test-001", True)
    write(finished / "test-r2", "s1b", "test-002", True, model=haiku.MODEL)
    with pytest.raises(ValueError, match="wrong model.*test-r2/s1b/test-002"):
        SCRIPT["analyse"](finished)
    write(finished / "test-r2", "s1b", "test-002", True)
    write(finished / "test-r2", "haiku_lean", "test-003", True, prompts="old")
    with pytest.raises(ValueError, match="frozen prompts.*test-r2/haiku_lean/test-003"):
        SCRIPT["analyse"](finished)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku_team.py -q`
Expected: collection error, `FileNotFoundError` for `scripts/haiku_team.py`.

- [ ] **Step 3: Write the script**

Create `scripts/haiku_team.py`:

```python
"""The Haiku team's final analysis (spec docs/superpowers/specs/2026-10-10-haiku-team-design.md §5), run once on the
finished final test. Reads answer keys and runs; never calls a model. From the repository root:

  .venv/bin/python scripts/haiku_team.py --out docs/results/haiku-team.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import analysis, haiku
from acqlab.bench.referee import rows as trace_rows
from debate_pilot import versus
from upside_pilot import keys, load, stats

ROOT = Path(__file__).resolve().parents[1] / "data"
OPUS, OPUS_MODEL = ("s1b", "s4"), "claude-opus-5-5"
EPS = 1e-9


def systems() -> tuple[str, ...]:
    """The final test's systems: the Opus baselines, the two Haiku controls and the frozen winner (once)."""
    if haiku.FINAL is None:
        raise ValueError("no frozen winner: haiku.FINAL is set at the freeze")
    return tuple(dict.fromkeys((*OPUS, "haiku_solo", "haiku_team", haiku.FINAL)))


def pairs(winner: str) -> list[tuple[str, str]]:
    """Spec §5's comparisons, a − b; one that would compare a system with itself is left out."""
    return [(a, b) for a, b in ((winner, "s1b"), (winner, "s4"), (winner, "haiku_solo"), ("haiku_team", "s4"))
            if a != b]


def verdict(c: dict) -> str:
    """Spec §5's wording for winner − s1b."""
    if analysis.below(c):
        return "better"
    if analysis.above(c):
        return "worse"
    return f"no clear difference: at most {c['ci95'][1]:.4f} worse"


def check(by: dict[str, dict[str, dict]], ks: dict, name: str) -> None:
    """Refuse a final test that is not the pre-registered one: a system missing deals, a row on the wrong model (a
    timed-out row may show none), or a Haiku row made with prompts other than the frozen ones."""
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{name}: {s} runs cover {sorted(set(rows) ^ set(ks))} differently from the test split")
    want = {s: [OPUS_MODEL] if s in OPUS else [haiku.MODEL] for s in by}
    wrong = [f"{name}/{s}/{d}" for s, rows in by.items() for d, r in rows.items() if r["models"] != want[s]
             and not (not r["models"] and (r["status"] == "timeout" or r["timeouts"] >= r["sessions"]))]
    if wrong:
        raise ValueError(f"rows on the wrong model: {wrong}")
    stale = [f"{name}/{s}/{d}" for s in by if s not in OPUS for d, r in by[s].items()
             if r.get("prompts") != haiku.prompt_sha(s)]
    if stale:
        raise ValueError(f"rows not made with the frozen prompts: {stale}")


def card(rows: list[dict], refused: list[int]) -> dict:
    if not rows:
        return {"n": 0}
    return stats(rows) | {"decoy_pages": float(np.mean([r["decoy_pages"] for r in rows])),
                          "over_budget": sum(r["spent"] > r["budget"] + EPS for r in rows if "spent" in r),
                          "refused_calls": int(sum(refused))}


def one_set(by: dict[str, dict[str, dict]], refused: dict[str, dict[str, int]], winner: str) -> dict:
    """Everything spec §5 reports for one deal set (by: system -> deal -> row)."""
    cmp = {f"{a}-{b}": versus(by[a], by[b]) for a, b in pairs(winner)}
    cost = {s: c for s in by if (c := card(list(by[s].values()), [0])["cost"])}
    ids = sorted(next(iter(by.values())))
    cases = sorted({by["s1b"][d]["case_type"] for d in ids})
    return {
        "n": len(ids), "verdict": verdict(cmp[f"{winner}-s1b"]), "versus": cmp,
        "cost_ratio": {f"{o}/{h}": cost[o] / cost[h] if o in cost and h in cost else None
                       for o in OPUS for h in by if h not in OPUS},
        "systems": {s: {"all": card(list(rows.values()), list(refused[s].values())),
                        "by_case": {c: card([r for r in rows.values() if r["case_type"] == c],
                                            [refused[s][d] for d, r in rows.items() if r["case_type"] == c])
                                    for c in cases}}
                    for s, rows in by.items()},
    }


def analyse(root: Path) -> dict:
    names, winner = systems(), haiku.FINAL
    by, refused = {}, {}
    for name in haiku.TEST_SETS:
        ks = keys(root / name, "test")
        by[name] = {s: load(root / name, s) for s in names}
        check(by[name], ks, name)
        refused[name] = {s: {d: sum(bool(x.get("refused")) for x in trace_rows(root / name / "runs" / s /
                                                                                 f"{d}.trace.jsonl"))
                             for d in ks} for s in names}
    together = {s: {f"{n}/{d}": r for n in haiku.TEST_SETS for d, r in by[n][s].items()} for s in names}
    refused_all = {s: {f"{n}/{d}": c for n in haiku.TEST_SETS for d, c in refused[n][s].items()} for s in names}
    sets = {n: one_set(by[n], refused[n], winner) for n in haiku.TEST_SETS} | {
        "all": one_set(together, refused_all, winner)}
    verdicts = {n: sets[n]["verdict"] for n in sets}
    return {"winner": winner, "systems": list(names), "verdicts": verdicts,
            "sets_agree": len({sets[n]["verdict"].split(":")[0] for n in haiku.TEST_SETS}) == 1, "sets": sets}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the two test sets")
    ap.add_argument("--out", type=Path, required=True, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot, like the earlier pilots: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.root)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"winner": out["winner"], "verdicts": out["verdicts"], "sets_agree": out["sets_agree"],
                      "cost_ratio": out["sets"]["all"]["cost_ratio"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_haiku_team.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/haiku_team.py tests/bench/test_haiku_team.py
git commit -m "feat: Haiku team final analysis: one-shot verdicts per deal set with paired ranges and cost ratios

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The practice deals, the base rates, the tuning log and the full check

**Files:**
- Create (git-ignored, not committed): `data/practice-r2u/`
- Create: `acqlab/bench/base_rates.json`, `docs/results/haiku-team-tuning-log.md`
- Modify: `tests/bench/test_haiku.py`, `docs/HANDOFF.md`

**Interfaces:**
- Consumes: `testset.used_seeds(roots)`, `testset.clashes(base, n, used, split)`; `python -m acqlab.generator.batch`; `haiku.main(["--base-rates"])`; `haiku.RATES`, `haiku.PRACTICE`.
- Produces: 30 dev deals in `data/practice-r2u` (seeds 640000–640029); the committed `acqlab/bench/base_rates.json`.

- [ ] **Step 1: Check the practice seeds clash with nothing**

Run:

```bash
.venv/bin/python -c "
from pathlib import Path
from acqlab.bench.testset import used_seeds, clashes
print(clashes(640000, 30, used_seeds([Path('data')]), 'dev'))"
```

Expected: `[]`. If anything else prints, stop and report it (do not pick another seed yourself).

- [ ] **Step 2: Generate the 30 practice deals**

Run: `.venv/bin/python -m acqlab.generator.batch --out data/practice-r2u --dev 30 --test 0 --hand 0 --showcase 0 --seed 640000 --profile r2u`
Expected: `generated 30 deals into data/practice-r2u; 0 batch problems` (about 10 seconds; a trial run gave 12 relief, 6 confirmed and 12 other deals).

Then confirm the deal types:

```bash
.venv/bin/python -c "
import json, glob, collections
print(collections.Counter(json.load(open(p))['truth']['case_type'] for p in glob.glob('data/practice-r2u/truth/*.json')))"
```

Expected: 30 deals in all, with `relief` 12 and `confirmed` 6.

- [ ] **Step 3: Write the failing test for the committed base rates**

Append to `tests/bench/test_haiku.py`:

```python


def test_the_committed_base_rates_come_from_the_90_practice_deals_only():
    from acqlab.generator.traps import TRAPS
    out = json.loads(haiku.RATES.read_text())
    assert set(out["rates"]) == set(TRAPS) and all(0 < r < 1 for r in out["rates"].values())
    assert len(out["deals"]) == 90 and {d.split("/")[0] for d in out["deals"]} == set(haiku.PRACTICE)
```

Run: `.venv/bin/python -m pytest tests/bench/test_haiku.py -q -k committed`
Expected: FAIL with `FileNotFoundError` for `base_rates.json`.

- [ ] **Step 4: Compute the base rates**

Run: `.venv/bin/python -m acqlab.bench.haiku --base-rates`
Expected: `wrote .../acqlab/bench/base_rates.json`. Open the file: five rates between 0 and 1 (the Plan 6 post-hoc found 0.15–0.38 by type on cal-r2 and heldout-r2) and 90 deal ids, 30 from each practice set.

Run: `.venv/bin/python -m pytest tests/bench/test_haiku.py -q`
Expected: `17 passed`.

- [ ] **Step 5: Start the tuning log**

Create `docs/results/haiku-team-tuning-log.md`:

```markdown
# Haiku team: tuning log

**Spec:** `docs/superpowers/specs/2026-10-10-haiku-team-design.md` §3. **Scorecard:**
`.venv/bin/python scripts/haiku_practice.py`.

Practice deals only (`data/cal-r2`, `data/heldout-r2`, `data/practice-r2u`; 90 in all). The held-out sets
(`data/test-r2`, `data/pilot-r2u`) are never run before the freeze.

**Base rates** (`acqlab/bench/base_rates.json`, from the 90 practice answer keys): <paste the five rates from the
file, as `addback 0.xx, debt_like 0.xx, concentration 0.xx, nwc 0.xx, capex 0.xx`>.

**Rules:** one change per round, as a new registry entry in `acqlab/bench/haiku.py`; kept only if
`scripts/haiku_practice.py --keep <new> --over <best>` says True. Cap: 8 rounds or $15, round 0 included.

Each round records: the change and why (the commonest cause of the best candidate's misses), the scorecard before and
after, the cost, and kept or reverted.

## Round 0

Not run yet: awaits the user's OK for the practice phase.
```

Replace the `<paste ...>` placeholder with the actual five values from `acqlab/bench/base_rates.json`, rounded to two
decimals.

- [ ] **Step 6: Update the HANDOFF resume point**

In `docs/HANDOFF.md`, change the heading `## Resume here (2026-10-09, evening)` to `## Resume here (2026-10-10)`.
Then insert the bullets below directly after the section's first line ("A new session (possibly on the user's other
Claude account) continues from this point."), before the "Where to work" bullet. Leave the rest of the section as it
is: it is the history. Its two "Next: Plan 7" bullets stay true for after this track.

```markdown
- **Current track: the Haiku team** (spec `docs/superpowers/specs/2026-10-10-haiku-team-design.md`, plan
  `docs/superpowers/plans/2026-10-10-haiku-team.md`). Built and tested: the runner (`acqlab/bench/haiku.py`), the
  practice scorecard (`scripts/haiku_practice.py`) and the one-shot final analysis (`scripts/haiku_team.py`). The 30
  practice deals are in `data/practice-r2u` (seed 640000) and the base rates in `acqlab/bench/base_rates.json`.
- **Next: the smoke test, then up to 8 practice rounds** (one OK from the user covers the practice phase, capped at
  $15). Log each round in `docs/results/haiku-team-tuning-log.md`. Then freeze the winner (set `haiku.FINAL`, pin its
  prompts with a fingerprint test, commit `docs/results/haiku-team-prereg.md`), then the final test on
  `data/test-r2` and `data/pilot-r2u` after the user's OK (about $5–10).
- **After that:** Plan 7 (the demo and slides), then stage 2 of the hidden-upside track.
```

- [ ] **Step 7: Run the full suite and the frozen-files check**

Run: `.venv/bin/python -m pytest -q`
Expected: `477 passed` (451 before this plan, plus 9, 7, 3, 6 and 1).

Run: `git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers`
Expected: no output.

Run: `git status --short`
Expected: only the files of this task; nothing under `data/`.

- [ ] **Step 8: Commit**

```bash
git add acqlab/bench/base_rates.json tests/bench/test_haiku.py docs/results/haiku-team-tuning-log.md docs/HANDOFF.md
git commit -m "feat: Haiku practice set: 30 fresh r2u deals (seed 640000) and base rates from the 90 practice answer keys

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Runbook after the plan (not subagent tasks; each paid step needs the user's OK)

1. **Ask the user for one OK covering the practice phase** (smoke test plus up to 8 rounds, capped at $15).
2. **Smoke test** on `data/cal-r2` deals `dev-000,dev-001`:
   `.venv/bin/python -m acqlab.bench.haiku --data data/cal-r2 --deals dev-000,dev-001 --confirm-claude`.
   Check every row: `answered`, `status`, `spent <= budget`, `models == ["claude-haiku-5-5"]` (Review Focus 1), cost.
   Prompts may be fixed here only. If any candidate's prompts change, delete that candidate's two smoke rows (and
   traces) so round 0 reruns them; otherwise round 0 reuses them.
3. **Round 0:** the same command on all three practice sets (`--data data/cal-r2`, `data/heldout-r2`,
   `data/practice-r2u`), then `scripts/haiku_practice.py`. Log it.
4. **Rounds 1–7:** one change each, as a new `CANDIDATES` entry (prompt constants or settings in `haiku.py`, with a
   test), run on the 90 deals, `--keep/--over`, log. Stop at 8 rounds or $15.
5. **Freeze:** set `FINAL`, add a fingerprint test pinning `prompt_sha(FINAL)` and each step's rendered prompt on the
   fixed test room (as `test_debate.py::test_the_frozen_prompts_are_unchanged`), commit
   `docs/results/haiku-team-prereg.md`.
6. **The user's OK, then the final test:** `--final --split test` on `data/test-r2` and `data/pilot-r2u` for
   `haiku_solo`, `haiku_team` and the winner.
7. **Analysis once:** `.venv/bin/python scripts/haiku_team.py --out docs/results/haiku-team.json`; then the
   write-up `docs/results/haiku-team.md` and a HANDOFF update.

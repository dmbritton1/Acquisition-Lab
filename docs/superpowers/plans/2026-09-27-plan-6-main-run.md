# Plan 6: The Main Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tools for the pre-registered main run (the test-set checks, the engine-ablation valuer, the
ablation configs, the resumable campaign runner and the H1–H6 analysis), rehearse them, then run the experiment once
on 160 fresh test deals and report it.

**Architecture:** Everything new lives in `acqlab/bench` (plus a Codex guard in `acqlab/llm.py` and a small refactor
in `acqlab/generator/batch.py`); S4's files stay byte-identical to tag `s4-frozen-plan5`. `testset.py` checks seeds,
fingerprints the test set and runs the recoverability sample; `valuer.py` replays S4's final record and runs one
valuer turn; `pilot.py` gains the test split, the two panel ablations and `run_replays`; `campaign.py` runs the three
phases with waits and one retry; `analysis.py` computes H1–H6 from the finished runs.

**Tech Stack:** Python 3.12, uv, pytest, numpy; `claude -p` (Claude Code 2.1.280) on the user's subscription; Codex
CLI 0.158 (ChatGPT app) for recoverability.

**Spec:** `docs/superpowers/specs/2026-09-27-plan-6-main-run-design.md` (approved 2026-09-27). Also binding:
`docs/results/plan-4b-preregistration.md`.

**Branch:** `claude/plan-4b-freeze-preregistration-0908fa` (worktree `.claude/worktrees/plan-4b-freeze-preregistration-0908fa`),
at `169fe80` plus this plan's commit. 295 tests pass there; the full suite takes about 6 minutes.

**Pre-verified.** Tasks 1–6 were built in a scratch copy of this branch, in order, with every test run: 296, 302,
306, 311, 324 and 331 passed after each task. Task 7's rehearsal script ran the whole campaign (all three phases) and
the analysis on 3 throwaway deals with the fake claude: every phase completed, and no regret reached the log.

## Global Constraints

- Ponytail: minimal code, stdlib and numpy only, no speculative abstractions; match the surrounding comment density
  and idiom. Line length at most 120 characters.
- **S4 is frozen:** never edit anything under `acqlab/agents` or `acqlab/routers` (tag `s4-frozen-plan5`). New code goes
  in `acqlab/bench`. `git diff --quiet s4-frozen-plan5 -- acqlab/agents acqlab/routers` must succeed after every task.
- **Parity:** S1b's prompt is unchanged. The valuer's prompt is new S4-ablation text, logged in
  `docs/results/plan-6-prompt-log.md` (Task 7).
- **No answer-key information** in any system or ablation code: `acqlab/bench/valuer.py` must not contain the words
  `AnswerKey`, `DealTruth` or `truth`. Answer keys are read only for scoring and analysis.
- **No early stopping, no peeking:** the campaign logs counts, never regret; the analysis runs once, after every phase.
- **Never make a real Claude or Codex call without the user's explicit OK** (Tasks 8, 10 and 11 each need their own).
  Never modify settings or permissions files. If a git operation is blocked, stop and report.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Values fixed by the spec: test seed base `3500000` (test seeds 3,510,000–3,510,159), `--profile r2`, 160 test deals,
  ablation deals `test-000`–`test-039`, recoverability sample of 20 at numpy seed 0, H1 cut 25%, H5 factor 2, H6
  minimum 5 deals, bootstrap 2000 resamples at seed 0, wait 5 minutes after a reset, 30 minutes for an unreadable
  limit, one retry after 10 minutes.

## Review Focus

1. **A usage-limit message with no readable time** (a weekly limit's wording may differ) — the campaign must wait 30
   minutes and try again, not stop. Task 5 tests it (`test_a_limit_with_no_readable_time_waits_thirty_minutes`).
2. **A valuer turn that never submits** — it must be scored as unanswered (B0's call), like any run, and counted.
   Task 4 tests it (`test_a_valuer_turn_that_never_submits_is_scored_as_unanswered`).
3. **A replay that does not reproduce S4's call, or an S4 run that is missing** — the phase must stop rather than
   score a replay that isn't S4's run. Task 4 tests both.
4. **Someone edits or adds a file under S4's frozen paths** — the campaign must refuse before the next phase,
   including for a new untracked file. Task 5 tests edits, additions and a changed test set.
5. **Floating-point noise at zero** — a CI that only rounds away from zero must not count as excluding it (identical
   gains once made H2 "hold"). Task 6 tests the no-difference cases for H2 and H3.

## File map

| File | Task | Change |
|---|---|---|
| `acqlab/llm.py` | 1 | the new Codex path; `ToolUsed` and the no-tools guard in `run_codex` |
| `acqlab/generator/batch.py` | 2 | `recover_deal`, shared by the batch and the test-set sample |
| `acqlab/bench/testset.py` | 2 | new: seed clashes, fingerprint, the recoverability sample; CLI |
| `acqlab/bench/valuer.py` | 3 | new: `replay`, `prompts`, `value` |
| `tests/conftest.py` | 3 | `_fake_exe`; the session fixture `s4_fake_run` |
| `acqlab/bench/pilot.py` | 4 | `split`; `ABLATIONS`, `PANELS`; `run_replays`; `--split` |
| `acqlab/bench/campaign.py` | 5 | new: phases, waits, preflight, status/stop |
| `acqlab/bench/analysis.py` | 6 | new: H1–H6 |
| docs | 7–12 | the addendum, prompt log, rehearsal script, test-set fingerprint, results, handoff |

---
### Task 1: Codex's new path, and no answer that used a tool

The ChatGPT app moved its Codex CLI: `/Applications/ChatGPT.app/Contents/Resources/codex` no longer exists, and the
CLI is now `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` (codex-cli 0.158.0-alpha.2.1; the flags in
`CODEX_ARGS` are unchanged). The spec's guard (§2): Codex's `--json` event stream reports each step as an `item.*`
event whose `item.type` is `agent_message` or `reasoning` for plain text, and something else (`command_execution`,
`file_change`, `mcp_tool_call`, `web_search`) when it reached outside its prompt. Any such item makes the call fail
with the new `ToolUsed`, and nothing is cached.

**Files:**
- Modify: `acqlab/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `llm.ToolUsed(RuntimeError)` (not an `LLMUnavailable`: a batch treats it as a failed check, not a stop);
  `llm.TEXT_ITEMS`; `llm.APP_CODEX` = the new path. `run_codex` raises `ToolUsed` after its existing failure checks.

- [ ] **Step 1: Write the failing test**

In `tests/test_llm.py`, directly above `def test_codex_bin_falls_back_to_the_chatgpt_app_copy(monkeypatch):`, add:

```python
def test_run_codex_refuses_an_answer_that_used_a_tool(monkeypatch):
    """Plan 6 spec §2: an extractor that ran a command, changed or read a file, called a tool or searched may not have
    answered from its prompt alone."""
    for item in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
        _fake_codex(monkeypatch, events=[{"type": "item.started", "item": {"id": "i0", "type": item}}])
        with pytest.raises(llm.ToolUsed, match=item):
            llm.run_codex("the prompt")
    _fake_codex(monkeypatch, events=[{"type": "item.completed", "item": {"id": "i0", "type": "reasoning"}},
                                     {"type": "item.completed", "item": {"id": "i1", "type": "agent_message"}}])
    assert llm.run_codex("the prompt")[0] == "answer"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q tests/test_llm.py`
Expected: 1 failed (`AttributeError: module 'acqlab.llm' has no attribute 'ToolUsed'`), 8 passed.

- [ ] **Step 3: Implement**

In `acqlab/llm.py`, replace:

```python
# The ChatGPT desktop app bundles the Codex CLI without putting it on PATH.
APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
# Flags checked against `codex exec --help` (codex-cli 0.155.0-alpha.9.2). --ephemeral keeps thousands of
# generator calls out of the user's Codex session history.
CODEX_ARGS = ["exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only"]
ERROR_EVENTS = {"error", "turn.failed"}  # JSONL event types that mean the call did not complete
```

with:

```python
# The ChatGPT desktop app bundles the Codex CLI without putting it on PATH (under codex-cli/ since the app update
# found on 2026-09-27).
APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
# Flags checked against `codex exec --help` (codex-cli 0.158.0-alpha.2.1). --ephemeral keeps thousands of
# generator calls out of the user's Codex session history.
CODEX_ARGS = ["exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only"]
ERROR_EVENTS = {"error", "turn.failed"}  # JSONL event types that mean the call did not complete
TEXT_ITEMS = {"agent_message", "reasoning"}  # the only item types a text-only call produces; any other (a command, a
# file change, a tool call, a web search) means Codex reached outside its prompt (Plan 6 spec §2)
```

In `acqlab/llm.py`, replace:

```python
class LLMUnavailable(RuntimeError):
    """A call failed (usage limit, auth, network). Nothing was cached, so rerunning the same command resumes."""
```

with:

```python
class LLMUnavailable(RuntimeError):
    """A call failed (usage limit, auth, network). Nothing was cached, so rerunning the same command resumes."""


class ToolUsed(RuntimeError):
    """Codex used a tool (ran a command, touched a file, called a tool, searched), so its answer may not come from the
    prompt alone. Nothing is cached; the recoverability check counts it as a failure (Plan 6 spec §2)."""
```

Directly above `def _usage_tokens(jsonl: str) -> int:`, add:

```python
def _tool_items(jsonl: str) -> list[str]:
    """The item types in Codex's event stream beyond plain text and reasoning."""
    return sorted({e["item"].get("type", "?") for e in _events(jsonl)
                   if str(e.get("type", "")).startswith("item.") and isinstance(e.get("item"), dict)
                   and e["item"].get("type") not in TEXT_ITEMS})
```

In `run_codex`, directly after the line
`            raise LLMUnavailable(f"codex exec failed (exit {proc.returncode}): {detail}")`, add (same
indentation as the `if` above it):

```python
        used = _tool_items(proc.stdout)
        if used:
            raise ToolUsed(f"codex exec used {', '.join(used)}")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q tests/test_llm.py`
Expected: 9 passed.

Run: `uv run pytest -q`
Expected: `296 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/llm.py tests/test_llm.py
git commit -m "fix(llm): Codex's new path, and an answer that used a tool is refused (Plan 6, Task 1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: The test-set tools (seed check, fingerprint, recoverability sample)

**Files:**
- Modify: `acqlab/generator/batch.py`
- Create: `acqlab/bench/testset.py`
- Test: `tests/bench/test_testset.py`

**Interfaces:**
- Consumes: `llm.ToolUsed` (Task 1).
- Produces: `batch.recover_deal(out: Path, key: AnswerKey, extract) -> list[str]`; `testset.used_seeds(roots:
  list[Path]) -> set[int]`; `testset.clashes(base: int, n: int, used: set[int]) -> list[int]`;
  `testset.fingerprint(data: Path) -> dict` (`{"files": {name: sha256}, "all": sha256}`);
  `testset.recover_sample(data: Path, n: int = 20, seed: int = 0, extract=None) -> tuple[list[str], list[str]]`;
  CLI `python -m acqlab.bench.testset seeds|fingerprint|recover` (exit 0 clean, 1 clash/problem, 2 Codex stopped,
  3 refused).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_testset.py`:

```python
import json
import shutil

import numpy as np
import pytest

from acqlab.bench import testset
from acqlab.generator import batch
from acqlab.llm import ToolUsed


@pytest.fixture(scope="module")
def tests_batch(tmp_path_factory):
    """Two generated test-split deals (seed 0: test seeds 10000 and 10001)."""
    out = tmp_path_factory.mktemp("testset")
    assert batch.run(out, {"dev": 0, "test": 2, "hand": 0, "showcase": 0}, mc=20) == []
    return out


def test_a_clash_is_a_used_seed_equal_to_a_test_seed_or_one_of_its_retries():
    used = {3_510_005, 1_510_007, 42, 510_200, 3_510_160}  # a test seed; a retry relative; unrelated; beyond n
    assert testset.clashes(3_500_000, 160, used) == [1_510_007, 3_510_005]
    assert testset.clashes(3_500_000, 160, {10_000, 620_000, 1_930_182}) == []


def test_used_seeds_reads_every_answer_key_under_the_roots_and_skips_junk(tmp_path):
    for rel, body in (("a/truth/x.json", {"truth": {"seed": 7}}), ("b/c/truth/y.json", {"truth": {"seed": 9}}),
                      ("a/truth/no_seed.json", {"truth": {}})):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(json.dumps(body))
    (tmp_path / "a" / "truth" / "bad.json").write_text("not json")
    assert testset.used_seeds([tmp_path / "a", tmp_path / "b"]) == {7, 9}


def test_the_fingerprint_changes_when_any_answer_key_changes(tests_batch, tmp_path):
    copy = shutil.copytree(tests_batch / "truth", tmp_path / "d" / "truth")
    before = testset.fingerprint(tmp_path / "d")
    assert set(before["files"]) == {"test-000.json", "test-001.json"}
    assert testset.fingerprint(tmp_path / "d") == before  # stable
    (copy / "test-001.json").write_text((copy / "test-001.json").read_text() + " ")
    after = testset.fingerprint(tmp_path / "d")
    assert after["all"] != before["all"] and after["files"]["test-000.json"] == before["files"]["test-000.json"]


def test_the_recoverability_sample_is_seeded_and_a_tool_using_extractor_fails_each_deal(tests_batch):
    def uses_a_tool(prompt, schema=None):
        raise ToolUsed("codex exec used command_execution")

    chosen, problems = testset.recover_sample(tests_batch, n=5, extract=uses_a_tool)
    assert chosen == ["test-000", "test-001"]  # n above the split's size: every deal, in order
    assert problems == [f"{d}: the extractor used a tool (codex exec used command_execution)" for d in chosen]
    deals = json.loads((tests_batch / "splits.json").read_text())["test"]
    assert testset.recover_sample(tests_batch, n=1, extract=uses_a_tool)[0] == sorted(
        np.random.default_rng(0).choice(deals, 1, replace=False).tolist())


def test_an_extractor_that_finds_nothing_fails_every_fact_it_should_have_found(tests_batch):
    _, problems = testset.recover_sample(tests_batch, n=1, extract=lambda prompt, schema=None: ('{"low": null, '
                                                                                               '"high": null}', 1))
    assert problems and all("extractor answered None-None" in p for p in problems)


def test_the_cli_refuses_codex_calls_without_the_flag_and_checks_seeds(tests_batch, tmp_path, capsys):
    assert testset.main(["recover", "--data", str(tests_batch)]) == 3
    assert testset.main(["seeds", "--base", "0", "--n", "2", "--roots", str(tests_batch)]) == 1  # its own seeds
    assert testset.main(["seeds", "--base", "3500000", "--n", "160", "--roots", str(tests_batch)]) == 0
    assert testset.main(["fingerprint", "--data", str(tests_batch)]) == 0
    assert json.loads(capsys.readouterr().out.split("clashes with base 3500000: none\n")[-1]) == testset.fingerprint(
        tests_batch)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/bench/test_testset.py`
Expected: a collection error, `ImportError: cannot import name 'testset' from 'acqlab.bench'`.

- [ ] **Step 3: Implement**

In `acqlab/generator/batch.py`, change the import `from acqlab.llm import LLMUnavailable` to
`from acqlab.llm import LLMUnavailable, ToolUsed`. In `_recoverability`, delete its first body line
`    from acqlab.generator.recover import check` (it moves into `recover_deal`), then replace:

```python
    problems = []
    for key in keys:
        if key.truth.id not in chosen:
            continue
        room = out / "deals" / key.truth.id / "room"
        texts = {p.stem: p.read_text() for p in room.glob("*.md")}
        filler = next(d["id"] for d in json.loads((room / "index.json").read_text())["documents"]
                      if d["domain"] == "filler")
        found, _ = check(key.truth, key.evidence, texts, extract, filler)
        problems += [f"{key.truth.id}: {p}" for p in found]
    return problems
```

with:

```python
    return [p for key in keys if key.truth.id in chosen for p in recover_deal(out, key, extract)]


def recover_deal(out: Path, key: AnswerKey, extract) -> list[str]:
    """One deal's recoverability problems, each prefixed with its id. An extractor that used a tool fails the deal:
    its answer may not come from the documents it was shown (Plan 6 spec §2)."""
    from acqlab.generator.recover import check
    room = out / "deals" / key.truth.id / "room"
    texts = {p.stem: p.read_text() for p in room.glob("*.md")}
    filler = next(d["id"] for d in json.loads((room / "index.json").read_text())["documents"]
                  if d["domain"] == "filler")
    try:
        found, _ = check(key.truth, key.evidence, texts, extract, filler)
    except ToolUsed as e:
        found = [f"the extractor used a tool ({e})"]
    return [f"{key.truth.id}: {p}" for p in found]
```

Create `acqlab/bench/testset.py`:

```python
"""The Plan 6 test set (spec §2): the seed check before it is generated, its fingerprint, and the recoverability check
on a seeded sample of it.

  uv run python -m acqlab.bench.testset seeds --base 3500000 --n 160 --roots DIR [DIR ...]
  uv run python -m acqlab.bench.testset fingerprint --data data/test-r2 > docs/results/plan-6-test-set.json
  uv run python -m acqlab.bench.testset recover --data data/test-r2 --n 20 --confirm-codex

Exit codes: 0 clean; 1 a clash or a recoverability problem; 2 Codex stopped (rerun later: calls are cached); 3
refused (no --confirm-codex)."""
import argparse
import hashlib
import json
from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np

from acqlab.generator.batch import RETRY_SEED, SEED_OFFSET, AnswerKey, recover_deal
from acqlab.llm import LLMUnavailable


def used_seeds(roots: list[Path]) -> set[int]:
    """Every seed recorded in an answer key under these directories (any depth)."""
    seeds = set()
    for root in roots:
        for p in Path(root).rglob("truth/*.json"):
            try:
                seed = json.loads(p.read_text())["truth"]["seed"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if isinstance(seed, int):
                seeds.add(seed)
    return seeds


def clashes(base: int, n: int, used: set[int]) -> list[int]:
    """Used seeds equal to one of the n test deals' seeds or to one of its retries (retries add multiples of
    RETRY_SEED, so a clash is a match modulo RETRY_SEED)."""
    mine = {(base + SEED_OFFSET["test"] + i) % RETRY_SEED for i in range(n)}
    return sorted(s for s in used if s % RETRY_SEED in mine)


def fingerprint(data: Path) -> dict:
    """SHA-256 of every answer key, and one hash over them in name order."""
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((data / "truth").glob("*.json"))}
    return {"files": files, "all": hashlib.sha256("".join(f"{k} {v}\n" for k, v in files.items()).encode()).hexdigest()}


def recover_sample(data: Path, n: int = 20, seed: int = 0, extract: Callable | None = None) -> tuple[list[str], list]:
    """The recoverability gate (spec §2): a seeded random sample of n test deals. Returns (chosen, problems)."""
    if extract is None:
        from acqlab.llm import complete
        extract = partial(complete, cache_dir=data / "llm_cache")
    deals = json.loads((data / "splits.json").read_text())["test"]
    chosen = sorted(np.random.default_rng(seed).choice(deals, min(n, len(deals)), replace=False).tolist())
    problems = []
    for deal in chosen:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        problems += recover_deal(data, key, extract)
    return chosen, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seeds", help="fail if a test seed clashes with any seed already used")
    s.add_argument("--base", type=int, required=True)
    s.add_argument("--n", type=int, required=True)
    s.add_argument("--roots", type=Path, nargs="+", required=True)
    f = sub.add_parser("fingerprint", help="print the answer keys' fingerprint as JSON")
    f.add_argument("--data", type=Path, required=True)
    r = sub.add_parser("recover", help="the recoverability check on a seeded sample (uses Codex)")
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--n", type=int, default=20)
    r.add_argument("--confirm-codex", action="store_true", help="required to make real Codex calls")
    args = ap.parse_args(argv)
    if args.cmd == "seeds":
        used = used_seeds(args.roots)
        found = clashes(args.base, args.n, used)
        print(f"{len(used)} seeds used; clashes with base {args.base}: {found or 'none'}")
        return 1 if found else 0
    if args.cmd == "fingerprint":
        print(json.dumps(fingerprint(args.data), indent=2))
        return 0
    if not args.confirm_codex:
        print("Refusing to run: this uses your Codex quota. Add --confirm-codex to proceed.")
        return 3
    try:
        chosen, problems = recover_sample(args.data, args.n)
    except LLMUnavailable as e:
        print(f"Codex stopped: {e}\nEvery completed call is cached. Run the same command again to continue.")
        return 2
    print(f"checked {len(chosen)} deals: {', '.join(chosen)}")
    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q tests/bench/test_testset.py tests/generator`
Expected: all pass (6 + 91).

Run: `uv run pytest -q`
Expected: `302 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator/batch.py acqlab/bench/testset.py tests/bench/test_testset.py
git commit -m "feat(bench): test-set seed check, fingerprint and recoverability sample (Plan 6, Task 2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: The valuer (the engine ablations' final step)

The replay is Plan 5's diagnostic (`docs/results/scripts/plan-5-caution-replay.py`), which reproduced all 59 recorded
S4 calls. `Record.view()`'s first line is the engine's call, so −engine drops it. `run_session` with tools
`["submit"]` passes `--allowedTools mcp__room__submit`, so the valuer can call nothing else, and budget 0 means it
could read nothing anyway.

**Files:**
- Create: `acqlab/bench/valuer.py`
- Modify: `tests/conftest.py`
- Test: `tests/bench/test_valuer.py`

**Interfaces:**
- Consumes: `acqlab.agents.record.Record`, `load_face`; `acqlab.agents.solver.run_session` (imports only; no edits).
- Produces: `valuer.MODES = ("s4_noengine", "s4_llmdecides")`; `valuer.ReplayMismatch(RuntimeError)`;
  `valuer.replay(room: Path, trace: list[dict]) -> Record`; `valuer.prompts(rec: Record, teaser: str, mode: str) ->
  tuple[str, str]`; `valuer.value(room: Path, rec: Record, mode: str, trace: Path, **kw) -> dict`. Fixture
  `s4_fake_run` → `(room, trace rows)` of one fake S4 run on dev-000.

- [ ] **Step 1: Write the failing tests**

In `tests/conftest.py`, add `import json` above `import sys`, and replace:

```python
@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Path to an executable fake `claude`; set FAKE_CLAUDE (mode) with monkeypatch.setenv."""
    from acqlab.agents import solver
    exe = tmp_path / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    monkeypatch.setenv("FAKE_ARGS", str(tmp_path / "args.json"))
    # solver.py scrubs the child env to an allowlist (F1); widen it here only, so the fake still gets its mode
    # and args-file path, without production code ever knowing these test-only names.
    monkeypatch.setattr(solver, "ENV_KEEP", solver.ENV_KEEP + ("FAKE_CLAUDE", "FAKE_ARGS"))
    return str(exe)
```

with:

```python
def _fake_exe(where: Path) -> str:
    exe = where / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    return str(exe)


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Path to an executable fake `claude`; set FAKE_CLAUDE (mode) with monkeypatch.setenv."""
    from acqlab.agents import solver
    monkeypatch.setenv("FAKE_ARGS", str(tmp_path / "args.json"))
    # solver.py scrubs the child env to an allowlist (F1); widen it here only, so the fake still gets its mode
    # and args-file path, without production code ever knowing these test-only names.
    monkeypatch.setattr(solver, "ENV_KEEP", solver.ENV_KEEP + ("FAKE_CLAUDE", "FAKE_ARGS"))
    return _fake_exe(tmp_path)


@pytest.fixture(scope="session")
def s4_fake_run(data, tmp_path_factory):
    """One S4 run on dev-000 with the fake claude, shared by the tests that replay it: (room, trace rows)."""
    from acqlab.agents import panel, solver
    out = tmp_path_factory.mktemp("s4run")
    room, trace = data / "deals" / "dev-000" / "room", out / "s4.trace.jsonl"
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("FAKE_CLAUDE", "ok")
        mp.setattr(solver, "ENV_KEEP", solver.ENV_KEEP + ("FAKE_CLAUDE",))
        panel.solve(room, 20, trace, panel.Config(), claude=_fake_exe(out))
    return room, [json.loads(x) for x in trace.read_text().splitlines()]
```

Create `tests/bench/test_valuer.py`:

```python
import json
from pathlib import Path

import pytest

from acqlab.bench import valuer


def test_the_replay_rebuilds_s4_s_final_record_and_its_call(s4_fake_run):
    room, trace = s4_fake_run
    rec = valuer.replay(room, trace)
    submit = next(r for r in trace if r["tool"] == "submit")["args"]
    assert rec.decide() == (submit["go"], pytest.approx(submit["walk_away"]))
    assert all(not e.objections for e in rec.entries.values())  # cleared, as Panel.run clears them


def test_the_no_engine_prompt_holds_no_engine_output_and_llm_decides_gets_the_engine_s_walk_away(s4_fake_run):
    room, trace = s4_fake_run
    rec = valuer.replay(room, trace)
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    median = f"${rec.decide()[1]:,.1f}M"
    system, user = valuer.prompts(rec, teaser, "s4_noengine")
    assert teaser in user and "engine" not in (system + user).lower() and median not in user
    assert "- addback" in user and "- capex" in user  # the team's findings, one line per issue type
    system, user = valuer.prompts(rec, teaser, "s4_llmdecides")
    assert f"median {median}" in user and "engine's median" in system


def test_the_valuer_reads_no_answer_key():
    source = Path(valuer.__file__).read_text()
    assert not any(word in source for word in ("AnswerKey", "DealTruth", "truth"))


def test_a_valuer_turn_may_only_submit_and_has_no_reading_budget(s4_fake_run, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    room, trace = s4_fake_run
    out = tmp_path / "v.trace.jsonl"
    cli = valuer.value(room, valuer.replay(room, trace), "s4_noengine", out, claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--allowedTools") + 1] == "mcp__room__submit" and cli["total_cost_usd"] == 0.5
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert any(r["tool"] == "submit" for r in rows) and not any(r["cost"] and not r["refused"] for r in rows)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/bench/test_valuer.py`
Expected: a collection error, `ImportError: cannot import name 'valuer' from 'acqlab.bench'`.

- [ ] **Step 3: Implement**

Create `acqlab/bench/valuer.py`:

```python
"""The engine ablations' valuer (Plan 6 spec §3): S4's final Deal Record, rebuilt from its trace, and one sandboxed
Claude turn that makes the final call in the engine's place. −engine (`s4_noengine`): the valuer sees no engine output
and gives the walk-away and the call. LLM decides (`s4_llmdecides`): it also sees the engine's walk-away and gives
only the call. Everything before the final step is S4's own run, so each ablation is paired with S4's exact reading.

It reads the room and S4's trace only, never an answer key."""
import json
from pathlib import Path

import numpy as np

from acqlab.agents.record import Record, load_face
from acqlab.agents.solver import run_session

MODES = ("s4_noengine", "s4_llmdecides")
SYSTEM = """You are a private-equity analyst making the final call on a leveraged buyout: should the sponsor buy the \
company at its asking price?

The diligence is finished. You get the teaser, with the lender terms and the sponsor's policy, and what the deal team \
established about each kind of issue: amounts it committed from the documents (with their quotes), issues still open \
(the team's chance that each is real, and its size range if it is), and issues nobody raised (treated as no problem). \
All amounts are in $M: addback = claimed add-backs that are not really one-time (they reduce EBITDA); debt_like = \
debt-like items payable at closing; concentration = annual revenue that will be lost; nwc = how far closing net \
working capital falls short of normal; capex = extra capital expenditure needed per year.

{task}

Call submit once, with go (true to buy at the asking price), walk_away in $M and a one-line reason. You are judged on \
the decision: buying a deal worth less than its price, or passing on one worth more, costs the difference."""
TASK = {
    "s4_noengine": "Work out the walk-away price yourself: the most the sponsor should pay, in $M, to meet its policy "
                   "given these findings. Then decide.",
    "s4_llmdecides": "The team's valuation engine has priced these findings; its walk-away is given below. Decide "
                     "whether to buy, and submit the engine's median as walk_away.",
}


class ReplayMismatch(RuntimeError):
    """The rebuilt record does not give S4's recorded call: the replay is not S4's run, so the phase stops."""


def replay(room: Path, trace: list[dict]) -> Record:
    """S4's final Deal Record: its proposals, commits and objections in trace order, the objections then cleared, as
    Panel.run clears them before the engine decides."""
    rec = Record(load_face(room))
    for r in trace:
        if r.get("refused"):
            continue
        if r["tool"] == "propose":
            rec.plan(r["args"]["issues"])
        elif r["tool"] == "report":
            rec.apply((r.get("result") or {}).get("commits", []))
        elif r["tool"] == "challenge":
            rec.challenge(r["args"]["objections"])
    for e in rec.entries.values():
        e.objections = []
    return rec


def prompts(rec: Record, teaser: str, mode: str) -> tuple[str, str]:
    """(system, user). The record's first line is the engine's call, so −engine drops it; LLM decides gets the
    engine's median walk-away and its 10-90% range instead."""
    findings = "\n".join(rec.view().split("\n")[1:])
    user = f"{teaser}\n\nWhat the deal team established:\n{findings}"
    if mode == "s4_llmdecides":
        lo, med, hi = np.percentile(rec.worlds()[1], [10, 50, 90])
        user += (f"\n\nThe valuation engine's walk-away at these findings: median ${med:,.1f}M (10-90%: ${lo:,.1f}M to "
                 f"${hi:,.1f}M); asking price ${rec.face.deal.asking_price:,.1f}M.")
    return SYSTEM.format(task=TASK[mode]), user + "\n\nSubmit your decision."


def value(room: Path, rec: Record, mode: str, trace: Path, **kw) -> dict:
    """One valuer turn: a sandboxed session whose only allowed tool is submit, with no reading budget. Returns the
    CLI's JSON result; raises LLMUnavailable like any session."""
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    system, user = prompts(rec, teaser, mode)
    return run_session(room, 0, trace, user, system, ["submit"], [], **kw)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q tests/bench/test_valuer.py tests/agents/test_solver.py`
Expected: 11 passed (about a minute: one fake S4 run).

Run: `uv run pytest -q`
Expected: `306 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/valuer.py tests/conftest.py tests/bench/test_valuer.py
git commit -m "feat(bench): the valuer, S4's final record replayed for the engine ablations (Plan 6, Task 3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: The runner learns the test split, the panel ablations and the replays

**Files:**
- Modify: `acqlab/bench/pilot.py`
- Test: `tests/bench/test_pilot.py`

**Interfaces:**
- Consumes: `valuer.MODES`, `valuer.replay`, `valuer.value`, `valuer.ReplayMismatch` (Task 3); fixture `s4_fake_run`.
- Produces: `pilot.run(..., split: str = "dev")`; `pilot.ABLATIONS = {"s4_nochal": Config(challenger=False),
  "s4_nosweep": Config(sweep=False)}`; `pilot.PANELS = STAGES | ABLATIONS`; `pilot.ALL` includes both ablations and
  `valuer.MODES`; `pilot.run_replays(data: Path, n: int, systems: list[str], value=valuer.value, split: str = "dev")
  -> list[dict]` (rows like `score`'s; pages and decoy pages are S4's; LLM decides keeps the engine's walk-away);
  `--split` on the CLI, which routes `valuer.MODES` to `run_replays`.

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/bench/test_pilot.py`:

```python


def test_a_split_other_than_dev_runs_only_its_own_deals(fresh):
    """Plan 6: the main run reads the test split."""
    splits = json.loads((fresh / "splits.json").read_text())
    (fresh / "splits.json").write_text(json.dumps(splits | {"test": ["dev-001"]}))

    def solver(room, budget, trace, router):
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}

    rows = run(fresh, 5, ["s1b"], solver=solver, split="test")
    assert [r["deal"] for r in rows] == ["dev-001"]


def test_the_reading_ablations_run_as_panels_with_one_switch_off(fresh):
    """Plan 6 spec §3: −Challenger keeps the two-pass reading (the router stays on); −sweep drops only the sweep."""
    assert pilot.ABLATIONS == {"s4_nochal": panel.Config(challenger=False), "s4_nosweep": panel.Config(sweep=False)}
    assert {"s4_nochal", "s4_nosweep", "s4_noengine", "s4_llmdecides"} <= set(pilot.ALL)
    seen = []

    def panel_solver(room, budget, trace, cfg):
        seen.append(cfg)
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 1.0, "reason": "engine"})) + "\n")
        return {"usage": {}, "sessions": 3}

    run(fresh, 1, ["s4_nochal", "s4_nosweep"], panel_solver=panel_solver)
    assert seen == [panel.Config(challenger=False), panel.Config(sweep=False)]


def _replay_ready(fresh, s4_fake_run):
    """S4's fake run on dev-000, filed where run_replays looks for it."""
    room, trace = s4_fake_run
    out = fresh / "runs" / "s4" / "dev-000.json"
    out.parent.mkdir(parents=True)
    out.with_suffix(".trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    out.write_text(json.dumps({"deal": "dev-000", "system": "s4", "pages": 7.0, "decoy_pages": 2.0}))
    return trace


def test_the_engine_ablations_replay_s4_and_llm_decides_keeps_the_engine_s_walk_away(fresh, s4_fake_run):
    _replay_ready(fresh, s4_fake_run)
    seen = []

    def value(room, rec, mode, trace):
        seen.append(mode)
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 123.0, "reason": "r"})) + "\n")
        return {"usage": {}, "total_cost_usd": 0.05}

    rows = {r["system"]: r for r in pilot.run_replays(fresh, 1, ["s4_noengine", "s4_llmdecides"], value=value)}
    assert seen == ["s4_noengine", "s4_llmdecides"]
    engine = pilot.valuer.replay(fresh / "deals" / "dev-000" / "room", s4_fake_run[1]).decide()[1]
    assert rows["s4_noengine"]["walk_away"] == 123.0 and rows["s4_llmdecides"]["walk_away"] == engine
    assert rows["s4_noengine"]["go"] is True and rows["s4_noengine"]["pages"] == 7.0  # S4's reading
    assert pilot.run_replays(fresh, 1, ["s4_noengine"], value=value) == []  # resumed


def test_a_replay_that_does_not_give_s4_s_call_stops_the_batch(fresh, s4_fake_run):
    trace = _replay_ready(fresh, s4_fake_run)
    flipped = [r | {"args": r["args"] | {"go": not r["args"]["go"]}} if r["tool"] == "submit" else r for r in trace]
    (fresh / "runs" / "s4" / "dev-000.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in flipped))
    with pytest.raises(pilot.valuer.ReplayMismatch):
        pilot.run_replays(fresh, 1, ["s4_noengine"], value=lambda *a: pytest.fail("no valuer turn"))
    splits = json.loads((fresh / "splits.json").read_text())
    (fresh / "splits.json").write_text(json.dumps(splits | {"test": ["dev-001"]}))  # S4 never ran dev-001
    with pytest.raises(RuntimeError, match="missing"):
        pilot.run_replays(fresh, 1, ["s4_noengine"], value=lambda *a: pytest.fail("no valuer turn"), split="test")


def test_a_valuer_turn_that_never_submits_is_scored_as_unanswered(fresh, s4_fake_run):
    """Plan 6 spec, Risks: an unanswered valuer turn gets B0's call, like any unanswered run."""
    _replay_ready(fresh, s4_fake_run)

    def value(room, rec, mode, trace):
        trace.write_text(json.dumps(_row("initialize", {})) + "\n")  # the server ran; no submit
        return {"usage": {}}

    (row,) = pilot.run_replays(fresh, 1, ["s4_noengine"], value=value)
    assert row["answered"] is False and row["go"] == _key(fresh).truth.face_go
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/bench/test_pilot.py -k "split_other or reading_ablations or engine_ablations or does_not_give or never_submits_is_scored_as"`
Expected: 5 failed (`TypeError: run() got an unexpected keyword argument 'split'`, `AttributeError: module
'acqlab.bench.pilot' has no attribute 'ABLATIONS'` / `'run_replays'`).

- [ ] **Step 3: Implement**

In `acqlab/bench/pilot.py`, replace:

```python
"""Pilot runner: single-agent systems on dev deals, scored against the answer keys (Plan 4a design §3; Plan 4b adds
S0 and S3, reframe design §4; Plan 5 adds S4 and its build steps, s4_1 to s4_3, reframe design §5).
```

with:

```python
"""Pilot runner: single-agent systems on dev deals, scored against the answer keys (Plan 4a design §3; Plan 4b adds
S0 and S3, reframe design §4; Plan 5 adds S4 and its build steps, s4_1 to s4_3, reframe design §5; Plan 6 adds the
test split and the ablations: s4_nochal and s4_nosweep as panels, s4_noengine and s4_llmdecides as replays of S4's
runs, Plan 6 spec §3).
```

In `acqlab/bench/pilot.py`, replace:

```python
  uv run python -m acqlab.bench.pilot --data data/v3 --report [--s3 3]           # summary, no Claude
```

with:

```python
  uv run python -m acqlab.bench.pilot --data data/v3 --report [--s3 3]           # summary, no Claude
  uv run python -m acqlab.bench.pilot --data D --split test --n 40 --systems s4_noengine --confirm-claude  # replays
```

In `acqlab/bench/pilot.py`, replace:

```python
from acqlab.agents.panel import STAGES
```

with:

```python
from acqlab.agents.panel import STAGES, Config
```

In `acqlab/bench/pilot.py`, replace:

```python
from acqlab.agents.solver import RunTimeout, solve
```

with:

```python
from acqlab.agents.solver import RunTimeout, solve
from acqlab.bench import valuer
```

In `acqlab/bench/pilot.py`, replace:

```python
ALL = [*SYSTEMS, *STAGES]  # S4's build steps and S4 itself run as panels (acqlab.agents.panel)
```

with:

```python
ABLATIONS = {"s4_nochal": Config(challenger=False), "s4_nosweep": Config(sweep=False)}  # Plan 6 spec §3
PANELS = STAGES | ABLATIONS  # S4's build steps, S4 itself and its reading ablations run as panels
ALL = [*SYSTEMS, *PANELS, *valuer.MODES]  # the engine ablations replay S4's runs (run_replays)
```

In `acqlab/bench/pilot.py`, replace:

```python
def run(data: Path, n: int, systems: list[str], solver: Callable = solve, reps: int = 1,
        flip_only: bool = False, panel_solver: Callable = panel.solve) -> list[dict]:
    """Run each system `reps` times on the first n dev deals (only the decision-flip ones if flip_only), skipping
    finished runs. Raises LLMUnavailable to stop the batch."""
    deals = json.loads((data / "splits.json").read_text())["dev"][:n]
```

with:

```python
def run(data: Path, n: int, systems: list[str], solver: Callable = solve, reps: int = 1,
        flip_only: bool = False, panel_solver: Callable = panel.solve, split: str = "dev") -> list[dict]:
    """Run each system `reps` times on the first n deals of the split (only the decision-flip ones if flip_only),
    skipping finished runs. Raises LLMUnavailable to stop the batch."""
    deals = json.loads((data / "splits.json").read_text())[split][:n]
```

In `acqlab/bench/pilot.py`, replace:

```python
                    cli = (panel_solver(room, budget, trace_path, STAGES[system]) if system in STAGES else
```

with:

```python
                    cli = (panel_solver(room, budget, trace_path, PANELS[system]) if system in PANELS else
```

In `acqlab/bench/pilot.py`, replace:

```python
    ap.add_argument("--n", type=int, default=3, help="first n dev deals")
```

with:

```python
    ap.add_argument("--n", type=int, default=3, help="first n deals of the split")
    ap.add_argument("--split", default="dev", help="dev, or test for the main run (Plan 6)")
```

In `acqlab/bench/pilot.py`, replace:

```python
    try:
        run(args.data, args.n, [s for s in args.systems.split(",") if s], reps=args.reps, flip_only=args.flip_only)
```

with:

```python
    systems = [s for s in args.systems.split(",") if s]
    try:
        run(args.data, args.n, [s for s in systems if s not in valuer.MODES], reps=args.reps,
            flip_only=args.flip_only, split=args.split)
        run_replays(args.data, args.n, [s for s in systems if s in valuer.MODES], split=args.split)
```

Directly above `def s3_rows(rows: list[dict], n: int) -> dict[str, dict]:`, add:

```python
def run_replays(data: Path, n: int, systems: list[str], value: Callable = valuer.value,
                split: str = "dev") -> list[dict]:
    """The engine ablations (Plan 6 spec §3) on the first n deals of the split: S4's final record rebuilt from its
    trace, then one valuer turn. S4's run must exist and the rebuilt record must give its recorded call (else
    valuer.ReplayMismatch). Pages and decoy pages are S4's (the reading is S4's); cost is the valuer turn's alone.
    LLM decides keeps the engine's walk-away. Skips finished runs; raises LLMUnavailable to stop the batch."""
    deals = json.loads((data / "splits.json").read_text())[split][:n]
    rows = []
    for deal in deals:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        room = data / "deals" / deal / "room"
        s4 = data / "runs" / "s4" / f"{deal}.json"
        for system in systems:
            out = data / "runs" / system / f"{deal}.json"
            if out.exists():
                continue
            if not s4.exists():
                raise RuntimeError(f"{system}/{deal}: S4's run is missing, so there is nothing to replay")
            s4_trace = [json.loads(x) for x in s4.with_suffix(".trace.jsonl").read_text().splitlines()]
            rec = valuer.replay(room, s4_trace)
            go, wa = rec.decide()
            if go != next(r for r in s4_trace if r["tool"] == "submit")["args"]["go"]:
                raise valuer.ReplayMismatch(f"{system}/{deal}: the rebuilt record does not give S4's call")
            out.parent.mkdir(parents=True, exist_ok=True)
            trace_path = out.with_suffix(".trace.jsonl")
            trace_path.unlink(missing_ok=True)
            try:
                cli, status = value(room, rec, system, trace_path), "ok"
            except RunTimeout:
                cli, status = None, "timeout"
            trace = [json.loads(x) for x in trace_path.read_text().splitlines()] if trace_path.exists() else []
            if status == "ok" and not trace:
                raise LLMUnavailable(f"{system}/{deal}: the tool server never ran (no trace)")
            row = score(key, system, trace, cli, status) | {"rep": 0}
            s4_row = json.loads(s4.read_text())
            row |= {"pages": s4_row["pages"], "decoy_pages": s4_row["decoy_pages"]}
            if system == "s4_llmdecides":
                row |= {"walk_away": wa, "walk_away_error": abs(wa - key.truth.walk_away) / key.truth.deal.asking_price}
            out.write_text(json.dumps(row, indent=2))
            rows.append(row)
            print(f"{system:10s} {deal} r0: regret {row['regret']:.3f} answered={row['answered']}")
    return rows
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q tests/bench/test_pilot.py`
Expected: 34 passed.

Run: `uv run pytest -q`
Expected: `311 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/pilot.py tests/bench/test_pilot.py
git commit -m "feat(bench): the test split, the panel ablations and the engine-ablation replays (Plan 6, Task 4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 5: The campaign runner

**Files:**
- Create: `acqlab/bench/campaign.py`
- Test: `tests/bench/test_campaign.py`

**Interfaces:**
- Consumes: `pilot.run(..., split=)`, `pilot.run_replays` (Task 4), `valuer.MODES` (Task 3), `testset.fingerprint`
  (Task 2), `llm.LLMUnavailable`.
- Produces: `campaign.N_TEST = 160`, `N_ABLATION = 40`, `FROZEN_TAG`, `FROZEN`, `EXPECTED =
  Path("docs/results/plan-6-test-set.json")`, `EXPECTED_RUNS` (list of (system, rep, deals));
  `phases(data) -> list[(name, step)]`; `counts(data)`, `progress(data) -> str`, `complete(data) -> bool`;
  `resume_at(message: str, now: datetime) -> datetime | None`; `preflight(data, repo, expected=EXPECTED) -> str |
  None`; `campaign(data, repo, *, steps=None, check=preflight, now=..., sleep=..., log=None) -> int`; CLI with
  `--status`, `--stop`, `--confirm-claude` (exit 0 done, 1 stopped, 3 refused).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_campaign.py`:

```python
import json
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from acqlab.bench import campaign, testset
from acqlab.llm import LLMUnavailable

NY = ZoneInfo("America/New_York")


def _at(day, hour, minute):
    return datetime(2026, 9, day, hour, minute, tzinfo=NY)


@pytest.mark.parametrize("message, now, expected", [
    ("You've hit your session limit · resets 4:20pm (America/New_York)", _at(26, 14, 6), _at(26, 16, 25)),
    ("claude -p failed (exit 1): You've hit your session limit · resets 9:20pm (America/New_York)", _at(26, 22, 0),
     _at(27, 21, 25)),  # already past today: tomorrow
    ("resets 12:05am (America/New_York)", _at(26, 23, 50), _at(27, 0, 10)),
    ("resets 9pm (Europe/London)", _at(26, 14, 0), datetime(2026, 9, 26, 21, 5, tzinfo=ZoneInfo("Europe/London"))),
    ("Claude AI usage limit reached", _at(26, 14, 0), None),
])
def test_the_resume_time_is_five_minutes_after_the_next_reset_the_message_names(message, now, expected):
    assert campaign.resume_at(message, now) == expected


def test_a_reset_with_no_zone_is_local_time():
    now = datetime(2026, 9, 26, 14, 0).astimezone()
    assert campaign.resume_at("resets 4am", now) == now.replace(hour=4, minute=5) + timedelta(days=1)


class Clock:
    def __init__(self, start):
        self.t, self.slept = start, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += timedelta(seconds=seconds)


def _run(tmp_path, steps, clock):
    lines = []
    code = campaign.campaign(tmp_path, tmp_path, steps=steps, check=lambda data, repo: None, now=clock.now,
                             sleep=clock.sleep, log=lines.append)
    return code, lines


def test_a_usage_limit_is_waited_out_and_the_phase_resumes(tmp_path):
    clock, calls = Clock(_at(26, 14, 6)), []

    def h1():
        calls.append("h1")
        print("s4 test-000 r0: regret 0.123")  # a run's own line: never reaches the log
        if len(calls) == 1:
            raise LLMUnavailable("claude -p failed (exit 1): You've hit your session limit · resets 4:20pm "
                                 "(America/New_York)")

    code, lines = _run(tmp_path, [("h1", h1), ("s0", lambda: calls.append("s0"))], clock)
    assert code == 0 and calls == ["h1", "h1", "s0"] and clock.slept == [(_at(26, 16, 25) - _at(26, 14, 6)).seconds]
    assert any("waiting until 2026-09-26 16:25" in x for x in lines) and lines[-1] == "campaign complete"
    assert not any("regret" in x for x in lines)


def test_a_limit_with_no_readable_time_waits_thirty_minutes(tmp_path):
    clock, calls = Clock(_at(26, 14, 0)), []

    def h1():
        calls.append(1)
        if len(calls) == 1:
            raise LLMUnavailable("Claude AI usage limit reached")

    assert _run(tmp_path, [("h1", h1)], clock)[0] == 0 and clock.slept == [30 * 60]


def test_any_other_error_gets_one_retry_then_the_campaign_stops(tmp_path):
    clock, calls = Clock(_at(26, 14, 0)), []

    def h1():
        calls.append("h1")
        raise LLMUnavailable("claude -p failed (exit 1): invalid API key")

    code, lines = _run(tmp_path, [("h1", h1), ("s0", lambda: calls.append("s0"))], clock)
    assert code == 1 and calls == ["h1", "h1"] and clock.slept == [600]
    assert "stopped in phase h1: LLMUnavailable: claude -p failed (exit 1): invalid API key" in lines[-1]


def test_a_crash_is_retried_once_too_and_a_failed_check_stops_before_any_run(tmp_path):
    clock = Clock(_at(26, 14, 0))

    def boom():
        raise RuntimeError("s4_noengine/test-003: S4's run is missing, so there is nothing to replay")

    assert _run(tmp_path, [("ablations", boom)], clock)[0] == 1 and clock.slept == [600]
    lines = []
    code = campaign.campaign(tmp_path, tmp_path, steps=[("h1", lambda: pytest.fail("ran"))],
                             check=lambda data, repo: "the test set does not match its committed fingerprint",
                             log=lines.append)
    assert code == 1 and lines == ["stopped before phase h1: the test set does not match its committed fingerprint"]


def _repo(tmp_path):
    """A git repo with S4's frozen files tagged and a data dir whose fingerprint is committed."""
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / "acqlab" / "agents").mkdir(parents=True)
    (repo / "acqlab" / "agents" / "panel.py").write_text("S4 = 1\n")
    (data / "truth").mkdir(parents=True)
    (data / "truth" / "test-000.json").write_text('{"truth": {"seed": 3510000}}')
    (repo / campaign.EXPECTED).parent.mkdir(parents=True)
    (repo / campaign.EXPECTED).write_text(json.dumps(testset.fingerprint(data)))
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "frozen"], ["tag", campaign.FROZEN_TAG]):
        subprocess.run(git + cmd, check=True)
    return repo, data


def test_the_preflight_refuses_an_edited_or_added_s4_file_and_a_changed_test_set(tmp_path):
    repo, data = _repo(tmp_path)
    assert campaign.preflight(data, repo) is None
    (repo / "acqlab" / "agents" / "panel.py").write_text("S4 = 2\n")
    assert "differ from s4-frozen-plan5" in campaign.preflight(data, repo)
    (repo / "acqlab" / "agents" / "panel.py").write_text("S4 = 1\n")
    (repo / "acqlab" / "agents" / "new.py").write_text("")
    assert "new.py" in campaign.preflight(data, repo)
    (repo / "acqlab" / "agents" / "new.py").unlink()
    (data / "truth" / "test-000.json").write_text('{"truth": {"seed": 3510001}}')
    assert campaign.preflight(data, repo) == "the test set does not match its committed fingerprint"


def test_progress_counts_each_system_s_finished_test_runs(tmp_path):
    for rel in ("s1b/test-000.json", "s1b/test-000.r1.json", "s1b/test-001.json", "s4/test-000.json",
                "s4/test-000.trace.jsonl", "s1b/dev-000.json"):
        (tmp_path / "runs" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "runs" / rel).write_text("{}")
    assert campaign.progress(tmp_path).startswith("s1b 2/160, s4 1/160, s1b rep 1 1/160, s4_nochal 0/40")
    assert not campaign.complete(tmp_path)


def test_the_cli_refuses_without_the_flag_and_reports_status(tmp_path, capsys):
    assert campaign.main(["--data", str(tmp_path)]) == 3
    (tmp_path / "campaign.log").write_text("2026-09-27 10:00:00 EDT phase h1: running\n")
    assert campaign.main(["--data", str(tmp_path), "--status"]) == 0
    out = capsys.readouterr().out
    assert "not running; s1b 0/160" in out and "phase h1: running" in out
    assert campaign.main(["--data", str(tmp_path), "--stop"]) == 0 and "no campaign" in capsys.readouterr().out
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/bench/test_campaign.py`
Expected: a collection error, `ImportError: cannot import name 'campaign' from 'acqlab.bench'`.

- [ ] **Step 3: Implement**

Create `acqlab/bench/campaign.py`:

```python
"""The Plan 6 main run as one resumable campaign (spec §4): three phases in a fixed order, each checked against the
frozen S4 and the committed test-set fingerprint first; usage limits are waited out; the log shows progress counts,
never results.

  nohup caffeinate -i uv run python -m acqlab.bench.campaign --data data/test-r2 --confirm-claude \\
    > data/test-r2/campaign.out 2>&1 &
  uv run python -m acqlab.bench.campaign --data data/test-r2 --status
  uv run python -m acqlab.bench.campaign --data data/test-r2 --stop

Exit codes: 0 every phase done; 1 stopped (a failed check, or an error that survived one retry; see the log); 3
refused (no --confirm-claude, or already running)."""
import argparse
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from acqlab.bench import pilot, testset, valuer
from acqlab.llm import LLMUnavailable

N_TEST, N_ABLATION = 160, 40
FROZEN_TAG, FROZEN = "s4-frozen-plan5", ("acqlab/agents", "acqlab/routers")
EXPECTED = Path("docs/results/plan-6-test-set.json")  # the committed fingerprint, relative to the repo
AFTER_RESET = timedelta(minutes=5)
UNREADABLE_WAIT = timedelta(minutes=30)  # a usage limit whose message names no time
RETRY_WAIT = timedelta(minutes=10)  # any other error: one retry, then stop
RESET = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b(?:\s*\(([^)]+)\))?", re.I)
# (system, rep, deals): the runs the campaign owes, for progress and completeness
EXPECTED_RUNS = [("s1b", 0, N_TEST), ("s4", 0, N_TEST), ("s1b", 1, N_TEST), ("s4_nochal", 0, N_ABLATION),
                 ("s4_nosweep", 0, N_ABLATION), ("s4_noengine", 0, N_TEST), ("s4_llmdecides", 0, N_TEST),
                 ("s0", 0, N_TEST)]


def phases(data: Path) -> list[tuple[str, Callable[[], object]]]:
    """(name, step) in the spec's order; every step skips finished runs, so a restart resumes."""
    return [
        ("h1", lambda: (pilot.run(data, N_TEST, ["s1b", "s4"], split="test"),
                        pilot.run(data, N_TEST, ["s1b"], reps=2, split="test"))),  # S3's second S1b run
        ("ablations", lambda: (pilot.run(data, N_ABLATION, ["s4_nochal", "s4_nosweep"], split="test"),
                               pilot.run_replays(data, N_TEST, list(valuer.MODES), split="test"))),
        ("s0", lambda: pilot.run(data, N_TEST, ["s0"], split="test")),
    ]


def counts(data: Path) -> dict[tuple[str, int], int]:
    """Finished runs per (system, rep), test split only."""
    out = {}
    for system, rep, _ in EXPECTED_RUNS:
        runs = (data / "runs" / system).glob("test-*.json" if rep == 0 else f"test-*.r{rep}.json")
        out[(system, rep)] = sum(rep > 0 or p.name.count(".") == 1 for p in runs)  # rep 0: not test-000.r1.json
    return out


def progress(data: Path) -> str:
    done = counts(data)
    return ", ".join(f"{s}{f' rep {r}' if r else ''} {done[(s, r)]}/{n}" for s, r, n in EXPECTED_RUNS)


def complete(data: Path) -> bool:
    done = counts(data)
    return all(done[(s, r)] >= n for s, r, n in EXPECTED_RUNS)


def resume_at(message: str, now: datetime) -> datetime | None:
    """When to resume after a usage-limit message: AFTER_RESET past the next time it names ("resets 9:20pm
    (America/New_York)"; no zone means local time), or None if it names no time."""
    m = RESET.search(message)
    if not m:
        return None
    hour, minute = int(m[1]) % 12 + (12 if m[3].lower() == "pm" else 0), int(m[2] or 0)
    try:
        tz = ZoneInfo(m[4]) if m[4] else now.astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        tz = now.astimezone().tzinfo
    local = now.astimezone(tz)
    at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if at <= local:
        at += timedelta(days=1)
    return at + AFTER_RESET


def preflight(data: Path, repo: Path, expected: Path = EXPECTED) -> str | None:
    """Why the campaign must not run now, or None: S4's files must match the frozen tag (no edits, no new files),
    and the test set must match its committed fingerprint."""
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", FROZEN_TAG, "--", *FROZEN],
                          capture_output=True, text=True)
    new = subprocess.run(["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "--", *FROZEN],
                         capture_output=True, text=True)
    if diff.returncode != 0 or new.returncode != 0 or new.stdout.strip():
        return f"S4's files differ from {FROZEN_TAG} ({(diff.stderr + new.stdout).strip()[:300] or 'edited'})"
    if testset.fingerprint(data) != json.loads((repo / expected).read_text()):
        return "the test set does not match its committed fingerprint"
    return None


def campaign(data: Path, repo: Path, *, steps: list | None = None, check: Callable = preflight,
             now: Callable[[], datetime] = lambda: datetime.now().astimezone(), sleep: Callable = time.sleep,
             log: Callable[[str], None] | None = None) -> int:
    """Run every phase to the end. A usage limit is waited out; any other error gets one retry after RETRY_WAIT
    (again after progress resumes), then the campaign stops. Runs' own output (it carries regret) is never logged."""
    log = log or logger(data)
    for name, step in (phases(data) if steps is None else steps):
        retried, at_error = False, None
        while True:
            problem = check(data, repo)
            if problem:
                log(f"stopped before phase {name}: {problem}")
                return 1
            log(f"phase {name}: running ({progress(data)})")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    step()
                break
            except Exception as e:  # every failure is either waited out, retried once or reported
                text = f"{type(e).__name__}: {e}"
                wake = resume_at(str(e), now()) if isinstance(e, LLMUnavailable) else None
                if isinstance(e, LLMUnavailable) and (wake or "limit" in str(e).lower()):
                    wake = wake or now() + UNREADABLE_WAIT
                    log(f"usage limit in phase {name} ({progress(data)}); waiting until {wake:%Y-%m-%d %H:%M %Z}")
                else:
                    if progress(data) != at_error:  # progress since the last error: it gets its own retry
                        retried = False
                    if retried:
                        log(f"stopped in phase {name}: {text}")
                        return 1
                    retried, at_error, wake = True, progress(data), now() + RETRY_WAIT
                    log(f"error in phase {name}: {text}; one retry at {wake:%Y-%m-%d %H:%M %Z}")
                sleep(max(0.0, (wake - now()).total_seconds()))
        log(f"phase {name}: done ({progress(data)})")
    log("campaign complete")
    return 0


def logger(data: Path) -> Callable[[str], None]:
    def log(line: str) -> None:
        with (data / "campaign.log").open("a") as f:
            f.write(f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z} {line}\n")
    return log


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path("."), help="the repo holding the frozen tag and the fingerprint")
    ap.add_argument("--confirm-claude", action="store_true", help="required to make real Claude calls")
    ap.add_argument("--status", action="store_true", help="progress and the log's last lines; no Claude")
    ap.add_argument("--stop", action="store_true", help="stop a running campaign (it resumes when started again)")
    args = ap.parse_args(argv)
    pid_file, log_file = args.data / "campaign.pid", args.data / "campaign.log"
    pid = int(pid_file.read_text()) if pid_file.exists() else None
    running = pid is not None and _alive(pid)
    if args.status:
        print(f"{'running (pid ' + str(pid) + ')' if running else 'not running'}; {progress(args.data)}")
        print("".join((log_file.read_text().splitlines(keepends=True) if log_file.exists() else [])[-5:]), end="")
        return 0
    if args.stop:
        if running:
            os.kill(pid, signal.SIGTERM)
            print(f"stopped the campaign (pid {pid})")
        else:
            print("no campaign is running")
        return 0
    if not args.confirm_claude:
        print("Refusing to run: this uses your Claude subscription for days. Add --confirm-claude to proceed.")
        return 3
    if running:
        print(f"Refusing to run: a campaign is already running (pid {pid}).")
        return 3
    pid_file.write_text(str(os.getpid()))
    log = logger(args.data)
    signal.signal(signal.SIGTERM, lambda *_: (log("stopped by --stop"), pid_file.unlink(missing_ok=True),
                                              sys.exit(1)))
    try:
        return campaign(args.data, args.repo.resolve(), log=log)
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q tests/bench/test_campaign.py`
Expected: 13 passed.

Run: `uv run pytest -q`
Expected: `324 passed`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/campaign.py tests/bench/test_campaign.py
git commit -m "feat(bench): the resumable campaign runner for the main run (Plan 6, Task 5)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: The analysis (H1–H6)

**Files:**
- Create: `acqlab/bench/analysis.py`
- Test: `tests/bench/test_analysis.py`

**Interfaces:**
- Consumes: `campaign.complete`, `campaign.progress`, `campaign.EXPECTED` (Task 5); `testset.fingerprint` (Task 2);
  `pilot.ALL`, `pilot.s3_rows`, `pilot.s1b_matched`, `pilot.summarize` (Task 4 and Plan 5); `bootstrap_ci`.
- Produces: `analysis.analyse(by, real, first_plan) -> dict` with keys `H1`…`H6` (each with `holds`: True/False, or
  `"too few to test"` for H6) and `also`; `analysis.load(data) -> (by, real, first_plan, rows)`; CLI
  `--data --out [--repo]` (refuses, exit 1, unless the campaign is complete and the fingerprint matches).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_analysis.py`:

```python
import pytest

from acqlab.bench import analysis

CASES = ["interaction", "flip", "clean", "decoy", "unresolvable"] * 4  # 20 deals, 4 of each case type


def _rows(regret=0.0, wae=0.05, decoy=1.0, **by_case):
    """deal -> row; by_case overrides regret for a case type."""
    return {f"test-{i:03d}": {"case_type": c, "regret": by_case.get(c, regret), "walk_away_error": wae,
                              "decoy_pages": decoy} for i, c in enumerate(CASES)}


def _by(**systems):
    base = {"s1b": _rows(0.02), "s3": _rows(0.01), "s4": _rows(0.0), "s4_nochal": _rows(0.0),
            "s4_nosweep": _rows(0.0), "s4_noengine": _rows(wae=0.2), "s4_llmdecides": _rows(0.0),
            "s1b_matched": _rows(0.02)}
    return base | systems


def _analyse(by, missed=0):
    real = {d: {"nwc"} for d in by["s4"]}
    first = {d: (set() if i < missed else {"nwc"}) for i, d in enumerate(sorted(by["s4"]))}
    return analysis.analyse(by, real, first)


def test_h1_needs_a_25_percent_cut_a_ci_below_zero_and_s4_below_s3():
    s1b = {d: r | {"regret": 0.02 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}  # varied, so the CI is real
    out = _analyse(_by(s1b=s1b))["H1"]
    assert out["cut"] == 1.0 and out["s4_minus_s1b"]["ci95"][1] < 0 and out["holds"] is True
    assert _analyse(_by(s1b=s1b, s3=_rows(0.0)))["H1"]["holds"] is False  # not below S3
    s4 = {d: r | {"regret": 0.016 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}
    assert _analyse(_by(s1b=s1b, s4=s4))["H1"]["holds"] is False  # a 20% cut
    assert set(out["s4_minus_s1b"]["by_case"]) == set(analysis.CASES)


def test_h2_holds_when_the_gain_sits_on_interaction_and_flip_deals():
    s1b = _rows(0.0, interaction=0.05, flip=0.04)
    s1b["test-000"] = s1b["test-000"] | {"regret": 0.06}  # some spread inside the target group
    out = _analyse(_by(s1b=s1b))["H2"]
    assert out["n_target"] == 8 and out["n_rest"] == 12 and out["gap"] > 0 and out["holds"] is True
    assert _analyse(_by(s1b=_rows(0.02)))["H2"]["holds"] is False  # the same gain everywhere


def test_h3_and_h4_are_one_sided_paired_comparisons():
    nochal = {d: r | {"regret": 0.03 * (i % 3 > 0)} for i, (d, r) in enumerate(_rows().items())}
    assert _analyse(_by(s4_nochal=nochal))["H3"]["holds"] is True
    assert _analyse(_by())["H3"]["holds"] is False  # no difference: not shown
    s4 = {d: r | {"decoy_pages": 1.0 - 0.5 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}
    assert _analyse(_by(s4=s4))["H4"]["holds"] is True


def test_h5_needs_walk_away_error_to_at_least_double():
    noengine = {d: r | {"walk_away_error": 0.2 + 0.01 * (i % 3)} for i, (d, r) in enumerate(_rows().items())}
    out = _analyse(_by(s4_noengine=noengine))["H5"]
    assert out["ratio"] == pytest.approx(0.21 / 0.05, rel=0.05) and out["holds"] is True
    assert _analyse(_by(s4_noengine=_rows(wae=0.09)))["H5"]["holds"] is False  # 1.8x


def test_h6_looks_only_at_deals_where_a_real_trap_was_missing_from_the_first_plan():
    assert _analyse(_by(), missed=3)["H6"]["holds"] == "too few to test"
    nosweep = {d: r | {"regret": 0.03 + 0.01 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}
    out = _analyse(_by(s4_nosweep=nosweep), missed=6)["H6"]
    assert out["deals"] == [f"test-{i:03d}" for i in range(6)] and out["holds"] is True


def test_the_pessimism_control_and_llm_decides_are_reported_beside_the_hypotheses():
    out = _analyse(_by())
    assert out["also"]["s4_minus_s1b_matched"]["diff"] == pytest.approx(-0.02)
    assert out["also"]["llmdecides_minus_s4"]["n"] == 20


def test_the_analysis_refuses_to_run_before_the_campaign_is_complete(tmp_path, capsys):
    assert analysis.main(["--data", str(tmp_path), "--out", str(tmp_path / "r.json")]) == 1
    assert "not complete (s1b 0/160" in capsys.readouterr().out and not (tmp_path / "r.json").exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/bench/test_analysis.py`
Expected: a collection error, `ImportError: cannot import name 'analysis' from 'acqlab.bench'`.

- [ ] **Step 3: Implement**

Create `acqlab/bench/analysis.py`:

```python
"""The Plan 6 analysis (spec §5; the pre-registration and its addendum): H1-H6 exactly as locked, run once after every
phase of the campaign is complete. Every comparison is a paired per-deal difference with a paired bootstrap 95% CI,
also reported by case type.

  uv run python -m acqlab.bench.analysis --data data/test-r2 --out docs/results/plan-6-main-run.json
"""
import argparse
import json
from pathlib import Path

import numpy as np

from acqlab.bench import campaign, pilot, testset
from acqlab.generator.batch import AnswerKey
from acqlab.routers.track_a import bootstrap_ci

CASES = ("clean", "decoy", "flip", "interaction", "unresolvable")
TARGET = ("interaction", "flip")  # H2: interaction and belief-error deals; belief-error = the flip case type
H1_CUT, H5_FACTOR, H6_MIN = 0.25, 2.0, 5  # H1's 25% cut; "sharply" in H5 = at least double; H6's fewest deals
BOOT, SEED = 2000, 0
EPS = 1e-12  # float noise: a CI that only rounds away from zero does not exclude it


def _ci(d: np.ndarray) -> list:
    return list(bootstrap_ci(d, BOOT, SEED)) if len(d) > 1 else [float(d[0])] * 2 if len(d) else [None, None]


def compare(a: dict, b: dict, field: str = "regret", deals: list | None = None) -> dict:
    """a − b per deal (on `deals`, else the deals both have): n, mean, CI, and the same by case type."""
    ds = sorted(set(a) & set(b) if deals is None else deals)

    def one(sub: list) -> dict:
        d = np.array([a[x][field] - b[x][field] for x in sub], dtype=float)
        return {"n": len(sub), "diff": float(d.mean()) if len(d) else None, "ci95": _ci(d)}

    return one(ds) | {"by_case": {c: one([x for x in ds if a[x]["case_type"] == c]) for c in CASES}}


def below(c: dict) -> bool:
    """The CI lies wholly below zero."""
    return c["ci95"][1] is not None and c["ci95"][1] < -EPS


def above(c: dict) -> bool:
    return c["ci95"][0] is not None and c["ci95"][0] > EPS


def mean(rows: dict, field: str = "regret") -> float:
    return float(np.mean([r[field] for r in rows.values()]))


def gap(s1b: dict, s4: dict) -> dict:
    """H2: the mean gain (S1b − S4 regret) on interaction and flip deals minus the mean gain on the rest, with a
    bootstrap CI that resamples within each group."""
    deals = sorted(set(s1b) & set(s4))
    gain = {d: s1b[d]["regret"] - s4[d]["regret"] for d in deals}
    a = np.array([gain[d] for d in deals if s4[d]["case_type"] in TARGET])
    b = np.array([gain[d] for d in deals if s4[d]["case_type"] not in TARGET])
    if len(a) < 2 or len(b) < 2:
        return {"n_target": len(a), "n_rest": len(b), "gap": None, "ci95": [None, None]}
    rng = np.random.default_rng(SEED)
    boot = (a[rng.integers(0, len(a), (BOOT, len(a)))].mean(axis=1)
            - b[rng.integers(0, len(b), (BOOT, len(b)))].mean(axis=1))
    return {"n_target": len(a), "n_rest": len(b), "gap": float(a.mean() - b.mean()),
            "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]}


def analyse(by: dict[str, dict[str, dict]], real: dict[str, set], first_plan: dict[str, set]) -> dict:
    """by: system -> deal -> row (s1b, s3, s4, the ablations, s1b_matched); real: deal -> the traps with a nonzero
    amount; first_plan: deal -> the issue types in S4's first Deal Lead plan."""
    s1b, s3, s4 = by["s1b"], by["s3"], by["s4"]
    h1 = compare(s4, s1b)
    cut = 1 - mean(s4) / mean(s1b) if mean(s1b) else None
    out = {"H1": {"s4": mean(s4), "s1b": mean(s1b), "s3": mean(s3), "cut": cut, "s4_minus_s1b": h1,
                  "s4_minus_s3": compare(s4, s3),
                  "holds": cut is not None and cut >= H1_CUT and below(h1) and mean(s4) < mean(s3)}}
    out["H2"] = gap(s1b, s4)
    out["H2"]["holds"] = above(out["H2"])
    h3 = compare(by["s4_nochal"], s4)
    out["H3"] = {"nochal_minus_s4": h3, "holds": above(h3)}
    h4 = compare(s4, s1b, "decoy_pages")
    out["H4"] = {"s4_minus_s1b": h4, "holds": below(h4)}
    noengine = by["s4_noengine"]
    h5 = compare(noengine, s4, "walk_away_error")
    ratio = mean(noengine, "walk_away_error") / mean(s4, "walk_away_error") if mean(s4, "walk_away_error") else None
    out["H5"] = {"noengine": mean(noengine, "walk_away_error"), "s4": mean(s4, "walk_away_error"), "ratio": ratio,
                 "noengine_minus_s4": h5, "holds": ratio is not None and ratio >= H5_FACTOR and above(h5)}
    missed = sorted(d for d in by["s4_nosweep"] if d in s4 and real[d] - first_plan[d])
    h6 = compare(by["s4_nosweep"], s4, deals=missed)
    out["H6"] = {"deals": missed, "nosweep_minus_s4": h6,
                 "holds": "too few to test" if len(missed) < H6_MIN else above(h6)}
    out["also"] = {"s4_minus_s1b_matched": compare(s4, by["s1b_matched"]),
                   "llmdecides_minus_s4": compare(by["s4_llmdecides"], s4)}
    return out


def load(data: Path) -> tuple[dict, dict, dict, list]:
    """(by, real, first_plan, rows) from a finished campaign's test-split runs."""
    rows = [json.loads(p.read_text()) for s in pilot.ALL for p in sorted((data / "runs" / s).glob("test-*.json"))]
    by = {s: {r["deal"]: r for r in rows if r["system"] == s and r.get("rep", 0) == 0} for s in pilot.ALL}
    by["s3"] = pilot.s3_rows(rows, 2)
    by["s1b_matched"] = pilot.s1b_matched(by["s1b"], by["s4"])
    real, first_plan = {}, {}
    for deal in by["s4"]:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        real[deal] = {f.trap for f in key.truth.facts if f.amount > 0}
        trace = [json.loads(x) for x in (data / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
        plan = next((r for r in trace if r["tool"] == "propose" and not r["refused"]), None)
        first_plan[deal] = {i["type"] for i in plan["args"]["issues"]} if plan else set()
    return by, real, first_plan, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if not campaign.complete(args.data):
        print(f"Refusing to analyse: the campaign is not complete ({campaign.progress(args.data)})")
        return 1
    if testset.fingerprint(args.data) != json.loads((args.repo / campaign.EXPECTED).read_text()):
        print("Refusing to analyse: the test set does not match its committed fingerprint")
        return 1
    by, real, first_plan, rows = load(args.data)
    result = analyse(by, real, first_plan) | {"systems": pilot.summarize(rows, s3_n=2)}
    args.out.write_text(json.dumps(result, indent=2))
    for h in ("H1", "H2", "H3", "H4", "H5", "H6"):
        print(f"{h}: {result[h]['holds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q tests/bench/test_analysis.py`
Expected: 7 passed.

Run: `uv run pytest -q`
Expected: `331 passed`.

Run: `git diff --quiet s4-frozen-plan5 -- acqlab/agents acqlab/routers && echo frozen`
Expected: `frozen`.

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/analysis.py tests/bench/test_analysis.py
git commit -m "feat(bench): the H1-H6 analysis for the main run (Plan 6, Task 6)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: The addendum, the prompt log and the free rehearsal (controller; no Claude or Codex calls)

The addendum must be committed **before** Task 9 generates any test deal.

- [ ] **Step 1: Write the pre-registration addendum**

Create `docs/results/plan-6-preregistration-addendum.md`:

```markdown
# Pre-registration addendum: the Plan 6 main run (2026-09-27)

Written before any test deal is generated. It adds only what `plan-4b-preregistration.md` leaves open; H1–H6 are
unchanged. Design: `docs/superpowers/specs/2026-09-27-plan-6-main-run-design.md`. Code: `acqlab/bench/testset.py`,
`valuer.py`, `pilot.py`, `campaign.py`, `analysis.py`.

## Scope (user, 2026-09-27)

- On all 160 test deals: S1b; S3 with N = 2 (the majority of two S1b runs; a 1-1 tie is no-go, as `pilot.s3_rows`
  has done since Plan 4b); S4 at tag `s4-frozen-plan5`; S0.
- Not run: the budget sweep, repeat seeds on a subset and the hand-reviewed deals. The showcase deal moves to Plan 7.

## Definitions

- **H2's belief-error deals are the `flip` case type.** The target group is `interaction` and `flip`; the rest is
  `clean`, `decoy` and `unresolvable`.
- **The ablations:** −Challenger (`s4_nochal`, the frozen panel with the Challenger off; the router's two-pass reading
  is kept) and −residual sweep (`s4_nosweep`), full runs on `test-000` to `test-039`. −engine (`s4_noengine`) and LLM
  decides (`s4_llmdecides`): S4's final Deal Record rebuilt from its trace, then one valuer turn, on all 160 deals.
  −engine's valuer sees no engine output and gives the walk-away and the call; LLM decides' valuer sees the engine's
  median walk-away and its 10–90% range, gives the call and keeps the engine's walk-away.
- **H6:** a real trap is a fact with a nonzero amount; S4's first plan is its first accepted Deal Lead proposal.

## Pass/fail rules

Every comparison is a paired per-deal difference with a paired bootstrap 95% CI (2,000 resamples, seed 0), also
reported by case type. A CI "excludes zero" only if its bound clears zero by more than 1e-12 (float noise).

| | Deals | Holds if |
|---|---|---|
| H1 | 160 | S4's mean regret is at least 25% below S1b's, the CI on S4 − S1b lies below zero, and S4's mean regret is below S3's. |
| H2 | 160 | The mean gain (S1b − S4) on interaction and flip deals minus the mean gain on the rest is above zero, with a CI (resampling within each group) above zero. |
| H3 | 40 | −Challenger's regret exceeds S4's; CI above zero. |
| H4 | 160 | S4's decoy pages are below S1b's; CI below zero. |
| H5 | 160 | −engine's mean walk-away error is at least twice S4's, and the CI on the difference is above zero. |
| H6 | the 40 | On the deals where a real trap is missing from S4's first plan, −sweep's regret exceeds S4's; CI above zero. Fewer than 5 such deals: "too few to test". |

## Also reported (no pass/fail)

The pessimism control beside H1 (S4 − `s1b_matched`: S1b's least confident GO calls switched to NO-GO until it says
NO-GO as often as S4); LLM decides − S4; for every system, correct calls, walk-away error, pages, decoy pages,
sessions and cost; S0 and the no-AI floors. H3 and H6 have 40 deals and little power: a CI that includes zero is
reported as "not shown", not as evidence against.

## The test set

`--seed 3500000 --profile r2 --test 160` (test seeds 3,510,000–3,510,159), checked before generation against every seed
on disk (no match, modulo the 1,000,000 retry offset); its answer keys' fingerprint is committed at once
(`plan-6-test-set.json`). Recoverability: 20 test deals drawn with numpy seed 0 (`testset.recover_sample`), Codex as
the extractor, and any call where Codex used a tool counts as a failure. Any failure stops the main run until it is
understood; failures are reported, not regenerated.

## Conduct

No early stopping and no peeking: the campaign logs progress counts only, and the analysis runs once, after every
phase. If a run cannot complete (for example, a replay that does not give S4's call), the campaign stops and the user
decides; nothing is dropped silently.
```

- [ ] **Step 2: Write the prompt log**

Create `docs/results/plan-6-prompt-log.md`:

```markdown
# Plan 6 prompt log

## The valuer (2026-09-27)

- **What.** A new prompt for the engine ablations' one valuer turn (`acqlab/bench/valuer.py`, `SYSTEM` and `TASK`):
  the teaser, the deal team's findings (`Record.view()` without its first line, the engine's call) and, for LLM
  decides only, the engine's median walk-away and its 10–90% range. Tools: submit only; reading budget 0.
- **Why.** Spec §3: −engine tests whether an LLM can do the final valuation and call without the engine (H5); LLM
  decides tests whether the code decision matters.
- **Parity.** An S4 ablation's prompt; S1b's prompt is unchanged. It carries no diligence knowledge beyond the issue
  types' definitions, which S1b's tools already state (`server.ADJUSTMENTS`).
- **Checked on:** see Task 8's real rehearsal below.
```

- [ ] **Step 3: Add the rehearsal script and run it**

Create `docs/results/scripts/plan-6-rehearsal.py`:

```python
"""The Plan 6 rehearsal, step 1 (spec §6): the whole campaign and the analysis on 3 throwaway test-split deals with
the fake claude from the tests. No Claude or Codex calls, no quota.

  uv run python docs/results/scripts/plan-6-rehearsal.py <empty scratch dir>

The deals use seed 3,800,000 (test seeds 3,810,000-3,810,002), clear of the real test set's 3,510,000-3,510,159."""
import json
import os
import sys
from pathlib import Path

from acqlab.bench import analysis, campaign, pilot, testset
from acqlab.generator import batch

out = Path(sys.argv[1]).resolve()
data, repo = out / "data", Path(".").resolve()
assert testset.clashes(3_800_000, 3, {3_510_000 + i for i in range(160)}) == []
assert batch.run(data, {"dev": 0, "test": 3, "hand": 0, "showcase": 0}, seed=3_800_000, mc=20) == []
expected = out / "fingerprint.json"
expected.write_text(json.dumps(testset.fingerprint(data)))

fake = out / "claude"  # the tests' fake claude; the solver's env allowlist drops FAKE_*, so it runs in "ok" mode
fake.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(repo / 'tests/agents/fake_claude.py')!r}, "
                "run_name='__main__')\n")
fake.chmod(0o755)
os.environ["CLAUDE_BIN"] = str(fake)

campaign.N_TEST, campaign.N_ABLATION = 3, 2
campaign.EXPECTED_RUNS = [(s, r, 3 if n == 160 else 2) for s, r, n in campaign.EXPECTED_RUNS]
code = campaign.campaign(data, repo, check=lambda d, r: campaign.preflight(d, r, expected))
print("campaign exit", code, "|", campaign.progress(data))
print((data / "campaign.log").read_text())
assert code == 0 and campaign.complete(data)
assert "regret" not in (data / "campaign.log").read_text()

by, real, first_plan, rows = analysis.load(data)
result = analysis.analyse(by, real, first_plan) | {"systems": pilot.summarize(rows, s3_n=2)}
print({h: result[h]["holds"] for h in ("H1", "H2", "H3", "H4", "H5", "H6")})
print("systems:", sorted(result["systems"]["systems"]))
```

Run (about 6 minutes; the fake claude, no quota):

```bash
mkdir -p "$TMPDIR/plan6-rehearsal" && rm -rf "$TMPDIR/plan6-rehearsal"/*
uv run python docs/results/scripts/plan-6-rehearsal.py "$TMPDIR/plan6-rehearsal"
```

Expected: `campaign exit 0 | s1b 3/3, s4 3/3, s1b rep 1 3/3, s4_nochal 2/2, s4_nosweep 2/2, s4_noengine 3/3,
s4_llmdecides 3/3, s0 3/3`; the printed log has `phase h1`, `phase ablations` and `phase s0` each running then done,
then `campaign complete`, and no line containing `regret`; then a dict of H1–H6 verdicts (meaningless on 3 fake
deals) and the systems list including `s1b_matched`, `s3`, `s4_llmdecides`, `s4_nochal`, `s4_noengine` and
`s4_nosweep`. Any other outcome: stop and fix before Task 8.

- [ ] **Step 4: Commit (before any test deal exists)**

```bash
git add docs/results/plan-6-preregistration-addendum.md docs/results/plan-6-prompt-log.md docs/results/scripts/plan-6-rehearsal.py
git commit -m "docs: Plan 6 pre-registration addendum, prompt log and rehearsal (Plan 6, Task 7)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: The valuer on real Claude (controller; needs the user's OK; a few cents)

- [ ] **Step 1: Ask the user.** Four valuer turns (−engine and LLM decides on 2 `cal-r2` dev deals, from their
existing S4 runs), about $0.20 notional. Do not run without an explicit yes.

- [ ] **Step 2: Run on a copy of `cal-r2`** (so its dev runs stay as they were):

```bash
rm -rf "$TMPDIR/cal-r2-valuer" && cp -R data/cal-r2 "$TMPDIR/cal-r2-valuer"
export CLAUDE_BIN="$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude"
uv run python -m acqlab.bench.pilot --data "$TMPDIR/cal-r2-valuer" --n 2 --systems s4_noengine,s4_llmdecides --confirm-claude
```

Expected: four lines `s4_noengine dev-000 …`, `s4_llmdecides dev-000 …`, and the same for dev-001, each with
`answered=True`. Check each row in `$TMPDIR/cal-r2-valuer/runs/s4_noengine/*.json` and `s4_llmdecides/*.json`:
`answered` true, `walk_away` a positive number (for LLM decides, the engine's median), `cost_usd` around 0.05. If a
turn did not submit, read its `.trace.jsonl` and stop: any prompt change goes back through review and the prompt log.

- [ ] **Step 3: Record and commit.** Append to `docs/results/plan-6-prompt-log.md` under "Checked on": the date, the 2
deals, each turn's call and walk-away against S4's, and the cost. Then:

```bash
git add docs/results/plan-6-prompt-log.md
git commit -m "docs: the valuer checked on real Claude (Plan 6, Task 8)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Generate the test set, once (controller; no LLM calls)

- [ ] **Step 1: The seed check**

```bash
uv run python -m acqlab.bench.testset seeds --base 3500000 --n 160 --roots /Users/dwightbritton/Developer/acquisition-lab /private/tmp/claude-501
```

Expected: exit 0 and `clashes with base 3500000: none` (2,257 or more seeds used). A clash: stop and ask the user.

- [ ] **Step 2: Generate**

```bash
test ! -e data/test-r2 && uv run python -m acqlab.generator.batch --out data/test-r2 --dev 0 --test 160 --hand 0 --showcase 0 --seed 3500000 --profile r2
```

Expected: `generated 160 deals into data/test-r2; 0 batch problems` (the word-leak check runs at 160 deals). Any
problem: stop and report to the user; never regenerate on another seed without the user.

- [ ] **Step 3: Fingerprint and record**

```bash
uv run python -m acqlab.bench.testset fingerprint --data data/test-r2 > docs/results/plan-6-test-set.json
uv run python - <<'EOF'
import collections, json
from pathlib import Path
t = [json.loads(p.read_text())["truth"] for p in sorted(Path("data/test-r2/truth").glob("*.json"))]
print(len(t), dict(collections.Counter(x["case_type"] for x in t)), "flips", sum(x["go"] != x["face_go"] for x in t),
      "GO", sum(x["go"] for x in t), {x["generator_version"] for x in t}, {x["profile"] for x in t})
EOF
```

Create `docs/results/plan-6-test-set.md` with: the command above, the date, generator version and profile, the case
mix, decision flips and GO counts printed above, "0 batch problems", the `all` hash from `plan-6-test-set.json`, and
the sentence "No system has been run on these deals." (Counts only: no deal is opened or read.)

- [ ] **Step 4: Commit at once**

```bash
git add docs/results/plan-6-test-set.json docs/results/plan-6-test-set.md
git commit -m "docs: the Plan 6 test set, generated once, and its fingerprint (Plan 6, Task 9)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The recoverability gate (controller; Codex; needs the user's OK)

- [ ] **Step 1: Check Codex and ask the user.** Run
`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex login status` (expect "Logged in using ChatGPT"; the
user's Codex account is dacuber01). Tell the user: about 200 Codex calls on their account, possibly over several
usage windows (calls are cached, so a rerun resumes). Do not run without an explicit yes. If Codex is out of usage and
everything else is ready, ask the user how to proceed.

- [ ] **Step 2: Run**

```bash
uv run python -m acqlab.bench.testset recover --data data/test-r2 --n 20 --confirm-codex
```

Expected: `checked 20 deals: test-…` and `0 problems`, exit 0. Exit 2: Codex stopped at a limit; rerun the same
command later. Exit 1: problems. Stop, report them to the user, and do not start the campaign (spec §2).

- [ ] **Step 3: Record and commit.** Append to `docs/results/plan-6-test-set.md`: the date, the 20 deals checked,
"0 problems", and that no call used a tool. Then:

```bash
git add docs/results/plan-6-test-set.md
git commit -m "docs: the recoverability gate passed on 20 test deals (Plan 6, Task 10)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The campaign (controller; needs the user's go)

- [ ] **Step 1: A private copy of Claude Code 2.1.280** (the version of every S1b and S4 run so far; an app update
could remove the original mid-campaign):

```bash
cp -R "$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app" data/claude-2.1.280.app
data/claude-2.1.280.app/Contents/MacOS/claude --version
```

Expected: `2.1.280 (Claude Code)`.

- [ ] **Step 2: Preflight**

```bash
uv run python -c "from pathlib import Path; from acqlab.bench import campaign; print(campaign.preflight(Path('data/test-r2'), Path('.').resolve()))"
```

Expected: `None`.

- [ ] **Step 3: Ask the user for the go.** About $210 notional on their Claude subscription, about 12–13 usage
windows, roughly 4–5 days; keep the Mac plugged in; `--status` shows progress; `--stop` pauses it; starting again
resumes. Do not start without an explicit go.

- [ ] **Step 4: Start**

```bash
export CLAUDE_BIN="$PWD/data/claude-2.1.280.app/Contents/MacOS/claude"
nohup caffeinate -i uv run python -m acqlab.bench.campaign --data data/test-r2 --confirm-claude > data/test-r2/campaign.out 2>&1 &
```

After a minute: `uv run python -m acqlab.bench.campaign --data data/test-r2 --status`. Expected: `running (pid …)`,
and the log's last line `phase h1: running (…)`.

- [ ] **Step 5: Record where things stand.** In `docs/HANDOFF.md`'s "Resume here", add: the campaign's start time,
how to check it (`--status`), how to restart it if it stopped (Step 4's two lines), and that the analysis (Task 12)
waits for `campaign complete`. Commit:

```bash
git add docs/HANDOFF.md
git commit -m "docs: handoff, the Plan 6 campaign is running (Plan 6, Task 11)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

While it runs: check `--status` when the user asks. If the log's last line is `stopped …`, report it to the user
before anything else; no fix may touch `acqlab/agents` or `acqlab/routers`, and a restart resumes where it stopped.

---

### Task 12: The analysis and the results (controller; after `campaign complete`)

- [ ] **Step 1: Run the analysis, once**

```bash
uv run python -m acqlab.bench.analysis --data data/test-r2 --out docs/results/plan-6-main-run.json
```

Expected: six lines `H1: …` to `H6: …`. It refuses (exit 1) if the campaign is incomplete or the test set changed.

- [ ] **Step 2: Write `docs/results/plan-6-main-run.md`** from `plan-6-main-run.json` only: each hypothesis with its
numbers, CI and verdict exactly as the addendum's rules give it; H1 by case type; the pessimism control and LLM decides;
a per-system table (regret, correct calls, walk-away error, pages, decoy pages, sessions, cost; from `systems`); S0
and the floors; unanswered runs and timeouts per system; any campaign stops from `data/test-r2/campaign.log`; and the
power note for H3 and H6. Report failures as plainly as successes.

- [ ] **Step 3: Handoff and commit**

In `docs/HANDOFF.md`: "Resume here" and Next steps say Plan 6 is done, with the headline verdict, and the next step is
Plan 7 (the demo and slides). Then:

```bash
git add docs/results/plan-6-main-run.json docs/results/plan-6-main-run.md docs/HANDOFF.md
git commit -m "docs: the Plan 6 main run, H1-H6 as pre-registered (Plan 6, Task 12)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

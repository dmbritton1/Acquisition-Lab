# Mixed-Model Frontier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** build the runner, cascades, frontier rule, practice scorecard and one-shot final analysis for mixing Opus,
Sonnet and Haiku, plus the 100 fresh held-out deals, so the paid phases (practice, freeze, final test) can start.

**Architecture:** one new module, `acqlab/bench/mix.py`, runs single Claude on any model and effort, and
reader-and-pricers pipelines with a model per step (a run-time swap of `solver.command` per step, as the Haiku track's
`on_haiku` does). Each row records every step's models and tokens, so a mixed run is priced step by step. Cascades
(a cheap system, a strong system, a public escalation signal) are computed from existing rows, never run. Two scripts
read finished runs: `scripts/mix_practice.py` (scorecard and frontier picks; writes nothing) and
`scripts/mix_final.py` (the one-shot final analysis). Everything reuses the Haiku track's parts (`haiku.second_zero`,
`calibrated_call`, `vote`, `Candidate`, `Refused`, `cli_version`) and the pilots' (`recon.step`, `recon.combine`,
`pilot.score`, `debate_pilot.versus`, `haiku_team.verdict`, `upside_pilot.keys/load`).

**Tech Stack:** Python 3.12, pytest, numpy; the Claude Code CLI via `acqlab.agents.solver`; the fake `claude`
(`tests/agents/fake_claude.py`) in tests.

**Spec:** `docs/superpowers/specs/2026-10-11-mixed-models-design.md`

## Global Constraints

- `acqlab/agents`, `acqlab/routers` and `acqlab/bench/haiku.py` are not edited (`git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers` prints nothing; `git diff HEAD --stat -- acqlab/bench/haiku.py` prints nothing).
- Model ids: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`. List prices per million tokens (input / output / cache read / 1-hour cache write): Opus 4 / 20 / 0.20 / 8; Sonnet 2 / 10 / 0.20 / 4; Haiku 0.10 / 0.50 / 0.01 / 0.20.
- The fresh held-out sets are `data/mix-test-r2` (80 deals, profile r2, `--seed 650000`) and `data/mix-test-r2u` (20 deals, profile r2u, `--seed 670000`), test split. The practice sets are `data/cal-r2`, `data/heldout-r2`, `data/practice-r2u` (dev split).
- No step reads the answer key (`truth/`); scoring does, after the final call. Cascade signals read only a run's own call and notes and the room's teaser.
- No real Claude call in this plan. Tests use the fake `claude`.
- Run tests with `.venv/bin/python -m pytest` from the repository root. The full suite has 488 tests before this plan and takes about 10 minutes.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `data/` is git-ignored; never `git add` it.

## Review Focus

1. **A step running on the wrong model** (the swap leaking from the reader's step into a pricer's, or past a run): each step must get its own `--model`/`--effort` and the original command must come back even on an error. Pinned in Task 1 (the `fakes` fixture records each step's command line; the error path is tested).
2. **Pricing a mixed run from summed tokens**: a Haiku+Opus row's summed tokens price at neither model; cost must be per step. Pinned in Task 1 (`row_cost` on `steps`) and Task 3 (the analysis's per-system costs).
3. **A cascade signal that peeks at the answer**: an unanswered run's `go` and `walk_away` come from the answer key's face values in `pilot.score`; such a run must escalate before any signal reads them. Pinned in Task 1 (`fires` escalates a run that never answered).
4. **Clone cascades crowding out the freeze**: a cascade whose signal never fires equals its cheap system; ties must count once. Pinned in Task 1 (`frontier` tie test) and Task 2 (real-shaped scorecard).
5. **A partial cascade (escalating to `s4`, which has no practice-r2u runs) winning the frontier on easier deals**: partial candidates are shown but not eligible. Pinned in Task 2.

---

### Task 1: `mix.py`: per-step models, per-step pricing, pipelines, cascades, the frontier and the runner

**Files:**
- Create: `acqlab/bench/mix.py`
- Test: `tests/bench/test_mix.py`

**Interfaces:**
- Consumes (existing): `solver.command` / `solver.solve`; `recon.step(name, path, fn, *args, **kw) -> (rows, cli|None)`, `recon.combine`, `recon.draft`, `recon.call_of`, `recon.spent`, `recon.USAGE`; `referee.opened`; `haiku.SOLO_SYSTEM`, `haiku.SECOND_ZERO`, `haiku.second_zero(room, read, *, trace, **kw)`, `haiku.calibrated_call`, `haiku.vote`, `haiku.Candidate`, `haiku.Refused`, `haiku.PRICES`, `haiku.load_rates`, `haiku.cli_version`, `haiku.too_old`, `haiku.MIN_CLI`; `pilot.score`.
- Produces: `OPUS, SONNET, HAIKU`; `TEST_SETS = ("mix-test-r2", "mix-test-r2u")`; `FINAL: tuple[str, ...] = ()`; `PRICES`; `on_model(model, effort=None)`; `price(models, tokens) -> float|None`; `row_cost(row) -> float|None`; `usage(name, cli) -> dict`; `run_single(room, budget, deal, out, *, model, effort=None, **kw) -> (trace, cli|None, steps)`; `run_pipeline(room, budget, deal, out, *, reader, pricer, pricers, w, rates=None, **kw) -> (trace, cli, steps)`; `CANDIDATES` (`mix_haiku_solo`, `mix_sonnet_solo`, `mix_opus_low`, `mix_h_haiku3`, `mix_h_opus1`, `mix_h_sonnet3`); `ALIASES = {"mix_haiku_solo": "haiku_solo", "mix_h_haiku3": "haiku_lean_zero_w0"}`; `fingerprint(name) -> str`; `models_of(name) -> list[str]`; `asking_price(teaser) -> float`; `fires(signal, row, teaser) -> bool`; `cascade(cheap, strong, signal, teaser) -> dict` (`go, correct, regret, case_type, cost, escalated`); `SIGNALS`; `parse(name) -> (cheap, strong, signal)|None` for `"cascade:<cheap>><strong>@<signal>"`; `frontier(points, s1b_cost, s4_cost, k=4) -> list[str]`; `refuse(...)`; `run(data, systems, split="dev", deals=None, final=False, *, cli=None, **kw)`; `main(argv)`. Rows add `rep, budget, spent, calls, settings, prompts, steps, cli` to `pilot.score`'s fields.

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_mix.py`:

```python
import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.agents.solver import RunTimeout
from acqlab.bench import haiku, mix

RATES = {"addback": 0.3, "debt_like": 0.2, "concentration": 0.4, "nwc": 0.1, "capex": 0.2}
TEASER = "Seller discloses: customer prepayments; estimated exposure up to $13.4M.\nAsking price: $1,078.4M\n"


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _submit(go=True, wa=100.0):
    return _row("submit", {"go": go, "walk_away": wa, "reason": "r"})


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


# --- the model switch, per step ------------------------------------------------------------------------------------

def test_on_model_sets_the_model_and_effort_and_restores_the_original(fake_claude, room, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    original = solver.command
    with mix.on_model(mix.SONNET, "low"):
        solver.solve(room, 5, tmp_path / "t.jsonl", False, claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5" and argv[argv.index("--effort") + 1] == "low"
    assert solver.command is original
    with pytest.raises(RuntimeError):
        with mix.on_model(mix.OPUS):
            raise RuntimeError("boom")
    assert solver.command is original


@pytest.fixture
def fakes(monkeypatch):
    """The reader and pricers replaced by sessions that write a scripted trace (scripts[step]; none scripted = a
    timeout) and record the model and effort their command line would carry (seen[step])."""
    f = {"scripts": {}, "seen": {}}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        cmd = solver.command("claude", "p", "s", Path("m.json"), [])
        f["seen"][name] = (cmd[cmd.index("--model") + 1], cmd[cmd.index("--effort") + 1] if "--effort" in cmd else None,
                           args)
        if name not in f["scripts"]:
            raise RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        model = cmd[cmd.index("--model") + 1]
        return {"total_cost_usd": 0.5, "usage": {"output_tokens": 1_000_000}, "modelUsage": {model: {}}}

    monkeypatch.setattr(mix, "draft", run)
    monkeypatch.setattr(mix, "second_zero", run)
    return f


def test_a_pipeline_runs_each_step_on_its_own_model_and_prices_it_step_by_step(fakes, room, tmp_path):
    reads = [_row("open_document", {"doc_id": "qoe"}, 4.0)]
    fakes["scripts"] |= {"reader": [*reads, _submit(False)], "pricer1": [_submit(True)]}
    s = mix.CANDIDATES["mix_h_opus1"].settings
    trace, cli, steps = mix.run_pipeline(room, 20.0, "dev-000", tmp_path / "x.json", rates=RATES, **s)
    assert fakes["seen"]["reader"][:2] == ("claude-haiku-5-5", None)
    assert fakes["seen"]["pricer1"][:2] == ("claude-opus-5-5", None) and fakes["seen"]["pricer1"][2][1] == ["qoe"]
    assert [x["step"] for x in steps] == ["reader", "pricer1"]
    assert [x["models"] for x in steps] == [["claude-haiku-5-5"], ["claude-opus-5-5"]]
    assert mix.row_cost({"steps": steps}) == pytest.approx(0.50 + 20.0)  # a million output tokens each
    assert set(cli["calls"]) == {"reader", "pricer1"} and mix.call_of(trace) is not None
    assert solver.command.__module__ == "acqlab.agents.solver"


def test_a_single_run_carries_its_effort_and_a_timeout_costs_nothing_known(fakes, room, tmp_path):
    rows, cli, steps = mix.run_single(room, 20.0, "dev-000", tmp_path / "x.json", model=mix.OPUS, effort="low")
    assert fakes["seen"]["solo"][:2] == ("claude-opus-5-5", "low") and cli is None
    assert steps == [{"step": "solo", "models": [], "tokens": dict.fromkeys(mix.USAGE, 0)}]
    assert mix.row_cost({"steps": steps}) == 0.0


def test_row_cost_prices_single_model_rows_from_their_summed_tokens():
    tokens = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 1_000_000,
              "cache_creation_input_tokens": 0}
    assert mix.row_cost({"models": ["claude-sonnet-5-5"], "tokens": tokens}) == pytest.approx(2.0 + 0.20)
    assert mix.row_cost({"models": ["claude-opus-5-5"], "tokens": tokens}) == pytest.approx(4.0 + 0.20)
    assert mix.row_cost({"models": [], "tokens": tokens}) is None


# --- cascades ------------------------------------------------------------------------------------------------------

def _run(go=True, wa=1000.0, answered=True, calls=None, correct=True, regret=0.0, cost_tokens=1_000_000):
    return {"go": go, "walk_away": wa, "answered": answered, "calls": calls, "correct": correct, "regret": regret,
            "case_type": "clean", "models": ["claude-haiku-5-5"],
            "tokens": {"input_tokens": 0, "output_tokens": cost_tokens, "cache_read_input_tokens": 0,
                       "cache_creation_input_tokens": 0}}


def test_each_signal_fires_as_specified():
    assert mix.asking_price(TEASER) == pytest.approx(1078.4)
    plain = TEASER.replace("Seller discloses", "Seller notes")
    assert mix.fires("pass", _run(go=False), plain) and not mix.fires("pass", _run(go=True), plain)
    split = {"reader": {"go": True}, "pricer1": {"go": True}, "pricer2": {"go": False}, "pricer3": None}
    assert mix.fires("split", _run(calls=split), plain)
    assert not mix.fires("split", _run(calls={"pricer1": {"go": True}, "pricer2": {"go": True}}), plain)
    assert not mix.fires("split", _run(calls=None), plain)
    assert mix.fires("close:0.05", _run(wa=1078.4 * 1.04), plain) and not mix.fires("close:0.02", _run(wa=1078.4 * 1.04), plain)
    assert mix.fires("flag", _run(), TEASER) and not mix.fires("flag", _run(), plain)
    assert mix.fires("pass|flag", _run(go=True), TEASER) and not mix.fires("pass|flag", _run(go=True), plain)
    assert mix.fires("flag", _run(answered=False), plain)  # a cheap run that never answered is always escalated


def test_a_cascade_takes_the_strong_call_and_pays_for_it_only_when_it_escalates():
    cheap, strong = _run(go=False, correct=False, regret=0.04), _run(go=True, correct=True, regret=0.0)
    strong |= {"models": ["claude-opus-5-5"]}
    up = mix.cascade(cheap, strong, "pass", TEASER)
    assert up["escalated"] and up["go"] and up["regret"] == 0.0 and up["cost"] == pytest.approx(0.50 + 20.0)
    stay = mix.cascade(_run(go=True), strong, "pass", TEASER.replace("Seller discloses", "Seller notes"))
    assert not stay["escalated"] and stay["cost"] == pytest.approx(0.50)


def test_cascade_names_parse():
    assert mix.parse("cascade:mix_haiku_solo>s1b@split|close:0.05") == ("mix_haiku_solo", "s1b", "split|close:0.05")
    assert mix.parse("mix_opus_low") is None


def test_the_frontier_keeps_undominated_mixes_and_the_two_named_picks_first():
    points = {"a": (0.020, 0.01), "b": (0.015, 0.05), "c": (0.012, 0.20), "d": (0.016, 0.06), "e": (0.009, 0.50),
              "f": (0.010, 0.40)}
    # d is dominated by b; s1b costs 0.13 and s4 0.53: best under 0.13 is b, best under 0.53 is e
    assert mix.frontier(points, 0.13, 0.53) == ["b", "e", "a", "c"]
    assert mix.frontier(points, 0.13, 0.53, k=2) == ["b", "e"]
    assert mix.frontier({"x": (0.02, 0.9)}, 0.13, 0.53) == ["x"]  # nothing cheaper: only the cheapest-first fill
    clones = {"cascade:a>s1b@split": (0.020, 0.01), "a": (0.020, 0.01), "cascade:a>s1b@flag": (0.010, 0.05),
              "cascade:a>s1b@flag|close:0.05": (0.010, 0.05)}
    assert mix.frontier(clones, 0.13, 0.53) == ["cascade:a>s1b@flag", "a"]  # a tie counts once, as the simplest


# --- the registry and the runner -----------------------------------------------------------------------------------

def test_the_aliases_are_the_same_systems_as_the_haiku_track_ran():
    lean, h3 = haiku.CANDIDATES["haiku_lean_zero_w0"], mix.CANDIDATES["mix_h_haiku3"]
    assert lean.prompts == h3.prompts and lean.settings["w"] == h3.settings["w"] == 0.0
    assert lean.settings["pricers"] == h3.settings["pricers"] and lean.settings["zero"]
    assert haiku.CANDIDATES["haiku_solo"].prompts == mix.CANDIDATES["mix_haiku_solo"].prompts
    assert set(mix.ALIASES) <= set(mix.CANDIDATES)


def test_fingerprints_differ_and_models_are_listed():
    shas = {n: mix.fingerprint(n) for n in mix.CANDIDATES}
    assert len(set(shas.values())) == len(shas)
    assert mix.models_of("mix_h_opus1") == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert mix.models_of("mix_opus_low") == ["claude-opus-5-5"]


def test_the_fresh_sets_are_refused_before_the_freeze(tmp_path, monkeypatch):
    for name in mix.TEST_SETS:
        with pytest.raises(mix.Refused, match="held out"):
            mix.run(tmp_path / name, ["mix_opus_low"], split="dev")
    with pytest.raises(mix.Refused, match="held out"):
        mix.run(tmp_path / "cal-r2", ["mix_opus_low"], split="test")
    with pytest.raises(mix.Refused, match="no frozen mixes"):
        mix.run(tmp_path / "mix-test-r2", ["mix_opus_low"], split="test", final=True)
    monkeypatch.setattr(mix, "FINAL", ("cascade:mix_haiku_solo>mix_opus_low@pass", "mix_h_opus1"))
    with pytest.raises(mix.Refused, match="test split"):
        mix.run(tmp_path / "mix-test-r2", ["mix_opus_low"], split="dev", final=True)
    with pytest.raises(mix.Refused, match="not \\['mix_sonnet_solo'\\]"):
        mix.run(tmp_path / "mix-test-r2", ["mix_h_opus1", "mix_sonnet_solo"], split="test", final=True)
    assert mix.main(["--data", str(tmp_path / "mix-test-r2u"), "--systems", "mix_opus_low", "--split", "test",
                     "--confirm-claude"]) == 3
    assert mix.main(["--data", str(tmp_path), "--systems", "mix_x", "--confirm-claude"]) == 1
    assert mix.main(["--data", str(tmp_path / "cal-r2"), "--systems", "mix_opus_low"]) == 3


def test_the_runner_refuses_an_old_cli(data, tmp_path, monkeypatch):
    monkeypatch.setattr(haiku, "cli_version", lambda: "2.1.280")
    assert mix.main(["--data", str(data), "--systems", "mix_opus_low", "--confirm-claude"]) == 3


def test_mixes_run_end_to_end_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    monkeypatch.setattr(haiku, "load_rates", lambda: RATES)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    rows = mix.run(d, ["mix_opus_low", "mix_h_opus1"], deals=["dev-001"], cli="2.1.291", claude=fake_claude)
    assert [(r["system"], r["deal"]) for r in rows] == [("mix_opus_low", "dev-001"), ("mix_h_opus1", "dev-001")]
    for r in rows:
        assert r["answered"] and r["spent"] <= r["budget"] + 1e-9 and r["cli"] == "2.1.291"
        assert r["prompts"] == mix.fingerprint(r["system"])
    assert [s["step"] for s in rows[1]["steps"]] == ["reader", "pricer1"] and rows[1]["sessions"] == 2
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"  # the last session was the Opus pricer
    assert not list((d / "runs").glob("*/*.tmp"))
    assert mix.run(d, ["mix_opus_low", "mix_h_opus1"], deals=["dev-001"], claude=fake_claude) == []


def test_no_step_reads_the_answer_key():
    source = Path(mix.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/bench/test_mix.py -q`
Expected: collection error, `ImportError: cannot import name 'mix' from 'acqlab.bench'`.

- [ ] **Step 3: Write the module**

Create `acqlab/bench/mix.py`:

```python
"""Mixing Opus, Sonnet and Haiku (spec docs/superpowers/specs/2026-10-11-mixed-models-design.md): single runs on any
model and effort, reader-and-pricers pipelines with a model per step, and cascades that escalate a cheap system's
deal to a strong one on a public signal. The frozen code runs unchanged: each step's model is switched at run time
(on_model). No step reads the answer key; scoring does, after the final call.

    uv run python -m acqlab.bench.mix --data data/cal-r2 --systems mix_sonnet_solo,mix_opus_low --confirm-claude
    uv run python -m acqlab.bench.mix --data data/mix-test-r2 --split test --final --systems mix_opus_low --confirm-claude

Runs go to <data>/runs/<system>/<deal>.json, the trace beside it (each step's own trace too); finished runs are
skipped. Each row records every step's models and tokens ("steps"), so a mixed run is priced step by step. Exit codes:
0 done; 1 an unknown system; 2 Claude stopped (rerun later to resume); 3 refused (no --confirm-claude, an old CLI, a
fresh test set before the freeze, or a system the final test does not run)."""
import argparse
import hashlib
import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

from acqlab.agents import solver
from acqlab.bench import haiku, referee
from acqlab.bench.haiku import SECOND_ZERO, SOLO_SYSTEM, Candidate, Refused, calibrated_call, second_zero, vote
from acqlab.bench.recon import USAGE, call_of, combine, draft, spent, step
from acqlab.llm import LLMUnavailable

OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"
TEST_SETS = ("mix-test-r2", "mix-test-r2u")  # spec §1: fresh deals, held out until the freeze
FINAL: tuple[str, ...] = ()  # the frozen mixes and cascades, set at the freeze (spec §2)
# $ per million tokens at list prices (spec §1); cache writes at the 1-hour rate, the cache the CLI writes
PRICES = haiku.PRICES | {SONNET: {"input_tokens": 2.0, "output_tokens": 10.0, "cache_read_input_tokens": 0.20,
                                  "cache_creation_input_tokens": 4.0}}


@contextmanager
def on_model(model: str, effort: str | None = None):
    """Every session started inside runs on `model` (and at `effort`, if given), without editing the frozen solver;
    the original command builder is restored after, even on an error."""
    original = solver.command

    def command(*args, **kw):
        cmd = original(*args, **kw)
        cmd[cmd.index("--model") + 1] = model
        return cmd + (["--effort", effort] if effort else [])

    solver.command = command
    try:
        yield
    finally:
        solver.command = original


# --- costs ---------------------------------------------------------------------------------------------------------

def price(models: list[str], tokens: dict) -> float | None:
    """Tokens at PRICES; None unless they came from exactly one priced model."""
    if len(models) != 1 or models[0] not in PRICES:
        return None
    return sum(tokens.get(k, 0) * p for k, p in PRICES[models[0]].items()) / 1e6


def row_cost(row: dict) -> float | None:
    """A run's cost: step by step when the row records its steps (a step that gave no CLI result costs nothing
    known), else from its summed tokens (a single-model run, such as s1b or s4)."""
    if "steps" in row:
        return sum(price(s["models"], s["tokens"]) or 0.0 for s in row["steps"])
    return price(row["models"], row["tokens"])


def usage(name: str, cli: dict | None) -> dict:
    """One step's models and tokens, as each row records them."""
    return {"step": name, "models": sorted((cli or {}).get("modelUsage", {})),
            "tokens": {k: int((cli or {}).get("usage", {}).get(k, 0)) for k in USAGE}}


# --- the systems ---------------------------------------------------------------------------------------------------

def run_single(room: Path, budget: float, deal: str, out: Path, *, model: str, effort: str | None = None,
               **kw) -> tuple[list[dict], dict | None, list[dict]]:
    """Single Claude, unchanged, on `model` at `effort`. The CLI result is None after a timeout."""
    with on_model(model, effort):
        rows, cli = step("solo", out.with_suffix(".solo.jsonl"), draft, room, budget, **kw)
    return rows, cli, [usage("solo", cli)]


def run_pipeline(room: Path, budget: float, deal: str, out: Path, *, reader: list, pricer: list, pricers: int,
                 w: float, rates: dict[str, float] | None = None, **kw) -> tuple[list[dict], dict, list[dict]]:
    """Spec §2: a reader ([model, effort]) at the full budget, then `pricers` second opinions (the Haiku track's zero
    rule) on [model, effort] over the documents it read; the engine prices each one's notes with open chances pulled
    toward the base rates by `w`, and the majority of those calls is final."""
    rates = rates or haiku.load_rates()
    with on_model(*reader):
        first = step("reader", out.with_suffix(".reader.jsonl"), draft, room, budget, **kw)
    read = referee.opened(first[0])
    priced = []
    for i in range(1, pricers + 1):
        with on_model(*pricer):
            priced.append(step(f"pricer{i}", out.with_suffix(f".pricer{i}.jsonl"), second_zero, room, read, **kw))
    calls = [calibrated_call(room, rows, rates, w) for rows, _ in priced]
    steps = [first, *priced]
    names = ["reader", *(f"pricer{i}" for i in range(1, pricers + 1))]
    trace, cli = combine([r for rows, _ in steps for r in rows], [c for _, c in steps], vote(calls))
    return trace, cli | {"calls": {"reader": call_of(first[0])} | dict(zip(names[1:], calls))}, \
        [usage(n, c) for n, (_, c) in zip(names, steps)]


SOLO, PIPELINE = (SOLO_SYSTEM,), (SOLO_SYSTEM, SECOND_ZERO)
CANDIDATES = {
    "mix_haiku_solo": Candidate(run_single, SOLO, settings={"model": HAIKU}),
    "mix_sonnet_solo": Candidate(run_single, SOLO, settings={"model": SONNET}),
    "mix_opus_low": Candidate(run_single, SOLO, settings={"model": OPUS, "effort": "low"}),
    "mix_h_haiku3": Candidate(run_pipeline, PIPELINE, settings={"reader": [HAIKU, None], "pricer": [HAIKU, None],
                                                                "pricers": 3, "w": 0.0}),
    "mix_h_opus1": Candidate(run_pipeline, PIPELINE, settings={"reader": [HAIKU, None], "pricer": [OPUS, None],
                                                               "pricers": 1, "w": 0.0}),
    "mix_h_sonnet3": Candidate(run_pipeline, PIPELINE, settings={"reader": [HAIKU, None], "pricer": [SONNET, None],
                                                                 "pricers": 3, "w": 0.0}),
}
# The same systems already run on the practice deals under the Haiku track's names (identical steps and settings)
ALIASES = {"mix_haiku_solo": "haiku_solo", "mix_h_haiku3": "haiku_lean_zero_w0"}


def fingerprint(name: str) -> str:
    """A candidate's prompts, run function and settings (models and effort included)."""
    c = CANDIDATES[name]
    setup = json.dumps({"run": c.run.__name__, "settings": c.settings}, sort_keys=True)
    return hashlib.sha256("\x00".join((*c.prompts, setup)).encode()).hexdigest()


def models_of(name: str) -> list[str]:
    """The models a candidate's rows must show."""
    s = CANDIDATES[name].settings
    return [s["model"]] if "model" in s else sorted({s["reader"][0], s["pricer"][0]})


# --- cascades (spec §2): a cheap system's call, escalated to a strong one on a public signal -----------------------

def asking_price(teaser: str) -> float:
    return float(re.search(r"Asking price: \$([\d.,]+)M", teaser).group(1).replace(",", ""))


def fires(signal: str, row: dict, teaser: str) -> bool:
    """Whether `signal` (names joined by "|", any of them) escalates this cheap run. Public information only: the cheap
    run's own call and notes, and the teaser. A run that never answered is always escalated."""
    if not row["answered"]:
        return True
    for part in signal.split("|"):
        name, _, arg = part.partition(":")
        if name == "pass" and not row["go"]:
            return True
        if name == "split":
            gos = {c["go"] for k, c in (row.get("calls") or {}).items() if k.startswith("pricer") and c}
            if len(gos) > 1:
                return True
        if name == "close" and abs(row["walk_away"] - asking_price(teaser)) <= float(arg) * asking_price(teaser):
            return True
        if name == "flag" and "Seller discloses:" in teaser:
            return True
    return False


def cascade(cheap: dict, strong: dict, signal: str, teaser: str) -> dict:
    """The cascade's result on one deal: the strong run's call when the signal fires, else the cheap run's; cost is
    the cheap run's plus the strong run's on escalated deals only."""
    up = fires(signal, cheap, teaser)
    used = strong if up else cheap
    return {"go": used["go"], "correct": used["correct"], "regret": used["regret"], "case_type": cheap["case_type"],
            "cost": (row_cost(cheap) or 0.0) + ((row_cost(strong) or 0.0) if up else 0.0), "escalated": up}


SIGNALS = ("pass", "split", "close:0.02", "close:0.05", "close:0.10", "flag", "split|close:0.05", "flag|close:0.05")


def parse(name: str) -> tuple[str, str, str] | None:
    """'cascade:<cheap>><strong>@<signal>' -> (cheap, strong, signal); None for a plain system."""
    m = re.fullmatch(r"cascade:([\w]+)>([\w]+)@(.+)", name)
    return m.groups() if m else None


# --- the frontier (spec §1) ----------------------------------------------------------------------------------------

def frontier(points: dict[str, tuple[float, float]], s1b_cost: float, s4_cost: float, k: int = 4) -> list[str]:
    """Up to k names from the candidates no other candidate beats on both regret and cost: the lowest-regret one
    cheaper than s1b, the lowest-regret one cheaper than s4, then the cheapest others. Candidates with the very same
    point (a cascade whose signal never fired is its cheap system again) count once, as the simplest of them: a plain
    system before a cascade, then by name."""
    first = {}
    for n in sorted(points, key=lambda n: (parse(n) is not None, n)):
        first.setdefault(points[n], n)
    points = {n: points[n] for n in first.values()}
    front = [n for n, (r, c) in points.items()
             if not any((r2 <= r and c2 <= c) and (r2 < r or c2 < c) for m, (r2, c2) in points.items() if m != n)]
    picks = []
    for limit in (s1b_cost, s4_cost):
        under = sorted((points[n][0], points[n][1], n) for n in front if points[n][1] < limit)
        if under and under[0][2] not in picks:
            picks.append(under[0][2])
    for n in sorted(front, key=lambda n: (points[n][1], points[n][0], n)):
        if len(picks) >= k:
            break
        if n not in picks:
            picks.append(n)
    return picks[:k]


# --- the runner ----------------------------------------------------------------------------------------------------

def refuse(data: Path, systems: list[str], split: str, final: bool) -> None:
    """Spec §1: the fresh sets run only in the final test, and the final test runs only frozen mixes' parts and the
    single-Haiku reference."""
    if (data.resolve().name in TEST_SETS or split == "test") and not final:
        raise Refused(f"{data.name} ({split}) is held out for the final test; practice never runs on it")
    if final:
        if split != "test":
            raise Refused(f"the final test runs on the test split, not {split}")
        if not FINAL:
            raise Refused("no frozen mixes yet: mix.FINAL is set at the freeze")
        parts = {"mix_haiku_solo"} | {p for n in FINAL for p in (parse(n)[:2] if parse(n) else (n,))}
        if bad := [s for s in systems if s not in parts]:
            raise Refused(f"the final test runs only the frozen mixes' parts {sorted(parts)}, not {bad}")


def run(data: Path, systems: list[str], split: str = "dev", deals: list[str] | None = None, final: bool = False,
        *, cli: str | None = None, **kw) -> list[dict]:
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
            trace, result, steps = c.run(room, budget, deal, path, **c.settings, **kw)
            path.with_suffix(".trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
            key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
            assert key.budget == budget, f"{deal}: the room's budget is not the answer key's"
            status = "timeout" if result is None else "ok" if call_of(trace) else "no_call"
            row = score(key, name, trace, result, status) | {
                "rep": 0, "budget": budget, "spent": spent(trace), "calls": (result or {}).get("calls"),
                "settings": c.settings, "prompts": fingerprint(name), "steps": steps, "cli": cli}
            tmp = path.with_suffix(".json.tmp")  # written whole, then renamed: a killed run leaves no half row
            tmp.write_text(json.dumps(row, indent=2))
            tmp.replace(path)
            out.append(row)
            print(f"{name} {deal}: answered={row['answered']} correct={row['correct']} regret {row['regret']:.3f} "
                  f"pages {row['pages']:g}/{budget:g} ${row_cost(row) or 0:.4f}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--systems", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--deals", default="", help="comma-separated deal ids (default: the whole split)")
    ap.add_argument("--final", action="store_true", help="the final test on a fresh set (after the freeze)")
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
        version = haiku.cli_version()
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Refusing: the claude CLI could not report its version: {e}")
        return 3
    if haiku.too_old(version):
        print(f"Refusing: claude CLI {version or '(unknown)'} is older than {'.'.join(map(str, haiku.MIN_CLI))}")
        return 3
    try:
        run(args.data, systems, args.split, [d for d in args.deals.split(",") if d] or None, args.final, cli=version)
    except LLMUnavailable as e:
        print(f"Claude stopped: {e}. Rerun to resume.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_mix.py tests/bench/test_haiku.py -q`
Expected: `14 passed` for `test_mix.py` plus the Haiku track's `26 passed` (40 in all), proving `haiku.py` still behaves.

- [ ] **Step 5: Check the frozen files and commit**

Run: `git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers` and `git diff HEAD --stat -- acqlab/bench/haiku.py`
Expected: no output from either.

```bash
git add acqlab/bench/mix.py tests/bench/test_mix.py
git commit -m "feat: mixed models: per-step model switch and pricing, pipelines, cascades, frontier rule, runner

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The practice scorecard and frontier picks

**Files:**
- Create: `scripts/mix_practice.py`
- Test: `tests/bench/test_mix_practice.py`

**Interfaces:**
- Consumes: Task 1's `mix.CANDIDATES`, `mix.ALIASES`, `mix.row_cost`, `mix.cascade`, `mix.SIGNALS`, `mix.frontier`; `haiku.PRACTICE`; `upside_pilot.load`; `haiku_practice.keeps` / `haiku_practice.scorecard` (for `--keep`).
- Produces: `rows(root, name) -> {"<set>/<deal>": row}` (aliases honoured); `teasers(root)`; `plain(rows)`; `summary(results, total) -> dict` (`n, partial, regret, correct, false_go, false_nogo, relief_false_nogo, confirmed_false_go, cost, escalated`); `scorecard(root) -> {name: summary}` (baselines `s1b`, `s4`, every candidate with runs, and every cascade `cascade:<cheap>><strong>@<signal>` over `CHEAP` x `STRONG` x `SIGNALS`); `picks(card) -> list[str]` (full-coverage candidates only); `table(card, chosen) -> str`; `main(argv)` (`--root`, `--keep`, `--over`).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_mix_practice.py`:

```python
import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import haiku, mix, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "mix_practice.py"))
OUT = {"s1b": 5_000, "s4": 25_000, "haiku_solo": 20_000, "mix_opus_low": 2_500}  # output tokens per deal
MODEL = {"s1b": mix.OPUS, "s4": mix.OPUS, "haiku_solo": mix.HAIKU, "mix_opus_low": mix.OPUS}


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


def write(d: Path, system: str, deal: str, go: bool) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    trace = [{"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    cli = {"total_cost_usd": 1.0, "sessions": 1, "modelUsage": {MODEL[system]: {}},
           "usage": {"output_tokens": OUT[system]}}
    (d / "runs" / system).mkdir(parents=True, exist_ok=True)
    (d / "runs" / system / f"{deal}.json").write_text(json.dumps(pilot.score(key, system, trace, cli, "ok")))


@pytest.fixture
def finished(practice, tmp_path):
    """s1b, mix_opus_low and s4 always right (s4 not on practice-r2u); single Haiku always passes (under its
    Haiku-track name)."""
    root = tmp_path / "p"
    shutil.copytree(practice, root)
    for s in haiku.PRACTICE:
        for deal in json.loads((root / s / "splits.json").read_text())["dev"]:
            key = AnswerKey.model_validate_json((root / s / "truth" / f"{deal}.json").read_text())
            for system in ("s1b", "mix_opus_low", *(("s4",) if s != "practice-r2u" else ())):
                write(root / s, system, deal, key.truth.go)
            write(root / s, "haiku_solo", deal, False)
    return root


def test_rows_read_a_candidate_under_its_haiku_track_name(finished):
    assert len(SCRIPT["rows"](finished, "mix_haiku_solo")) == 9 and len(SCRIPT["rows"](finished, "s4")) == 4
    assert SCRIPT["rows"](finished, "mix_sonnet_solo") == {}


def test_the_scorecard_scores_systems_and_cascades_and_flags_partial_ones(finished):
    card = SCRIPT["scorecard"](finished)
    assert card["s1b"]["regret"] == 0 and card["s1b"]["cost"] == pytest.approx(0.10) and not card["s1b"]["partial"]
    assert card["mix_haiku_solo"]["cost"] == pytest.approx(0.01) and card["mix_haiku_solo"]["false_go"] == 0
    up = card["cascade:mix_haiku_solo>mix_opus_low@pass"]
    assert up["regret"] == 0 and up["escalated"] == 1 and up["cost"] == pytest.approx(0.01 + 0.05)
    assert card["cascade:mix_haiku_solo>s4@pass"]["partial"] and card["cascade:mix_haiku_solo>s4@pass"]["n"] == 4
    assert "mix_sonnet_solo" not in card and not any("mix_sonnet_solo" in n for n in card)  # never run


def test_the_frontier_picks_full_coverage_candidates_only(finished):
    card = SCRIPT["scorecard"](finished)
    chosen = SCRIPT["picks"](card)
    # escalating only the flagged (r2u) deals, where single Haiku errs, to Opus at low effort reaches regret 0 at
    # $0.027 a deal, beating mix_opus_low ($0.05); single Haiku is the cheapest point; its clones count once
    assert chosen == ["cascade:mix_haiku_solo>mix_opus_low@flag", "mix_haiku_solo"]
    assert card["mix_opus_low"]["regret"] == 0 and card["mix_opus_low"]["cost"] == pytest.approx(0.05)


def test_main_prints_the_table_and_the_picks(finished, capsys):
    assert SCRIPT["main"](["--root", str(finished)]) == 0
    out = capsys.readouterr().out
    assert "frontier picks (*): ['cascade:mix_haiku_solo>mix_opus_low@flag', 'mix_haiku_solo']" in out
    assert "(partial)" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/bench/test_mix_practice.py -q`
Expected: collection error, `FileNotFoundError` for `scripts/mix_practice.py`.

- [ ] **Step 3: Write the script**

Create `scripts/mix_practice.py`:

```python
"""The mixed-model practice scorecard (spec docs/superpowers/specs/2026-10-11-mixed-models-design.md §2): every
system and every cascade on the 90 practice deals, by regret and cost, and the frontier the freeze takes. Reads answer
keys and runs; writes nothing and never calls a model. From the repository root:

  .venv/bin/python scripts/mix_practice.py
  .venv/bin/python scripts/mix_practice.py --keep mix_h_sonnet3b --over mix_h_sonnet3   # a tuning round's verdict"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import haiku, mix
from upside_pilot import load

ROOT = Path(__file__).resolve().parents[1] / "data"
BASELINES = ("s1b", "s4")
CHEAP = ("mix_haiku_solo", "mix_h_haiku3", "mix_h_sonnet3", "mix_h_opus1", "mix_sonnet_solo")
STRONG = ("s1b", "s4", "mix_opus_low", "mix_sonnet_solo")


def rows(root: Path, name: str) -> dict[str, dict]:
    """'<set>/<deal>' -> row over the practice sets' dev deals; a candidate the Haiku track already ran is read from
    its Haiku-track name (mix.ALIASES)."""
    out = {}
    for s in haiku.PRACTICE:
        deals = set(json.loads((root / s / "splits.json").read_text())["dev"])
        got = load(root / s, name) or load(root / s, mix.ALIASES.get(name, name))
        out |= {f"{s}/{d}": r for d, r in got.items() if d in deals}
    return out


def teasers(root: Path) -> dict[str, str]:
    return {f"{s}/{d}": json.loads((root / s / "deals" / d / "room" / "index.json").read_text())["teaser"]
            for s in haiku.PRACTICE for d in json.loads((root / s / "splits.json").read_text())["dev"]}


def plain(rs: dict[str, dict]) -> dict[str, dict]:
    return {k: {"go": r["go"], "correct": r["correct"], "regret": r["regret"], "case_type": r["case_type"],
                "cost": mix.row_cost(r) or 0.0, "escalated": False} for k, r in rs.items()}


def summary(results: dict[str, dict], total: int) -> dict:
    v = list(results.values())
    if not v:
        return {"n": 0}
    return {"n": len(v), "partial": len(v) < total, "regret": float(np.mean([x["regret"] for x in v])),
            "correct": float(np.mean([x["correct"] for x in v])),
            "false_go": sum(x["go"] and not x["correct"] for x in v),
            "false_nogo": sum(not x["go"] and not x["correct"] for x in v),
            "relief_false_nogo": sum(not x["go"] and not x["correct"] for x in v if x["case_type"] == "relief"),
            "confirmed_false_go": sum(x["go"] and not x["correct"] for x in v if x["case_type"] == "confirmed"),
            "cost": float(np.mean([x["cost"] for x in v])), "escalated": float(np.mean([x["escalated"] for x in v]))}


def scorecard(root: Path) -> dict[str, dict]:
    """name -> summary for the baselines, every candidate and every cascade with both parts run."""
    tz = teasers(root)
    runs = {n: rows(root, n) for n in (*BASELINES, *mix.CANDIDATES)}
    out = {n: summary(plain(r), len(tz)) for n, r in runs.items() if r}
    for c in CHEAP:
        for s in STRONG:
            if c == s or not runs[c] or not runs[s]:
                continue
            for sig in mix.SIGNALS:
                both = sorted(set(runs[c]) & set(runs[s]))  # s4 has no practice-r2u runs: those cascades are partial
                out[f"cascade:{c}>{s}@{sig}"] = summary({k: mix.cascade(runs[c][k], runs[s][k], sig, tz[k])
                                                         for k in both}, len(tz))
    return out


def picks(card: dict[str, dict]) -> list[str]:
    """Spec §1's frontier rule over the candidates and cascades scored on every practice deal (not the baselines, and
    not a partial cascade, which would be compared on easier, fewer deals)."""
    points = {n: (c["regret"], c["cost"]) for n, c in card.items()
              if n not in BASELINES and c["n"] and not c["partial"]}
    return mix.frontier(points, card["s1b"]["cost"], card["s4"]["cost"])


def table(card: dict[str, dict], chosen: list[str]) -> str:
    lines = [f"{'system':58s} {'n':>3s} {'regret':>7s} {'right':>6s} {'fGO':>4s} {'fNOGO':>5s} {'$/deal':>7s} "
             f"{'up':>5s}"]
    for n, c in sorted(card.items(), key=lambda kv: (kv[1].get("cost", 0), kv[0])):
        if not c["n"]:
            continue
        mark = (" *" if n in chosen else "") + (" (partial)" if c["partial"] else "")
        lines.append(f"{n:58s} {c['n']:3d} {c['regret']:7.4f} {c['correct']:6.1%} {c['false_go']:4d} "
                     f"{c['false_nogo']:5d} {c['cost']:7.4f} {c['escalated']:5.0%}{mark}")
    lines.append(f"frontier picks (*): {chosen}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the practice sets")
    ap.add_argument("--keep", help="a tuning change's system: is it kept over --over? (the Haiku track's keep rule)")
    ap.add_argument("--over", help="the current best system")
    args = ap.parse_args(argv)
    if args.keep:
        if not args.over:
            ap.error("--keep needs --over")
        from haiku_practice import keeps, scorecard as haiku_scorecard
        cards = haiku_scorecard(args.root, [args.keep, args.over])
        print(f"keep {args.keep} over {args.over}: {keeps(cards[args.keep], cards[args.over])}")
        return 0
    card = scorecard(args.root)
    print(table(card, picks(card)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_mix_practice.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Run it read-only on the real practice data**

Run: `.venv/bin/python scripts/mix_practice.py | tail -3`
Expected: a table and a `frontier picks (*): [...]` line, with no error. Only `s1b`, `s4` and the two aliased Haiku-track systems have runs yet, so cascades escalating to `s1b` or `s4` show as `(partial)` (no `s1b`/`s4` runs on practice-r2u yet) and the picks are among `mix_haiku_solo` and `mix_h_haiku3`. Paste the last 3 lines into the report.

- [ ] **Step 6: Commit**

```bash
git add scripts/mix_practice.py tests/bench/test_mix_practice.py
git commit -m "feat: mixed-model practice scorecard: systems and cascades by regret and cost, frontier picks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The one-shot final analysis

**Files:**
- Create: `scripts/mix_final.py`
- Test: `tests/bench/test_mix_final.py`

**Interfaces:**
- Consumes: Task 1's `mix.FINAL`, `mix.TEST_SETS`, `mix.parse`, `mix.cascade`, `mix.row_cost`, `mix.models_of`, `mix.fingerprint`, `mix.OPUS`; `debate_pilot.versus`; `haiku_team.verdict`; `upside_pilot.keys`, `load`.
- Produces: `parts() -> tuple[str, ...]`; `check(by, ks, root, name)`; `results(by, tz, system) -> {deal: result}`; `summary(res)`; `one_set(res)` (`n, systems, versus, verdicts, cost_ratio`); `readings(card)` (`cheaper_and_not_worse_than_s1b`, `cheaper_and_not_worse_than_s4`); `analyse(root)` (`frozen, systems, sets{mix-test-r2, mix-test-r2u, all}, readings`); `main(argv)` (`--root`, `--out`; 0 written, 1 refused).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_mix_final.py`:

```python
import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import mix, pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "mix_final.py"))
FROZEN = ("mix_h_opus1", "cascade:mix_haiku_solo>mix_opus_low@pass")
OUT = {"s1b": 5_000, "s4": 25_000, "mix_haiku_solo": 20_000, "mix_opus_low": 2_500}  # output tokens per deal


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    """The two fresh sets in miniature: five r2 test deals and five r2u test deals."""
    root = tmp_path_factory.mktemp("fresh")
    batch.run(root / "mix-test-r2", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2")
    batch.run(root / "mix-test-r2u", {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u")
    return root


def write(d: Path, system: str, deal: str, go: bool, models=None, prompts=None) -> None:
    key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
    trace = [{"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}]
    base = system in ("s1b", "s4")
    want = models or ([mix.OPUS] if base else mix.models_of(system))
    cli = {"total_cost_usd": 1.0, "sessions": 1, "modelUsage": {m: {} for m in want},
           "usage": {"output_tokens": OUT.get(system, 0)}}
    row = pilot.score(key, system, trace, cli, "ok")
    if not base:
        steps = ([{"step": "solo", "models": want, "tokens": row["tokens"]}] if system != "mix_h_opus1" else
                 [{"step": "reader", "models": [mix.HAIKU], "tokens": {"output_tokens": 20_000}},
                  {"step": "pricer1", "models": [mix.OPUS], "tokens": {"output_tokens": 1_000}}])
        row |= {"steps": steps, "prompts": prompts or mix.fingerprint(system)}
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text(json.dumps(trace[0]) + "\n")
    (out / f"{deal}.json").write_text(json.dumps(row))


def every(root: Path):
    for name in mix.TEST_SETS:
        for deal in json.loads((root / name / "splits.json").read_text())["test"]:
            yield root / name, deal, AnswerKey.model_validate_json((root / name / "truth" / f"{deal}.json").read_text())


@pytest.fixture
def finished(sets, tmp_path, monkeypatch):
    """A finished fake final test: everything right except single Haiku, which always passes."""
    monkeypatch.setattr(mix, "FINAL", FROZEN)
    root = tmp_path / "r"
    shutil.copytree(sets, root)
    for d, deal, key in every(root):
        for s in ("s1b", "s4", "mix_opus_low", "mix_h_opus1"):
            write(d, s, deal, key.truth.go)
        write(d, "mix_haiku_solo", deal, False)
    return root


def test_the_parts_are_the_baselines_the_reference_and_each_mix_s_parts(monkeypatch):
    monkeypatch.setattr(mix, "FINAL", FROZEN)
    assert SCRIPT["parts"]() == ("s1b", "s4", "mix_haiku_solo", "mix_h_opus1", "mix_opus_low")
    monkeypatch.setattr(mix, "FINAL", ())
    with pytest.raises(ValueError, match="no frozen mixes"):
        SCRIPT["parts"]()


def test_the_analysis_reads_a_finished_final_test(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    assert out["frozen"] == list(FROZEN) and [out["sets"][n]["n"] for n in (*mix.TEST_SETS, "all")] == [5, 5, 10]
    every_set = out["sets"]["all"]
    assert every_set["verdicts"] == dict.fromkeys([f"{m}-{b}" for m in FROZEN for b in ("s1b", "s4")],
                                                  "no clear difference: at most 0.0000 worse")
    cascade = every_set["systems"][FROZEN[1]]
    assert cascade["escalated"] == 1 and cascade["cost"] == pytest.approx(0.01 + 0.05) and cascade["regret"] == 0
    assert every_set["systems"]["mix_h_opus1"]["cost"] == pytest.approx(0.01 + 0.02)
    assert every_set["cost_ratio"]["s1b/mix_h_opus1"] == pytest.approx(0.10 / 0.03)
    assert out["readings"]["all"] == {"cheaper_and_not_worse_than_s1b": list(FROZEN),
                                      "cheaper_and_not_worse_than_s4": list(FROZEN)}
    assert every_set["systems"]["mix_haiku_solo"]["false_nogo"] > 0  # the reference is in the table
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--root", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_a_mix_worse_than_a_baseline_is_not_read_as_matching_it(finished):
    for d, deal, key in every(finished):
        write(d, "mix_h_opus1", deal, not key.truth.go)
    out = SCRIPT["analyse"](finished)
    assert "mix_h_opus1" not in out["readings"]["all"]["cheaper_and_not_worse_than_s1b"]


def test_the_analysis_refuses_what_was_not_preregistered(finished, tmp_path):
    (finished / "mix-test-r2u" / "runs" / "mix_opus_low" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="mix-test-r2u: mix_opus_low.*test-001"):
        SCRIPT["analyse"](finished)
    write(finished / "mix-test-r2u", "mix_opus_low", "test-001", True)
    (finished / "mix-test-r2" / "runs" / "s4" / "test-002.trace.jsonl").unlink()
    with pytest.raises(ValueError, match="without a trace.*mix-test-r2/s4/test-002"):
        SCRIPT["analyse"](finished)
    write(finished / "mix-test-r2", "s4", "test-002", True)
    write(finished / "mix-test-r2", "mix_h_opus1", "test-003", True, models=[mix.HAIKU, mix.SONNET])
    with pytest.raises(ValueError, match="wrong models.*mix-test-r2/mix_h_opus1/test-003"):
        SCRIPT["analyse"](finished)
    write(finished / "mix-test-r2", "mix_h_opus1", "test-003", True, prompts="old")
    with pytest.raises(ValueError, match="frozen mixes.*mix-test-r2/mix_h_opus1/test-003"):
        SCRIPT["analyse"](finished)
    assert SCRIPT["main"](["--root", str(finished), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/bench/test_mix_final.py -q`
Expected: collection error, `FileNotFoundError` for `scripts/mix_final.py`.

- [ ] **Step 3: Write the script**

Create `scripts/mix_final.py`:

```python
"""The mixed-model final analysis (spec docs/superpowers/specs/2026-10-11-mixed-models-design.md §1), run once on the
finished final test over the fresh deals. Reads answer keys and runs; never calls a model. From the repository root:

  .venv/bin/python scripts/mix_final.py --out docs/results/mix.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import mix
from debate_pilot import versus
from haiku_team import verdict
from upside_pilot import keys, load

ROOT = Path(__file__).resolve().parents[1] / "data"
OPUS_BASELINES = ("s1b", "s4")
REFERENCE = "mix_haiku_solo"


def parts() -> tuple[str, ...]:
    """Every system with runs in the final test: the baselines, the reference and each frozen mix's parts."""
    if not mix.FINAL:
        raise ValueError("no frozen mixes: mix.FINAL is set at the freeze")
    got = [*OPUS_BASELINES, REFERENCE]
    for n in mix.FINAL:
        got += list(mix.parse(n)[:2]) if mix.parse(n) else [n]
    return tuple(dict.fromkeys(got))


def check(by: dict[str, dict[str, dict]], ks: dict, root: Path, name: str) -> None:
    """Refuse a final test that is not the pre-registered one: a system missing deals or traces, a row on the wrong
    models (a run with timed-out steps may show fewer; a timed-out run none), or a mix row whose fingerprint is not
    the frozen one."""
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{name}: {s} runs cover {sorted(set(rows) ^ set(ks))} differently from the test split")
    lost = [f"{name}/{s}/{d}" for s in by for d in ks if not (root / name / "runs" / s / f"{d}.trace.jsonl").exists()]
    if lost:
        raise ValueError(f"runs without a trace: {lost}")
    wrong = []
    for s, rows in by.items():
        want = set([mix.OPUS] if s in OPUS_BASELINES else mix.models_of(s))
        for d, r in rows.items():
            got = set(r["models"])
            if got != want and not (r["timeouts"] and got < want) and not (not got and r["status"] == "timeout"):
                wrong.append(f"{name}/{s}/{d}")
    if wrong:
        raise ValueError(f"rows on the wrong models: {wrong}")
    stale = [f"{name}/{s}/{d}" for s in by if s not in OPUS_BASELINES for d, r in by[s].items()
             if r.get("prompts") != mix.fingerprint(s)]
    if stale:
        raise ValueError(f"rows not made with the frozen mixes: {stale}")


def results(by: dict[str, dict[str, dict]], tz: dict[str, str], system: str) -> dict[str, dict]:
    """deal -> {go, correct, regret, case_type, cost, escalated} for a run system or a frozen cascade."""
    if (p := mix.parse(system)) is not None:
        cheap, strong, signal = p
        return {d: mix.cascade(by[cheap][d], by[strong][d], signal, tz[d]) for d in by[cheap]}
    return {d: {"go": r["go"], "correct": r["correct"], "regret": r["regret"], "case_type": r["case_type"],
                "cost": mix.row_cost(r) or 0.0, "escalated": False} for d, r in by[system].items()}


def summary(res: dict[str, dict]) -> dict:
    v = list(res.values())
    return {"n": len(v), "regret": float(np.mean([x["regret"] for x in v])),
            "correct": float(np.mean([x["correct"] for x in v])),
            "false_go": sum(x["go"] and not x["correct"] for x in v),
            "false_nogo": sum(not x["go"] and not x["correct"] for x in v),
            "cost": float(np.mean([x["cost"] for x in v])), "escalated": float(np.mean([x["escalated"] for x in v]))}


def one_set(res: dict[str, dict[str, dict]]) -> dict:
    """Spec §1 for one deal set: each frozen mix against s1b and s4, with verdicts and cost ratios, and every
    system's summary (the quality-against-cost table)."""
    cards = {s: summary(r) for s, r in res.items()}
    out = {"n": cards["s1b"]["n"], "systems": cards, "versus": {}, "verdicts": {}, "cost_ratio": {}}
    for m in mix.FINAL:
        for b in OPUS_BASELINES:
            c = versus(res[m], res[b])
            out["versus"][f"{m}-{b}"] = c
            out["verdicts"][f"{m}-{b}"] = verdict(c)
            out["cost_ratio"][f"{b}/{m}"] = cards[b]["cost"] / cards[m]["cost"] if cards[m]["cost"] else None
    return out


def readings(card: dict) -> dict:
    """The two named readings on a set: the mixes cheaper than the baseline and not "worse" than it."""
    sys_ = card["systems"]
    return {f"cheaper_and_not_worse_than_{b}": [m for m in mix.FINAL if sys_[m]["cost"] < sys_[b]["cost"]
                                                 and card["verdicts"][f"{m}-{b}"] != "worse"]
            for b in OPUS_BASELINES}


def analyse(root: Path) -> dict:
    names = parts()
    res, tz_all = {}, {}
    for name in mix.TEST_SETS:
        ks = keys(root / name, "test")
        by = {s: load(root / name, s) for s in names}
        check(by, ks, root, name)
        tz = {d: json.loads((root / name / "deals" / d / "room" / "index.json").read_text())["teaser"] for d in ks}
        res[name] = {s: results(by, tz, s) for s in (*names, *mix.FINAL) if not mix.parse(s) or s in mix.FINAL}
    res["all"] = {s: {f"{n}/{d}": x for n in mix.TEST_SETS for d, x in res[n][s].items()} for s in res[mix.TEST_SETS[0]]}
    sets = {n: one_set(r) for n, r in res.items()}
    return {"frozen": list(mix.FINAL), "systems": list(res["all"]), "sets": sets,
            "readings": {n: readings(c) for n, c in sets.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the two fresh sets")
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
    print(json.dumps({"verdicts": out["sets"]["all"]["verdicts"], "readings": out["readings"]["all"],
                      "cost": {s: c["cost"] for s, c in out["sets"]["all"]["systems"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/bench/test_mix_final.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/mix_final.py tests/bench/test_mix_final.py
git commit -m "feat: mixed-model final analysis: verdicts against single Opus and the Opus team, readings, cost table

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The fresh deals, the tuning log and the full check

**Files:**
- Create (git-ignored, not committed): `data/mix-test-r2/`, `data/mix-test-r2u/`
- Create: `docs/results/mix-tuning-log.md`
- Modify: `docs/HANDOFF.md`

- [ ] **Step 1: Check the seeds clash with nothing**

Run:

```bash
.venv/bin/python -c "
from pathlib import Path
from acqlab.bench.testset import used_seeds, clashes
u = used_seeds([Path('data')])
print(clashes(650000, 80, u, 'test'), clashes(670000, 20, u, 'test'))"
```

Expected: `[] []`. If anything else prints, stop and report BLOCKED (do not pick other seeds).

- [ ] **Step 2: Generate the fresh deals**

Run:

```bash
.venv/bin/python -m acqlab.generator.batch --out data/mix-test-r2 --dev 0 --test 80 --hand 0 --showcase 0 --seed 650000 --profile r2
.venv/bin/python -m acqlab.generator.batch --out data/mix-test-r2u --dev 0 --test 20 --hand 0 --showcase 0 --seed 670000 --profile r2u
```

Expected: `generated 80 deals into data/mix-test-r2; N batch problems` and `generated 20 deals into data/mix-test-r2u; N batch problems`, each well under a minute. A non-zero `N` from the batch's word-presence check is acceptable (it can flag small sets); copy each set's `problems.json` content into the report. Then confirm the counts:

```bash
.venv/bin/python -c "
import json
for s in ('mix-test-r2', 'mix-test-r2u'):
    print(s, len(json.load(open(f'data/{s}/splits.json'))['test']))"
```

Expected: `mix-test-r2 80` and `mix-test-r2u 20`.

- [ ] **Step 3: Start the tuning log**

Create `docs/results/mix-tuning-log.md`:

```markdown
# Mixed models: tuning log

**Spec:** `docs/superpowers/specs/2026-10-11-mixed-models-design.md` §2. **Scorecard:** `.venv/bin/python scripts/mix_practice.py`.

Practice deals only (`data/cal-r2`, `data/heldout-r2`, `data/practice-r2u`; 90). The fresh held-out sets
(`data/mix-test-r2`, 80 deals, seed 650000; `data/mix-test-r2u`, 20 deals, seed 670000) are never run before the
freeze; `acqlab/bench/mix.py` refuses them.

**Rules:** round 0 runs the four building blocks (`mix_sonnet_solo`, `mix_opus_low`, `mix_h_opus1`,
`mix_h_sonnet3`) and `s1b` on `practice-r2u`; cascades are scored from the rows. At most 3 more rounds, one change each,
kept only if `scripts/mix_practice.py --keep <new> --over <parent>` says True. Cap: $50 for the practice phase, under
one OK from the user.

## Round 0

Not run yet: awaits the user's OK for the practice phase.
```

- [ ] **Step 4: Update the HANDOFF resume point**

In `docs/HANDOFF.md`, directly after the line `## Resume here (2026-10-10)` and the line under it ("A new session (possibly on the user's other Claude account) continues from this point."), insert:

```markdown
- **Next track after the Haiku write-up: mixing Opus, Sonnet and Haiku** (spec
  `docs/superpowers/specs/2026-10-11-mixed-models-design.md`, plan `docs/superpowers/plans/2026-10-11-mixed-models.md`).
  Built: `acqlab/bench/mix.py`, `scripts/mix_practice.py`, `scripts/mix_final.py`; fresh held-out deals in
  `data/mix-test-r2` (80) and `data/mix-test-r2u` (20). Next: the user's OK for the practice phase ($50 cap), then
  freeze up to 4 frontier mixes (`mix.FINAL`, fingerprint test, `docs/results/mix-prereg.md`), then the final test
  after another OK (about $110).
```

Leave the rest of the file unchanged.

- [ ] **Step 5: Run the full suite and the frozen-files checks**

Run: `.venv/bin/python -m pytest -q`
Expected: `510 passed` (488 before this plan, plus 14, 4 and 4).

Run: `git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers` and `git diff HEAD --stat -- acqlab/bench/haiku.py`
Expected: no output from either.

Run: `git status --short`
Expected: only `docs/results/mix-tuning-log.md` and `docs/HANDOFF.md`; nothing under `data/`.

- [ ] **Step 6: Commit**

```bash
git add docs/results/mix-tuning-log.md docs/HANDOFF.md
git commit -m "docs: mixed models: fresh held-out deals generated (80 r2 + 20 r2u), tuning log started, HANDOFF

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Runbook after the plan (not subagent tasks; each paid step needs the user's OK)

1. **The user's OK for the practice phase** ($50 cap; optionally +$16 to run `s4` on practice-r2u so cascades to the
   Opus team become eligible, see the handoff question).
2. **One-deal CLI check:** `.venv/bin/python -m acqlab.bench.mix --data data/cal-r2 --deals dev-000 --systems mix_sonnet_solo,mix_opus_low --confirm-claude`; confirm each row's `models` and `steps`, `cli`, and a sane token-priced cost; delete the two rows if anything is off.
3. **Round 0:** `s1b` on practice-r2u (`.venv/bin/python -m acqlab.bench.pilot --data data/practice-r2u --n 30 --systems s1b --confirm-claude`), then the four building blocks on all three practice sets (`mix --data data/<set> --systems mix_sonnet_solo,mix_opus_low,mix_h_opus1,mix_h_sonnet3 --confirm-claude`), with the retry loop. Then `scripts/mix_practice.py`; log it.
4. **Up to 3 tuning rounds,** each a new `CANDIDATES` entry with a test; keep rule via `--keep/--over`.
5. **Freeze:** set `mix.FINAL` to `picks(card)` from the scorecard, add a fingerprint test (every frozen component's `fingerprint` and rendered prompts on the fixed room), commit `docs/results/mix-prereg.md`.
6. **The user's OK, then the final test:** `s1b` and `s4` with `acqlab.bench.pilot --split test --n 80/20`, and every frozen part plus `mix_haiku_solo` with `mix --final --split test`, on both fresh sets.
7. **Analysis once:** `.venv/bin/python scripts/mix_final.py --out docs/results/mix.json`; write-up `docs/results/mix.md` with the quality-against-cost table; HANDOFF.

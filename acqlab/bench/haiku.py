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

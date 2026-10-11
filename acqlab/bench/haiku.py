"""The Haiku team (spec docs/superpowers/specs/2026-10-10-haiku-team-design.md): buy/pass systems built from Claude
Haiku, tuned on practice deals and tested once on held-out deals against single Opus. The frozen code runs unchanged:
the model is switched at run time (on_haiku), never by editing acqlab/agents. No step reads the answer key; scoring
does, after the final call.

    uv run python -m acqlab.bench.haiku --data data/cal-r2 --systems haiku_solo,haiku_lean --confirm-claude
    uv run python -m acqlab.bench.haiku --data data/test-r2 --split test --systems haiku_solo --final --confirm-claude
    uv run python -m acqlab.bench.haiku --base-rates     # spec §3, from the practice deals' answer keys (free)

Runs go to <data>/runs/<system>/<deal>.json, the trace beside it (each step's own trace too); finished runs are
skipped. Exit codes: 0 done; 1 an unknown system; 2 Claude stopped (rerun later to resume); 3 refused (no
--confirm-claude, a held-out set before the freeze, or a system the final test does not run)."""
import argparse
import hashlib
import json
import statistics
import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from acqlab.agents import panel, panel_prompts, prompts, solver
from acqlab.agents.knowledge import GUIDE
from acqlab.agents.solver import run_session
from acqlab.bench import referee
from acqlab.bench.recon import (SECOND_SYSTEM, call_of, combine, draft, notes_record, second, second_prompts, spent,
                                step)
from acqlab.llm import LLMUnavailable

MODEL = "claude-haiku-5-5"
TEST_SETS = ("test-r2", "pilot-r2u")  # spec §2: held out until the freeze
PRACTICE = ("cal-r2", "heldout-r2", "practice-r2u")  # spec §3: the 90 practice deals
FINAL: str | None = None  # the frozen winner, set at the freeze (spec §4); until then no held-out run is allowed
RATES = Path(__file__).with_name("base_rates.json")
MIN_CLI = (2, 1, 291)  # spec §1
# $ per million tokens at the published list prices. The CLI prices claude-haiku-5-5 as an unknown model (at about
# Opus rates), so costs are compared from token counts instead (the user's ruling, 2026-10-11). Cache writes are
# priced at the 1-hour rate (2x input), the cache the CLI writes.
# ponytail: Haiku's long-prompt tier (5x above 100K tokens per request) can't be seen in a run's summed tokens
PRICES = {"claude-haiku-5-5": {"input_tokens": 0.10, "output_tokens": 0.50, "cache_read_input_tokens": 0.01,
                               "cache_creation_input_tokens": 0.20},
          "claude-opus-5-5": {"input_tokens": 4.0, "output_tokens": 20.0, "cache_read_input_tokens": 0.40,
                              "cache_creation_input_tokens": 8.0}}


def list_cost(row: dict) -> float | None:
    """A run's cost from its token counts at PRICES; None unless it ran on exactly one priced model."""
    if len(row["models"]) != 1 or row["models"][0] not in PRICES:
        return None
    return sum(row["tokens"][k] * p for k, p in PRICES[row["models"][0]].items()) / 1e6


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


def cli_version() -> str:
    """The Claude Code CLI's version as `claude --version` prints it first (e.g. "2.1.291"); "" if it prints
    nothing."""
    out = subprocess.run([solver.claude_bin(), "--version"], capture_output=True, text=True, timeout=30).stdout
    return out.split()[0] if out.split() else ""


def too_old(version: str) -> bool:
    try:
        return tuple(int(x) for x in version.split(".")) < MIN_CLI
    except ValueError:
        return True


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


# --- the candidates ------------------------------------------------------------------------------------------------

def team(room: Path, budget: float, *, trace: Path, **kw) -> dict:
    """The frozen team, unchanged (it skips a timed-out session itself)."""
    return panel.solve(room, budget, trace, panel.STAGES["s4"], **kw)


def run_solo(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict | None]:
    """Single Claude, unchanged. The CLI result is None after a timeout."""
    return step("solo", out.with_suffix(".solo.jsonl"), draft, room, budget, **kw)


def run_team(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict | None]:
    return step("team", out.with_suffix(".team.jsonl"), team, room, budget, **kw)


# Tuning round 1 (docs/results/haiku-team-tuning-log.md): in round 0 the pricers left 385 issues open (at chance 0.27
# on average) that a document they had showed to be zero, and the engine priced those phantom risks into NO-GOs.
ZERO_RULE = ("A document that checks an issue and finds no problem settles it at zero: chance 1, low 0 and high 0 "
             "(the seller's own claims in the CIM never settle anything).")
SECOND_ZERO = SECOND_SYSTEM.replace("Where the documents say nothing either way",
                                    f"{ZERO_RULE} Where the documents say nothing either way")


def second_zero(room: Path, read: list[str], *, trace: Path, **kw) -> dict:
    """recon.second with the zero rule: the same documents and user prompt, no reading budget."""
    _, user = second_prompts(room, read)
    return run_session(room, 0, trace, user, SECOND_ZERO.format(guide=GUIDE), ["note_issue", "submit"], [], **kw)


def run_lean(room: Path, budget: float, deal: str, out: Path, *, w: float, pricers: int, zero: bool = False,
             rates: dict[str, float] | None = None, **kw) -> tuple[list[dict], dict]:
    """Spec §3: one reader at the full budget, then `pricers` second opinions on the documents it read (with the zero
    rule if `zero`); the engine prices each one's calibrated notes, and the majority of those calls is final."""
    rates = rates or load_rates()
    reader = step("reader", out.with_suffix(".reader.jsonl"), draft, room, budget, **kw)
    read = referee.opened(reader[0])
    price = second_zero if zero else second
    priced = [step(f"pricer{i}", out.with_suffix(f".pricer{i}.jsonl"), price, room, read, **kw)
              for i in range(1, pricers + 1)]
    calls = [calibrated_call(room, rows, rates, w) for rows, _ in priced]
    steps = [reader, *priced]
    trace, cli = combine([r for rows, _ in steps for r in rows], [c for _, c in steps], vote(calls))
    return trace, cli | {"calls": {"reader": call_of(reader[0])} | {f"pricer{i}": c for i, c in enumerate(calls, 1)}}


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
    "haiku_lean": Candidate(run_lean, SOLO + (SECOND_SYSTEM,), settings={"w": 0.5, "pricers": 3}),
    "haiku_lean_zero": Candidate(run_lean, SOLO + (SECOND_ZERO,), settings={"w": 0.5, "pricers": 3, "zero": True}),
}


def prompt_sha(name: str) -> str:
    """The candidate's fingerprint, recorded in every row as "prompts": its system prompts plus its run function,
    effort and settings, so a change to any of them is a new fingerprint."""
    c = CANDIDATES[name]
    setup = json.dumps({"run": c.run.__name__, "effort": c.effort, "settings": c.settings}, sort_keys=True)
    return hashlib.sha256("\x00".join((*c.prompts, setup)).encode()).hexdigest()


# --- the runner ----------------------------------------------------------------------------------------------------

def refuse(data: Path, systems: list[str], split: str, final: bool) -> None:
    """Spec §2: the held-out sets run only in the final test, and the final test runs only the systems it compares."""
    if (data.resolve().name in TEST_SETS or split == "test") and not final:
        raise Refused(f"{data.name} ({split}) is held out for the final test; tuning never runs on it")
    if final:
        if split != "test":
            raise Refused(f"the final test runs on the test split, not {split}")
        if FINAL is None:
            raise Refused("no frozen winner yet: haiku.FINAL is set at the freeze")
        if bad := [s for s in systems if s not in ("haiku_solo", "haiku_team", FINAL)]:
            raise Refused(f"the final test runs only haiku_solo, haiku_team and {FINAL}, not {bad}")


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
            with on_haiku(c.effort):
                trace, result = c.run(room, budget, deal, path, **c.settings, **kw)
            path.with_suffix(".trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
            key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
            assert key.budget == budget, f"{deal}: the room's budget is not the answer key's"
            status = "timeout" if result is None else "ok" if call_of(trace) else "no_call"
            row = score(key, name, trace, result, status) | {
                "rep": 0, "budget": budget, "spent": spent(trace), "calls": (result or {}).get("calls"),
                "effort": c.effort, "settings": c.settings, "prompts": prompt_sha(name), "cli": cli}
            tmp = path.with_suffix(".json.tmp")  # written whole, then renamed: a killed run leaves no half row
            tmp.write_text(json.dumps(row, indent=2))
            tmp.replace(path)
            out.append(row)
            print(f"{name} {deal}: answered={row['answered']} correct={row['correct']} regret {row['regret']:.3f} "
                  f"pages {row['pages']:g}/{budget:g} ${row['cost_usd'] or 0:.3f}")
    return out


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path)
    ap.add_argument("--systems", default="haiku_solo,haiku_team,haiku_lean")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--deals", default="", help="comma-separated deal ids (default: the whole split)")
    ap.add_argument("--final", action="store_true", help="the final test on a held-out set (after the freeze)")
    ap.add_argument("--confirm-claude", action="store_true", help="required: this spends real Claude usage")
    ap.add_argument("--base-rates", action="store_true", help=f"write {RATES.name} from the practice deals")
    args = ap.parse_args(argv)
    if args.base_rates:
        root = Path(__file__).resolve().parents[2] / "data"
        RATES.write_text(json.dumps(base_rates([root / d for d in PRACTICE]), indent=2) + "\n")
        print(f"wrote {RATES}")
        return 0
    systems = [s for s in args.systems.split(",") if s]
    if bad := [s for s in systems if s not in CANDIDATES]:
        print(f"Unknown systems {bad}: choose from {list(CANDIDATES)}")
        return 1
    if args.data is None:
        ap.error("--data is required")
    try:
        refuse(args.data, systems, args.split, args.final)
    except Refused as e:
        print(f"Refusing: {e}")
        return 3
    if not args.confirm_claude:
        print("Refusing: pass --confirm-claude to spend real Claude usage")
        return 3
    try:
        version = cli_version()
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Refusing: the claude CLI could not report its version: {e}")
        return 3
    if too_old(version):
        print(f"Refusing: claude CLI {version or '(unknown)'} is older than {'.'.join(map(str, MIN_CLI))}")
        return 3
    try:
        run(args.data, systems, args.split, [d for d in args.deals.split(",") if d] or None, args.final, cli=version)
    except LLMUnavailable as e:
        print(f"Claude stopped: {e}. Rerun to resume.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

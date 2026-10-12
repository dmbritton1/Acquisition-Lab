"""Mixing Opus, Sonnet and Haiku (spec docs/superpowers/specs/2026-10-11-mixed-models-design.md): single runs on any
model and effort, reader-and-pricers pipelines with a model per step, and cascades that escalate a cheap system's
deal to a strong one on a public signal. The frozen code runs unchanged: each step's model is switched at run time
(on_model). No step reads the answer key; scoring does, after the final call.

    uv run python -m acqlab.bench.mix --data data/cal-r2 --systems mix_sonnet_solo,mix_opus_low --confirm-claude
    uv run python -m acqlab.bench.mix --data data/mix-test-r2 --split test --final --systems mix_opus_low --confirm-claude

Runs go to <data>/runs/<system>/<deal>.json, the trace beside it (each step's own trace too); finished runs are
skipped. Each row records every step's models and tokens ("steps"), so a mixed run is priced step by step. Exit codes:
0 done; 1 an unknown system; 2 Claude stopped (rerun later to resume); 3 refused (no --confirm-claude, an old CLI, a
fresh test set before the freeze, or a system the final test does not run) or stopped on a step it cannot price. Retry
loops retry only on exit 2."""
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
# the frozen mixes and cascades (spec §1 picks; docs/results/mix-prereg.md)
FINAL: tuple[str, ...] = ("cascade:mix_h_haiku3>s1b@flag|close:0.05", "cascade:mix_h_opus1>mix_opus_low@close:0.02",
                          "mix_haiku_solo", "cascade:mix_haiku_solo>mix_sonnet_solo@close:0.02")
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
    """A run's cost: step by step when the row records its steps, else from its summed tokens (a single-model run,
    such as s1b or s4). A step with no models (a timeout, no CLI result) costs 0.0, nothing known; a step that ran on
    models it cannot price alone (two or more, or one not in PRICES) raises ValueError rather than under-price."""
    if "steps" in row:
        total = 0.0
        for s in row["steps"]:
            if not s["models"]:
                continue
            c = price(s["models"], s["tokens"])
            if c is None:
                raise ValueError(f"cannot price step {s['step']} on {s['models']}")
            total += c
        return total
    return price(row["models"], row["tokens"])


def usage(name: str, cli: dict | None) -> dict:
    """One step's models, tokens and raw per-model usage (so a row that cannot be priced now can be later)."""
    return {"step": name, "models": sorted((cli or {}).get("modelUsage", {})),
            "tokens": {k: int((cli or {}).get("usage", {}).get(k, 0)) for k in USAGE},
            "model_usage": (cli or {}).get("modelUsage", {})}


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


def models_in(row: dict) -> list[str]:
    """Every model a row ran on: its own list plus each step's."""
    return sorted({*row["models"], *(m for s in row.get("steps", []) for m in s["models"])})


def cascade(cheap: dict, strong: dict, signal: str, teaser: str) -> dict:
    """The cascade's result on one deal: the strong run's call when the signal fires, else the cheap run's; cost is
    the cheap run's plus the strong run's on escalated deals only."""
    up = fires(signal, cheap, teaser)
    used = strong if up else cheap
    return {"go": used["go"], "correct": used["correct"], "regret": used["regret"], "case_type": cheap["case_type"],
            "cost": (row_cost(cheap) or 0.0) + ((row_cost(strong) or 0.0) if up else 0.0), "escalated": up,
            "answered": used["answered"], "timeouts": used.get("timeouts", 0), "models": models_in(used)}


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
        first.setdefault((round(points[n][0], 12), round(points[n][1], 12)), n)
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
        if data.resolve().name not in TEST_SETS:
            raise Refused(f"the final test runs only on the fresh sets {list(TEST_SETS)}, not {data.name}")
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
    except ValueError as e:  # a step row_cost cannot price: stop the spend; retry loops retry only on exit 2
        print(f"Stopped: {e}. Not retried: fix pricing before rerunning.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

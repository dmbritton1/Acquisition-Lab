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
